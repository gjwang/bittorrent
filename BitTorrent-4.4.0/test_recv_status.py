
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

import json
import cgi


class GetPeerStatus(resource.Resource):
    isLeaf = True
    numberRequests = 0
    
    def render_GET(self, request):
        self.numberRequests += 1
        request.setHeader("content-type", "text/plain")
        print "request: %s"%request
        print request.uri
        return "I am request #" + str(self.numberRequests) + "\n"
    
    def render_POST(self, request):
        self.numberRequests += 1
        request.setHeader("content-type", "text/plain")

        print '\n\n'
        print request
        print request.args


        content = cgi.escape(request.content.read())
        print content
        task = {}
        try:
            task = json.loads(content)
        except Exception as e:
            print e
            return "json format error"

        #print task

        return "I am request #" + str(self.numberRequests) + "\n"


if __name__ == "__main__":    
    root = Resource()
    root.putChild("report_peerstatus", GetPeerStatus())
    
    factory = Site(root)
    reactor.listenTCP(8200, factory)
    reactor.run()
    
    
