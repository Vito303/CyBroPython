import struct
import binascii
import socket, threading
import exceptions
import datetime, time
import alloc
import logger
import binascii
import globals
import const
import sys_config


CmdPing = 0x10
CmdReadStatus = 0x11
CmdReadCode = 0x21
CmdWriteData = 0x32
CmdReadRandom = 0x33
CmdWriteRandom = 0x34

Request = 0x00
DirectionAck = 0x01
TypeCommand = 0x00
BroadcastTypeCommand = 0x64
ResponseCodeAck = 0x01

HeaderLength = 12
PasswordLength = 2
CrcLength = 2
KernelHeadMemoryAddress = 0x10120
PlcHeadMemorySegment = 0x0200

# RD_STATUS.system_status response values

SystemStatusLoaderActive = 0
SystemStatusKernelActive = 1

# RD_STATUS.plc_status response values

PlcStatusStop = 0
PlcStatusPause = 1
PlcStatusRun = 2
PlcStatusNoValidProgram = 3
PlcStatusCongestionError = 4

BandwidthMeasureTime = 60 # seconds

##############################################################################
#
#    Exceptions

class CommError(exceptions.Exception):
    pass

class CommTimeout(CommError):
    pass

class CommNAK(CommError):
    pass

class CommInvalidCRC(CommError):
    pass

class CommInvalidPassword(CommError):
    pass

class CommFrameError(CommError):
    pass

class CommSendError(CommError):
    pass

class CommSocketError(CommError):
    pass

class CommDataError(CommError):
    pass

class AllocFileNotFound(CommError):
    pass

##############################################################################
#
#    Response structures

class ReadStatusResponse:
    system_status = -1
    plc_status = -1

    def __str__(self):
        return "(ReadStatusResponse) system_status: %d, plc_status: %d" % \
            (self.system_status, self.plc_status)

    def get_str(self):

        if self.system_status == SystemStatusLoaderActive:
            return "loader"

        if self.system_status == SystemStatusKernelActive:
            if self.plc_status == PlcStatusStop:
                return "stop"
            if self.plc_status == PlcStatusPause:
                return "pause"
            if self.plc_status == PlcStatusRun:
                return "run"
            if self.plc_status == PlcStatusNoValidProgram:
                return "no pgm"
            if self.plc_status == PlcStatusCongestionError:
                return "scanovr"

        return "error"


#*****************************************************************************


class PlcHead:

    empty = magic = crc = code_crc = alloc_crc = retentive_crc = timestamp = 0


#*****************************************************************************


class FileEntry:
    struct_size = 46
    filename = ""
    filename_size = 0
    address = 0
    filesize = 0
    timestamp = 0
    read_ok = False

    def __str__(self):
        return "(FileEntry) filename: %s, filename_size: %d, address: %d, filesize: %d, timestamp: %s" % \
            (self.filename, self.filename_size, self.address, self.filesize, self.timestamp)


#*****************************************************************************


class BandwidthEntry:
    timestamp = None
    duration = 0

    def __init__(self, timestamp, duration):
        self.timestamp = timestamp
        self.duration = duration


#*****************************************************************************


class CommFrame:
    signature = 0
    length = 0
    from_nad = 0
    to_nad = 0
    direction = 0
    type = 0
    password = 0
    crc = 0
    binary_frame = ""

    #-------------------------------------------------------------------------

    def __init__(self, frame):
        self.binary_frame = frame
        frame_len = len(frame)

        if (frame_len >= HeaderLength + CrcLength):
            (self.signature, self.length, self.from_nad, self.to_nad, self.direction, self.type) = \
              struct.unpack("<HHLLBB", frame[0 : 14])
            (self.crc, ) = struct.unpack("<H", frame[frame_len - CrcLength : frame_len])
        else:
            raise CommFrameError

    #-------------------------------------------------------------------------

    def __str__(self):
        s = "(CommFrame) signature: 0x%04X, length: %d, from_nad: %d, to_nad: %d, direction: %d, type: %d" % \
            (self.signature, self.length, self.from_nad, self.to_nad, self.direction, self.type)
        s = s + ", password: 0x%04X, crc: 0x%04X" % (self.password, self.crc)
        return s

    #-------------------------------------------------------------------------

    def dump(self):
        return binascii.b2a_hex(self.binary_frame)

    #-------------------------------------------------------------------------

#*****************************************************************************


##############################################################################
#
#    Base class for CyBro communication

class CybroBase:

    plc_nad = 0

    abus_messages_tx_count = 0
    abus_error_count = 0
    last_error_timestamp = None
    last_error_code = "none"
    controller = None

    #-------------------------------------------------------------------------

    def __init__(self):
        pass

    #-------------------------------------------------------------------------
    #
    #    Utility functions
    #
    #-------------------------------------------------------------------------

    def calc_crc(self, data):
        PRIM_TABLE = (0x049D, 0x0C07, 0x1591, 0x1ACF, 0x1D4B, 0x202D, 0x2507, 0x2B4B,
                      0x34A5, 0x38C5, 0x3D3F, 0x4445, 0x4D0F, 0x538F, 0x5FB3, 0x6BBF)

        crc = 0
        for i in range(len(data)):
            c = struct.unpack("<1B", data[i])
            crc += (c[0] ^ 0x5A) * PRIM_TABLE[i & 0x0F]

        return crc & 0xFFFF # cast it to word

    #-------------------------------------------------------------------------

    def unpack_cybro_datetime(self, value):
        sec = (value & 0x0000001F) * 2
        min = (value & 0x000007FF) >> 5
        hh = (value & 0x0000FFFF) >> 11
        dd = (value & 0x001F0000) >> 16
        mm = (value & 0x01FF0000) >> 21
        yy = (value >> 25) + 1980

        return datetime.datetime(yy, mm, dd, hh, min, sec)

    #-------------------------------------------------------------------------

    def set_comm_err(self, code):
        self.abus_error_count += 1
        self.last_error_code = code
        self.last_error_timestamp = globals.tz_info.get_utc_datetime()
        self.controller.sys_status.comm_error_count += 1

    #-------------------------------------------------------------------------

    def check_received_frame(self, frame):
        frame_len = len(frame)

        # check frame length
        if (frame_len < HeaderLength + PasswordLength + CrcLength):
            self.set_comm_err("frame")
            raise CommFrameError, "(c%d) Invalid received frame length." % (self.plc_nad)

        #check header signature
        if (ord(frame[0]) != 0xAA or ord(frame[1]) != 0x55):
            self.set_comm_err("frame")
            raise CommFrameError, "(c%d) Invalid received frame signature." % (self.plc_nad)

        #check frame crc
        crc = ord(frame[frame_len - 1]) * 256 + ord(frame[frame_len - 2])
        if (self.calc_crc(frame[0 : len(frame) - 2]) != crc):
            self.set_comm_err("frame")
            raise CommInvalidCRC, "(c%d) Invalid received frame crc." % (self.plc_nad)

    #-------------------------------------------------------------------------

    def is_push_message(self, frame):
        return frame.to_nad == 0 and frame.direction == DirectionAck and frame.type == TypeCommand

    #-------------------------------------------------------------------------

    def is_broadcast_message(self, frame):
        return frame.to_nad == 0 and frame.direction == DirectionAck and frame.type == BroadcastTypeCommand

    #-------------------------------------------------------------------------

    def extract_sender_nad(self, frame):
        (NAD,) = struct.unpack("<L", frame[4 : 8])
        return int(NAD)

    #-------------------------------------------------------------------------



###########################################################################
#
#    Base class for CyBro communication

class CybroComm(CybroBase):

    client_nad = 0
    received_frame = 0
    log = None
    last_plc_head = None

    bandwidth_list = None

    #-------------------------------------------------------------------------

    def __init__(self, client_nad, plc_nad):
        self.client_nad = client_nad
        self.plc_nad = plc_nad
        self.bandwidth_list = []

        self.log = logger.create("c%d" % plc_nad)


    #-------------------------------------------------------------------------
    #
    #    frame creation functions
    #
    #-------------------------------------------------------------------------

    def __create_header_frame_part(self, data_block_len):
        return struct.pack("<2B1H2L", 0xAA, 0x55, data_block_len + PasswordLength, self.client_nad, self.plc_nad)

    #-------------------------------------------------------------------------

    def __create_password_frame_part(self):
        if self.controller.config.use_transaction_id:
            data = globals.udp_proxy.get_next_transaction_id()
        elif self.controller.config.use_password:
            data = self.calc_crc(self.controller.config.password)
        else:
            data = 0

        return struct.pack("<1H", data)

    #-------------------------------------------------------------------------

    def __create_request_frame(self, data):
        data = struct.pack("<2B", Request, TypeCommand) + data
        header = self.__create_header_frame_part(len(data))
        # password = self.__create_password_frame_part()
        password = struct.pack("<1H", 0) # none password
        crc = self.calc_crc(header + data + password)

        return header + data + password + struct.pack("<1H", crc)

    #-------------------------------------------------------------------------
    #
    #    frame functions
    #
    #-------------------------------------------------------------------------

    def send_raw(self, frame):
        # handle retry count
        retry_number = 1
        frame_received = False

        while not frame_received and retry_number <= self.controller.config.retry_count:
            if not self.controller.comm_proxy.send_frame_online(frame):
                msg = "Error sending frame."
                self.log.error(msg)
                raise CommSendError, msg

            try:
                rx_frame = self.controller.comm_proxy.receive_frame_online()
                frame_received = True
            except CommTimeout:
                retry_number += 1

        print "receive data %s" % (binascii.b2a_hex(rx_frame))
        data = self.__extract_frame_data(rx_frame)
        if len(data) < 2:
            msg = "(c%d) Invalid received data length." % self.plc_nad
            self.log.error(msg)
            self.set_comm_err("frame")
            raise CommFrameError, msg

        if ord(data[0]) == ResponseCodeAck:
            return data[2 : ]
        else:
            msg = "(c%d) Controller returned response error code %d." % (self.plc_nad, ord(data[0]))
            self.log.error(msg)
            self.set_comm_err("nak")
            raise CommNAK, msg


    def send_frame(self, frame, get_raw_response = False):

        # handle retry count
        retry_number = 1
        frame_received = False
        data = ""

        try:
            start_time = time.time()

            while not frame_received and retry_number <= self.controller.config.retry_count:
                if not self.send_frame_online(frame):
                    msg = "Error sending frame."
                    self.log.error(msg)
                    raise CommSendError, msg

                try:
                    rx_frame = self.receive_frame_online()
                    frame_received = True
                except CommTimeout:
                    retry_number += 1

            if frame_received:
                if get_raw_response:
                    return rx_frame
                self.check_received_frame(rx_frame)
            else:
                if self.plc_nad != 0:
                    msg = "(c%d) Communication timeout error." % self.plc_nad
                    self.log.error(msg)
                    self.set_comm_err("tout")
                    raise CommTimeout, msg
                else:
                    return

            data = self.__extract_frame_data(rx_frame)
            if len(data) < 2:
                msg = "(c%d) Invalid received data length." % self.plc_nad
                self.log.error(msg)
                self.set_comm_err("frame")
                raise CommFrameError, msg

            if ord(data[0]) == ResponseCodeAck:
                return data[2 : ]
            else:
                msg = "(c%d) Controller returned response error code %d." % (self.plc_nad, ord(data[0]))
                self.log.error(msg)
                self.set_comm_err("nak")
                raise CommNAK, msg
        finally:
            now = globals.tz_info.get_utc_datetime()
            cycle_duration = time.time() - start_time

            # clear old entries in bandwidth list
            while len(self.bandwidth_list) > 0 and (now - self.bandwidth_list[0].timestamp).seconds > BandwidthMeasureTime:
                self.bandwidth_list.pop(0)

            # add new duration at the end of list
            self.bandwidth_list.append(BandwidthEntry(now, cycle_duration))

    #-------------------------------------------------------------------------

    def __extract_frame_data(self, frame):
        return frame[HeaderLength : len(frame) - PasswordLength - CrcLength]

    #-------------------------------------------------------------------------

    def extract_frame_password(self, frame):
        return frame[-(PasswordLength + CrcLength) : -PasswordLength]


    #-------------------------------------------------------------------------
    #
    #    Application layer functions
    #
    #-------------------------------------------------------------------------

    def ping(self):
        data = struct.pack("<1B", CmdPing)
        send_data = self.__create_request_frame(data)
        print "send data %s" % (binascii.b2a_hex(send_data))
        self.send_raw(send_data)
        # self.send_frame(self.__create_request_frame(data))

    #-------------------------------------------------------------------------

    def read_status(self):
        tx_data = struct.pack("<1B", CmdReadStatus)
        #rx_data = self.send_frame(self.__create_request_frame(tx_data))
        send_data = self.__create_request_frame(tx_data)
        print "send data %s" % (binascii.b2a_hex(send_data))
        rx_data = self.send_raw(send_data)

        if len(rx_data) >= 2:
            result = ReadStatusResponse()
            result.system_status = ord(rx_data[0])
            result.plc_status = ord(rx_data[1])
            print "read status %s %s" % (result.plc_status, result.get_str())
            return result
        else:
            msg = "(c%d) Invalid data format." % self.plc_nad
            self.log.error(msg)
            raise CommDataError, msg

    #-------------------------------------------------------------------------

    def read_code_memory_block(self, segment_number, block_size):
        tx_data = struct.pack("<1B2H", CmdReadCode, segment_number, block_size)
        return self.send_frame(self.__create_request_frame(tx_data))

    #-------------------------------------------------------------------------

    def read_code_memory(self, address, size):
        SEGMENT_SIZE = 0x100
        first_segment = int(address / SEGMENT_SIZE)
        first_offset = address % SEGMENT_SIZE
        last_segment = int((address + size) / SEGMENT_SIZE)
        last_offset = (first_offset + size) % SEGMENT_SIZE
        data_size = SEGMENT_SIZE

        segment = first_segment

        rx_data = ''

        while segment <= last_segment:
            if segment == last_segment:
                data_size = last_offset

            tx_data = struct.pack("<1B2H", CmdReadCode, segment, data_size)
            data = self.send_frame(self.__create_request_frame(tx_data))

            if segment == first_segment and first_offset != 0:
                data = data[first_offset : ]

            rx_data += data
            segment += 1

        return rx_data

    #-------------------------------------------------------------------------

    def read_plc_head(self):
        # plchead structure offset 0x0200:0x0010
        data = self.read_code_memory_block(PlcHeadMemorySegment, 0x10)

        plc_head = PlcHead()

        (plc_head.empty, plc_head.magic, plc_head.crc, plc_head.code_crc, \
        plc_head.alloc_crc, plc_head.retentive_crc, plc_head.timestamp) = \
            struct.unpack("<6HL", data[:16])

        plc_head.timestamp = self.unpack_cybro_datetime(plc_head.timestamp)
        self.last_plc_head = plc_head

        return plc_head

    #-------------------------------------------------------------------------

    def read_zipped_alloc_file(self):
        try:
            # read pointer to array of file descriptiors
            data = self.read_code_memory(0x20040, 6)
            (file_descriptor_address, file_count) = struct.unpack("<LH", data[:6])

            # read file descriptors
            data = self.read_code_memory(file_descriptor_address, file_count * FileEntry.struct_size)

            for i in range(file_count):
                f = FileEntry()
                # read file name and trim 0's from the end
                f.filename = (data[ : 32]).rstrip("\0")
                # trim file name from the structure
                data = data[32 : ]

                if f.filename == "alc.zip":
                    (f.filename_size, f.address, f.filesize, f.timestamp) = \
                        struct.unpack("<1H3L", data[ : 14])

                    f.timestamp = self.unpack_cybro_datetime(f.timestamp)
                    data = self.read_code_memory(f.address, f.filesize)
                    return (f, data)

                # delete rest of data from processed structure
                data = data[14 : ]
        except:
            pass

        return (None, None)

    #-------------------------------------------------------------------------

    def read_alloc_file(self, transfer_timestamp):
        (f, data) = self.read_zipped_alloc_file()

        if f != None and data != None:
            self.controller.alloc.process_zipped_alloc(data, transfer_timestamp)
            self.log.info("(c%d) Allocation file downloaded, timestamp %s, size %d bytes." % (self.plc_nad, f.timestamp, f.filesize))
        else:
            self.controller.alloc.clear()
            self.controller.alloc.delete_cached_file()
            raise AllocFileNotFound

    #-------------------------------------------------------------------------

    def read_random_memory(self, byte_tags, word_tags, dword_tags):

        byte_tags_count = len(byte_tags)
        word_tags_count = len(word_tags)
        dword_tags_count = len(dword_tags)

        tx_data = struct.pack("<1B3H", CmdReadRandom, byte_tags_count, word_tags_count, dword_tags_count)

        tags = byte_tags + word_tags + dword_tags
        tags_count = len(tags)

        for tag in tags:
            if tag.valid:
                tx_data += struct.pack("<H", tag.address)
        # data = self.send_frame(self.__create_request_frame(tx_data))
        data = self.send_raw(self.__create_request_frame(tx_data))

        n = 0

        # extract byte values
        if byte_tags_count != 0:
            for i in range(byte_tags_count):
                (value,) = struct.unpack("<1B", data[i : i + 1])

                # skip invalid tags
                while not tags[n].valid and n < tags_count:
                    n += 1

                tags[n].value = value
                tags[n].timestamp = time.time()
                n += 1

            data = data[byte_tags_count : ]

        # extract word values
        if word_tags_count != 0:
            for i in range(word_tags_count):
                (value,) = struct.unpack("<1h", data[i * 2 : i * 2 + 2])

                # skip invalid tags
                while not tags[n].valid and n < tags_count:
                    n += 1

                tags[n].value = value
                tags[n].timestamp = time.time()
                n += 1

            data = data[word_tags_count * 2 : ]

        # extract long values
        if dword_tags_count != 0:
            for i in range(dword_tags_count):
                bin_data = data[i * 4 : i * 4 + 4]

                # skip invalid tags
                while not tags[n].valid and n < tags_count:
                    n += 1

                if tags[n].type == const.DataTypeReal:
                    (value,) = struct.unpack("<1f", bin_data)
                else:
                    (value,) = struct.unpack("<1l", bin_data)

                tags[n].value = value
                tags[n].timestamp = time.time()
                n += 1

            data = data[dword_tags_count * 4 : ]

    #-------------------------------------------------------------------------

    def read_tag_values(self, tags):
        try:
            if sys_config.DebugPrints or sys_config.DebugTcpServer:
                log_list= []

            byte_tags = []
            word_tags = []
            dword_tags = []

            for tag in tags:
                if sys_config.DebugPrints or sys_config.DebugTcpServer:
                    log_list.append(tag.name)

                if tag.size == 1:
                    byte_tags.append(tag)
                elif tag.size == 2:
                    word_tags.append(tag)
                elif tag.size == 4:
                    dword_tags.append(tag)
                else:
                    tag.valid = False

            if sys_config.DebugPrints:
                self.log.info("Read: %s", log_list)
            if sys_config.DebugTcpServer:
                globals.tcp_log_server.info("(c%d) Read: %s" % (self.plc_nad, log_list))

            self.read_random_memory(byte_tags, word_tags, dword_tags)

            if sys_config.DebugPrints or sys_config.DebugTcpServer:
                log_list = []
                for tag in tags:
                    log_list.append(tag.value)
                if sys_config.DebugPrints:
                    self.log.info("Received values: %s", log_list)
                if sys_config.DebugTcpServer:
                    globals.tcp_log_server.info("(c%d) Received values: %s" % (self.plc_nad, log_list))
        except:
            return False

        return True

    #-------------------------------------------------------------------------

    def write_random_memory(self, byte_tags, word_tags, dword_tags):
        tx_data = struct.pack("<1B3H", CmdWriteRandom, len(byte_tags), len(word_tags), len(dword_tags))

        tags = byte_tags + word_tags + dword_tags

        for tag in tags:
            tx_data += struct.pack("<H", tag.address)

        # set byte values
        for tag in byte_tags:
            tx_data += struct.pack("<1B", tag.value)

        # set word values
        for tag in word_tags:
            tx_data += struct.pack("<1h", tag.value)

        # extract long values
        for tag in dword_tags:
            if tag.type == const.DataTypeReal:
                tx_data += struct.pack("<1f", tag.value)
            else:
                tx_data += struct.pack("<1l", tag.value)

        self.send_raw(self.__create_request_frame(tx_data))

    #-------------------------------------------------------------------------

    def write_single_byte_abs_value(self, address, value):
        tx_data = struct.pack("<1B2H", CmdWriteData, address, 1) + \
                  struct.pack("<1B", value)
        self.send_frame(self.__create_request_frame(tx_data))

    #-------------------------------------------------------------------------

    def write_tag_values(self, tags, values):

        if len(tags) != len(values):
            return

        byte_tags = []
        word_tags = []
        dword_tags = []

        if sys_config.DebugPrints or sys_config.DebugTcpServer:
            log_list = []

        n = 0
        for tag in tags:
            if sys_config.DebugPrints or sys_config.DebugTcpServer:
                log_list.append(tag.name)

            if tag.size == 1:
                try:
                    tag.value = int(round(float(values[n]))) != 0
                    byte_tags.append(tag)
                except ValueError:
                    pass
            if tag.size == 2:
                try:
                    tag.value = int(round(float(values[n])))
                    word_tags.append(tag)
                except ValueError:
                    pass
            if tag.size == 4:
                try:
                    if tag.type == const.DataTypeReal:
                        tag.value = float(values[n])
                    else:
                        tag.value = int(values[n])
                    dword_tags.append(tag)
                except ValueError:
                    pass

            n += 1

        if sys_config.DebugPrints:
            self.log.info("Write: %s, Values: %s" % (log_list, values))
        if sys_config.DebugTcpServer:
            globals.tcp_log_server.info("(c%d) Write: %s, Values: %s" % (self.plc_nad, log_list, values))

        self.write_random_memory(byte_tags, word_tags, dword_tags)

        now = time.time()
        for tag, value in zip(tags, values):
            tag.value = value
            tag.timestamp = now

    #-------------------------------------------------------------------------

    def check_if_alloc_file_is_needed(self):
        plc_head = self.read_plc_head()
        alloc_file_transfer_datetime = self.controller.alloc.get_file_transfer_timestamp()
        need_transfer = alloc_file_transfer_datetime == None or alloc_file_transfer_datetime < plc_head.timestamp

        return (need_transfer, plc_head.timestamp)

    #-------------------------------------------------------------------------



###########################################################################
#
#    CyBro Ethernet communicator


class CybroProxy(CybroComm):

    __ip = ""
    __port = 0
    __data = ""

    data_received_event = None
    comm_request_start_time = 0
    tx_transaction_id = 0

    #-------------------------------------------------------------------------

    def __init__(self, controller, client_nad, plc_nad):
        self.controller = controller
        CybroComm.__init__(self, client_nad, plc_nad)
        self.data_received_event = threading.Event()

    #-------------------------------------------------------------------------

    def connect(self):
        return

    #-------------------------------------------------------------------------

    def disconnect(self):
        return

    #-------------------------------------------------------------------------

    def set_connection_parameters(self, ip, Port):
        return

    #-------------------------------------------------------------------------

    def send_frame_online(self, frame):

        self.data_received_event.clear()
        if globals.udp_proxy != None:
            if self.controller.config.use_transaction_id:
                self.tx_transaction_id = self.extract_frame_password(frame)

            self.comm_request_start_time = time.time()
            globals.udp_proxy.send(self.plc_nad, frame)
            self.controller.sys_status.bytes_transfered += len(frame)
            self.abus_messages_tx_count += 1

        return True

    #-------------------------------------------------------------------------

    def on_receive_frame(self, frame):
        # function is called from udp_proxy when frame for this controller is received

        if self.controller.config.use_transaction_id and self.tx_transaction_id != self.extract_frame_password(frame):
            # ignore frame if invaid transaction_id
            return

        self.__data = frame
        self.data_received_event.set()

    #-------------------------------------------------------------------------

    def receive_frame_online(self):

        # block here and wait for received frame or timeout
        self.data_received_event.wait(float(self.controller.config.timeout) / 1000.0)

        if self.data_received_event.isSet():
            # data received within specified timeout
            self.controller.sys_status.bytes_transfered += len(self.__data)
            self.controller.sys_status.last_response_time = int((time.time() - self.comm_request_start_time) * 1000)
            return self.__data
        else:
            # signal upper layer for comm timeout
            raise CommTimeout

    #-------------------------------------------------------------------------

    def get_bandwidth(self):
        now = globals.tz_info.get_utc_datetime()
        # clear old entries in bandwidth list
        while len(self.bandwidth_list) > 0 and (now - self.bandwidth_list[0].timestamp).seconds > BandwidthMeasureTime:
            self.bandwidth_list.pop(0)

        total = 0
        for entry in self.bandwidth_list:
            total += entry.duration

        return total / BandwidthMeasureTime * 100

    #-------------------------------------------------------------------------
