wwwroot = '/home/video' #download file store topdir

http_prefix = "http://127.0.0.1:8100" #only the server that made torrent need

node_domain = 'http://127.0.0.1:8080' #for example, the nginx publish domain

report_peer_status_url = 'http://127.0.0.1:8200/report_peerstatus'


maketorent_config = {'comment': '', 'filesystem_encoding': '', 'target': '', 'language': '', 'use_tracker': True, 'data_dir': '~/.bittorrent/data', 'piece_size_pow2': 18, 'tracker_list': '', 'tracker_name': 'http://223.82.137.218:8090/announce'}


#template, should translate into json before response
NodeIP   = "127.0.0.1"
NodeZone = "beijing"               #the node belong the the area zone
NodeID   = NodeZone + "_" + NodeIP #every peer should define a unique NodeID

#task template
task_template={"taskid"      : "",
               #"channel"    : "",     #the channel to publish this task
               #"nodeid"     : NodeID,
               #"nodezone"   : NodeZone,    #the node belong the the area zone
               #"nodeip"     : NodeIP,
               "event"       : "",
               "expire"      : "",          #task expire time
               "max_retries" : "",
               "args"        : {            #return value, referrence to event
                               #"sha1":""
                               }
              }



response_msg={"taskid"  : "",
              "nodeid"  : NodeID,
              "nodezone": NodeZone,    #the node belong the the area zone
              "nodeip"  : NodeIP,
              "event"   : "",
              "status"  : "",
              "result"  : "",          #success, failed
              "retries" : "0",
              "trackback": "",         #failed cause
              "args"    : {            #return value, referrence to event
                           #"sha1":""
                          }
             }
