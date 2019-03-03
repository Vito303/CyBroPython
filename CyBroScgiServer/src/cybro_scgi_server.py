#!/usr/bin/python

import sys, time
import sys_config
import logger
import globals
import sys_status
import const
import cybrocontrollers
import udp_proxy
import scgi_server
import transaction_pool


#*****************************************************************************

class CybroScgiServer:

    scgi_server = None

    #-------------------------------------------------------------------------

    def __init__(self):

        import config
        import tz_info

        globals.system_log = logger.create("service")
        globals.access_log = logger.create("access")

        globals.system_log.info("*** CybroScgiServer %s started ***" % const.ApplicationVersion)

        globals.tz_info = tz_info.TimezoneInfo()
        globals.sys_status = sys_status.SystemStatus()
        globals.controllers = cybrocontrollers.CybroControllers()
        globals.config = config.GlobalConfig()
        globals.transaction_pool = transaction_pool.TransactionPool()

        if sys_config.DebugRConsole:
            from rfoo.utils import rconsole
            rconsole.spawn_server()
            globals.system_log.warning("Debug rconsole server spawned.")

        if sys_config.DebugTcpServer:
            import tcp_logger_server
            globals.tcp_log_server = tcp_logger_server.create(sys_config.DebugTcpServerPort)

    #-------------------------------------------------------------------------

    def run(self):

        globals.udp_proxy = udp_proxy.UDPProxy()
        globals.udp_proxy.start()
        exit_code = 0

        try:
            self.scgi_server = scgi_server.SCGIServer()
            self.scgi_server.start()

            # query all controllers for allocation list and status uppon start
            for controller in globals.controllers.list:
                controller.perform_maintenance_read()

            last_controller_list_cleanup = time.time()

            if sys_config.DataLoggerEnable:
                import data_logger
                globals.data_logger = data_logger.DataLogger()
                globals.data_logger.start()

            if sys_config.DataDiggerEnable:
                import data_digger
                data_digger = data_digger.DataDigger()
                data_digger.start()

            if sys_config.RelayEnable:
                import relay
                globals.relay = relay.CybroRelay()
                globals.relay.start()

            try:
                while 1:
                    time.sleep(1)

                    # every 60s check for push list timeout and remove inactive controllers
                    if time.time() - last_controller_list_cleanup >= 60:
                        globals.controllers.clean_timeout_push_list()
                        globals.controllers.terminate_invalid()
                        last_controller_list_cleanup = time.time()
                        if sys_config.DebugPrints:
                            print "CLEANUP"

                    # shutdown SCGI server on global request
                    if globals.ServerShutdownRequest:
                        globals.system_log.info("CybroScgiServer remote shutdown requested.")
                        raise SystemExit

            except (KeyboardInterrupt, SystemExit):
                pass

            globals.terminating = True

            if globals.relay != None:
                globals.relay.terminate()

            if globals.data_logger != None:
                globals.data_logger.terminate()

            if sys_config.DataDiggerEnable:
                data_digger.terminate()

            self.scgi_server.terminate()
            time.sleep(0.5)

        except IOError:
            globals.system_log.error("Port %d already open. Cannot start SCGI server." % sys_config.ScgiServerPort)
            exit_code = 1


        globals.transaction_pool.terminate()
        globals.config.terminate()
        globals.controllers.terminate()
        globals.udp_proxy.terminate()
        time.sleep(1)

        globals.system_log.info("*** CybroScgiServer %s terminated ***" % const.ApplicationVersion)

        return exit_code

    #-------------------------------------------------------------------------


#*****************************************************************************


#-----------------------------------------------------------------------------

def print_hello_header():

    app_line = "CybroScgiServer v%s (c) 2010-2013 Cybrotech Ltd. All rights reserved." % (const.ApplicationVersion)

    print
    print app_line
    print "-" * len(app_line)

#-----------------------------------------------------------------------------

def print_help():

    print_hello_header()
    print "Usage: cybro_scgi_server [ -options ] [ start|stop|restart|status ]"
    print
    print "    Options:"
    print "      -bg       Starts server as background process, any console output is disabled."
    print "      -s        Silent. Any console output is disabled."
    print
    print "    Commands:"
    print "      start     Starts CybroScgiServer. This is the default command, if any omitted."
    print "      stop      Stops CybroScgiServer."
    print "      restart   Restarts CybroScgiServer."
    print "      status    Prints current status of CybroScgiServer server."

#-----------------------------------------------------------------------------

def is_server_running():
    return scgi_server.SCGIServerRequest().perform(["scgi_port_status"], 0.5) != None

#-----------------------------------------------------------------------------

def start_server_in_background(fname):
    import os
    if os.system(fname + " -s &") == 0:
        print "CybroScgiServer started."

#-----------------------------------------------------------------------------

def start_server(fname, print_hello, run_in_background):

    if not is_server_running():
        if run_in_background:
            start_server_in_background(fname)
        else:
            if print_hello:
                print_hello_header()
            CybroScgiServer().run()
    else:
        print "CybroScgiServer already running."

#-----------------------------------------------------------------------------

def stop_server():

    if is_server_running():
        scgi_server.SCGIServerRequest().perform(["sys.server_shutdown=1"], 0.5)

        t = time.time()
        timeout = False

        while True:
            time.sleep(0.5)

            if time.time() - t > 10:
                timeout = True
                break

            if not is_server_running():
                break

        if timeout:
            print "CybroScgiServer cannot be stopped."
            return False
        else:
            print "CybroScgiServer stopped."
    else:
        print "CybroScgiServer is not running."

    return True

#-----------------------------------------------------------------------------

def restart_server(fname):

    if stop_server():
        time.sleep(3)
        start_server_in_background(fname)

#-----------------------------------------------------------------------------

def print_status():

    print_hello_header()

    if is_server_running():

        def get_key_value(node, key):
            sub_node = node.getElementsByTagName(key)
            return sub_node[0].firstChild.data if len(sub_node) != 0 else ""

        def xml_to_txt(data):
            from xml.dom import minidom
            res = []
            try:
                xml = minidom.parseString(data)
                for var_node in xml.getElementsByTagName("var"):
                    name = get_key_value(var_node, "name")
                    value = get_key_value(var_node, "value")
                    if (value.find("\n") != -1):
                        res.append("%s:\n%s" % (name, value))
                    else:
                        res.append("%s: %s" % (name, value))
            except:
                raise
                pass
            return res

        print "CybroScgiServer is running.\n"

        var_list = [
            "sys.scgi_port_status", "sys.scgi_request_count", "sys.scgi_request_pending", "sys.server_version", "sys.server_uptime",
            "sys.cache_valid", "sys.cache_request", "sys.push_port_status", "sys.push_count", "sys.push_list_count", "sys.push_ack_errors",
            "sys.push_list", "sys.udp_rx_count", "sys.udp_tx_count", "sys.abus_list", "sys.datalogger_status", "sys.datalogger_list"
         ]
        data = scgi_server.SCGIServerRequest().perform(var_list)

        print "\n".join(xml_to_txt(data))
    else:
        print "CybroScgiServer is not running."

#-----------------------------------------------------------------------------

if __name__ == "__main__":

    cmd = "start"
    print_hello = True
    run_in_background = False

    for (n, arg) in enumerate(sys.argv):
        if n > 0:
            if arg == "-h" or arg == "--help" or arg == "-?":
                print_help()
                quit()
            elif arg == "-s":
                print_hello = False
                globals.enable_logged_console_output = False
            elif arg == "-bg":
                print_hello = False
                globals.enable_logged_console_output = False
                run_in_background = True
            elif arg in ["start", "stop", "restart", "status"]:
                cmd = arg
            else:
                print "Invalid argument '%s'." % (arg)
                quit()

    if cmd == "start":
        start_server(sys.argv[0], print_hello, run_in_background)
    elif cmd == "stop":
        stop_server()
    elif cmd == "restart":
        restart_server(sys.argv[0])
    elif cmd == "status":
        print_status()

#-----------------------------------------------------------------------------


#*****************************************************************************