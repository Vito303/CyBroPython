import threading
import time
import globals
import sys_config

###########################################################################
#
#    Exceptions


class InvalidCache(Exception):
    pass


###########################################################################
#
#    TagCacheEntry contains single cached tag

class TagCacheEntry:

    hash = 0
    value = ""
    timestamp = 0
    description = ""

    #-------------------------------------------------------------------------

    def __init__(self, hash, value):
        self.hash = hash
        self.value = value
        self.timestamp = time.time()

    #-------------------------------------------------------------------------

    def set_value(self, value):
        self.value = value
        self.timestamp = time.time()

    #-------------------------------------------------------------------------


###########################################################################
#
#    TagCache handles tag caching

class TagCache:

    items = None
    lock = None
    terminating = False

    #-------------------------------------------------------------------------

    def __init__(self):
        self.items = []
        self.lock = threading.Lock()
        self.start_cleanup_timer()

    #-------------------------------------------------------------------------

    def terminate(self):
        self.cleanup_timer.cancel()
        self.terminating = True

    #-------------------------------------------------------------------------

    def start_cleanup_timer(self):
        self.cleanup_timer = threading.Timer(sys_config.CacheCleanupPeriod, self.empty_invalid_cache_items)
        self.cleanup_timer.daemon = True
        self.cleanup_timer.start()

    #-------------------------------------------------------------------------

    def get_tag(self, tag_hash):

        for item in self.items:
            if item.hash == tag_hash:
                return item

        return None

    #-------------------------------------------------------------------------

    def is_value_cached(self, tag_hash, validity_period):
        tag = self.get_tag(tag_hash)
        return tag != None and time.time() - tag.timestamp < validity_period

    #-------------------------------------------------------------------------

    def get_value(self, tag_hash, validity_period):

        tag = self.get_tag(tag_hash)

        if tag and time.time() - tag.timestamp < validity_period:
            return tag

        raise InvalidCache

    #-------------------------------------------------------------------------

    def set_value(self, tag_hash, value, description = ""):

        tag = self.get_tag(tag_hash)

        if tag != None:
            tag.set_value(value)
        else:
            tag = TagCacheEntry(tag_hash, value)
            self.lock.acquire()
            self.items.append(tag)
            self.lock.release()

        tag.description = description

    #-------------------------------------------------------------------------

    def empty_invalid_cache_items(self):

        validity_period = sys_config.CacheValid

        # set lock to prevent adding items
        self.lock.acquire()

        try:
            now = time.time()
            n = 0
            while n < len(self.items):
                if now - self.items[n].timestamp > validity_period:
                    self.items.pop(n)
                else:
                    n += 1
        finally:
            # release lock and let other threads add items
            self.lock.release()

        self.start_cleanup_timer()

    #-------------------------------------------------------------------------
