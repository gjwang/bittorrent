
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
            if self.multidl.dls.has_key(self.localtorrentfile):
                #TODO: torrentfile is downloading or not
                print '%s is downloading' % self.localtorrentfile
                msg['status'] = 'downloading'
                msg['result'] = 'success'
            else:
                try:
                    print "btdown %s to %s" %((self.localtorrentfile, self.localfilename))

                    dl_config = {}
                    dl_config['save_as'] = self.localfilename
                    dl = self.multidl.add_dl(torrentfile=self.localtorrentfile, singledl_config = dl_config)
                    dl.start() 
                    msg['status'] = 'beginning'
                    msg['result'] = 'success'
                except Exception as e:
                    msg['result'] = 'failed'
                    msg['trackback'] = str(e)

        except Exception as e:
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



class HelloResource(resource.Resource):
    isLeaf = True
    numberRequests = 0
    
    def render_GET(self, request):
        self.numberRequests += 1
        request.setHeader("content-type", "text/plain")
        print request
        print request.uri
        return "I am request #" + str(self.numberRequests) + "\n"
    
    def render_POST(self, request):
        self.numberRequests += 1
        request.setHeader("content-type", "text/plain")
        print request
        print request.args
        return "I am request #" + str(self.numberRequests) + "\n"
    

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
        
        msg = copy.deepcopy(self.response_msg)#make a new copy of response_msg

        #taskdict.add(task.get('taskid'))
        torrentfileurl = task.get('torrentfileurl')
        topdir = task.get('wwwroot')
        event = task.get('event')
        print "taskid: %s"%task.get('taskid')
        print "event: %s"%event
        print "seedurl: %s"%task.get('seederurl')        
        print "torrentfileurl: %s"%torrentfileurl
        print "sha1: %s"%task.get('sha1')

        #args = {}
        
        if event == 'download' and torrentfileurl:
            #if file not exits, download the torrent file 

            msg['event'] = 'download_response'            
            #args['torrentfileurl'] = torrentfileurl
            msg['args']['torrentfileurl'] = torrentfileurl

            if topdir is None:
                topdir = self.wwwroot
            
            try:
                adl = AsyncDownloader(topdir, self.multidl, torrentfileurl, request, msg)
                adl.start()
                return NOT_DONE_YET
            except Exception as e:
                #msg = {}
                msg['result'] = 'failed'
                msg['trackback'] = "%s" % str(e)

                self.return_request(request, msg)
        else:
            #msg = {}
            msg['result'] = 'failed'
            msg['trackback'] = "unknown event: %s" % event

            self.return_request(request, msg)
            
                
        return 'should not be here'


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
        print content
        task = {}
        try:
            task = json.loads(content)
        except Exception as e:
            print e
            return "maketorent: json format error"

        
        #taskdict.add(task.get('taskid'))
        torrentfileurl = task.get('torrentfileurl')
        fileurl = task.get('fileurl')
        topdir = task.get('wwwroot')
        event = task.get('event')

        trackers = task.get('trackers')
        print "type(trackers) %s" % type(trackers)

        for tracker in trackers:
            #print tracker['tracker']
            print tracker
       
        print "taskid: %s"%task.get('taskid')
        print "event: %s"%event
        print "seedurl: %s"%task.get('seederurl')        
        print "torrentfileurl: %s"%torrentfileurl
        print "sha1: %s"%task.get('sha1')

        msg = copy.deepcopy(self.response_msg)#make a new copy of response_msg
        print "response_msg", self.response_msg


        if topdir is None:
            topdir = self.wwwroot
            
        localfilename = join(topdir, urlsplit(fileurl).path[1:])

        args = msg['args']
        args['filename'] = localfilename
        args['torrentfile'] = localfilename + '.torrent'        
        args['torrentfileurl'] = join(self.http_prefix, urlsplit(fileurl).path[1:] + '.torrent')

        msg['event'] = 'maketorrent_response'
        
        if event == 'maketorrent' and fileurl:
            #if file not exits, download the torrent file 
            print 'download %s' % fileurl

            try:
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
                msg['result'] = 'failed'
                msg['trackback'] = str(e)
                self.return_request(request, msg)
        else:  
            #msg = {}
            msg['result'] = 'failed'
            msg['trackback'] = "unknown event: %s" % event

            self.return_request(request, msg)

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
        
        torrentfileurl = task.get('torrentfileurl')
        topdir = task.get('wwwroot')
        event = task.get('event')
        print "taskid: %s"%task.get('taskid')
        print "event: %s"%event
        print "seedurl: %s"%task.get('seederurl')        
        print "torrentfileurl: %s"%torrentfileurl
        print "sha1: %s"%task.get('sha1')

        if topdir is None:
            topdir = self.wwwroot

        msg = copy.deepcopy(self.response_msg)#make a new copy of response_msg        
        msg['event'] = 'shutdownall_response'
        
        if event == 'shutdown':
            if torrentfileurl:
                torrentfile = join(topdir, urlsplit(torrentfileurl).path[1:])
                try:
                    self.multidl.shutdown(torrentfile)
                    #msg = " ".join(["shutdown", torrentfileurl, "OK"])
                    msg['result'] = 'success'
                except Exception as e:
                    msg['result'] = 'failed'
                    msg['trackback'] = str(e)                    
            else:
                msg['result'] = 'failed'
                msg['trackback'] = "shutdown: not special shutdown file"                   
        elif event == 'shutdownall':
            try:
                self.multidl.shutdown()
                msg['result'] = 'success'
            except Exception as e:
                msg['result'] = 'failed'
                msg['trackback'] = str(e)
        else:                
            msg['result'] = 'failed'
            msg['trackback'] = "unknown command"

        print msg    
        #return_request(request, msg)
        self.return_request(request, msg)
        return NOT_DONE_YET


import Queue
taskqueue = Queue.Queue(3)
taskdict = {}
if __name__ == "__main__":
    

    root = Resource()
    root.putChild("hello", HelloResource())
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

    
    
