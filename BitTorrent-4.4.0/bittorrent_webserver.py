
'''
Created on 2013-11-29

@author: gjwang
'''

from BitTorrent.makemetafile import make_meta_files
from BitTorrent.parseargs import parseargs, printHelp
from BitTorrent import BTFailure
from sha import *
from BitTorrent.bencode import *

from twisted.web import server, resource
from twisted.web.server import Site
from twisted.web.server import NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.web.client import HTTPDownloader
from twisted.web.client import downloadPage
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
from twisted.internet import reactor


import os
import copy
import urllib2
from urlparse import urlsplit
from os.path import join, dirname, basename, normpath, splitext, getsize, dirname
from os import errno
import logging

import hashlib
md5 = hashlib.md5

import json
import cgi
from conf import wwwroot, maketorent_config, response_msg, http_prefix, node_domain, bt_user, bt_password, AM_I_MK_METAINFO_SERVER

bt_password = md5(bt_password).hexdigest()

#TODO: for temp use; maybe can use twisted.cred, twisted.web.guard... instead
def validate(func):
    def __decorator(self, request):
        user = request.args.get('user')
        pwd = request.args.get('pwd')        

        if (user and user[0]== bt_user) and (pwd and pwd[0].lower() == bt_password):
            return func(self, request)
        else:
            request.setResponseCode(401)
            logger = logging.getLogger()
            logger.error("login errro: user:%s, pwd:%s", user, pwd)
            return 'Unauthorized'

    return __decorator  

def return_request(request, msg):
    msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
    request.write(msg)
    request.finish()


class Ping(Resource):
    @validate
    def render_GET(self, request):
        return 'PONG'
    
    def render_POST(self, request):
        return self.render_GET(request)


class AsyncDownloader():
    def __init__(self, topdir, multidl, url, request, msg, filesize = None, localfilename = None):
        self._logger = logging.getLogger(self.__class__.__name__)

        self.topdir = topdir
        self.node_domain = node_domain
        self.multidl = multidl
        self.url = url
        self.request = request
        self.msg = msg
        self.filesize = filesize
        self.localtorrentfile = None

        if localfilename is None:
            f = join(self.topdir, urlsplit(self.url).path[1:])
            if splitext(f)[1].lower() == '.torrent':
                self.localtorrentfile = f
                self.localfilename = splitext(f)[0]
            else:
                self.localfilename = f
        else:            
            self.localfilename = localfilename
            if splitext(self.url)[1].lower() == '.torrent':
                self.localtorrentfile = splitext(self.url)[0]
            
        self.msg['args']['filenmae'] = self.localfilename
        self.msg['args']['fileurl'] = self.localfilename.replace(self.topdir, self.node_domain)
        self.msg['args']['torrentfile'] =  self.localtorrentfile

    def return_request(self, request, msg):
        msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
        request.write(msg)
        request.finish()

    def download_done(self, context, msg):
        if self.localtorrentfile:
            self.add_task_to_multidl(msg)
        else:
            msg['result'] = 'failed'
            msg['traceback'] = "No torrent file: %s" % self.localtorrentfile
            self._logger.error(msg['traceback'])
            self.return_request(self.request, msg)

    def error_handler(self, error, msg = None):
        if msg is None:
            copy.deepcopy(self.msg)#make a new copy of response_msg        

        msg['result'] = 'failed'         
        msg['traceback'] = "download %s Exception: %s" % (self.url, str(error))    
        self._logger.error(msg['traceback'])    

        self.return_request(self.request, msg)

    def add_task_to_multidl(self, msg):
        try:
            sha1 = msg['args'].get('sha1')
            if sha1 and self.multidl.dls.has_key(sha1):
                dl, _= self.multidl.dls[sha1]

                status = dl.get_activity()
                if status == 'seeding' or status == 'download succeeded':
                    msg["args"]["percent"] = 100
    
                msg['result'] = 'sucess'
                msg['traceback'] = 'sha1:%s is already %s' % (sha1, status)

                self._logger.error(msg['traceback'])
                self.return_request(self.request, msg)
                return
            
            for (hash_info, (dl, f)) in self.multidl.dls.items():
                if f == self.localtorrentfile:
                    status = dl.get_activity()
                    if status == 'seeding' or status == 'download succeeded':
                        msg["args"]["percent"] = 100

                    msg['result'] = 'sucess'
                    msg['traceback'] = 'file:%s is already %s' % (self.localtorrentfile,  status)

                    self._logger.error(msg['traceback'])
                    self.return_request(self.request, msg)
                    return

            try:
                self._logger.info("btdown %s to %s", self.localtorrentfile, self.localfilename)

                dl_config = {}
                dl_config['save_as'] = self.localfilename
                #add_dl would start to download
                #dl = self.multidl.add_dl(torrentfile=self.localtorrentfile, singledl_config = dl_config)
                dl = self.multidl.add_task(torrentfile=self.localtorrentfile, singledl_config = dl_config, sha1=sha1)

                msg['status'] = dl.get_activity()
                msg['result'] = 'success'
            except Exception as e:
                msg['result'] = 'failed'
                msg['traceback'] = "multidl.add_dl Execption: %s" % str(e)
                self._logger.error(msg['traceback'])
                self._logger.exception("multidl.add_dl Execption")

        except Exception as e:
            msg['result'] = 'failed'
            msg['traceback'] = "add_task_to_multidl Execption: %s" % str(e)

            self._logger.error(msg['traceback'])

        self.return_request(self.request, msg)


    def makedir(self):
        dstdirname = dirname(self.localfilename)
        try:
            if not os.path.exists(dstdirname):
                os.makedirs(dstdirname)
        except Exception, exc:
            msg = {}
            msg['result'] = 'failed'
            msg['traceback'] = str(exc)
            self._logger.error("mkdir: %s failed: %s", dstdirname, exc)
            self.return_request(self.request, msg)
            return False
        else:
            return True

    def start(self, redownload=True):
        '''
            redownload: redownload torrent file or not
        '''

        if self.makedir() == False:
            return 

        if redownload:
            deferred = downloadPage(bytes(self.url), self.localtorrentfile)
            deferred.addCallback(self.download_done, self.msg)
            deferred.addErrback(self.error_handler, self.msg)
            self._logger.info("download %s to %s", self.url, self.localtorrentfile)
        else:
            self.download_done(context=None, msg=self.msg)

class FormPage(Resource):
    @validate
    def render_GET(self, request):
        return '<html><body><form method="POST"><input name="the-field" type="text" /></form></body></html>'

    @validate
    def render_POST(self, request):
        return '<html><body>You submitted: %s</body></html>' % (cgi.escape(request.content.read()),)


def rmfile_and_emptypath(task, msg, request):
    logger = logging.getLogger()

    args = task.get('args') or {}

    torrentfileurl = args.get('torrentfileurl')    
    topdir = args.get('wwwroot') or wwwroot #global var wwwroot
    localname = args.get('filename')

    if localname is None:
        if torrentfileurl is None:
            msg['result'] = 'failed'
            msg['traceback'] = "not special delete file"
            logger.error('rmfile_and_emptypath: %s', msg['traceback'])
            return_request(request, msg)            
            return 

        torrentfile = join(topdir, urlsplit(torrentfileurl).path[1:])
        localname = splitext(torrentfile)[0]
    else:
        torrentfile = localname + '.torrent'
    
    msg['event'] = 'delete_response'
    msg['result'] = 'sucess'

    for f in (torrentfile, localname):
        if os.path.exists(f):
            try:
                os.remove(f)
                msg['result'] = 'sucess'
                logger.info('rmfile_and_emptypath: rm %s sucess', f)
            except OSError as ex:
                msg['result'] = 'failed'
                msg['traceback'] += "rmfile %s failed: %s; "%(f, ex)
                logger.error('rmfile_and_emptypath: %s', msg['traceback'])
        else:
            msg['traceback'] += '%s not exists; '% f
            logger.error('rmfile_and_emptypath: %s', msg['traceback'])

    #rm empty dir, avoid empty 'holes'
    try:
        os.removedirs(dirname(localname))
    except OSError as ex:
        if ex.errno == errno.ENOTEMPTY:
            pass
        else:
            msg['result'] = 'failed'
            msg['traceback'] += "rmdir exception: %s"% ex
            logger.error('rmfile_and_emptypath: %s', msg['traceback'])

    return_request(request, msg)
    

class PutTask(Resource):
    tasknum = 0
    def __init__(self, multidl):
        self._logger = logging.getLogger(self.__class__.__name__)

        self.multidl = multidl
        self.wwwroot = wwwroot #global var wwwroot
        self.response_msg = response_msg


    def return_request(self, request, msg):
        msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
        request.write(msg)
        request.finish()


    @validate        
    def render_GET(self, request):
        self._logger.info('recv get request')
        return '<html><body><form method="POST"><input name="the-field" type="text" /></form></body></html>'

    @validate
    def render_POST(self, request):
        self.tasknum += 1
        content = cgi.escape(request.content.read())
        self._logger.info('PutTask: %s', content)

        msg = copy.deepcopy(self.response_msg)#make a new copy of response_msg
        msg['event'] = 'puttask_response'

        task = {}
        try:
            task = json.loads(content)
        except Exception as e:
            msg['result'] = 'failed'
            msg['traceback'] = "json format error,  Exception: %s" % str(e)
            self._logger.error(msg['traceback'])
            msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))
            return msg

        event = task.get('event')        
        msg['taskid'] = task.get('taskid') or ''

        if event == 'download':
            taskargs = task.get('args') or {}
            torrentfileurl = taskargs.get('torrentfileurl')

            if torrentfileurl is None:
                msg['result'] = 'failed'
                msg['traceback'] = "undefine torrentfileurl"
                msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))
                return msg

            msg['event'] = 'download_response'            
            msg['args']['torrentfileurl'] = torrentfileurl
            msg['args']['sha1'] = taskargs.get('sha1')

            topdir = taskargs.get('wwwroot') or self.wwwroot
            
            try:
                adl = AsyncDownloader(topdir, self.multidl, torrentfileurl, request, msg)
                adl.start(redownload = not AM_I_MK_METAINFO_SERVER)
                return NOT_DONE_YET
            except Exception as e:
                #msg = {}
                msg['result'] = 'failed'
                msg['traceback'] = "AsyncDownloader Exception: %s" % str(e)
        elif event == 'delete':
            try:
                rmfile_and_emptypath(task, msg, request)
                return NOT_DONE_YET
            except Exception as e:
                #msg = {}
                msg['event'] = 'delete_response'
                msg['result'] = 'failed'
                msg['traceback'] = "Exception: %s" % str(e)
        else:
            #msg = {}
            msg['result'] = 'failed'
            msg['traceback'] = "unknown event: %s" % event

        self._logger.error(msg['traceback'])                            
        msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
        return msg


class MakeTorrent(Resource):
    tasknum = 0
    def __init__(self, multidl):
        self._logger = logging.getLogger(self.__class__.__name__)

        self.agent = Agent(reactor)

        self.multidl = multidl
        self.wwwroot = wwwroot #global var wwwroot
        self.maketorent_config = maketorent_config
        self.http_prefix = http_prefix
        self.response_msg = response_msg


    def return_request(self, request, msg):
        msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
        request.write(msg)
        request.finish()

    def maketorrent(self, filename, request, msg):
        self._logger.debug('Going to make torrent: %s', filename)

        def dc(v):
            #print v
            pass

        def prog(amount):
            #print '%.1f%% complete\r' % (amount * 100),
            #self._logger.debug('%.1f%% complete', amount * 100)
            pass

        config = self.maketorent_config
	trackers = msg['args']['trackers']
	if trackers:
	    tracker = trackers[0]
	else:
            tracker = config['tracker_name']
	    msg['trackers'] = [tracker]

        try:
            meta = make_meta_files(bytes(tracker),
                            [filename],
                            progressfunc=prog,
                            filefunc=dc,
                            piece_len_pow2=config['piece_size_pow2'],
                            comment=config['comment'],
                            target=config['target'],
                            filesystem_encoding=config['filesystem_encoding'],
                            use_tracker=config['use_tracker'],
                            data_dir=config['data_dir'])


            metainfo_file = open(filename + '.torrent', 'rb')
            metainfo = bdecode(metainfo_file.read())
            metainfo_file.close()
            info = metainfo['info']
            info_hash = sha(bencode(info))

            msg['args']['sha1'] = info_hash.hexdigest()
            msg['result'] = 'success'
        except BTFailure, e:
            msg['result'] = 'failed'
            msg['traceback'] = "Excepition BTFailure: %s" % str(e)
        except Exception, e:
            msg['result'] = 'failed'         
            msg['traceback'] = "make_meta_files failed: %s" % str(e)

        if msg['result'] == 'failed':            
            self._logger.error(msg['traceback'])
        else:
            self._logger.info("make_meta_files: %s sucess, sha1: %s", filename + '.torrent', msg['args']['sha1'])

        self.return_request(request, msg)

    def download_done(self, context, filename, request, msg):
        self._logger.info("download: %s done", filename)
        self.maketorrent(filename, request, msg)
        
    def error_handler(self, error, request, msg = None):
        if msg is None:
            msg = copy.deepcopy(self.response_msg)#make a new copy of response_msg        
        msg['result'] = 'failed'         
        msg['traceback'] = "%s" % str(error)
        self._logger.error(msg['traceback'])

        self.return_request(request, msg)
               
    @validate        
    def render_GET(self, request):
        self._logger.info("recv get request")
        return '<html><body><form method="POST"><input name="the-field" type="text" /></form></body></html>'

    @validate
    def render_POST(self, request):
        self.tasknum += 1
        content = cgi.escape(request.content.read())
        task = {}

        self._logger.info("MakeTorrent: %s", content)

        try:
            task = json.loads(content)
        except Exception as e:
            msg = {}
            msg['event'] = 'maketorrent_response'
            msg['result'] = 'failed'
            msg['traceback'] = "maketorent: json format error"
            msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        

            self._logger.error("maketorent: json format error, Exception:%s", str(e))

            return msg

        event = task.get('event')

        msg = copy.deepcopy(self.response_msg)#make a new copy of response_msg
        msg['taskid'] = task.get('taskid') or ''
        msg['event'] = 'maketorrent_response'
        
        if event == 'maketorrent':
            try:
                args = task.get('args') or {}
                fileurl = args.get('fileurl')
                path = urlsplit(fileurl).path[1:]

                if fileurl is None:
                    msg['result'] = 'failed'
                    msg['traceback'] = "undefine fileurl in args"
                    msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))

                    self._logger.info("maketorrent_response: %s", msg['traceback'])
                    return msg

		trackers = args.get('trackers')
		if trackers and type(trackers) is not list:
		    msg['result'] = 'failed'
                    msg['traceback'] = "trackers must be json array"
                    msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))

                    self._logger.info("maketorrent_response: %s", msg['traceback'])
                    return msg 

                topdir = args.get('wwwroot') or self.wwwroot
                filename  = args.get('filename')
                if filename:
                    localfilename = join(topdir, filename)
                    path = filename
                elif path:
                    localfilename = join(topdir, path)
                else:
                    msg['result'] = 'failed'
                    msg['traceback'] = "uneffective url path or undefine filename"
                    msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))

                    self._logger.info("maketorrent_response: %s", msg['traceback'])
                    return msg
                    
                args_rsp = msg['args']
                args_rsp['filename'] = localfilename
                args_rsp['torrentfile'] = localfilename + '.torrent'
                args_rsp['torrentfileurl'] = join(self.http_prefix, path) + '.torrent'
		args_rsp['trackers'] = trackers 

                def downloadfile(fileurl, localfilename):
                    dstdirname = dirname(localfilename)
                    if not os.path.exists(dirname(localfilename)):
                        os.makedirs(dstdirname)

                    self._logger.info("Going to download %s to %s", fileurl, localfilename)

                    deferred = downloadPage(bytes(fileurl), localfilename)
                    deferred.addCallback(self.download_done, localfilename, request, msg)
                    deferred.addErrback(self.error_handler, request, msg)
	
                if os.path.exists(localfilename):
                    d = self.agent.request(
                        'GET',
                        bytes(fileurl),
                        Headers({'User-Agent': ['Twisted Web Client'],
                                 'Content-Type': ['text/plain']}),
                        #body
                        )

                    def cbRequest(response):
                        if response.length == getsize(localfilename):
                            self._logger.info("maketorrent: %s already exist, and filesize(%s) equals", 
                                                                     localfilename, response.length)
                            self.maketorrent(localfilename, request, msg)
                        else:
                            self._logger.error("maketorrent: %s already exist, but filesize(%s)!=response.length(%s), redownload", 
                                                                     localfilename, response.length, getsize(localfilename))
                            downloadfile(fileurl, localfilename)
                    
                    def cbErrRequest(error):
                        msg['result'] = 'failed'
                        msg['traceback'] = "Get filesize error: %s" % error
                        self.return_request(request, msg)

                    d.addCallback(cbRequest)
                    d.addErrback(cbErrRequest)
                else:
                    downloadfile(fileurl, localfilename)

                return NOT_DONE_YET
            except Exception as e:
                msg['result'] = 'failed'
                msg['traceback'] = str(e)
                self._logger.error("maketorrent_response: %s", msg['traceback'])

                msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
                return msg
        else:  
            #msg = {}
            msg['result'] = 'failed'
            msg['traceback'] = "unknown event: %s" % event
            msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
            self._logger.error("maketorrent_response: %s", msg['traceback'])
            return msg

        self._logger.error("maketorrent_response: should not be here")
        return 'should not be here'


class ShutdownTask(Resource):
    def __init__(self, multidl):
        self._logger = logging.getLogger(self.__class__.__name__)

        self.multidl = multidl
        self.wwwroot = wwwroot #global var wwwroot
        self.response_msg = response_msg

    def return_request(self, request, msg):
        msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
        request.write(msg)
        request.finish()

    @validate
    def render_GET(self, request):        
        return '<html><body><form method="POST"><input name="the-field" type="text" /></form></body></html>'

    @validate    
    def render_POST(self, request):
        content = cgi.escape(request.content.read())

        self._logger.info('ShutdownTask: %s', content)

        task = {}
        try:
            task = json.loads(content)
        except Exception as e:
            self._logger.info('ShutdownTask json format error: %s', str(e))
            return "json format error"
        
        event = task.get('event')
        taskid = task.get('taskid') or ""

        msg = copy.deepcopy(self.response_msg)#make a new copy of response_msg        

        msg['taskid'] = taskid

        if event == 'shutdown':
            msg['event'] = 'shutdown_response'

            taskargs = task.get('args') or {}
            torrentfileurl = taskargs.get('torrentfileurl')
            sha1 = taskargs.get('sha1')
            topdir = taskargs.get('wwwroot') or self.wwwroot

            if sha1 or torrentfileurl:
                if torrentfileurl:
                    torrentfile = join(topdir, urlsplit(torrentfileurl).path[1:])
                else:
                    torrentfile = None

                try:
                    self.multidl.shutdown(sha1=sha1, torrentfile=torrentfile)
                    msg['result'] = 'success'
                except Exception as e:
                    msg['result'] = 'failed'
                    msg['traceback'] = str(e)                                    
            else:
                msg['result'] = 'failed'
                msg['traceback'] = "shutdown: not special sha1 or file"
        elif event == 'shutdownall':
            msg['event'] = 'shutdownall_response'
            try:
                self.multidl.shutdown()
                msg['result'] = 'success'
            except Exception as e:
                msg['result'] = 'failed'
                msg['traceback'] = str(e)
        else:                
            #msg['event'] = 'shutdown_response'
            msg['result'] = 'failed'
            msg['traceback'] = "unknown event: %s" % event

        self._logger.info(msg)            
        msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
        return msg


if __name__ == "__main__":
    
    root = Resource()
    root.putChild("form", FormPage())
    root.putChild("ping", Ping())
    root.putChild("puttask", PutTask())
    root.putChild("shutdowntask", ShuddownTask())
    
    factory = Site(root)
    reactor.listenTCP(8090, factory)
    #reactor.run()    
    p = Process(target=reactor.run)
    p.start()
    print 'site is runnning...'
    p.join()

    
    
