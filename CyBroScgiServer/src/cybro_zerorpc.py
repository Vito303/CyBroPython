import zerorpc

import globals
import sys_status
import cybrocontrollers
import logger
import config
import tz_info
import udp_proxy
import time

c = zerorpc.Client()
c.connect("tcp://127.0.0.1:4242")
print c.PushRequest("UDP_push_activated")

globals.system_log = logger.create("service")

globals.tz_info = tz_info.TimezoneInfo()
globals.sys_status = sys_status.SystemStatus()
globals.controllers = cybrocontrollers.CybroControllers()
globals.config = config.GlobalConfig()

udpThread = udp_proxy.UDPProxy()
udpThread.start()

#print('The result is')
try:
    while 1:
        #time.sleep(0.015)
        time.sleep(1)
        # every 15ms check for push list timeout and remove inactive controllers

        print c.ServerShutdownRequest()
        # shutdown SCGI server on global request
        #if c.ServerShutdownRequest():
        #    globals.system_log.info("CybroScgiServer remote shutdown requested.")
        #    raise SystemExit

except Exception, e:
    print "An error occurred: %s" % e


