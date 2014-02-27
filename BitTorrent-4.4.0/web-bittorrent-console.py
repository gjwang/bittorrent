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

import sys, traceback
import os
import threading
from multiprocessing import Process
import copy
import time
from time import strftime
from cStringIO import StringIO
import binascii
import pickle

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
from conf import report_peer_status_url, response_msg, downloader_config, bt_remote_ctrl_listen_port
from conf import logfile, persistent_tasks_file, task_expire_time

def check_runtime_env():
    import resource
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    min_limit =  10240
    if soft < min_limit or hard < min_limit:
        try:
            resource.setrlimit(resource.RLIMIT_NOFILE, (min_limit, min_limit))
        except Exception as e:
            print "os max open files limit(soft=%d, hard=%d) less than (soft=%s, hard=%s). and %s" % \
                   (soft, hard, min_limit, min_limit, str(e))
            print "Please raise maximum limit to fix it!\nstart failed. exit!"
            exit(0)            


check_runtime_env()

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

    def __init__(self, taskid, doneflag):
        self._logger = logging.getLogger(self.__class__.__name__)

        self.taskid =  taskid
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
        #self.downRate = '---'
        #self.display({'activity':_("download succeeded"), 'fractionDone':1})

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

        #self._logger.info('\n\n\n\n')
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
            self._logger.info("ERROR: %s", err)
        del self.errors[:]

        self._logger.info("taskid:        %s", self.taskid)
        self._logger.info("saving:        %s", self.file)
        self._logger.info("file size:     %s", self.fileSize)
        self._logger.info("percent done:  %s", self.percentDone)
        self._logger.info("time left:     %s", self.timeEst)
        self._logger.info("download to:   %s", self.downloadTo)
        self._logger.info("download rate: %s", self.downRate)
        self._logger.info("upload rate:   %s", self.upRate)
        self._logger.info("share rating:  %s", self.shareRating)
        self._logger.info("seed status:   %s", self.seedStatus)
        self._logger.info("peer status:   %s", self.peerStatus)
        self._logger.info("done:          %s", self.done)


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
        if self.recv == 'success':            
            self.finished.callback(None)

class StatusReporter(object):
    def __init__(self, taskid, report_url):
        self._logger = logging.getLogger(self.__class__.__name__)

        self.taskid = taskid
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
        self.status = statistics.get('activity')

        if self.send_seedstatus_ok:
            #make sure seeding status been reported success at least once
            #if success report seeding status, then stop to repeat report it
            return

        fractionDone = statistics.get('fractionDone')
        timeEst = statistics.get('timeEst')
        downRate = statistics.get('downRate')
        upRate = statistics.get('upRate')
        downTotal = statistics.get('downTotal')
        #spew = statistics.get('spew')

        if True:
            status_msg = copy.deepcopy(self.status_msg)
            status_msg["taskid"] = self.taskid
            status_msg["event"]  = "status_response"
            status_msg["status"] = self.status or ''
                
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
            self.send(status_msg)


    def send_finished(self, ignored, status_msg):
        self.send_seedstatus_ok = True        
        self._logger.info("sha1: %s, send status: %s to %s success",
			   status_msg['args']['sha1'], status_msg['status'], self.report_url)

    def cb_response(self, response, status_msg):
        #print 'Response version:', response.version
	status = status_msg['status']
	sha1 = status_msg['args']['sha1']
        self._logger.info('sha1: %s, send status: %s, Response code: %s', sha1, status, response.code)
        #print 'Response phrase:', response.phrase
        #print 'Response headers:'
        #from pprint import pformat
        #print pformat(list(response.headers.getAllRawHeaders()))
        if response.code == 200:
            self.retries = 0
            if status == 'seeding' or status == 'download succeeded':
                finished = Deferred()
                finished.addCallback(self.send_finished, status_msg)
                response.deliverBody(BeginningPrinter(finished))
        else:
            self.retries += 1
            self._logger.error("sha1: %s, send status: %s to %s failed, response_code: %s, retries: %s", 
                                sha1, status, self.report_url, response.code, self.retries)

    def cb_error_response(self, error, status_msg):
        self.retries += 1
        self._logger.error("sha1: %s, send status: %s to %s failed, error: %s, retries: %s",
			    status_msg['args']['sha1'], status_msg['status'], self.report_url, str(error), self.retries)

    def send(self, status_msg):
        body = StringProducer(json.dumps(status_msg, indent=4, sort_keys=True, separators=(',', ': ')))
        d = self.agent.request(
            'POST',
            self.report_url,
            Headers({'User-Agent': ['Twisted Web Client'],
                     'Content-Type': ['application/json']}),
            body)

        d.addCallback(self.cb_response, status_msg)
        d.addErrback(self.cb_error_response, status_msg)


class DL(Feedback):

    def __init__(self, taskid, metainfo, config, singledl_config = {}, multitorrent=None, doneflag=None):
        self._logger = logging.getLogger(self.__class__.__name__)

        self.taskid = taskid
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
        self.d = HeadlessDisplayer(self.taskid, self.doneflag)
        self.status_reporter = StatusReporter(self.taskid, report_peer_status_url)

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

            if self.config['save_as']:
                if self.config['save_in']:
                    raise BTFailure(_("You cannot specify both --save_as and "
                                      "--save_in"))
                saveas = self.config['save_as']
            elif self.config['save_in']:
                saveas = os.path.join(self.config['save_in'], torrent_name)
            else:
                saveas = torrent_name

            self.d.set_torrent_values(metainfo.name, os.path.abspath(saveas),
                                metainfo.total_bytes, len(metainfo.hashes))

            self._logger.info("start_torrent: %s", saveas)
            self.torrent = self.multitorrent.start_torrent(metainfo,
                                Preferences(self.config), self, saveas)
        except BTFailure, e:
            self._logger.exception("start_torrent raise Exception BTFailure: %s", str(e))
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

        status = self.torrent.get_status(self.config['spew'])
        activity = status.get('activity')
        if activity == 'seeding' or activity == 'download succeeded':
            self.activity = 'seeding'
        elif activity == 'downloading' or activity == 'Initial startup' or activity == 'checking existing file':
            self.activity = 'downloading'
        else:
            self._logger.error('get_status: what the fuck status= %s', activity)
            self.activity = activity

        self.d.display(status)

        if activity == 'Initial startup' or activity == 'checking existing file':
	    self._logger.info('skip send status=%s', activity)
	    pass
	else:
            self.status_reporter.send_status(status, self.torrentfile, self.hash_info)
        
        if self.status_reporter.retries:
            self.interval = min(60*15, self.config['display_interval']*2**self.status_reporter.retries)
            self._logger.info("retries: %s, report status in %s seconds later\n\n", self.status_reporter.retries, self.interval)
        elif self.activity == 'seeding' or self.activity == 'download succeeded':
            #reduce the frequency of getting seeding status 
            self.time_after_seeding +=1
            self.interval = min(60*60, max(self.interval, self.config['display_interval']*2**self.time_after_seeding))
            self._logger.info("status: %s, get status in %s seconds later, times_after_seeding=%s\n\n", 
			self.activity, self.interval, self.time_after_seeding)
        else:
            self.interval = self.config['display_interval']
            self._logger.info("status: %s, get status in %s seconds later\n\n", self.activity, self.interval)

        self.multitorrent.rawserver.add_task(self.get_status, self.interval)

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

        status = self.torrent.get_status(self.config['spew'])

        activity = status.get('activity')
	self.activity = 'seeding' if activity == 'download succeeded' else activity
        self._logger.info('download finished: status=%s', activity)

        self.d.display(status)
        self.status_reporter.send_status(status, self.torrentfile, self.hash_info)
        self.time_after_seeding +=1

class MultiDL():
    def __init__(self, config):
        self._logger = logging.getLogger(self.__class__.__name__)

        self.doneflag = threading.Event()
        self.config = Preferences().initWithDict(config)
        self.multitorrent = Multitorrent(self.config, self.doneflag,
                                         self.global_error)

        self.dls = {}       #downloaders dict
        self.tasks = {}
        self.expire_time = task_expire_time
        self.persistent_file = persistent_tasks_file
        self.multitorrent.rawserver.add_task(self.reload_tasks, 0)

        self.check_expire_interval = 1800
        self.multitorrent.rawserver.add_task(self.del_expire_tasks, self.check_expire_interval)

    #def __enter__(self):
    #    print '__enter__'
    #    self.tasks_file = open('tasks.pkl', 'r+b')
    #    return self

    def __exit__(self, *args):
        self._logger.error("MultiDL __exit__, shutdown all downloaders")
        for (dl, f) in self.dls.values():
            try:
                dl.shutdown()
            except Exception as e:
                self._logger.error("shutdown downloads Exception: %s, %s", str(e), f)


    def reload_tasks(self):
        tsks = {}
        try:
            with open(self.persistent_file, 'rb') as f:
                tsks =pickle.load(f)
        except IOError as e:
            pass
        except Exception as e:
            pass

        self._logger.info("persistent tasks count=%d", len(tsks))
        i = 0
        tasks_len = len(tsks)
        for hash_info, task in tsks.items():
            expire = task['expire'] - (int(time.time()) - task['begintime'])
            if expire <= 0:
                self._logger.info("task expire time=%s, do not reload. %s", -expire, task)
                continue
            delay = i/3.0
            i += 1
            persistent_task = True if i == tasks_len else False

            self._logger.info("reload task in %.2fsec later. task:%s", delay, task)
            try:
                self.multitorrent.rawserver.add_task(self.add_task, delay, 
                     args=(task.get('taskid'), task['torrentfile'], task['config'], hash_info, persistent_task, expire))
            except Exception as e:
                self._logger.error("reload task:%s Exception: %s", task, str(e))

    def persistent_tasks(self, tasks):
        self._logger.info("pickle.dump tasks_count=%d",len(tasks))
        try:
            with open(self.persistent_file, 'wb') as f:
                pickle.dump(tasks, f)
        except Exception as e:
            self._logger.error("persistent_tasks :%s Exception: %s", tasks, str(e))

    def add_task(self, taskid, torrentfile, singledl_config = {}, sha1=None, is_persistent_tasks = True, expire = 0):
        if sha1 and self.dls.has_key(sha1):
            self._logger.error('sha1: %s is already downloading', sha1)
            return self.dls[sha1][0]

        for (hash_info, (dl, f)) in self.dls.items():
            if f == torrentfile:
                status = dl.get_activity()
                self._logger.error('file: %s already downloading, status: %s', f, status)
                return dl

        if torrentfile is not None:
            metainfo, errors = GetTorrent.get(torrentfile)
            if errors:
                raise BTFailure(_("Error reading .torrent file: ") + '\n'.join(errors))
        else:
            raise BTFailure(_("you must specify a .torrent file"))

        dl = DL(taskid, metainfo, self.config, singledl_config, self.multitorrent, self.doneflag)
        dl.start()

        expire = self.expire_time if expire <= 0 else expire
        self.tasks[dl.hash_info] = {'taskid': taskid, 'torrentfile': torrentfile, 'status':{},'config':singledl_config,
                                    'begintime': int(time.time()), 'expire': expire}
        self.dls[dl.hash_info] = (dl, torrentfile)
        if is_persistent_tasks:
            self.persistent_tasks(self.tasks)
        return dl
        

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
            self._logger.info("Going to shutdown sha1= %s, file= %s", sha1, torrentfile)
            if sha1:
                if self.dls.has_key(sha1):
                    dl, _ = self.dls[sha1]
                    dl.shutdown()
                    del self.dls[sha1]
                    del self.tasks[sha1]
                    self.persistent_tasks(self.tasks)
                    self._logger.error("shutdown sha1: %s OK", sha1)
                    return
                else:
                    self._logger.error("shutdown sha1: %s is not downloading", sha1)

            if torrentfile:
                for (hash_info, (dl, f)) in self.dls.items():
                    if f == torrentfile:
                        dl.shutdown()
                        del self.dls[hash_info]
                        del self.tasks[hash_info]
                        self.persistent_tasks(self.tasks)
                        self._logger.error("shutdown file: %s OK", torrentfile)
                        return
                self._logger.error("file: %s is not downloading", torrentfile)

            shutdownall = sha1 is None and torrentfile is None
            if shutdownall:
                #shutdown the all downloads
                for (dl, _) in self.dls.values():
                    dl.shutdown()

                self.dls.clear()
                self.tasks.clear()
                self.persistent_tasks(self.tasks)
                self._logger.error("shutdownall OK")
                return
        except Exception as e:
            self._logger.error("shutdown raise %s exception: %s", torrentfile, e)
            raise e

    def global_error(self, level, text):
        #self.d.error(text)
        self._logger.error(text)

    def del_expire_tasks(self):
        try:
            del_tasks=[]
            for hash_info, task in self.tasks.items():
                expire = task['expire'] - (int(time.time()) - task['begintime'])
                #self._logger.info('%s, %s, %s, %s', expire, task['expire'], int(time.time()), task['begintime'])
                if expire <= 0:
                    del_tasks.append(hash_info)
                    self._logger.info("task expire time=%s, shut it down. %s:%s", -expire, hash_info, task)
          
            for hash_info in del_tasks:
                self.shutdown(hash_info)
        except Exception as e:
            self._logger.exception("del_expire_tasks exception")

        self._logger.info("check expire tasks in %s seconds later, tasks_left=%s", 
                           self.check_expire_interval, len(self.tasks))
        self.multitorrent.rawserver.add_task(self.del_expire_tasks, self.check_expire_interval)

def main(logger):
    root = Resource()
    root.putChild("form", FormPage())
    root.putChild("ping", Ping())
    
    factory = Site(root)
    port = reactor.listenTCP(bt_remote_ctrl_listen_port, factory)

    if True:    
        try:
            config = downloader_config
            multidl = MultiDL(config)

            root.putChild("puttask", PutTask(multidl))
            root.putChild("shutdowntask", ShutdownTask(multidl))
            root.putChild("maketorrent", MakeTorrent(multidl))
            multidl.listen_forever()
        except Exception, ex:
            logger.exception("MultiDL exit! Something unexpected happened!")
        else:
	    formatted_lines = traceback.format_exc()
            logger.error("MultiDL exit: %s ", formatted_lines)
        #restart_later = 3
        #logger.error("\n\nrestart MultiDL in %s seconds", restart_later)
        #time.sleep(restart_later)

    try:
         port.stopListening()
    except Exception as e:
        logger.exception("port.stopListening()") 
        try:
            port.connectionLost(reason=None)
        except Exception as e:
            logger.exception("port.connectionLost(reason=None)")
            try:
                port.lostConnection()
            except Exception as e:
                logger.exception("port.lostConnection()")

    try:
        reactor.stop()
    except Exception as e:
        logger.exception("reactor.stop() exception!")


if __name__ == '__main__':
    #redirect to twisted log to python stardard logger, for backCount
    #observer = log.PythonLoggingObserver(loggerName='web-bittorrent-console') 
    #observer.start()
    #log.startLogging(DailyLogFile.fromFullPath(logfile))
    logHandler = TimedRotatingFileHandler(filename=logfile, when='midnight', interval=1, backupCount=7)
    logFormatter = logging.Formatter('%(asctime)s %(message)s')
    logHandler.setFormatter( logFormatter )
    logger = logging.getLogger()
    logger.addHandler( logHandler )
    logger.setLevel( logging.INFO )

    total_restart_times = 0
    unsuccess_restart_times = 0
    while True:
        last_restart_time = time.time() 
        try:
            if total_restart_times == 0: 
                #first_start
                print "start web-bittorrent-console, listening port:%s forever" % bt_remote_ctrl_listen_port
                logger.info("start web-bittorrent-console, listening port:%s forever", bt_remote_ctrl_listen_port)

            #main will never exit unless something unexpected happen
            p = Process(target=main, args=(logger,))
            p.start()
            p.join()
        except Exception, ex:
            logger.exception("Something awful happened!")
        else:
            logger.error("main loop exit, this should never happen in normal case!!!")

        total_restart_times += 1
        if time.time() - last_restart_time < 60*5:
            #consider last restart unsuccess
            restart_later = min(60*30, 2**unsuccess_restart_times)
            unsuccess_restart_times += 1
            if unsuccess_restart_times > 1000:
                logger.error("I can NOT endure anymore! You win, I give up! Please help me!")
                break
        else:
            restart_later = 0
            unsuccess_restart_times = 0
            
        logger.error("\n\n\n\nrestart web-bittorrent-console in %s seconds later. listening port:%s forever. total_restart_times=%s, latest unsuccess_restart_times=%s", 
                      restart_later, bt_remote_ctrl_listen_port, total_restart_times, unsuccess_restart_times)
        time.sleep(restart_later)
        
