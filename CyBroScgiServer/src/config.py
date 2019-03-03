import os
import ConfigParser
import sys_config
import re
import globals
import threading


##############################################################################
#
#    CybroConfig contains configuration for each PLC


class CybroConfig:
    nad = 0
    ip = ""
    port = 8442
    password = ""
    timeout = 2000
    retry_count = 3
    created_from_push = False
    created_from_config_ini = False
    always_running = False
    assigned_for_termination = False
    use_password = False
    use_transaction_id = True



##############################################################################
#
#    GlobalConfig is wrapper for scgi_server.ini file


class GlobalConfig:

    push_ack_address = 0x0417 # cybro address to set for push acknowledge

    check_file_timer = None
    config_file_timestamp = 0

    terminating = False
    items = None

    #-------------------------------------------------------------------------

    def __init__(self):
        self.items = []
        self.read()
        self.start_check_file_timer()

    #-------------------------------------------------------------------------

    def __del__(self):
        self.check_file_timer.cancel()

    #-------------------------------------------------------------------------

    def get_controller_index(self, nad):
        for n, item in enumerate(self.items):
            if item.nad == nad:
                return n
        return None

    #-------------------------------------------------------------------------

    def get_controller(self, nad):
        n = self.get_controller_index(nad)
        return self.items[n] if n != None else None

    #-------------------------------------------------------------------------

    def add_controller(self, cfg):
        if self.get_controller_index(cfg.nad) == None:
            self.items.append(cfg)

    #-------------------------------------------------------------------------

    def terminate(self):
        self.terminating = True

        if self.check_file_timer != None:
            self.check_file_timer.cancel()

    #-------------------------------------------------------------------------

    def start_check_file_timer(self):
        self.check_file_timer = threading.Timer(sys_config.ConfigIniCheckPeriod, self.check_file_for_changes)
        self.check_file_timer.daemon = True
        self.check_file_timer.start()

    #-------------------------------------------------------------------------

    def safe_read(self, ini, section, key, required, default = ""):

        try:
            return ini.get(section, key)
        except ConfigParser.NoOptionError:
            if required:
                globals.system_log.warning("%s: No value found for [%s]:%s, using default value %s." % \
                    (sys_config.ConfigIniFilename, section, key, default))

        return default

    #-------------------------------------------------------------------------

    def safe_read_bool(self, ini, section, key, required, default = False):

        try:
            value = ini.get(section, key)
            return value.lower() == "true" or value == "1"
        except ConfigParser.NoOptionError:
            if required:
                globals.system_log.warning("%s: No value found for [%s]:%s, using default value %s." % \
                    (sys_config.ConfigIniFilename, section, key, default))

        return default

    #-------------------------------------------------------------------------

    def safe_read_int(self, ini, section, key, required, default = 0, base = 10):

        try:
            value = self.safe_read(ini, section, key, required, default)
            return int(value, base)
        except TypeError:
            return value
        except ValueError:
            if required:
                value = ini.get(section, key)
                globals.system_log.warning("%s: Int expected for [%s]:%s, read %s, using default value %d." % \
                    (sys_config.ConfigIniFilename, section, key, value, default))

        if base != 10:
            return int(default, base)
        else:
            return default

    #-------------------------------------------------------------------------

    def read_connection_params(self, ini, section):
        conn_type = self.safe_read(ini, section, "ConnectionType", False, default = sys_config.ConnectionType).lower()
        if conn_type == "lan":
            return (sys_config.LanTimeout, sys_config.LanRetry)
        elif conn_type == "gsm":
            return (sys_config.GsmTimeout, sys_config.GsmRetry)
        else:
            return (sys_config.WanTimeout, sys_config.WanRetry)

    #-------------------------------------------------------------------------

    def read_config_timestamp(self):

        old_timestamp = self.config_file_timestamp
        if os.path.isfile(sys_config.ConfigIni):
            self.config_file_timestamp = os.stat(sys_config.ConfigIni).st_mtime
        return self.config_file_timestamp == old_timestamp

    #-------------------------------------------------------------------------

    def read(self):

        globals.system_log.info("Reading %s" % sys_config.ConfigIni)

        self.read_config_timestamp()

        ini = ConfigParser.ConfigParser()
        if os.path.isfile(sys_config.ConfigIni):
            ini.readfp(open(sys_config.ConfigIni))

        globals.tz_info.clear()
        globals.controllers.reset_create_from_config_flag()

        # read PLC configurations from separate sections

        for section in ini.sections():
            match = re.search(r'^c(\d+)$', section)
            try:
                nad = int(match.group(1))
            except:
                continue

            cfg = self.get_controller(nad)
            if cfg == None:
                cfg = CybroConfig()
                cfg.nad = nad
                self.add_controller(cfg)

            cfg.ip = self.safe_read(ini, section, "Ip", False)
            cfg.port = self.safe_read_int(ini, section, "Port", False, 8442)
            cfg.password = self.safe_read(ini, section, "Password", False, default = sys_config.Password)
            cfg.use_password = cfg.password != ""
            (cfg.timeout, cfg.retry_count) = self.read_connection_params(ini, section)
            cfg.use_transaction_id = self.safe_read_bool(ini, section, "TransactionId", False, sys_config.TransactionId if sys_config.TransactionId != None else not cfg.use_password)
            cfg.always_running = sys_config.LocalAccess or cfg.ip != ""

            if cfg.always_running and globals.controllers.get_by_nad(cfg.nad) == None:
                controller = globals.controllers.create_from_config(cfg)
                controller.config.created_from_config_ini = True

            # commented by Damir
            # globals.tz_info.add(nad, self.safe_read(ini, section, "Timezone", False, default = sys_config.TimeZone))

    #-------------------------------------------------------------------------

    def read_for_controller(self, nad):

        ini = ConfigParser.ConfigParser()
        if os.path.isfile(sys_config.ConfigIni):
            ini.readfp(open(sys_config.ConfigIni))

        # read PLC configurations from separate sections

        for section in ini.sections():
            match = re.search(r'^c(\d+)$', section)
            try:
                ini_nad = int(match.group(1))
            except:
                continue

            if nad == ini_nad:
                cfg = self.get_controller(nad)
                if cfg == None:
                    cfg = CybroConfig()
                    cfg.nad = nad
                    self.add_controller(cfg)

                cfg.ip = self.safe_read(ini, section, "Ip", False)
                cfg.port = self.safe_read_int(ini, section, "Port", False, 8442)
                cfg.password = self.safe_read(ini, section, "Password", False, default = sys_config.Password)
                cfg.use_password = cfg.password != ""
                (cfg.timeout, cfg.retry_count) = self.read_connection_params(ini, section)
                cfg.use_transaction_id = self.safe_read_bool(ini, section, "TransactionId", False, sys_config.TransactionId if sys_config.TransactionId != None else not cfg.use_password)
                cfg.always_running = sys_config.LocalAccess or cfg.ip != ""

                # commented by Damir
                # globals.tz_info.add(nad, self.safe_read(ini, section, "Timezone", False, default = sys_config.TimeZone))
                return cfg

        return None

    #-------------------------------------------------------------------------

    def check_file_for_changes(self):

        if self.terminating:
            return

        if not self.read_config_timestamp():
            globals.system_log.info("Configuration file changed, reloading...")
            self.read()
            globals.udp_proxy.disconnect()

        self.start_check_file_timer()

    #-------------------------------------------------------------------------


##############################################################################