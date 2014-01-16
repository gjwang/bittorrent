bt_user = 'admin'
bt_password = 'admin123456'

NodeIP   = "127.0.0.1"
NodeZone = "beijing"               #the node belong the the area zone
NodeID   = NodeZone + "_" + NodeIP #every peer should define a unique NodeID
AM_I_MK_METAINFO_SERVER = False     #True or False

bt_remote_ctrl_listen_port = 8090

wwwroot = '/home/video' #download file store topdir
node_domain = 'http://127.0.0.1:8080' #for example, the nginx publish domain
http_prefix = node_domain             #only the server that made torrent need

report_peer_status_url = 'http://127.0.0.1:8200/report_peerstatus'

logfile = 'log/web-bittorrent-console.log'
persistent_tasks_file = 'tasks.pkl'
task_expire_time = 48*3600   #48hours

#template, should translate into json before response
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
              "traceback": "",         #failed cause
              "args"    : {            #return value, referrence to event
                           #"sha1":""
                          }
             }

import os
import os
data_dir = os.path.expanduser('~/.bittorrent/data')
try:
    if not os.path.exists(os.path.join(data_dir, 'resume')):
        os.makedirs(os.path.join(data_dir, 'resume'))
except Exception, exc:
    print str(exc)

maketorent_config = {'comment': '', 
                     'filesystem_encoding': '',
                     'target': '', 
                     'language': '', 
                     'use_tracker': True, 
                     'data_dir': data_dir, 
                     'piece_size_pow2': 18, 
                     'tracker_list': '', 
                     'tracker_name': 'http://127.0.0.1:8090/announce'
                    }

downloader_config = {'one_connection_per_ip': True, 
                     'max_slice_length': 16384, 

                     'save_in': '', 
                     'save_as': '', 
                     'data_dir': data_dir, 

                     'minport': 6881, 
                     'maxport': 6999, 

                     'max_uploads': -1, 
                     'min_uploads': 2, 
                     'max_upload_rate': 0, 

                     'twisted': -1, 

                     'url': '', 

                     'display_interval': 30, 
                     'max_announce_retry_interval': 30, 

                     'start_trackerless_client': False, 

                     'rarest_first_cutoff': 10, 
                     'bad_libc_workaround': False, 
                     'ip': '', 
                     'download_slice_size': 16384, 
                     'max_files_open': 50, 
                     'close_with_rst': 0,                      
                     'filesystem_encoding': '', 
                     'rerequest_interval': 300, 
                     'upnp': True, 
                     'peer_socket_tos': 8, 
                     'spew': False, 
                     'socket_timeout': 300.0, 
                     'forwarded_port': 0, 
                     'timeout_check_interval': 60.0, 
                     'max_initiate': 60, 
                     'max_rate_period_seedtime': 100.0, 
                     'max_message_length': 8388608, 
                     'tracker_proxy': '', 
                     'check_hashes': True, 
                     'min_peers': 20, 
                     'ask_for_save': 0, 
                     'snub_time': 30.0, 
                     'retaliate_to_garbled_data': True, 
                     'keepalive_interval': 120.0,                      
                     'language': '', 
                     'bind': '', 
                     'max_rate_period': 20.0, 
                     'max_incomplete': 100, 
                     'responsefile': '', 
                     'upload_unit_size': 1380, 
                     'max_allow_in': 80,
                    }



