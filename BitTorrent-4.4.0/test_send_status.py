from zope.interface import implements

from twisted.internet.defer import succeed
from twisted.web.iweb import IBodyProducer

from StringIO import StringIO

from twisted.internet import reactor
from twisted.web.client import Agent
from twisted.web.http_headers import Headers

from twisted.web.client import FileBodyProducer

import json

report_peer_status_url = 'http://127.0.0.1:8200/report_peerstatus'

class StringProducer(object):
    implements(IBodyProducer)

    def __init__(self, body):
        self.body = body
        self.length = len(body)

    def startProducing(self, consumer):
        consumer.write(self.body)
        return succeed(None)

    def pauseProducing(self):
        pass

    def stopProducing(self):
        pass

agent = Agent(reactor)
body = StringProducer(json.dumps({"hello":"world"}))
#body = FileBodyProducer(StringIO("hello, world"))
d = agent.request(
    'POST',
    report_peer_status_url,
    Headers({'User-Agent': ['Twisted Web Client'],
             'Content-Type': ['application/json']}),
    body)

def cbResponse(ignored):
    print ignored
    print 'Response received'
#d.addCallback(cbResponse)

def cbRequest(response):
    print 'Response version:', response.version
    print 'Response code:', response.code
    print 'Response phrase:', response.phrase
    print 'Response headers:'
    print pformat(list(response.headers.getAllRawHeaders()))
    finished = Deferred()
    response.deliverBody(BeginningPrinter(finished))
    return finished

d.addCallback(cbRequest)

def cbShutdown(ignored):
    reactor.stop()
d.addBoth(cbShutdown)

reactor.run()
