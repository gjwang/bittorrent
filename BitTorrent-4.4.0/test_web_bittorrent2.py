import time
import urllib2
import httplib
import json
import copy
from conf import task_template, response_msg


def postToServer(posturl, data):
    if posturl is None:
        #self.__logger.error("posturl is null")
        print "posturl is null"
        return

    data = json.dumps(data, indent=4, sort_keys=True, separators=(',', ': '))

    print data
    print '\n'

    response_msg = None

    try:
        req = urllib2.Request(url=posturl, 
                              data=data, 
                              headers={'Content-Type': 'application/json'})
        ret = urllib2.urlopen(req)
        response_msg = ret.read()
        ret.close()
    except Exception as exc:
        #self.__logger.error("Exception: %s occured post xml to: %s", exc, self.posturl)
        print "Exception: %s occured while post json to: %s"%(exc, posturl)

    print response_msg
    return response_msg


def getToServer(url, data):
    conn = httplib.HTTPConnection("127.0.0.1", '8090')
    #conn = httplib.HTTPConnection(url)
    conn.request("GET", "/ping")
    r1 = conn.getresponse()
    #print r1.status, r1.reason
    data1 = r1.read()
    print data1
    conn.close()


def httppostToServer(url, data):
    conn = httplib.HTTPConnection("127.0.0.1", '8090')
    #conn = httplib.HTTPConnection(url)
    conn.request("POST", "/ping")
    r1 = conn.getresponse()
    #print r1.status, r1.reason
    data1 = r1.read()
    print data1
    conn.close()


if __name__ == '__main__':    
    maketorent_server = 'http://127.0.0.1:8090' #tianjin wwwroot='/data/data/ysten'
    #maketorent_server = 'http://127.0.0.1:8090'
    maketorrenturl = maketorent_server + '/maketorrent'  + '?user=admin&pwd=admin123456'
    peerurls = [
                #maketorent_server, 
                #'http://127.0.0.1:8100', #jiangxi wwwroot='/data/project/xmlfile'
                'http://127.0.0.1:8090', 
                #'http://127.0.0.1:8090', #xinjiang wwwroot='/data/ysten'
                #'http://127.0.0.1:8090', #xinjiang wwwroot='/data/ysten'
                #'http://127.0.0.1:8090', #shanxi_taiyuan wwwroot='/home/video'
               ]

    for url in peerurls:
        postdata = 'asdfasdf'
        pingurl = url + '/ping' + '?user=admin&pwd=admin123456'
        postToServer(pingurl, postdata)
    print '\n\n'
    

    #print "shutdown all downloads"
    for peerurl in peerurls:
        peerurl = peerurl + '/shutdowntask'  + '?user=admin&pwd=admin123456'
        task = copy.deepcopy(task_template)
        task['taskid'] = '13241324'
        task['event'] = "shutdownall"
        postToServer(peerurl, task)
    time.sleep(3)
    print '\n\n'


                             #"fileurl":"http://125.39.27.142/media/new/2013/icntv2/media/2013/12/11/0188a9f829cd4f9b81f92142991da481.ts"

    print "make torrent info"
    task = copy.deepcopy(task_template)
    task['taskid'] = '13241324'
    task['event'] = "maketorrent"
    task["args"] = {
                       "trackers":["http://127.0.0.1:8090/announce", "http://tracker2.com/announce"], 
                       "starttoseed":"",
                       "fileurl":"http://www.pathname.com/fhs/pub/fhs-2.3.pdf"
                   }

    #response = postToServer(maketorrenturl, task)
    metainfo = None
    try:
        metainfo = json.loads(response)        
        pass
    except Exception as e:
        print e
    
    if metainfo is None:
        metainfo = {
            "args": {
                "filename": "/data/data/ysten/media/new/2013/icntv2/media/2013/12/11/0188a9f829cd4f9b81f92142991da481.ts",
                "sha1": "ad1d2be923eecaa12e2c3066e3b89ca8572ea9e1",
                "torrentfile": "/data/data/ysten/media/new/2013/icntv2/media/2013/12/11/0188a9f829cd4f9b81f92142991da481.ts.torrent",
                "torrentfileurl": "http://125.39.95.58:80/media/new/2013/icntv2/media/2013/12/11/0188a9f829cd4f9b81f92142991da481.ts.torrent"
            },
            "event": "maketorrent_response",
            "nodeid": "tianjian_mkbtinfo_125.39.95.58",
            "nodeip": "125.39.95.58",
            "nodezone": "tianjian_mkbtinfo",
            "result": "success",
            "retries": "0",
            "status": "",
            "taskid": "",
            "trackback": ""
        }
    
    print '\n\n'

    print "tell peers to download"
    for peerurl in peerurls:
        peerurl = peerurl + '/puttask'  + '?user=admin&pwd=admin123456'
        task = copy.deepcopy(task_template)
        task['taskid'] = metainfo['args']['sha1']   
        task['event'] = "download"        
        task['args']['sha1'] =  metainfo['args']['sha1']   
        task['args']['torrentfileurl'] = metainfo['args']['torrentfileurl']   
        postToServer(peerurl, task)
        time.sleep(1)
    time.sleep(3)
    print '\n\n'


    #shutdown the special download by sha1 or torrentfileurl
    for peerurl in peerurls:
        peerurl = peerurl + '/shutdowntask' + '?user=admin&pwd=admin123456'
        task = copy.deepcopy(task_template)
        task['taskid'] = '13241324'
        task['event'] = "shutdown"
        #task['args']['sha1'] = 'ad1d2be923eecaa12e2c3066e3b89ca8572ea9e1'
        task['args']['torrentfileurl'] = 'http://125.39.95.58:80/media/new/2013/icntv2/media/2013/12/11/0188a9f829cd4f9b81f92142991da481.ts.torrent'

        postToServer(peerurl, task)
    time.sleep(1)
    print '\n\n'

