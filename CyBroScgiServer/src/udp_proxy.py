import socket
import cybrocontrollers
import threading
import logger
import cybrocomm
import sys_config
import globals
import binascii
import struct


###########################################################################
#
#    UDPProxy thread

class UDPProxy(threading.Thread):

    terminating = False
    sock = None
    cybrobase = None
    comm_debug_log = None
    last_transaction_id = 0
    transaction_id_lock = None

    push_count = 0

    RECEIVE_BLOCKING_TIMEOUT = 500 # [ms]

    #----------------------------------------------------------------------

    def __init__(self):
        self.cybrobase = cybrocomm.CybroBase()

        self.transaction_id_lock = threading.Lock()

        if sys_config.DebugComm:
            self.comm_debug_log = logger.create("comm")

        self.connect()
        threading.Thread.__init__(self)

        self.daemon = True

    #----------------------------------------------------------------------

    def __delete__(self):
        self.disconnect()

    #----------------------------------------------------------------------

    def get_next_transaction_id(self):
        self.transaction_id_lock.acquire()
        self.last_transaction_id += 1
        res = self.last_transaction_id & 0xFFFF
        self.transaction_id_lock.release()
        return res

    #----------------------------------------------------------------------

    def set_push_port(self, value):
        self.disconnect()

    #----------------------------------------------------------------------

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.sock.settimeout(self.RECEIVE_BLOCKING_TIMEOUT / 1000.0)
        self.sock.bind((sys_config.InterfaceBindAddress, sys_config.PushPort))

    #----------------------------------------------------------------------

    def disconnect(self):
        if self.sock != None:
            self.sock.close()

    #----------------------------------------------------------------------

    def terminate(self):
        self.terminating = True

    #----------------------------------------------------------------------

    def running(self):
        return not self.terminating

    #----------------------------------------------------------------------

    def send(self, nad, data):
        controller = globals.controllers.get_by_nad(nad)
        if nad == 0:
            controller = globals.broadcastController;
        if controller:
            ip_address = controller.get_ip_address()
            if ip_address != "":
                try:
                    if sys_config.DebugComm:
                        self.comm_debug_log.info("    TX [%d] %s:%d %s" % (nad, ip_address, controller.config.port, binascii.b2a_hex(data)))
                    if sys_config.DebugTcpServer:
                        globals.tcp_log_server.debug("    TX [%d] %s:%d %s" % (nad, ip_address, controller.config.port, binascii.b2a_hex(data)))

                    self.sock.sendto(data, (ip_address, controller.config.port))
                    globals.sys_status.udp_tx_count += 1
                except Exception, e:
                    globals.system_log.error("(UDPProxy::send(nad:%d) Exception) %s" % (nad, e))
                    if sys_config.DebugTcpServer:
                        globals.tcp_log_server.error("(UDPProxy::send(nad:%d) Exception) %s" % (nad, e))

    #----------------------------------------------------------------------

    def send_raw_data(self, ip_address, port, data):
        print "SEND send_raw_data..."
		
        if sys_config.DebugComm or sys_config.DebugTcpServer:
            from_nad, to_nad = struct.unpack("<LL", data[4 : 12])
            if sys_config.DebugComm:
                self.comm_debug_log.info("    TXraw [%d -> %d] %s:%d %s" % (from_nad, to_nad, ip_address, port, binascii.b2a_hex(data)))
            if sys_config.DebugTcpServer:
                globals.tcp_log_server.debug("    TXraw [%d -> %d] %s:%d %s" % (from_nad, to_nad, ip_address, port, binascii.b2a_hex(data)))

        try:
            self.sock.sendto(data, (ip_address, port))
            globals.sys_status.udp_tx_count += 1
        except Exception, e:
            globals.system_log.error("(UDPProxy::send(nad:%d) Exception) %s" % (nad, e))
            if sys_config.DebugTcpServer:
                globals.tcp_log_server.error("(UDPProxy::send_raw_data(nad:%d) Exception) %s" % (nad, e))

    #----------------------------------------------------------------------

    def route_received_data(self, data, address):

        ip = address[0]
        port = address[1]

        # globals.sys_status.udp_rx_count += 1

        try:
            # check_received_frame will raise exception if received frame is invalid
            self.cybrobase.check_received_frame(data)

            try:
                frame = cybrocomm.CommFrame(data)
            except:
                return
            
            if frame.type == 0:
                globals.sys_status.udp_rx_count += 1

            if sys_config.RelayEnable and globals.relay != None and globals.relay.process_relay_message(ip, port, data, frame.from_nad, frame.to_nad):
                # it's relay message. processed - leave routing
                return
				
            controller = globals.controllers.get_by_nad(frame.from_nad)
            
            if sys_config.DebugComm:
                self.comm_debug_log.info("    RX [%d] %s:%d %s" % (frame.from_nad, ip, port, binascii.b2a_hex(data)))
            if sys_config.DebugTcpServer:
                globals.tcp_log_server.debug("    RX [%d] %s:%d %s" % (frame.from_nad, ip, port, binascii.b2a_hex(data)))
            
            is_push_message = self.cybrobase.is_push_message(frame)
            is_broadcast_message = self.cybrobase.is_broadcast_message(frame)

            if controller == None and frame.from_nad != 1 and (is_push_message or is_broadcast_message == False):
                if is_push_message:
                    controller = globals.controllers.create(frame.from_nad, is_push_message)
                elif frame.to_nad == 1:
                    controller = globals.broadcastController
                    globals.controllersForNadList.append(frame.from_nad)

            if controller != None:
                if is_push_message:				
                    if not sys_config.PushEnable:
                        return
                    
                    globals.sys_status.push_count += 1
                    cybro_log = logger.create("c%d" % frame.from_nad)
                    cybro_log.info("c%d push from %s:%d." % (frame.from_nad, ip, port))

                    if sys_config.DebugTcpServer:
                        globals.tcp_log_server.info("c%d push from %s:%d." % (frame.from_nad, ip, port))

                    controller.set_push_data(ip, int(port))
                    controller.set_write_push_ack_request()

                    if sys_config.ReadAllocAfterPush:
                        controller.perform_maintenance_read()

                    controller.sys_status.bytes_transfered += len(data)
                else:
                    # print "rx data %s" % (binascii.b2a_hex(data))
                    controller.comm_proxy.on_receive_frame(data)
                    controller.config.ip = ip
                    controller.config.port = int(port)
        except Exception, e:
            globals.system_log.error("(UDPProxy::route_received_data(address: %s:%d) Exception) %s" % (ip, port, e))
            if sys_config.DebugTcpServer:
                globals.tcp_log_server.error("(UDPProxy::route_received_data(address: %s:%d) Exception) %s" % (ip, port, e))

    #----------------------------------------------------------------------

    def run(self):
        import errno
        globals.system_log.info("UDPProxy started.")

        

        while not self.terminating:
            try:
                # block here for self.RECEIVE_BLOCKING_TIMEOUT seconds
                (data, address) = self.sock.recvfrom(8192)

                if not self.terminating:
                    self.route_received_data(data, address)
            except socket.timeout:
                pass
            except socket.error, e:
                if not self.terminating:
                    # bind socket if disconnected
                    if e.errno == errno.EBADF:
                        self.connect()
                    else:
                        raise
            except Exception, e:
                globals.system_log.error("(UDPProxy::run() Exception) %s" % (e))
                if sys_config.DebugTcpServer:
                    globals.tcp_log_server.error("(UDPProxy::run() Exception) %s" % (e))

        globals.system_log.info("UDPProxy stopped.")

    #----------------------------------------------------------------------
