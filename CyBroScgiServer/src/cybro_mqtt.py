import paho.mqtt.client as mqtt

import globals
import sys_status
import cybrocontrollers
import logger
import config
import tz_info
import udp_proxy

broker_url = "10.1.1.178"
broker_port = 1883

def on_connect(client, userdata, flags, rc):
   print("Connected With Result Code " (rc))

def on_message(client, userdata, message):
   print("message received ", str(message.payload.decode("utf-8")))
   print("message topic=", message.topic)
   print("message qos=", message.qos)
   print("message retain flag=", message.retain)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect(broker_url, broker_port)

client.subscribe("Cybro/output", qos=1)

#client.publish(topic="TestingTopic", payload="TestingPayload", qos=1, retain=False)
globals.system_log = logger.create("service")

globals.tz_info = tz_info.TimezoneInfo()
globals.sys_status = sys_status.SystemStatus()
globals.controllers = cybrocontrollers.CybroControllers()
globals.config = config.GlobalConfig()


udpThread = udp_proxy.UDPProxy()
udpThread.start()

client.loop_forever()