
'''
Created on 2013-11-29

@author: gjwang
'''
#from multiprocessing import Process, Queue

from BitTorrent.makemetafile import make_meta_files
from BitTorrent.parseargs import parseargs, printHelp
from BitTorrent import BTFailure

from twisted.web import server, resource
from twisted.web.server import Site
from twisted.web.server import NOT_DONE_YET
from twisted.web.resource import Resource
from twisted.web.client import HTTPDownloader
from twisted.web.client import downloadPage
from twisted.internet import reactor


import os
import urllib2
from urlparse import urlsplit
from os.path import join, dirname, basename, normpath, splitext, getsize

import json
import cgi
from conf import wwwroot


class AsyncDownloader():
    def __init__(self, topdir, multidl, url, request, filesize = None, localfilename = None):
        self.topdir = topdir
        self.multidl = multidl
        self.url = url
        self.request = request
        self.filesize = filesize

        if localfilename is None:
            self.localfilename = join(self.topdir, urlsplit(self.url).path[1:])
        else:
            self.localfilename = localfilename

    def retRequest(self, msg):
        self.request.write(msg.encode('utf-8'))
        self.request.finish()

    def download_done(self, context):
        if splitext(self.localfilename)[1].lower() == '.torrent':
            self.add_task_to_multidl()
        else:
            msg = ''.join(['download: ', self.url, ' OK'])
            self.retRequest(msg)

    def error_handler(self, error, msg = None):
        if msg is None:
            msg = ''.join(['download: ', self.url, ' failed: ', str(error)])
        
        self.retRequest(msg)

    def add_task_to_multidl(self):
        msg = ''.join(['unknown error while add ', self.url, ' to download: '])
        try:
            if self.multidl.dls.has_key(self.localfilename):
                #TODO: torrentfile is downloading or not
                print '%s is downloading' % self.localfilename
                msg = ''.join([self.url, ' is already downloading'])        
            else:
                try:
                    dl = self.multidl.add_dl(self.localfilename)
                    dl.start() 
                    msg = ''.join([self.url, ' is beginning to download'])
                except Exception as e:
                    msg = ''.join(['add ', self.url, ' to multidl error: ', str(e)])            
        except Exception as e:
            msg.join(str(e))

        self.retRequest(msg)

    def makedir(self):
        dstdirname = dirname(self.localfilename)
        try:
            if not os.path.exists(dstdirname):
                os.makedirs(dstdirname)
        except Exception, exc:
            #logger.info("down: %s to %s failed: %s", url, self.localfilename, exc)
            print "mkdir: %s failed: %s"%(dstdirname, exc)            
            msg = "mkdir: %s failed: %s"%(dstdirname, exc)
            self.error_handler(exc, msg)
            return False
        else:
            return True


    def start(self, redownload=True):
        if self.makedir() == False:
            return 

        deferred = downloadPage(bytes(self.url), self.localfilename)
        deferred.addCallback(self.download_done)

        deferred.addErrback(self.error_handler)



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
        
        #taskdict.add(task.get('taskid'))
        torrentfileurl = task.get('torrentfileurl')
        topdir = task.get('wwwroot')
        event = task.get('event')
        print "taskid: %s"%task.get('taskid')
        print "event: %s"%event
        print "seedurl: %s"%task.get('seederurl')        
        print "torrentfileurl: %s"%torrentfileurl
        print "sha1: %s"%task.get('sha1')
        
        if event == 'download' and torrentfileurl:
            #if file not exits, download the torrent file 
            print 'download %s' % torrentfileurl            

            if topdir is None:
                topdir = self.wwwroot
            
            try:
                adl = AsyncDownloader(topdir, self.multidl, torrentfileurl, request)
                adl.start()
                return NOT_DONE_YET
            except Exception as e:
                ret = "".join(["download ", torrentfileurl, " failed: ", str(e)])
                print ret
                return ret.encode('utf-8')
                
        return 'task_received'


class MakeTorrent(Resource):
    tasknum = 0
    def __init__(self, taskqueue, multidl):
        self.taskqueue = taskqueue
        self.multidl = multidl
        self.wwwroot = wwwroot #global var wwwroot


    def return_request(self, request, msg):
        request.write(msg.encode('utf-8'))
        request.finish()

    def maketorrent(self, filename, request):
        print 'begin to make torrent: %s'%filename

        def dc(v):
            print v

        def prog(amount):
            print '%.1f%% complete\r' % (amount * 100),

        config = {'comment': '', 'filesystem_encoding': '', 'target': '', 'language': '', 'use_tracker': True, 'data_dir': '/home/gjwang/.bittorrent/data', 'piece_size_pow2': 18, 'tracker_list': '', 'tracker_name': 'http://223.82.137.218:8090/announce'}

        #args = ['http://223.82.137.218:8090/announce', 'test_web_bittorrent.py', 'testdownload.py']
        #tracker = 'http://223.82.137.218:8090/announce'
        tracker = config['tracker_name']

        try:
            make_meta_files(tracker,
                            [filename],
                            progressfunc=prog,
                            filefunc=dc,
                            piece_len_pow2=config['piece_size_pow2'],
                            comment=config['comment'],
                            target=config['target'],
                            filesystem_encoding=config['filesystem_encoding'],
                            use_tracker=config['use_tracker'],
                            data_dir=config['data_dir'])

            msg = ' '.join(['maketorrent:', filename, '->', filename + '.torrent', 'OK'])
        except BTFailure, e:
            msg = "make_meta_files failed: %s" % str(e)
            print msg
        except Exception, e:
            msg = "make_meta_files Exception: %s" % str(e)
            print msg

        
        print msg
        self.return_request(request, msg)

    def download_done(self, context, filename, request):
        print "download: %s done"%filename
        self.maketorrent(filename, request)

        
    def error_handler(self, error, request, msg = None):
        if msg is None:
            msg = ' '.join(['maketorrent failed:', str(error)])
        
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
        
        if event == 'maketorrent' and fileurl:
            #if file not exits, download the torrent file 
            print 'download %s' % fileurl

            if topdir is None:
                topdir = self.wwwroot
            
            localfilename = join(topdir, urlsplit(fileurl).path[1:])

            try:
                if os.path.exists(localfilename):
                    #and getsize(localfilename) == filesize:
                    #hash_info == task.get('hasn_info')
                    print "%s already exist" % localfilename
                    self.maketorrent(localfilename, request)
                else:
                    dstdirname = dirname(localfilename)
                    if not os.path.exists(dirname(localfilename)):
                        os.makedirs(dstdirname)

                    deferred = downloadPage(bytes(fileurl), localfilename)
                    deferred.addCallback(self.download_done, localfilename, request)
                    deferred.addErrback(self.error_handler, request)

                return NOT_DONE_YET
                #adl = AsyncDownloader(topdir, self.multidl, torrentfileurl, request)
                #adl.start()
                #return 'unknown error: should be here'
            except Exception as e:
                ret = " ".join(["maketorrent:", fileurl, "failed:", str(e)])
                print ret
                return ret.encode('utf-8')
        else:                            
            return 'unknown event'


class ShutdownTask(Resource):
    def __init__(self, taskqueue, multidl):
        self.taskqueue = taskqueue
        self.multidl = multidl
        self.wwwroot = wwwroot #global var wwwroot

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

        
        if event == 'shutdown':
            if torrentfileurl:
                torrentfile = join(topdir, urlsplit(torrentfileurl).path[1:])
                try:
                    self.multidl.shutdown(torrentfile)
                    msg = " ".join(["shutdown", torrentfileurl, "OK"])
                except Exception as e:
                    msg = " ".join(["shutdown", torrentfileurl, "failed: ", str(e)])           
            else:
                msg = "shutdown: not special shutdown file"            
        elif event == 'shutdownall':
            try:
                self.multidl.shutdown()
                msg = "shutdown all downloads: OK"
            except Exception as e:
                msg = " ".join(["shutdown all downloads: failed:", str(e)])
        else:                
            msg = "shutdown: unknown command"

        print msg    
        return msg.encode('utf-8')



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

    
    
