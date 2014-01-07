#!/usr/bin/env python

# The contents of this file are subject to the BitTorrent Open Source License
# Version 1.1 (the License).  You may not copy or use this file, in either
# source code or executable form, except in compliance with the License.  You
# may obtain a copy of the License at http://www.bittorrent.com/license/.
#
# Software distributed under the License is distributed on an AS IS basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied.  See the License
# for the specific language governing rights and limitations under the
# License.

# Written by Bram Cohen, Uoti Urpala and John Hoffman

from __future__ import division

from BitTorrent.platform import install_translation
install_translation()

import sys
import os
import threading
import copy
from time import time, strftime
from cStringIO import StringIO
import binascii

import logging
import logging.handlers
from logging.handlers import TimedRotatingFileHandler
from twisted.python import log
from twisted.python.logfile import DailyLogFile

from BitTorrent.download import Feedback, Multitorrent
from BitTorrent.defaultargs import get_defaults
from BitTorrent.parseargs import printHelp
from BitTorrent.zurllib import urlopen
from BitTorrent.bencode import bdecode
from BitTorrent.ConvertedMetainfo import ConvertedMetainfo
from BitTorrent.prefs import Preferences
from BitTorrent import configfile
from BitTorrent import BTFailure
from BitTorrent import version
from BitTorrent import GetTorrent

from zope.interface import implements

from twisted.internet.protocol import Protocol
from twisted.internet.defer import succeed, Deferred
from twisted.web.iweb import IBodyProducer
from twisted.web import server, resource
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.internet import reactor
from twisted.web.client import Agent
from twisted.web.http_headers import Headers
#from twisted.web.client import FileBodyProducer

import json
import cgi

from bittorrent_webserver import FormPage, Ping, PutTask, ShutdownTask, MakeTorrent
from conf import report_peer_status_url, response_msg, downloader_config, bt_remote_ctrl_listen_port, logfile


def fmttime(n):
    if n == 0:
        return _("download complete!")
    try:
        n = int(n)
        assert n >= 0 and n < 5184000  # 60 days
    except:
        return _("<unknown>")
    m, s = divmod(n, 60)
    h, m = divmod(m, 60)
    return _("finishing in %d:%02d:%02d") % (h, m, s)

def fmtsize(n):
    s = str(n)
    size = s[-3:]
    while len(s) > 3:
        s = s[:-3]
        size = '%s,%s' % (s[-3:], size)
    if n > 999:
        unit = ['B', 'KiB', 'MiB', 'GiB', 'TiB', 'PiB', 'EiB', 'ZiB', 'YiB']
        i = 1
        while i + 1 < len(unit) and (n >> 10) >= 999:
            i += 1
            n >>= 10
        n /= (1 << 10)
        size = '%s (%.0f %s)' % (size, n, unit[i])
    return size


class HeadlessDisplayer(object):

    def __init__(self, doneflag):
        self.doneflag = doneflag

        self.done = False
        self.percentDone = ''
        self.timeEst = ''
        self.downRate = '---'
        self.upRate = '---'
        self.shareRating = ''
        self.seedStatus = ''
        self.peerStatus = ''
        self.errors = []
        self.file = ''
        self.downloadTo = ''
        self.fileSize = ''
        self.numpieces = 0

    def set_torrent_values(self, name, path, size, numpieces):
        self.file = name
        self.downloadTo = path
        self.fileSize = fmtsize(size)
        self.numpieces = numpieces

    def finished(self):
        self.done = True
        self.downRate = '---'
        self.display({'activity':_("download succeeded"), 'fractionDone':1})

    def error(self, errormsg):
        newerrmsg = strftime('[%H:%M:%S] ') + errormsg
        self.errors.append(newerrmsg)
        self.display({})

    def display(self, statistics):
        fractionDone = statistics.get('fractionDone')
        activity = statistics.get('activity')
        timeEst = statistics.get('timeEst')
        downRate = statistics.get('downRate')
        upRate = statistics.get('upRate')
        spew = statistics.get('spew')

        self._logger.info('\n\n\n\n')
        if spew is not None:
            self.print_spew(spew)

        if timeEst is not None:
            self.timeEst = fmttime(timeEst)
        elif activity is not None:
            self.timeEst = activity

        if fractionDone is not None:
            self.percentDone = str(int(fractionDone * 1000) / 10)
        if downRate is not None:
            self.downRate = '%.1f KB/s' % (downRate / (1 << 10))
            #print "type(%s), downRate%s"%(type(downRate), downRate)
            
        if upRate is not None:
            self.upRate = '%.1f KB/s' % (upRate / (1 << 10))
        downTotal = statistics.get('downTotal')
        if downTotal is not None:
            upTotal = statistics['upTotal']
            if downTotal <= upTotal / 100:
                self.shareRating = _("oo  (%.1f MB up / %.1f MB down)") % (
                    upTotal / (1<<20), downTotal / (1<<20))
            else:
                self.shareRating = _("%.3f  (%.1f MB up / %.1f MB down)") % (
                   upTotal / downTotal, upTotal / (1<<20), downTotal / (1<<20))
            numCopies = statistics['numCopies']
            nextCopies = ', '.join(["%d:%.1f%%" % (a,int(b*1000)/10) for a,b in
                    zip(xrange(numCopies+1, 1000), statistics['numCopyList'])])
            if not self.done:
                self.seedStatus = _("%d seen now, plus %d distributed copies "
                                    "(%s)") % (statistics['numSeeds' ],
                                               statistics['numCopies'],
                                               nextCopies)
            else:
                self.seedStatus = _("%d distributed copies (next: %s)") % (
                    statistics['numCopies'], nextCopies)
            self.peerStatus = _("%d seen now") % statistics['numPeers']

        for err in self.errors[-4:]:
            print _("ERROR:\n") + err + '\n'
        self._logger.info(_("saving:        "), self.file)
        self._logger.info(_("file size:     "), self.fileSize)
        self._logger.info(_("percent done:  "), self.percentDone)
        self._logger.info(_("time left:     "), self.timeEst)
        self._logger.info(_("download to:   "), self.downloadTo)
        self._logger.info(_("download rate: "), self.downRate)
        self._logger.info(_("upload rate:   "), self.upRate)
        self._logger.info(_("share rating:  "), self.shareRating)
        self._logger.info(_("seed status:   "), self.seedStatus)
        self._logger.info(_("peer status:   "), self.peerStatus)
        self._logger.info(_("done:          "), self.done)


    def print_spew(self, spew):
        s = StringIO()
        s.write('\n\n\n')
        for c in spew:
            s.write('%20s ' % c['ip'])
            if c['initiation'] == 'L':
                s.write('l')
            else:
                s.write('r')
            total, rate, interested, choked = c['upload']
            s.write(' %10s %10s ' % (str(int(total/10485.76)/100),
                                     str(int(rate))))
            if c['is_optimistic_unchoke']:
                s.write('*')
            else:
                s.write(' ')
            if interested:
                s.write('i')
            else:
                s.write(' ')
            if choked:
                s.write('c')
            else:
                s.write(' ')

            total, rate, interested, choked, snubbed = c['download']
            s.write(' %10s %10s ' % (str(int(total/10485.76)/100),
                                     str(int(rate))))
            if interested:
                s.write('i')
            else:
                s.write(' ')
            if choked:
                s.write('c')
            else:
                s.write(' ')
            if snubbed:
                s.write('s')
            else:
                s.write(' ')
            s.write('\n')
        self._logger.info(s.getvalue())


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

class BeginningPrinter(Protocol):
    def __init__(self, finished):
        self._logger = logging.getLogger(self.__class__.__name__)

        self.finished = finished
        self.remaining = 1024 * 10
        self.recv = ''
        
    def dataReceived(self, bytes):
        if self.remaining:
            self.recv += bytes[:self.remaining]
            self.remaining -= len(display)

    def connectionLost(self, reason):
        self._logger.info('received: %s', self.recv)
        #print 'Finished receiving body:', reason.getErrorMessage()
        if self.recv == 'success':            
            self.finished.callback(None)

class StatusReporter(object):
    def __init__(self, report_url):
        self._logger = logging.getLogger(self.__class__.__name__)

        self.report_url = report_url
        self.agent = Agent(reactor)
        self.status_msg = copy.deepcopy(response_msg)
        self.status_msg["status"] = ""
        self.status_msg["args"]["percent"] = 0
        self.status_msg["args"]["timeleft"] = 0
        self.status_msg["args"]["downrate"] = 0
        self.status_msg["args"]["uprate"] = 0                
        self.status_msg["args"]["downtotal"] = 0
        self.status_msg["args"]["uptotal"] = 0               
        self.status_msg["args"]["numpeers"] = 0
        self.status_msg["args"]["numseeds"] = 0

        self.send_seedstatus_ok = False
        self.status = None
        self.retries = 0

    def send_status(self, statistics, torrentfile=None, sha1=None):
        activity = statistics.get('activity')
        self.status = activity
        if self.send_seedstatus_ok:
            #make sure seeding status been reported success at least once
            #if sucess report seeding status, then stop to repeat report it
            return

        fractionDone = statistics.get('fractionDone')
        timeEst = statistics.get('timeEst')
        downRate = statistics.get('downRate')
        upRate = statistics.get('upRate')
        downTotal = statistics.get('downTotal')
        #spew = statistics.get('spew')

        if True:
            status_msg = copy.deepcopy(self.status_msg)
            status_msg["event"]  = "status_response"

            if activity is not None:
                status_msg["status"] = activity
                
            #status_msg["result"] = "success",          #success, failed
            #"trackback": "",         #failed cause
            status_msg["args"]["sha1"] = sha1 or ''

            if fractionDone is not None:
                status_msg["args"]["percent"] = str(int(fractionDone * 1000) / 10)

            if timeEst is not None:
                status_msg["args"]["timeleft"] = int(timeEst)    #seconds

            if downRate is not None:
                status_msg["args"]["downrate"] = int(downRate)

            if upRate is not None:
                status_msg["args"]["uprate"] = int(upRate)

            if torrentfile is not None:
                status_msg["args"]["torrentfile"] = torrentfile

            if downTotal is not None:
                upTotal = statistics['upTotal']
                status_msg["args"]["downtotal"] = int(downTotal)
                status_msg["args"]["uptotal"] = int(upTotal)
                status_msg["args"]["numpeers"] = statistics['numPeers']
                status_msg["args"]["numseeds"] = statistics['numSeeds' ]
                #status_msg["args"]["seedstatus"] = self.seedStatus

            self._logger.info('send_status: %s', status_msg)
            self.send(json.dumps(status_msg, indent=4, sort_keys=True, separators=(',', ': ')))


    def send_finished(self, ignored):
        self.send_seedstatus_ok = True        
        self._logger.info("send seeding status to %s success", self.report_url)

    def cb_response(self, response):
        #print 'Response version:', response.version
        self._logger.info('Response code: %s', response.code)
        #print 'Response phrase:', response.phrase
        #print 'Response headers:'
        #from pprint import pformat
        #print pformat(list(response.headers.getAllRawHeaders()))
        if response.code == 200:
            self.retries = 0
            if self.status == 'seeding' or self.status == 'download succeeded':
                finished = Deferred()
                finished.addCallback(self.send_finished)
                response.deliverBody(BeginningPrinter(finished))
        else:
            self.retries += 1
            self._logger.error("send status to %s failed, response_code: %s, retries: %s", 
                                self.report_url, response.code, self.retries)

    def cb_error_response(self, error):
        self.retries += 1
        self._logger.error("send status to %s failed, error: %s, retries: %s", self.report_url, str(error), self.retries)
        

    def send(self, status):
        body = StringProducer(status)
        d = self.agent.request(
            'POST',
            self.report_url,
            Headers({'User-Agent': ['Twisted Web Client'],
                     'Content-Type': ['application/json']}),
            body)

        d.addCallback(self.cb_response)
        d.addErrback(self.cb_error_response)


class DL(Feedback):

    def __init__(self, metainfo, config, singledl_config = {}, multitorrent=None, doneflag=None):
        self._logger = logging.getLogger(self.__class__.__name__)

        self.doneflag = doneflag
        self.metainfo = metainfo

        try:
            for k, v in singledl_config.items():
                config[k] = v
        except Exception as e:
            self._logger.error("parse DL config Exception: %s", str(e))

        self.config = config        
        self.multitorrent = multitorrent
        self.shutdownflag = False
        self.torrentfile = None
        self.torrent_name = None
        self.hash_info = None
        self.activity = None
        self.interval = self.config['display_interval']
        self.time_after_seeding = 0

    def run(self):
        self.d = HeadlessDisplayer(self.doneflag)
        self.status_reporter = StatusReporter(report_peer_status_url)

        try:
            self._logger.info('DL.run.Multitorrent')
            if self.multitorrent is None:
                self.doneflag = threading.Event()
                self.multitorrent = Multitorrent(self.config, self.doneflag,
                                                 self.global_error)

            # raises BTFailure if bad
            metainfo = ConvertedMetainfo(bdecode(self.metainfo))
            self.hash_info = binascii.b2a_hex(metainfo.infohash)

            torrent_name = metainfo.name_fs
            if self.torrentfile is None:
                self.torrentfile = '.'.join([torrent_name, 'torrent'])

            if config['save_as']:
                if config['save_in']:
                    raise BTFailure(_("You cannot specify both --save_as and "
                                      "--save_in"))
                saveas = config['save_as']
            elif config['save_in']:
                saveas = os.path.join(config['save_in'], torrent_name)
            else:
                saveas = torrent_name

            self.d.set_torrent_values(metainfo.name, os.path.abspath(saveas),
                                metainfo.total_bytes, len(metainfo.hashes))

            self._logger.info("start_torrent: %s", saveas)
            self.torrent = self.multitorrent.start_torrent(metainfo,
                                Preferences(self.config), self, saveas)
        except BTFailure, e:
            self._logger.error("start_torrent raise Exception BTFailure: %s", str(e))
            raise e

        self.get_status()

    def start(self):
        self.run()

    def shutdown(self):
        self.torrent.shutdown()
        self.shutdownflag = True

    def reread_config(self):
        try:
            newvalues = configfile.get_config(self.config, 'bittorrent-console')
        except Exception, e:
            self.d.error(_("Error reading config: ") + str(e))
            return
        self.config.update(newvalues)
        # The set_option call can potentially trigger something that kills
        # the torrent (when writing this the only possibility is a change in
        # max_files_open causing an IOError while closing files), and so
        # the self.failed() callback can run during this loop.
        for option, value in newvalues.iteritems():
            self.multitorrent.set_option(option, value)
        for option, value in newvalues.iteritems():
            self.torrent.set_option(option, value)

    def get_status(self):
        if self.shutdownflag:
            #status = 'shutdown'
            #self.status_reporter.send_status(status)
            return
        
        if self.status_reporter.retries:
            self.interval = min(60*15, self.config['display_interval']*2**self.status_reporter.retries)
            self._logger.info("retries: %s, report status in %s seconds later", self.status_reporter.retries, self.interval)
        elif self.activity == 'seeding':
            #reduce the frequency of getting seeding status 
            self.time_after_seeding +=1
            self.interval = min(60*30, max(self.interval, self.config['display_interval']*2**self.time_after_seeding))
            self._logger.info("status: %s, get status in %s seconds later", self.activity, self.interval)
        else:
            self.interval = self.config['display_interval']
            self._logger.info("status: %s, get status in %s seconds later", self.activity, self.interval)

        self.multitorrent.rawserver.add_task(self.get_status, self.interval)
        status = self.torrent.get_status(self.config['spew'])
        self.activity = status.get('activity')

        self.d.display(status)
        self.status_reporter.send_status(status, self.torrentfile, self.hash_info)


    def get_activity(self):
        return self.activity

    def global_error(self, level, text):
        self.d.error(text)

    def error(self, torrent, level, text):
        self.d.error(text)

    def failed(self, torrent, is_external):
        self.doneflag.set()

    def finished(self, torrent):
        self.d.finished()


class MultiDL():
    def __init__(self, config):
        self._logger = logging.getLogger(self.__class__.__name__)

        self.doneflag = threading.Event()
        self.config = Preferences().initWithDict(config)
        self.multitorrent = Multitorrent(self.config, self.doneflag,
                                         self.global_error)
        self.dls = {}       #downloaders dict

    def add_dl(self, torrentfile, singledl_config = {}):
        if torrentfile is not None:
            metainfo, errors = GetTorrent.get(torrentfile)
            if errors:
                raise BTFailure(_("Error reading .torrent file: ") + '\n'.join(errors))
        else:
            raise BTFailure(_("you must specify a .torrent file"))

        dl = DL(metainfo, self.config, singledl_config, self.multitorrent, self.doneflag)
        dl.start()
        self.dls[dl.hash_info] = (dl, torrentfile)
        return dl

    def listen_forever(self):
        self.multitorrent.rawserver.install_sigint_handler()
        self.multitorrent.rawserver.listen_forever()

    def shutdown(self, sha1 = None, torrentfile = None):
        #TODO: get the hash_info to avoid the same file with two torrent file
        self._logger.error('MultiDl.shutdown')
        try:
            #delete the downloader to avoid mem leak?
            if sha1:
                self._logger.error("Going to shutdown sha1: %s", sha1)
                if self.dls.has_key(sha1):
                    dl, _ = self.dls[sha1]
                    dl.shutdown()
                    del self.dls[sha1]
                    self._logger.error("shutdown sha1: %s ok", sha1)                    
                else:
                    self._logger.error("sha1: %s is not downloading", sha1)
            elif torrentfile:
                self._logger.error("shutdown file: %s...", torrentfile)
                for (hash_info, (dl, f)) in self.dls.items():
                    if f == torrentfile:
                        dl.shutdown()
                        del self.dls[hash_info]
                        self._logger.error("shutdown file: %s ok", torrentfile)
                        break
            else:
                #shutdown the all downloads
                for (dl, _) in self.dls.values():
                    dl.shutdown()

                self.dls.clear()
        except Exception as e:
            self._logger.error("shutdown raise %s exception: %s", torrentfile, e)
            raise e

    def global_error(self, level, text):
        #self.d.error(text)
        self._logger.error(text)


def main(logger):
    config = downloader_config
    multidl = MultiDL(config)

    root = Resource()
    root.putChild("form", FormPage())
    root.putChild("ping", Ping())
    root.putChild("puttask", PutTask(multidl))
    root.putChild("shutdowntask", ShutdownTask(multidl))
    root.putChild("maketorrent", MakeTorrent(multidl))
    
    factory = Site(root)

    reactor.listenTCP(bt_remote_ctrl_listen_port, factory)

    multidl.listen_forever()
    multidl.shutdown()

if __name__ == '__main__':

    first_start = True
    while True:
        try:
            #redirect to twisted log to python stardard logger, for backCount
            #observer = log.PythonLoggingObserver(loggerName='web-bittorrent-console') 
            #observer.start()
            #log.startLogging(DailyLogFile.fromFullPath(logfile))

            logHandler = TimedRotatingFileHandler(filename=logfile, when='midnight', interval=1, backupCount=15)
            logFormatter = logging.Formatter('%(asctime)s %(message)s')
            logHandler.setFormatter( logFormatter )
            logger = logging.getLogger()
            logger.addHandler( logHandler )
            logger.setLevel( logging.INFO )
            if first_start:
                print "start web-bittorrent-console, listening port:%s forever" % bt_remote_ctrl_listen_port
                logger.info("start web-bittorrent-console, listening port:%s forever", bt_remote_ctrl_listen_port)
                first_start = False

            #main will never exit unless something unexpected happen
            main(logger)
        except Exception, ex:
            logger.exception("Something awful happened!")
            logger.error("\n\n\n\nrestart web-bittorrent-console, listening port:%s forever", bt_remote_ctrl_listen_port)
            logging.shutdown()

            time.sleep(1)
