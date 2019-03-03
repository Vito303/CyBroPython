import datetime
import zlib
import globals
import sys_config
import threading



###########################################################################
#
#    Exceptions


class UnknownSysTag(Exception):
    pass


###########################################################################
#
#    SystemStatus handles internal sys tags


class SystemStatus:

    server_start_time = 0
    scgi_request_count = 0
    scgi_request_pending = -1
    udp_rx_count = 0
    udp_tx_count = 0
    push_count = 0
    push_ack_errors = 0

    func_hash = None
    scgi_request_pending_lock = None

    #-------------------------------------------------------------------------

    def __init__(self):
        self.func_hash = []
        self.server_start_time = datetime.datetime.now()

        self.func_hash.append({"tag_name": zlib.crc32("scgi_port_status"), "getter": self.get_scgi_port_status, "description": "SCGI port status can be 'active' or empty (server is down)."})
        self.func_hash.append({"tag_name": zlib.crc32("scgi_request_count"), "getter": self.get_scgi_request_count, "description": "Total number of executed requests since startup."})
        self.func_hash.append({"tag_name": zlib.crc32("scgi_request_pending"), "getter": self.get_scgi_request_pending, "description": "Number of requests pending to be processed."})
        self.func_hash.append({"tag_name": zlib.crc32("server_version"), "getter": self.get_server_version, "description": "Server version, 'major.minor.release'."})
        self.func_hash.append({"tag_name": zlib.crc32("server_uptime"), "getter": self.get_server_uptime, "description": "Time since the server is started, 'hh:mm:ss' or 'xx days, hh:mm:ss'."})
        self.func_hash.append({"tag_name": zlib.crc32("cache_valid"), "getter": self.get_cache_valid, "description": "Time in seconds after cached value is invalidated. If value is -1, cache is disabled."})
        self.func_hash.append({"tag_name": zlib.crc32("cache_request"), "getter": self.get_cache_request, "description": "Time in seconds after data is read from cache, but communication request is initiated. If value is 0, no requests are generated until cache expires."})
        self.func_hash.append({"tag_name": zlib.crc32("push_port_status"), "getter": self.get_push_port_status, "description": "Push port status can be 'active' (PushEnable=True), 'inactive' (PushEnable=False) or 'error' (port used by another application)."})
        self.func_hash.append({"tag_name": zlib.crc32("push_count"), "getter": self.get_push_count, "description": "Total number of push messages received from controllers."})
        self.func_hash.append({"tag_name": zlib.crc32("push_list_count"), "getter": self.get_push_list_count, "description": "Total number of controllers in push list."})
        self.func_hash.append({"tag_name": zlib.crc32("push_ack_errors"), "getter": self.get_push_ack_errors, "description": "Total number of push acknowledge errors."})
        self.func_hash.append({"tag_name": zlib.crc32("nad_list"), "getter": self.get_nad_list, "description": "List of available controllers, push and autodetect list combined."})
        self.func_hash.append(
            {
                "tag_name": zlib.crc32("push_list"),
                "getter": self.get_push_list,
                "description": "Push list represents the list of Cybro controllers that sent push message to the server, containing last message timestamp, " \
                    "controller NAD, IP address and port, controller status, program status, allocation status, last program timestamp and response time in milliseconds."
            }
        )
        self.func_hash.append({"tag_name": zlib.crc32("udp_rx_count"), "getter": self.get_udp_rx_count, "description": "Total number of UDP packets received through UDP proxy."})
        self.func_hash.append({"tag_name": zlib.crc32("udp_tx_count"), "getter": self.get_udp_tx_count, "description": "Total number of UDP packets transmitted through UDP proxy."})
        self.func_hash.append(
            {
                "tag_name": zlib.crc32("abus_list"),
                "getter": self.get_abus_list,
                "description": "Abus list contains detailed information for low level communication between SCGI server and Cybro controllers. It is shown NAD, total number of abus messages, " \
                    "number of abus errors, last error timestamp, last error code and bandwidth used for each controller. Bandwidth represents the amount of time spent for " \
                    "communication in last 60 seconds for particular controller."
            }
        )
        self.func_hash.append({"tag_name": zlib.crc32("datalogger_status"), "getter": self.get_datalogger_status, "description": "Datalogger module can be 'active' or 'stopped'."})
        self.func_hash.append(
            {
                "tag_name": zlib.crc32("datalogger_list"),
                "getter": self.get_datalogger_list,
                "description": "Datalogger list contains detailed data for datalogger sample, alarm and event tasks - type of task, number of tags for this type of task, " \
                    "number of tasks for this type, number of tasks triggering, last trigger timestamp, number of correctly read tags, number of unknown tags or " \
                    "for some other reason not read tags, last communication status and complete task execution time."
            }
        )
        self.func_hash.append({"tag_name": zlib.crc32("server_shutdown"), "getter": self.get_server_shutdown, "setter": self.set_server_shutdown, "description": "Temporary shut down SCGI server."})

        self.scgi_request_pending_lock = threading.Lock()

    #-------------------------------------------------------------------------

    def get_value(self, tag_name):
        v = zlib.crc32(tag_name)

        for f in self.func_hash:
            if f["tag_name"] == v:
                return (f["getter"](), f["description"])

        raise UnknownSysTag()

    #-------------------------------------------------------------------------

    def set_value(self, tag_name, value):
        v = zlib.crc32(tag_name)

        for f in self.func_hash:
            if f["tag_name"] == v:
                return f["setter"](value)

        raise UnknownSysTag()

    #-------------------------------------------------------------------------
    def get_list_separator_line(self):
        return "-" * 103 + "\r\n"

    #-------------------------------------------------------------------------

    def get_scgi_port_status(self):
        return "active"

    #-------------------------------------------------------------------------

    def get_scgi_request_count(self):
        return self.scgi_request_count

    #-------------------------------------------------------------------------

    def get_scgi_request_pending(self):
        return self.scgi_request_pending

    #-------------------------------------------------------------------------

    def get_server_version(self):
        import const
        return const.ApplicationVersion

    #-------------------------------------------------------------------------

    def get_server_uptime(self):

        delta = datetime.datetime.now() - self.server_start_time
        minutes, seconds = divmod(delta.seconds, 60)
        hours, minutes = divmod(minutes, 60)
        time = "%d:%02d:%02d" % (hours, minutes, seconds)

        if delta.days > 0:
            if delta.days == 1:
                day_str = "day"
            else:
                day_str = "days"
            return "%d %s, %s" % (delta.days, day_str, time)
        else:
            return time

    #-------------------------------------------------------------------------

    def get_cache_valid(self):
        return sys_config.CacheValid

    #-------------------------------------------------------------------------

    def get_cache_request(self):
        return sys_config.CacheRequest

    #-------------------------------------------------------------------------

    def get_push_port_status(self):
        return "active" if sys_config.PushEnable else "inactive"

    #-------------------------------------------------------------------------

    def get_push_list_count(self):

        n = 0
        for controller in globals.controllers.list:
            if controller.config.created_from_push != 0:
                n += 1

        return n

    #-------------------------------------------------------------------------

    def get_push_ack_errors(self):
        return self.push_ack_errors

    #-------------------------------------------------------------------------

    def get_push_count(self):
        return self.push_count

    #-------------------------------------------------------------------------

    def get_nad_list(self):
        if sys_config.LocalAccess:
            globals.controllersForNadList=[]
            globals.system_log.info("SCGIServer broadcast to all controllers in LAN.")
            globals.broadcastController = globals.controllers.create_for_broadcast()
            globals.broadcastController.comm_proxy.ping()
        
        res = []
        for controller in globals.controllers.get_sorted():
            if not controller.config.nad in globals.controllersForNadList:
                res.append("<item>%d</item>" % controller.config.nad)
        for nad in globals.controllersForNadList:
            res.append("<item>%d</item>" % nad)
        globals.controllersForNadList=None
        return "".join(res)

    #-------------------------------------------------------------------------

    def get_push_list(self):
        import const
        from util import format_datetime

        sep = self.get_list_separator_line()
        res = "push message         nad    ip address:port       status  program alc     program downloaded   response\r\n"
        res += sep

        for controller in globals.controllers.get_sorted():
            if controller.config.created_from_push:
                file_transfer_timestamp = controller.alloc.get_file_transfer_timestamp()
                if file_transfer_timestamp != None:
                    file_transfer_timestamp = file_transfer_timestamp.strftime(const.Timeformat)
                else:
                    file_transfer_timestamp = "unknown            "

                try:
                    response_time = "%d" % controller.sys_status.get_sys_response_time()
                except:
                    response_time = controller.sys_status.get_sys_response_time()

                res += "%s  %s  %s%s %s %s %s  %s\r\n" % \
                (
                    format_datetime(controller.sys_status.last_push_timestamp),
                    repr(controller.config.nad).ljust(5),
                    ("%s:%s" % (controller.config.ip, repr(controller.config.port))).ljust(22),
                    controller.sys_status.get_sys_plc_status().ljust(7),
                    controller.sys_status.get_sys_plc_program_status().ljust(7),
                    controller.sys_status.get_sys_alc_file_status().ljust(7),
                    file_transfer_timestamp,
                    response_time.ljust(8),
                )

        return res + sep

    #-------------------------------------------------------------------------

    def get_udp_rx_count(self):
        return self.udp_rx_count

    #-------------------------------------------------------------------------

    def get_udp_tx_count(self):
        return self.udp_tx_count

    #-------------------------------------------------------------------------

    def get_abus_list(self):
        from util import format_datetime

        sep = self.get_list_separator_line()
        res = "nad    abus total  abus error  last error at        code   bandwidth\r\n"
        res += sep

        for controller in globals.controllers.get_sorted():
            if controller.comm_proxy.last_error_timestamp != None:
                last_error_timestamp = format_datetime(controller.comm_proxy.last_error_timestamp)
            else:
                last_error_timestamp = "-"

            res += "%s  %s  %s  %s  %s  %.2f%%\r\n" % \
            (
                repr(controller.config.nad).ljust(5),
                repr(controller.comm_proxy.abus_messages_tx_count).ljust(10),
                repr(controller.comm_proxy.abus_error_count).ljust(10),
                last_error_timestamp.ljust(19),
                controller.comm_proxy.last_error_code.ljust(5),
                controller.comm_proxy.get_bandwidth(),
            )

        return res + sep

    #-------------------------------------------------------------------------
    def get_datalogger_status(self):
        return "active" if globals.data_logger != None else "stopped"

    #-------------------------------------------------------------------------

    def get_datalogger_list(self):
        import const
        types = ["sample", "alarm", "event"]

        sep = self.get_list_separator_line()
        res = "type    tags   tasks  trigger count  last request at      tags ok  tags err  status  duration\r\n"
        res += sep

        if globals.data_logger != None:
            for type, type_str in enumerate(types):
                last_request_timestamp = globals.data_logger.get_last_request_timestamp(type)
                last_request_timestamp = last_request_timestamp.strftime(const.Timeformat) if last_request_timestamp != None else "-"

                res += "%s  %s  %s  %s  %s  %s  %s  %s  %dms\r\n" % \
                (
                    type_str.ljust(6),
                    repr(globals.data_logger.get_tag_count(type)).ljust(5),
                    repr(globals.data_logger.get_task_count(type)).ljust(5),
                    repr(globals.data_logger.get_trigger_count(type)).ljust(13),
                    last_request_timestamp.ljust(19),
                    repr(globals.data_logger.get_tags_ok(type)).ljust(7),
                    repr(globals.data_logger.get_tags_err(type)).ljust(8),
                    globals.data_logger.get_status(type).ljust(6),
                    globals.data_logger.get_duration(type),
                )

        return res + sep

    #-------------------------------------------------------------------------

    def scgi_request_begin(self):
        self.scgi_request_pending_lock.acquire()
        self.scgi_request_pending += 1
        self.scgi_request_pending_lock.release()

    #-------------------------------------------------------------------------

    def scgi_request_end(self):
        self.scgi_request_pending_lock.acquire()
        self.scgi_request_pending -= 1
        self.scgi_request_pending_lock.release()

    #-------------------------------------------------------------------------

    def get_server_shutdown(self):
        return

    #-------------------------------------------------------------------------

    def set_server_shutdown(self, value):
        globals.ServerShutdownRequest = True

    #-------------------------------------------------------------------------