
'''
Created on 2013-11-29

@author: gjwang
'''
#from multiprocessing import Process, Queue

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


def download(topdir, url, request, filesize = None, localFileName = None):
    def retGET(context, request):
        msg = ''.join(['download: ', url, ' OK'])
        request.write(msg.encode('utf-8'))
        request.finish()
    def errorHandler(error, request):
        msg = ''.join(['download: ', url, ' failed: ', str(error)])
        request.write(msg.encode('utf-8'))
        request.finish()

    try:
        dstdir = topdir
        if localFileName != None:
            localName = localFileName
        else:
            #print "dstdir:", dstdir
            localName = join(dstdir, urlsplit(url).path[1:])

        print localName

        #url = 'http://223.82.137.218:8088/01254aa4909c4596b41b547e9fa83378.ts.torrent'
        #dl= HTTPDownloader(url, localName)

        dstdirname = dirname(localName)
        if not os.path.exists(dstdirname):
            os.makedirs(dstdirname)

        
        #HOW to know download finish or error?
        deferred = downloadPage(bytes(url), localName)
        deferred.addCallback(retGET, request)
        deferred.addErrback(errorHandler, request)

        return localName        
    except Exception, exc:
        #logger.info("down: %s to %s failed: %s", url, localName, exc)
        print "down: %s to %s failed: %s"%(url, localName, exc)
        raise exc


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
        print "taskid: %s"%task.get('taskid')
        print "event: %s"%task.get('event')
        print "seedurl: %s"%task.get('seederurl')        
        print "torrentfileurl: %s"%torrentfileurl
        print "sha1: %s"%task.get('sha1')
        
        if task.get('event') == 'download' and torrentfileurl:
            #if file not exits, download the torrent file 
            print 'download %s' % torrentfileurl            

            if topdir is None:
                topdir = self.wwwroot
            
            torrentfile = None
            try:
                #self.multidl.multitorrent.rawserver.add_task(download, 0, args=(topdir, torrentfileurl))
                torrentfile= download(topdir, torrentfileurl, request)
                return NOT_DONE_YET
            except Exception as e:
                ret = "".join(["download ", torrentfileurl, " failed: ", str(e)])
                print ret
                return ret.encode('utf-8')
                

            #TODO: torrentfile is downloading or not
            if self.multidl.dls.has_key(torrentfile):
                print '%s is downloading' % torrentfile
                return '%s is downloading' % torrentfile
            else:
                #dl = self.multidl.add_dl(torrentfile)
                #dl.start()        
                pass
        #try:
        #    taskqueue.put_nowait(task)
        #except Exception as e:
        #    print e
        #    return "task queue is Full"
        #request.write('task_received')
        #request.finish()
        return 'task_received'

    def render_POST(self, request):
        return self.render_GET(request)

taskqueue = Queue(3)
taskdict = {}
if __name__ == "__main__":
    

    root = Resource()
    root.putChild("hello", HelloResource())
    root.putChild("form", FormPage())
    root.putChild("ping", Ping())
    root.putChild("puttask", PutTask(taskqueue))
    
    factory = Site(root)
    reactor.listenTCP(8090, factory)
    #reactor.run()    
    p = Process(target=reactor.run)
    p.start()
    print 'site is runnning...'
    p.join()

    
    
