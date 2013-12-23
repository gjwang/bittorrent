#!/bin/sh

### BEGIN INIT INFO
# Provides:          gjwang
# Required-Start:    $local_fs $remote_fs $network $syslog $named
# Required-Stop:     $local_fs $remote_fs $network $syslog $named
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: start/stop/restart the bt tracker server
# Description:       starts bt tracker server using start-stop-daemon
### END INIT INFO


startup()
{
    python bittorrent-tracker.py --port 8090 --dfile downloaders.log --reannounce_interval 60 &
}

shutdown()
{
	ps -ef|grep "bittorrent-tracker.py"|grep -v grep|awk '{print $2}'|xargs kill
}

case "$1" in
        start)
                startup
                ;;
        stop)
                shutdown
                ;;
        restart)
                shutdown
                startup
                ;;

        *)
                echo "usage: start | stop | restart"
                exit 1
                ;;
esac
exit
