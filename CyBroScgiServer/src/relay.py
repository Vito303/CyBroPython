
import sys_config
import globals
import logger
import datetime
import db
import threading


DataSyncInterval = 10 #s


#*****************************************************************************


class RelayController:

    user_id = 0
    session_id = 0
    nad = 0
    message_count_tx = 0
    message_count_rx = 0
    last_controller_nad = 0
    last_message = None
    last_update = None
    ip = ""
    port = 0
    valid = False

    #-------------------------------------------------------------------------

    def __str__(self):
        return "(RelayController) session_id: %d, nad: %d" % (self.session_id, self.nad)

    #-------------------------------------------------------------------------


#*****************************************************************************


class DataSync(threading.Thread):

    terminate_event = None
    relay = None
    sync_active = False
    access_lock = None

    #-------------------------------------------------------------------------

    def __init__(self, relay):
        self.terminate_event = threading.Event()
        self.access_lock = threading.Lock()
        self.relay = relay
        threading.Thread.__init__(self)

    #-------------------------------------------------------------------------

    def run(self):

        terminated = False
        while not terminated:
            try:
                self.do_sync()
            except Exception, e:
                import sys, traceback
                globals.system_log.info("Relay exception: %s" % traceback.format_exc())

            self.terminate_event.wait(DataSyncInterval)
            terminated = self.terminate_event.is_set()

    #-------------------------------------------------------------------------

    def terminate(self):
        self.terminate_event.set()

    #-------------------------------------------------------------------------

    def do_sync(self):

        data = self.relay.db.get_relay_data()

        self.lock()
        try:
            # invalidate data
            for item in self.relay.items:
                item.valid = False

            #invalidate sessions
            for n in self.relay.session_data.keys():
                self.relay.session_data[n]["valid"] = False

            for d in data:
                session_id = d["relay"]["session_id"]
                user_id = d["relay"]["user_id"]

                if self.relay.session_data.has_key(user_id):
                    if self.relay.session_data[user_id]["modified"]:
                        # write stats to db
                        self.relay.db.write_relay_data(
                            {
                                "user_id": user_id,
                                "session_id": session_id,
                                "message_count_tx": self.relay.session_data[user_id]["message_count_tx"],
                                "message_count_rx": self.relay.session_data[user_id]["message_count_rx"],
                                "last_message": self.relay.session_data[user_id]["last_message"],
                                "last_controller_nad": self.relay.session_data[user_id]["last_controller_nad"],
                            }
                        )
                        self.relay.session_data[user_id]["message_count_tx"] = 0
                        self.relay.session_data[user_id]["message_count_rx"] = 0
                        self.relay.session_data[user_id]["modified"] = False
                        self.relay.session_data[user_id]["valid"] = True
                else:
                    # create new stats record
                    self.relay.session_data.update(
                        {
                            user_id:
                                {
                                    "session_id": session_id,
                                    "user_id": user_id,
                                    "message_count_tx": 0,
                                    "message_count_rx": 0,
                                    "last_message": None,
                                    "last_controller_nad": 0,
                                    "modified": False,
                                    "valid": True,
                                }
                        }
                    )

                for c in d["controllers"]:
                    item = self.relay.get_controller(session_id, c["nad"])
                    if item == None:
                        item = RelayController()
                        self.relay.items.append(item)

                    item.user_id = user_id
                    item.session_id = session_id
                    item.nad = c["nad"]
                    item.valid = True


            # delete invalid sessions
            for n in self.relay.session_data.keys():
                if not self.relay.session_data[n]["valid"]:
                    del self.relay.session_data[n]

            # delete invalid items
            n = 0
            while n < len(self.relay.items):
                if not self.relay.items[n].valid:
                    self.relay.items.pop(n)
                else:
                    n += 1
        finally:
            self.unlock()

    #-------------------------------------------------------------------------

    def lock(self):
        self.access_lock.acquire()

    #-------------------------------------------------------------------------

    def unlock(self):
        self.access_lock.release()

    #-------------------------------------------------------------------------


#*****************************************************************************


class CybroRelay:

    items = None
    session_data = None
    db = None
    data_sync = None

    #-------------------------------------------------------------------------

    def __init__(self):

        self.db = db.create_db_connection()
        self.items = []
        self.session_data = {}

        if globals.system_log == None:
            globals.system_log = logger.create("service")

        self.data_sync = DataSync(self)

    #-------------------------------------------------------------------------

    def start(self):
        self.data_sync.start()
        globals.system_log.info("Relay started.")

    #-------------------------------------------------------------------------

    def terminate(self):
        self.data_sync.terminate()
        globals.system_log.info("Relay stopped.")

    #-------------------------------------------------------------------------

    def get_controller(self, session_id, nad):
        for item in self.items:
            if item.session_id == session_id and item.nad == nad:
                return item

        return None

    #-------------------------------------------------------------------------

    def process_relay_message(self, ip, port, data, from_nad, to_nad):
        processed = False
        self.data_sync.lock()
        try:
            # search relay controllers
            relays = []

            for item in self.items:
                is_for_plc = item.session_id == from_nad and (to_nad in [0, item.nad])
                is_for_relay = item.session_id == to_nad and (from_nad in [0, item.nad])
                if is_for_plc or is_for_relay:
                    if is_for_plc:
                        # store ip and port for later response
                        item.ip = ip
                        item.port = port
                    relays.append(item)
        finally:
            self.data_sync.unlock()

        for r in relays:
            controller = globals.controllers.get_by_nad(r.nad)
            if controller != None:
                user_id = r.user_id

                # detect direction
                if to_nad == controller.config.nad:
                    # it's request for plc
                    to_ip = controller.config.ip
                    to_port = controller.config.port
                    # update stats
                    if self.session_data.has_key(user_id):
                        self.session_data[user_id]["message_count_tx"] += 1
                        self.session_data[user_id]["last_controller_nad"] = controller.config.nad
                        self.session_data[user_id]["last_message"] = globals.tz_info.get_local_datetime(controller.config.nad)
                        self.session_data[user_id]["modified"] = True
                else:
                    # it's response to relay
                    to_ip = r.ip
                    to_port = r.port
                    # update stats
                    if self.session_data.has_key(user_id):
                        self.session_data[user_id]["message_count_rx"] += 1
                        self.session_data[user_id]["last_message"] = globals.tz_info.get_local_datetime(controller.config.nad)
                        self.session_data[user_id]["modified"] = True

                globals.udp_proxy.send_raw_data(to_ip, to_port, data)
                processed = True

        return processed

    #-------------------------------------------------------------------------


#*****************************************************************************
