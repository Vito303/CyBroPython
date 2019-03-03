import threading
import cybrocomm
import sys, time, zlib
import config
import logger
import zipfile
import globals
import alloc
import sys_config


AccessReqReadAlloc      = 0x0001
AccessReqReadTags       = 0x0002
AccessReqWriteTags      = 0x0004
AccessReqPlcStatus      = 0x0008
AccessReqWritePushAck   = 0x0010

###########################################################################
#
#    CybroControllers manages list of controller threads

class CybroControllers:

    list = None

    #----------------------------------------------------------------------

    def __init__(self):
        self.clear()

    #----------------------------------------------------------------------

    def add(self, controller):
        self.list.append(controller)
        globals.system_log.info("c%d created." % controller.config.nad)

    #----------------------------------------------------------------------

    def create_from_config(self, config):

        if config.nad == 0:
            return None

        controller = self.get_by_nad(config.nad)
        if not controller:
            controller = CybroController(config)
            self.add(controller)
            controller.start()
        else:
            controller.set_config(config)

        return controller

    #----------------------------------------------------------------------

    def create_for_broadcast(self):
        cfg = config.CybroConfig()
        cfg.nad = 0

        controller = CybroController(cfg)
        # self.add(controller)
        controller.start()

        return controller

    #----------------------------------------------------------------------

    def create(self, nad, created_from_push):
        cfg = globals.config.read_for_controller(nad)
        if cfg == None:
            cfg = config.CybroConfig()
            cfg.nad = nad
        # cfg.created_from_push = True
        cfg.created_from_push = created_from_push		
        return self.create_from_config(cfg)

    #----------------------------------------------------------------------

    def clear(self):
        self.list = []

    #----------------------------------------------------------------------

    def terminate(self):
        for controller in self.list:
            controller.terminate()
        self.clear()

    #----------------------------------------------------------------------

    def get_by_nad(self, nad):
        for controller in self.list:
            if controller.config.nad == nad:
                return controller
        return None

    #----------------------------------------------------------------------

    def delete_by_nad(self, nad):
        for i in range(len(self.list)):
            controller = self.list[i]
            if controller.config.nad == nad:
                controller.terminate()
                self.list.pop(i)
                return

    #----------------------------------------------------------------------

    def reset_create_from_config_flag(self):
        for controller in self.list:
            controller.config.created_from_config_ini = False

    #----------------------------------------------------------------------

    def terminate_invalid(self):
        terminate_list = []

        for controller in self.list:
            if controller.config.assigned_for_termination:
                terminate_list.append(controller)

        for controller in terminate_list:
            if sys_config.DebugPrints:
                print "ASSIGNED FOR TERMINATION", controller.config.nad
            self.delete_by_nad(controller.config.nad)

    #----------------------------------------------------------------------

    def clean_timeout_push_list(self):
        import datetime
        now = datetime.datetime.now()
        # convert timeout from hours to seconds
        push_timeout = sys_config.PushTimeout * 60 * 60
        for controller in self.list:
            if not controller.config.always_running:
                try:
                    dt = now - datetime.datetime.fromtimestamp(controller.sys_status.last_push_timestamp)
                    if (dt.days * 86400.0 + dt.seconds) > push_timeout:
                        controller.config.assigned_for_termination = True
                        if sys_config.DebugPrints:
                            print "SET FOR TERMINATION", controller.config.nad
                except:
                    pass

    #----------------------------------------------------------------------

    def get_sorted(self):
        items = []
        for item in self.list:
            items.append(item)
        return sorted(items, key = lambda item: item.config.nad)

    #----------------------------------------------------------------------



###########################################################################
#
#    Base class for CyBro communication

class CybroSysStatus:

    last_push_ip = ""
    last_push_port = 0
    last_push_timestamp = 0
    bytes_transfered = 0
    last_response_time = "?"
    last_plc_status = None
    last_alc_file_status = False
    last_alc_file_check_timestamp = 0
    comm_error_count = 0

    func_hash = None
    controller = None

    #----------------------------------------------------------------------

    def __init__(self, controller):

        self.controller = controller

        self.func_hash = []
        self.func_hash.append({"value": zlib.crc32("timestamp"), "function": self.get_sys_timestamp, "description": "Program download timestamp."})
        self.func_hash.append({"value": zlib.crc32("ip_port"), "function": self.get_sys_ip_port, "description": "IP address and UDP port of the controller."})
        self.func_hash.append({"value": zlib.crc32("response_time"), "function": self.get_sys_response_time, "description": "Last communication cycle duration in milliseconds."})
        self.func_hash.append({"value": zlib.crc32("plc_program_status"), "function": self.get_sys_plc_program_status, "description": "Program status."})
        self.func_hash.append({"value": zlib.crc32("alc_file_status"), "function": self.get_sys_alc_file_status, "description": "Allocation file status."})
        self.func_hash.append({"value": zlib.crc32("plc_status"), "function": self.get_sys_plc_status, "description": "Controller status."})
        self.func_hash.append({"value": zlib.crc32("bytes_transfered"), "function": self.get_sys_bytes_transfered, "description": "Total number of bytes sent to and received from controller."})
        self.func_hash.append({"value": zlib.crc32("alc_file"), "function": self.get_sys_alc_file, "description": "Complete allocation file for the controller, in ASCII format."})
        self.func_hash.append({"value": zlib.crc32("comm_error_count"), "function": self.get_sys_comm_error_count, "description": "Total number of communication errors for controller."})

    #-------------------------------------------------------------------------

    def get_value(self, value):
        v = zlib.crc32(value)

        for f in self.func_hash:
            if f["value"] == v:
                return (f["function"](), f["description"])

        from sys_status import UnknownSysTag
        raise UnknownSysTag()

    #----------------------------------------------------------------------

    def get_sys_push_timestamp(self):
        return self.last_push_timestamp

    #----------------------------------------------------------------------

    def get_sys_timestamp(self):
        plc_head = self.controller.comm_proxy.last_plc_head
        return plc_head.timestamp if plc_head != None else "?"

    #----------------------------------------------------------------------

    def get_sys_ip_port(self):
        if len(self.controller.config.ip) != "":
            return "%s:%d" % (self.controller.config.ip, self.controller.config.port)
        else:
            return "?"

    #----------------------------------------------------------------------

    def get_sys_response_time(self):
        return self.last_response_time

    #----------------------------------------------------------------------

    def get_sys_plc_program_status(self):
        if not self.controller.online:
            return "-"

        plc_head = self.controller.comm_proxy.last_plc_head

        if plc_head != None:
            return "ok" if plc_head.empty == 0 else "missing"

        return "?"

    #----------------------------------------------------------------------

    def get_sys_alc_file_status(self):
        if not self.controller.online:
            return "-"

        return "ok" if self.last_alc_file_status else "missing"

    #----------------------------------------------------------------------

    def get_sys_plc_status(self):
        if not self.controller.online:
            return "offline"
        return self.last_plc_status.get_str() if self.last_plc_status != None else "?"

    #----------------------------------------------------------------------

    def get_sys_bytes_transfered(self):
        return self.bytes_transfered

    #----------------------------------------------------------------------

    def get_sys_alc_file(self):
        return self.controller.alloc.read_from_file()

    #----------------------------------------------------------------------

    def get_sys_comm_error_count(self):
        return self.comm_error_count

    #----------------------------------------------------------------------


###########################################################################
#
#    Base class for CyBro communication

class CybroController(threading.Thread):

    config = None
    alloc = None
    comm_proxy = None
    sys_status = None
    online = False

    terminating = False
    access_request = 0
    access_trigger = None

    #----------------------------------------------------------------------

    def __init__(self, config):

        self.sys_status = CybroSysStatus(self)
        self.comm_proxy = cybrocomm.CybroProxy(self, 1, config.nad)
        self.set_config(config)

        self.alloc = alloc.Allocation(config.nad)
        self.alloc.read()

        self.access_trigger = threading.Event()

        threading.Thread.__init__(self)
        self.daemon = True

        if sys_config.DebugPrints:
            print "CREATED", self.config.nad

    #----------------------------------------------------------------------

    def set_push_data(self, ip, port):
        import datetime
        self.sys_status.last_push_ip = ip
        self.sys_status.last_push_port = port
        self.sys_status.last_push_timestamp = datetime.datetime.now()
        self.online = True
        self.config.created_from_push = True
        self.config.assigned_for_termination = False
        self.config.ip = ip
        self.config.port = port

        self.comm_proxy.set_connection_parameters(ip, port)

    #----------------------------------------------------------------------

    def set_config(self, config):
        # preserve old ip and port, if available
        if self.config and self.config.ip != "":
            config.ip = self.config.ip
            config.port = self.config.port

        self.config = config

    #----------------------------------------------------------------------

    def get_ip_address(self):
        if self.config.ip != 0 and self.config.ip != "":
            return self.config.ip

        if sys_config.LocalAccess:
            return sys_config.BroadcastAddress

        return ""

    #----------------------------------------------------------------------

    def terminate(self):
        self.terminating = True
        # set event to terminate thread
        self.access_trigger.set()
        if sys_config.DebugPrints:
            print "TERMINATED", self.config.nad

    #----------------------------------------------------------------------

    def process_read_requests(self):
        # if last allocation read was not successful or allocation timeout occured
        if time.time() - self.sys_status.last_alc_file_check_timestamp > sys_config.AlcTimeout or \
            not self.sys_status.last_alc_file_status:
            self.perform_maintenance_read()

        self.access_request |= AccessReqReadTags
        self.access_trigger.set()

    #----------------------------------------------------------------------

    def process_write_requests(self):
        # if last allocation read was not successful or allocation timeout occured
        if time.time() - self.sys_status.last_alc_file_check_timestamp > sys_config.AlcTimeout or \
            not self.sys_status.last_alc_file_status:
            self.perform_maintenance_read()

        self.access_request |= AccessReqWriteTags
        self.access_trigger.set()

    #----------------------------------------------------------------------

    def set_read_allocation_request(self):
        self.access_request |= AccessReqReadAlloc
        self.access_trigger.set()

    #----------------------------------------------------------------------

    def set_write_push_ack_request(self):
        self.access_request |= AccessReqWritePushAck
        self.access_trigger.set()

    #----------------------------------------------------------------------

    def read_plc_status(self):
        self.access_request |= AccessReqPlcStatus
        self.access_trigger.set()

    #----------------------------------------------------------------------

    def perform_maintenance_read(self):
        self.set_read_allocation_request()
        self.read_plc_status()

    #----------------------------------------------------------------------

    def read_alloc_file_immediately(self):
        self.__read_allocation()

    #----------------------------------------------------------------------
    
    def __read_allocation(self):

        comm_ok = True
        try:
            self.comm_proxy.log.info("Checking allocation file...")
            (need_read, plc_transfer_time) = self.comm_proxy.check_if_alloc_file_is_needed()
            if need_read:
                self.comm_proxy.log.info("Downloading allocation file...")
                try:
                    self.comm_proxy.read_alloc_file(plc_transfer_time)
                    self.comm_proxy.log.info("Allocation file downloaded ok.")
                    self.sys_status.last_alc_file_status = True
                    self.sys_status.last_alc_file_check_timestamp = time.time()
                except cybrocomm.AllocFileNotFound:
                    self.sys_status.last_alc_file_status = False
                    self.comm_proxy.log.error("No allocation file found in controller.")
            else:
                self.sys_status.last_alc_file_status = True
                self.sys_status.last_alc_file_check_timestamp = time.time()
                self.comm_proxy.log.info("Allocation file is up-to-date.")
        except cybrocomm.CommError, err:
            self.sys_status.last_alc_file_status = False
            comm_ok = False
        except Exception, e:
            self.comm_proxy.log.error("(Exception) %s" % (e))

        return comm_ok

    #----------------------------------------------------------------------

    def __read_tags(self):

        # loop through all tags and check for read requests

        n = 0
        tags = []
        data_size = 0
        result = True

        while n < len(self.alloc.tags.list):
            tag = self.alloc.tags.list[n]

            if tag.read_request:
                req_frame_data_len = 6 + (len(tags) + 1) * 2
                resp_frame_data_len = data_size + tag.size

                if req_frame_data_len <= sys_config.MaxFrameDataBytes and resp_frame_data_len < sys_config.MaxFrameDataBytes:
                    tags.append(tag)
                    tag.read_request = False
                    data_size += tag.size
                else:
                    # do the request, clear buffers, append tag and loop further
                    result = self.comm_proxy.read_tag_values(tags)
                    globals.transaction_pool.on_values_received(self, tags, result)
                    tags = [tag]
                    tag.read_request = False
                    data_size = tag.size

            n += 1

        # do the request for remaining tags
        if len(tags) > 0:
            result = self.comm_proxy.read_tag_values(tags)
            globals.transaction_pool.on_values_received(self, tags, result)

        return result

    #----------------------------------------------------------------------

    def __write_tags(self):

        # loop through all tags and check for read requests

        n = 0
        tags = []
        values = []
        data_size = 0

        while n < len(self.alloc.tags.list):
            tag = self.alloc.tags.list[n]

            if tag.write_request:
                req_frame_data_len = 6 + (len(tags) + 1) * 2 + data_size + tag.size

                if req_frame_data_len <= sys_config.MaxFrameDataBytes:
                    tags.append(tag)
                    values.append(tag.value)
                    tag.write_request = False
                    data_size += tag.size
                else:
                    # do the request, clear buffers, append tag and loop further
                    self.comm_proxy.write_tag_values(tags, values)
                    globals.transaction_pool.on_values_written(self, tags)
                    tags = [tag]
                    values = [tag.value]
                    tag.read_request = False
                    data_size = tag.size

            n += 1

        # do the request for remaining tags
        if len(tags) > 0:
            self.comm_proxy.write_tag_values(tags, values)
            globals.transaction_pool.on_values_written(self, tags)

        return True

    #----------------------------------------------------------------------

    def run(self):
        if self.config.nad != 0:
            globals.system_log.info("c%d started." % self.config.nad)

        last_comm_ok = True

        while not self.terminating:
            self.access_trigger.wait()

            if not self.terminating:

                # check if valid ip address
                if self.get_ip_address() != "":
                    last_comm_ok = True


                    #------------------------------------------------------
                    # check for push ack write request

                    if self.access_request & AccessReqWritePushAck:
                        if last_comm_ok:
                            try:
                                self.comm_proxy.write_single_byte_abs_value(globals.config.push_ack_address, 1)
                            except Exception, e:
                                globals.sys_status.push_ack_errors += 1
                                last_comm_ok = False
                                if sys_config.DebugTcpServer:
                                    globals.tcp_log_server.error("(c%d) AccessReqWritePushAck: %s" % (self.config.nad, e))
                        self.access_request &= ~AccessReqWritePushAck


                    #------------------------------------------------------
                    # check for allocation read request

                    if self.access_request & AccessReqReadAlloc:
                        if last_comm_ok:
                            try:
                                last_comm_ok = self.__read_allocation()
                            except Exception, e:
                                last_comm_ok = False
                                if sys_config.DebugTcpServer:
                                    globals.tcp_log_server.error("(c%d) AccessReqReadAlloc: %s" % (self.config.nad, e))
                        self.access_request &= ~AccessReqReadAlloc


                    #------------------------------------------------------
                    # check for plc status

                    if self.access_request & AccessReqPlcStatus:
                        if last_comm_ok:
                            try:
                                self.sys_status.last_plc_status = self.comm_proxy.read_status()
                            except Exception, e:
                                self.sys_status.last_plc_status = None
                                last_comm_ok = False
                                if sys_config.DebugTcpServer:
                                    globals.tcp_log_server.error("(c%d) AccessReqPlcStatus: %s" % (self.config.nad, e))
                        self.access_request &= ~AccessReqPlcStatus


                    #------------------------------------------------------
                    # check for tag write request

                    if self.access_request & AccessReqWriteTags:
                        try:
                            if last_comm_ok and self.__read_allocation():
                                self.__write_tags()
                            else:
                                globals.transaction_pool.on_invalidate_all_tags(self)
                        except Exception, e:
                            if sys_config.DebugTcpServer:
                                globals.tcp_log_server.error("(c%d) AccessReqWriteTags: %s" % (self.config.nad, e))
                        self.access_request &= ~AccessReqWriteTags

                    #------------------------------------------------------
                    # check for tag read request

                    if self.access_request & AccessReqReadTags:
                        try:
                            if last_comm_ok:
                                last_comm_ok = self.__read_tags()
                            else:
                                globals.transaction_pool.on_invalidate_all_tags(self)
                        except Exception, e:
                            if sys_config.DebugTcpServer:
                                globals.tcp_log_server.error("(c%d) AccessReqReadTags: %s" % (self.config.nad, e))
                        self.access_request &= ~AccessReqReadTags

                else:
                    self.comm_proxy.log.info("Waiting for first push message.")
                    globals.transaction_pool.on_invalidate_all_tags(self)
                    self.access_trigger.clear()

                # reset trigger only if no requests exists
                if self.access_request == 0:
                    self.access_trigger.clear()

                self.online = last_comm_ok

        globals.system_log.info("c%d stopped." % self.config.nad)

    #----------------------------------------------------------------------
