import globals
import const
import time
import tag_cache
import threading
import sys_config


ReqTagNoError = 0
ReqTagCommTimeout = 1
ReqTagUnknownTag = 2
ReqTagDeviceNotFound = 3


###########################################################################
#
#    RequestTag contains all data for particular tag, from request to response

class RequestTag:

    name = ""
    plc_name = ""
    tag_name = ""
    value = "?"
    description = ""
    nad = 0
    request = const.ReadRequest
    perform_request = True
    valid = False
    request_pending = False
    wait_for_request_complete = True
    is_system_tag = False
    is_cybro_system_tag = False
    is_array = False
    cache_valid_time = 0
    array_index = 0
    hash = 0
    timestamp = 0
    error_code = ReqTagNoError

    #-------------------------------------------------------------------------

    def __init__(self, name = "", request = const.ReadRequest):

        import zlib, re

        if len(name) > 0:
            (self.plc_name, separator, self.tag_name) = name.partition(".")
            self.name = name
            self.request = request
            self.is_system_tag = self.plc_name == "sys"
            self.hash = self.calc_hash(request)

            # check if array
#            match = re.search("^(\w*)\[(\d*)\]", self.tag_name)
#            if match:
#                self.is_array = True
#                self.tag_name = match.group(1)
#                self.array_index = int(match.group(2))

            if not self.is_system_tag and self.plc_name[0:1] == "c":
                try:
                    self.nad = int(self.plc_name[1:])
                    self.is_cybro_system_tag = self.tag_name.find("sys") == 0
                    if self.is_cybro_system_tag:
                        (dummy, separator, self.tag_name) = self.tag_name.partition(".")
                except:
                    pass

    #-------------------------------------------------------------------------

    def calc_hash(self, request):
        import zlib
        return zlib.crc32(self.name.lower() + " %d" % request)

    #-------------------------------------------------------------------------

    def __str__(self):
        return "<RequestTag> name: %s\nplc_name: %s\nnad: %d\ntag_name: %s\nrequest: %d\nsystem_tag: %s\nvalid: %s\nvalue: %s\ncache_valid_time: %d\n" % \
            (self.name, self.plc_name, self.nad, self.tag_name, self.request, self.is_system_tag, self.valid, self.value, self.cache_valid_time)

    #-------------------------------------------------------------------------

    def is_nad_valid(self):
        return self.nad != 0 or self.is_system_tag

    #-------------------------------------------------------------------------



###########################################################################
#
#    Transaction

class Transaction:

    id = 0
    tags = None

    def __init__(self, req_tags):
        self.tags = req_tags
        self.id = id(self)

    #-------------------------------------------------------------------------

    def calc_hash(self, nad, name, request):
        import zlib
        return zlib.crc32("c%d.%s %d" % (nad, name.lower(), request))

    #-------------------------------------------------------------------------

    def get_tag(self, nad, name, request):
        hash = self.calc_hash(nad, name.lower(), request)
        for tag in self.tags:
            if tag.nad == nad and tag.hash == hash:
                return tag
        return None

    #-------------------------------------------------------------------------


###########################################################################
#
#    TransactionPool handles requests and dispatch it


class TransactionPool:

    req_tags = None

    transactions = None
    transaction_lock = None
    tag_cache = None
    terminating = False

    #-------------------------------------------------------------------------

    def __init__(self):
        self.req_tags = []
        self.transactions = []
        self.transaction_lock = threading.Lock()
        self.tag_cache = tag_cache.TagCache()

    #-------------------------------------------------------------------------

    def terminate(self):
        self.terminating = True
        self.tag_cache.terminate()

    #-------------------------------------------------------------------------

    def define_cache_validity_times(self, req_tags):

        cache_valid_time = sys_config.CacheValid
        n = 0
        while n < len(req_tags):
            tag = req_tags[n]
            if tag.request == const.WriteRequest and tag.name == "sys.cache_valid":
                try:
                    cache_valid_time = int(tag.value)
                except:
                    pass
                # remove sys.cache_valid from the list of requested tags
                req_tags.pop(n)
            else:
                tag.cache_valid_time = cache_valid_time
                n += 1

    #-------------------------------------------------------------------------

    def fetch_cached_values(self, req_tags):

        from tag_cache import InvalidCache
        controllers = []

        # sort tags by controllers
        for tag in req_tags:
            if tag.request == const.ReadRequest and not tag.is_system_tag:
                nad = tag.plc_name
                found = False
                for controller in controllers:
                    if controller["nad"] == nad:
                        controller["tags"].append(tag)
                        found = True
                        break

                if not found:
                    controllers.append({"nad": nad, "tags": [tag]})

        for controller in controllers:
            use_cache = True
            n = 0
            while use_cache and n < len(controller["tags"]):
                tag = controller["tags"][n]
                use_cache = tag.is_cybro_system_tag or self.tag_cache.is_value_cached(tag.hash, tag.cache_valid_time)
                n += 1
            if use_cache:
                for tag in controller["tags"]:
                    # get cached tag value for real tags, system tags will be processed later
                    if not tag.is_cybro_system_tag:
                        try:
                            cache_entry = self.tag_cache.get_value(tag.hash, tag.cache_valid_time)
                            tag.value = cache_entry.value
                            tag.description = cache_entry.description
                            tag.valid = True
                            tag.perform_request = sys_config.CacheRequest != -1 and not self.tag_cache.is_value_cached(tag.hash, sys_config.CacheRequest)
                        except tag_cache.InvalidCache:
                            pass

                    tag.wait_for_request_complete = False

    #-------------------------------------------------------------------------

    def create_request(self, req_tags):

        if self.terminating:
            return

        from sys_status import UnknownSysTag

        controllers_to_trigger_read = []
        controllers_to_trigger_write = []
        self.req_tags = req_tags

        transaction = Transaction(req_tags)
        self.transaction_lock.acquire()
        try:
            self.transactions.append(transaction)
        finally:
            self.transaction_lock.release()

        self.define_cache_validity_times(req_tags)
        self.fetch_cached_values(req_tags)

        # go ahead with requests
        for req_tag in req_tags:
            req_tag.request_pending = False

            # skip cached and tags with invalid nad
            if not req_tag.perform_request or not req_tag.is_nad_valid():
                continue
				
            # first check if tag is system tag
            if req_tag.is_system_tag:
                if req_tag.request == const.ReadRequest:
                    try:
                        (req_tag.value, req_tag.description) = globals.sys_status.get_value(req_tag.tag_name)
                        req_tag.perform_request = False
                        req_tag.valid = True
                    except UnknownSysTag:
                        req_tag.error_code = ReqTagUnknownTag
                else:
                    try:
                        globals.sys_status.set_value(req_tag.tag_name, req_tag.value)
                    except UnknownSysTag:
                        req_tag.error_code = ReqTagUnknownTag
            else:
                # fetch controller for nad, if avalable
                controller = globals.controllers.get_by_nad(req_tag.nad)
				
                if controller is None and sys_config.LocalAccess:
                    controller = globals.controllers.create(req_tag.nad, False)
                    controller.read_alloc_file_immediately()
                    if not controller.sys_status.last_alc_file_status:
                       globals.controllers.delete_by_nad(req_tag.nad)
                        
                if controller:
                    # if controller has no valid allocation list, read it now
                    if not controller.sys_status.last_alc_file_status:
                        controller.perform_maintenance_read()

                    # check if is cybro system tag
                    if req_tag.is_cybro_system_tag:
                        try:
                            (req_tag.value, req_tag.description) = controller.sys_status.get_value(req_tag.tag_name)
                            req_tag.valid = True
                        except UnknownSysTag:
                            req_tag.error_code = ReqTagUnknownTag
                    else:
                        if req_tag.request == const.ReadRequest:
                            # it's cybro tag, get value
                            tag = controller.alloc.tags.get_by_name(req_tag.tag_name)
                            if tag:
                                req_tag.description = tag.description
                                # add controller to list for later access triggering
                                try:
                                    controllers_to_trigger_read.index(controller)
                                except ValueError:
                                    controllers_to_trigger_read.append(controller)

                                # set flags
                                tag.read_request = True
                                if req_tag.wait_for_request_complete:
                                    req_tag.request_pending = True
                            else:
                                req_tag.error_code = ReqTagUnknownTag
                        else:
                            # perform write request
                            tag = controller.alloc.tags.get_by_name(req_tag.tag_name)
                            if tag:
                                req_tag.description = tag.description
                                # add controller to list for later access triggering
                                try:
                                    controllers_to_trigger_write.index(controller)
                                except ValueError:
                                    controllers_to_trigger_write.append(controller)
                                tag.value = req_tag.value
                                tag.write_request = True
                                req_tag.request_pending = True
                            else:
                                req_tag.error_code = ReqTagUnknownTag

        for controller in controllers_to_trigger_write:
            controller.process_write_requests()

        for controller in controllers_to_trigger_read:
            controller.process_read_requests()

        start = time.time()
        data_received = False

        # loop and wait for transaction to be completed, or timeout occurs
        while not data_received and time.time() - start < sys_config.ScgiRequestTimeout:
            n = 0
            data_received = True
            while data_received and n < len(req_tags):
                data_received = data_received and not req_tags[n].request_pending
                n += 1

            if not data_received:
                time.sleep(0.01)

        # lock transaction list and remove current transaction
        self.transaction_lock.acquire()
        try:
            self.transactions.remove(transaction)
        finally:
            self.transaction_lock.release()

    #-------------------------------------------------------------------------

    def on_values_received(self, controller, tags, result):

        nad = controller.config.nad

        self.transaction_lock.acquire()
        try:
            for read_tag in tags:
                for transaction in self.transactions:
                    tag = transaction.get_tag(nad, read_tag.name, const.ReadRequest)
                    if tag:
                        if result:
                            tag.value = read_tag.value
                        else:
                            tag.value = "?"
                        tag.valid = result
                        tag.request_pending = False

                # store value to cache, if cache enabled
                if result and sys_config.CacheValid > 0:
                    hash = Transaction(None).calc_hash(nad, read_tag.name, const.ReadRequest)
                    self.tag_cache.set_value(hash, read_tag.value, read_tag.description)
        finally:
            self.transaction_lock.release()

    #-------------------------------------------------------------------------

    def on_values_written(self, controller, tags):

        nad = controller.config.nad

        self.transaction_lock.acquire()
        try:
            for written_tag in tags:
                for transaction in self.transactions:
                    tag = transaction.get_tag(nad, written_tag.name, const.WriteRequest)
                    if tag:
                        tag.valid = True
                        tag.request_pending = False

                        # store value to cache, if cache enabled
                        if sys_config.CacheValid > 0:
                            self.tag_cache.set_value(tag.calc_hash(const.ReadRequest), written_tag.value)
        finally:
            self.transaction_lock.release()

    #-------------------------------------------------------------------------

    def on_invalidate_all_tags(self, controller):

        nad = controller.config.nad

        # set all pending tags for this controller as read and invalid
        self.transaction_lock.acquire()
        try:
            for transaction in self.transactions:
                for tag in transaction.tags:
                    if tag.nad == nad and not tag.is_cybro_system_tag:
                        tag.valid = False
                        tag.request_pending = False
                        tag.error_code = ReqTagCommTimeout
        finally:
            self.transaction_lock.release()

    #-------------------------------------------------------------------------


#*****************************************************************************
