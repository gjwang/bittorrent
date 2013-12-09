wwwroot = '/home/video' #download file store topdir

http_prefix = "http://127.0.0.1:8100" #only the server that made torrent need

node_domain = 'http://127.0.0.1:8080' #for example, the nginx publish domain

maketorent_config = {'comment': '', 'filesystem_encoding': '', 'target': '', 'language': '', 'use_tracker': True, 'data_dir': '~/.bittorrent/data', 'piece_size_pow2': 18, 'tracker_list': '', 'tracker_name': 'http://223.82.137.218:8090/announce'}




#task template

#response template, should translate into json before response
NodeIP   = "127.0.0.1"
NodeZone = "beijing"               #the node belong the the area zone
NodeID   = NodeZone + "_" + NodeIP #every peer should define a unique NodeID

response_msg={"taskid"  : "",
              "nodeid"  : NodeID,
              "nodezone": NodeZone,    #the node belong the the area zone
              "nodeip"  : NodeIP,
              "event"   : "",
              #"expire"  : "",         #task expire time
              "state"   : "",
              "result"  : "",          #success, failed
              "trackback": "",         #failed cause
              "args"    : {            #return value, referrence to event
                           #"sha1":""
                           }
             }
