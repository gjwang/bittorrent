import time
import urllib2
import httplib

postdata= '''{"hello":"world, you"}'''


def postToServer(posturl, data):
    if posturl is None:
        #self.__logger.error("posturl is null")
        print "posturl is null"
        return

    try:
        req = urllib2.Request(url=posturl, 
                              data=data, 
                              headers={'Content-Type': 'application/json'})
        ret = urllib2.urlopen(req)
        print ret.read()
        ret.close()
    except Exception as exc:
        #self.__logger.error("Exception: %s occured post xml to: %s", exc, self.posturl)
        print "Exception: %s occured while post json to: %s"%(exc, posturl)


def getToServer(url, data):
    conn = httplib.HTTPConnection("127.0.0.1", '8090')
    conn.request("GET", "/ping")
    r1 = conn.getresponse()
    #print r1.status, r1.reason
    data1 = r1.read()
    print data1
    conn.close()


def httppostToServer(url, data):
    conn = httplib.HTTPConnection("127.0.0.1", '8090')
    conn.request("POST", "/ping")
    r1 = conn.getresponse()
    #print r1.status, r1.reason
    data1 = r1.read()
    print data1
    conn.close()


if __name__ == '__main__':
    puttaskurl = 'http://127.0.0.1:8090/puttask'

    #taskdata= '''{"taskid":"1341234jljdafl", "event":"download", "sha1":"fajpqeru", 
    #              "torrentfileurl":"http://www.example.com/a.xml"}'''
    #postToServer(puttaskurl, taskdata)

    #shutdown all downloads
    shutdowntaskurl = 'http://127.0.0.1:8090/shutdowntask'
    taskdata= '''{"taskid":"1341234jljdafl", "event":"shutdownall", "sha1":"fajpqeru", 
                  "torrentfileurl":""}'''
    postToServer(shutdowntaskurl, taskdata)
    time.sleep(1)


    maketorrenturl = 'http://127.0.0.1:8090/maketorrent'
    taskdata= '''{"taskid":"1341234jljdafl", 
                  "event":"maketorrent", 
                  "trackers":["http://223.82.137.218:8090/announce", "http://tracker2.com/announce"], 
                  "starttoseed":"",
                  "fileurl":"http://223.82.137.218:8088/a.xml"}'''
    postToServer(maketorrenturl, taskdata)

    #taskdata= '''{"taskid":"1341234jljdafl", "event":"download", "sha1":"fajpqeru", 
    #              "torrentfileurl":"http://223.82.137.218:8088/a.xml"}'''
    #postToServer(puttaskurl, taskdata)


    taskdata= '''{"taskid":"1341234jljdafl", "event":"download", "sha1":"fajpqeru", 
                  "torrentfileurl":"http://223.82.137.218:8088/01254aa4909c4596b41b547e9fa83378.ts.torrent"}'''
    postToServer(puttaskurl, taskdata)
    time.sleep(5)

    #shutdown the special download by torrentfileurl
    shutdowntaskurl = 'http://127.0.0.1:8090/shutdowntask'
    taskdata= '''{"taskid":"1341234jljdafl", "event":"shutdown", "sha1":"fajpqeru", 
                  "torrentfileurl":"http://223.82.137.218:8088/01254aa4909c4596b41b547e9fa83378.ts.torrent"}'''
    postToServer(shutdowntaskurl, taskdata)
    #time.sleep(5)

    #taskdata= '''{"taskid":"1341234jljdafl", "event":"download", "sha1":"fajpqeru", 
    #              "torrentfileurl":"http://223.82.137.218:8088/01254aa4909c4596b41b547e9fa83378.ts.torrent"}'''
    #postToServer(puttaskurl, taskdata)
    #time.sleep(5)


    shutdowntaskurl = 'http://127.0.0.1:8090/shutdowntask'
    taskdata= '''{"taskid":"1341234jljdafl", "event":"shutdown", "sha1":"fajpqeru", 
                  "torrentfileurl":""}'''
    postToServer(shutdowntaskurl, taskdata)
    time.sleep(5)


    #taskdata= '''{"taskid":"1341234jljdafl", "event":"download", "sha1":"fajpqeru", 
    #              "torrentfileurl":"http://223.82.137.218:8088/01254aa4909c4596b41b547e9fa83378.ts.torrent"}'''
    #postToServer(puttaskurl, taskdata)
    #time.sleep(5)


    pingurl = 'http://127.0.0.1:8090/ping'
    postToServer(pingurl, postdata)
    getToServer(pingurl, postdata)
    httppostToServer(pingurl, postdata)
