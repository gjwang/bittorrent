
'''
Created on 2013-11-29

@author: gjwang
'''
#from multiprocessing import Process, Queue

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
from twisted.internet import reactor


import os
import copy
import urllib2
from urlparse import urlsplit
from os.path import join, dirname, basename, normpath, splitext, getsize

import json
import cgi
from conf import wwwroot, maketorent_config, response_msg, http_prefix, node_domain


class AsyncDownloader():
    def __init__(self, topdir, multidl, url, request, msg, filesize = None, localfilename = None):
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
            msg['result'] = 'success'
            return_request(self.request, msg)

    def error_handler(self, error, msg = None):
        if msg is None:
            copy.deepcopy(self.msg)#make a new copy of response_msg
        
        msg['result'] = 'failed'         
        msg['trackback'] = "%s" % str(error)        
        self.return_request(self.request, msg)

    def add_task_to_multidl(self, msg):
        try:
            sha1 = msg['args']['sha1']            
            if sha1 and self.multidl.dls.has_key(sha1):
                #TODO: torrentfile is downloading or not
                dl, _= self.multidl.dls[sha1]

                msg['status'] = dl.get_activity()
                msg['result'] = 'success'
                self.return_request(self.request, msg)
                return
            
            for (hash_info, (dl, f)) in self.multidl.dls.items():
                if f == self.localtorrentfile:
                    print 'file: %s is already downloading' % self.localtorrentfile

                    msg['status'] = dl.get_activity()
                    msg['result'] = 'success'
                    self.return_request(self.request, msg)
                    return                    

            try:
                print "btdown %s to %s" %((self.localtorrentfile, self.localfilename))

                dl_config = {}
                dl_config['save_as'] = self.localfilename
                #add_dl would start to download
                dl = self.multidl.add_dl(torrentfile=self.localtorrentfile, singledl_config = dl_config)

                msg['status'] = dl.get_activity()
                msg['result'] = 'success'
            except Exception as e:
                print str(e)
                msg['result'] = 'failed'
                msg['trackback'] = "multidl.add_dl Execption: %s" % str(e)

        except Exception as e:
            print str(e)
            msg['result'] = 'failed'
            msg['trackback'] = str(e)

        self.return_request(self.request, msg)


    def makedir(self):
        dstdirname = dirname(self.localfilename)
        try:
            if not os.path.exists(dstdirname):
                os.makedirs(dstdirname)
        except Exception, exc:
            #logger.info("down: %s to %s failed: %s", url, self.localfilename, exc)
            print "mkdir: %s failed: %s"%(dstdirname, exc)            
            msg = {}
            msg['result'] = 'failed'
            msg['trackback'] = str(exc)
            self.error_handler(exc, msg)
            return False
        else:
            return True

    def start(self, redownload=True):
        if self.makedir() == False:
            return 

        print "download %s to %s" %((self.url, self.localtorrentfile))

        deferred = downloadPage(bytes(self.url), self.localtorrentfile)
        deferred.addCallback(self.download_done, self.msg)
        deferred.addErrback(self.error_handler, self.msg)


class Ping(Resource):
    def render_GET(self, request):        
        return 'PONG'
    
    def render_POST(self, request):
        return self.render_GET(request)

class FormPage(Resource):
    def render_GET(self, request):
        return '<html><body><form method="POST"><input name="the-field" type="text" /></form></body></html>'

    def render_POST(self, request):
        #print cgi.escape(request.content.read())
        return '<html><body>You submitted: %s</body></html>' % (cgi.escape(request.content.read()),)

class PutTask(Resource):
    tasknum = 0
    def __init__(self, taskqueue, multidl):
        self.taskqueue = taskqueue
        self.multidl = multidl
        self.wwwroot = wwwroot #global var wwwroot
        self.response_msg = response_msg


    def return_request(self, request, msg):
        msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
        request.write(msg)
        request.finish()

        
    def render_GET(self, request):
        print "recv get request"
        return '<html><body><form method="POST"><input name="the-field" type="text" /></form></body></html>'

    def render_POST(self, request):
        self.tasknum += 1
        content = cgi.escape(request.content.read())
        print content
        task = {}
        try:
            task = json.loads(content)
        except Exception as e:
            print e
            return "json format error"
        
        event = task.get('event')

        msg = copy.deepcopy(self.response_msg)#make a new copy of response_msg
        msg['taskid'] = task.get('taskid') or ''
        
        if event == 'download':
            taskargs = task.get('args') or {}
            torrentfileurl = taskargs.get('torrentfileurl')

            if torrentfileurl is None:
                msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
                return msg

            msg['event'] = 'download_response'            
            msg['args']['torrentfileurl'] = torrentfileurl
            msg['args']['sha1'] = taskargs.get('sha1')

            topdir = task.get('wwwroot') or self.wwwroot
            
            try:
                adl = AsyncDownloader(topdir, self.multidl, torrentfileurl, request, msg)
                adl.start()
                return NOT_DONE_YET
            except Exception as e:
                #msg = {}
                msg['result'] = 'failed'
                msg['trackback'] = "AsyncDownloader Exception: %s" % str(e)
        else:
            #msg = {}
            msg['result'] = 'failed'
            msg['trackback'] = "unknown event: %s" % event
                            
        msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
        return msg


class MakeTorrent(Resource):
    tasknum = 0
    def __init__(self, taskqueue, multidl):
        self.taskqueue = taskqueue
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
        print 'begin to make torrent: %s'%filename

        def dc(v):
            print v

        def prog(amount):
            print '%.1f%% complete\r' % (amount * 100),

        config = self.maketorent_config
        tracker = config['tracker_name']

        try:
            meta = make_meta_files(tracker,
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
            msg['trackback'] = "%s" % str(e)
        except Exception, e:
            msg['result'] = 'failed'         
            msg['trackback'] = "make_meta_files failed: %s" % str(e)

        #msg['args'] = args
        self.return_request(request, msg)

    def download_done(self, context, filename, request, msg):
        print "down: %s done"%filename
        self.maketorrent(filename, request, msg)
        
    def error_handler(self, error, request, msg = None):
        if msg is None:
            msg = copy.deepcopy(self.response_msg)#make a new copy of response_msg
        
        msg['result'] = 'failed'         
        msg['trackback'] = "%s" % str(error)

        self.return_request(request, msg)
               
        
    def render_GET(self, request):
        print "recv get request"
        return '<html><body><form method="POST"><input name="the-field" type="text" /></form></body></html>'

    def render_POST(self, request):
        self.tasknum += 1
        content = cgi.escape(request.content.read())
        task = {}

        print 'content=',content
        try:
            task = json.loads(content)
        except Exception as e:
            print e
            msg = {}
            msg['event'] = 'maketorrent_response'
            msg['result'] = 'failed'
            msg['trackback'] = "maketorent: json format error"
            msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
            return msg

        event = task.get('event')

        msg = copy.deepcopy(self.response_msg)#make a new copy of response_msg
        msg['taskid'] = task.get('taskid') or ''
        msg['event'] = 'maketorrent_response'
        
        if event == 'maketorrent':
            try:
                args = task.get('args') or {}
                print args
                fileurl = args.get('fileurl')
                print fileurl
                if fileurl is None:
                    msg['result'] = 'failed'
                    msg['trackback'] = "undefine fileurl in args"                    
                    msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))
                    return msg

                topdir = args.get('wwwroot') or self.wwwroot
                trackers = args.get('trackers') or []

                localfilename = join(topdir, urlsplit(fileurl).path[1:])
                args_rsp = msg['args']
                args_rsp['filename'] = localfilename
                args_rsp['torrentfile'] = localfilename + '.torrent'        
                args_rsp['torrentfileurl'] = join(self.http_prefix, urlsplit(fileurl).path[1:] + '.torrent')

                if os.path.exists(localfilename):
                    #and getsize(localfilename) == filesize:
                    #hash_info == task.get('hasn_info')
                    print "%s already exist" % localfilename
                    self.maketorrent(localfilename, request, msg)
                else:
                    dstdirname = dirname(localfilename)
                    if not os.path.exists(dirname(localfilename)):
                        os.makedirs(dstdirname)

                    print "download %s to %s"%(fileurl, localfilename)
                    deferred = downloadPage(bytes(fileurl), localfilename)
                    deferred.addCallback(self.download_done, localfilename, request, msg)
                    deferred.addErrback(self.error_handler, request, msg)

                return NOT_DONE_YET
            except Exception as e:
                print str(e)
                msg['result'] = 'failed'
                msg['trackback'] = str(e)
                msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
                return msg

        else:  
            #msg = {}
            msg['result'] = 'failed'
            msg['trackback'] = "unknown event: %s" % event
            msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
            return msg

        return 'should not be here'

def return_request(request, msg):
    msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
    request.write(msg)
    request.finish()


class ShutdownTask(Resource):
    def __init__(self, taskqueue, multidl):
        self.taskqueue = taskqueue
        self.multidl = multidl
        self.wwwroot = wwwroot #global var wwwroot
        self.response_msg = response_msg

    def return_request(self, request, msg):
        msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
        request.write(msg)
        request.finish()

    def render_GET(self, request):        
        return '<html><body><form method="POST"><input name="the-field" type="text" /></form></body></html>'
    
    def render_POST(self, request):
        content = cgi.escape(request.content.read())
        print content
        task = {}
        try:
            task = json.loads(content)
        except Exception as e:
            print e
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
                    msg['trackback'] = str(e)                                    
            else:
                msg['result'] = 'failed'
                msg['trackback'] = "shutdown: not special sha1 or file"
        elif event == 'shutdownall':
            msg['event'] = 'shutdownall_response'
            try:
                self.multidl.shutdown()
                msg['result'] = 'success'
            except Exception as e:
                msg['result'] = 'failed'
                msg['trackback'] = str(e)
        else:                
            msg['result'] = 'failed'
            msg['trackback'] = "unknown command"

        msg = json.dumps(msg, indent=4, sort_keys=True, separators=(',', ': '))        
        return msg


import Queue
taskqueue = Queue.Queue(3)
taskdict = {}
if __name__ == "__main__":
    
    root = Resource()
    root.putChild("form", FormPage())
    root.putChild("ping", Ping())
    root.putChild("puttask", PutTask(taskqueue))
    root.putChild("shutdowntask", ShuddownTask(taskqueue))
    
    factory = Site(root)
    reactor.listenTCP(8090, factory)
    #reactor.run()    
    p = Process(target=reactor.run)
    p.start()
    print 'site is runnning...'
    p.join()

    
    
