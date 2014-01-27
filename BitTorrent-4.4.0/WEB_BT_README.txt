bt部署方法：
一， 安装python依赖库
      1， easy_install。
             如果机器原来没有安装easy_install的话，下载https://pypi.python.org/packages/source/s/setuptools/setuptools-2.0.1.tar.gz#md5=04aedc705644fda5848b7b428774e5ff 
             解压， 执行python setup.py install    安装
      2， pip
             如果没有安装过pip工具的话，执行easy_install pip 安装
      3， twisted
     以上1,2为python通用安装工具， twisted为bt依赖的库
           安装twisted: pip install twisted  或者 easy_install twisted
           通过这两个工具安装twisted， 正常情况下能自动解决其他依赖库，否则需要手动安装twisted依赖的其他库

二，系统设置
    为了安全建议将本软件运行在普通权限（非root）账号下。

    如果是普通账号运行本软件，需要对系统做以下修改：
    修改os最大打开文件数限制。
    修改方式：
    打开 /etc/security/limits.conf 
    添加以下两行（将nofile限制修改到10万以上）
    *                soft    nofile          102400                                                                                                      
    *                hard    nofile          102400 


二，BT软件配置
       打开bt软件下的conf.py  文件， 需要配置的有：
      bt_user = 'bt_ysten'                          #本节点用户名（未启用），
      bt_password = 'bt_ysten123456'     #本节点密码（未启用），节点用户名和密码用CDN管理系统对节点的访问控制，除非https, 否则不能提供‘真正的' 安全访问
 
      NodeIP   = "127.0.0.1"                     #本节点IP地址， [可选]
      NodeZone = "beijing"                    #the node belong the the area zone， 节点地区, [必选]
      NodeID   = NodeZone + "_" + NodeIP #every peer should define a unique NodeID， 节点ID[必选]， 节点ID可任意命名， 保证唯一性即可。 默认是'NodeZone _NodeIP'形式
  
      bt_remote_ctrl_listen_port = 8090  #本节点用于CDN管理系统控制的端口， [必选]
   
      wwwroot = '/home/video' #download file store topdir                                           #下载文件默认存放根目录[必选]，
      node_domain = 'http://127.0.0.1:8080' #for example, the nginx publish domain  #资源发布域名，[天津制作种子的服务器必选]， 其他节点使下载种子通过的域名。
      http_prefix = node_domain             #only the server that made torrent need
 
      report_peer_status_url = 'http://127.0.0.1:8200/cdnmanager/report_peerstatus'    #节点上报下载状态接口，[必选，由陈赟提供]
 
三, 启动方式
     1，tracker,  usage: start | stop | restart 
          ./bttracker start
     2,  bt downloader,  usage: start | stop | restart 
          ./web_bt.sh  start

