import sys
import threading
sys.path.append("../")
import sys_config
import logger
import globals


if sys_config.DatabaseEngine == "mysql":
    try:
        import MySQLdb
    except ImportError:
        print "Fatal error: MySQLdb library not found!"
        quit()


#*****************************************************************************


def create_db_connection():

    if globals.db_conn == None:
        if sys_config.DatabaseEngine == "mysql":
            globals.db_conn = DBaseMySQL()
        else:
            globals.system_log.error("Unknown DataLogger database engine: %s." % sys_config.DatabaseEngine)
            quit()

    return globals.db_conn

#*****************************************************************************


def db_connector(method):

    def wrapper(self, *args, **kwargs):
        res = None
        try:
            self.access_lock.acquire()

            if self.connect():
                try:
                    res = method(self, *args, **kwargs)
                except Exception, e:
                    self.log_exception(e)
                    self.disconnect()
        finally:
            self.access_lock.release()

        return res

    return wrapper


#*****************************************************************************


class DBase:

    connected = False
    access_lock = None
    db = None
    log = None

    #-------------------------------------------------------------------------

    def __init__(self):

        if globals.system_log == None:
            globals.system_log = logger.create("service")

        self.access_lock = threading.Lock()
        #self.connect()

    #-------------------------------------------------------------------------

    def __del__(self):
        self.disconnect()

    #-------------------------------------------------------------------------

    def log_exception(self, e):
        globals.system_log.error(e)

    #-------------------------------------------------------------------------

    def connect(self):
        try:
            if not self.connected:
                globals.system_log.info("Connecting to database host %s..." % (sys_config.DatabaseHost))
                self.db = self._connect()
                self.db.set_character_set('utf8')
                c = self.db.cursor()
                c.execute('SET NAMES utf8;')
                c.execute('SET CHARACTER SET utf8;')
                c.execute('SET character_set_connection=utf8;')
                globals.system_log.info("Database connection ok.")
                self.connected = True
            return True
        except Exception, e:
            self.log_exception(e)
            self.disconnect()
            return False

    #-------------------------------------------------------------------------

    def get_nad_from_tag(self, tag_name):
        import re
        try:
            return int(re.match("^c(\d+)\.", tag_name).group(1))
        except:
            return 0

    #-------------------------------------------------------------------------

    @db_connector
    def write_tag_values(self, tags, time_zone):
        records = []
        for tag, value in tags:
            nad = self.get_nad_from_tag(tag)
            records.append((nad, tag, value))

        self._write_tag_values(records, time_zone)

    #-------------------------------------------------------------------------

    @db_connector
    def update_tag_values(self, tags, time_zone):
        records = []
        for tag, value in tags:
            nad = self.get_nad_from_tag(tag)
            records.append((nad, tag, value))

        self._update_tag_values(records, time_zone)

    #-------------------------------------------------------------------------

    @db_connector
    def add_alarms_raised(self, tags, task_type, time_zone):
        records = []
        for tag, value, alarm_class, message, priority in tags:
            nad = self.get_nad_from_tag(tag)
            records.append((nad, tag, value, alarm_class, message, priority))

        self._add_alarms_raised(records, task_type, time_zone)

    #-------------------------------------------------------------------------

    @db_connector
    def update_alarms_gone(self, tags, time_zone):
        records = []
        for tag, value in tags:
            nad = self.get_nad_from_tag(tag)
            records.append((nad, tag, value))

        self._update_alarms_gone(records, time_zone)

    #-------------------------------------------------------------------------

    @db_connector
    def read_last_alarm_event_value(self, tag):
        return self._read_last_alarm_event_value(tag)

    #-------------------------------------------------------------------------

    def get_set_timezone_sql(self, time_zone):
        return self._get_set_timezone_sql(time_zone) if len(time_zone) != 0 else ""

    #-------------------------------------------------------------------------

    @db_connector
    def get_relay_session_data(self, session_id):
        return self._get_relay_session_data(session_id)

    #-------------------------------------------------------------------------

    @db_connector
    def get_relay_data(self):
        return self._get_relay_data()

    #-------------------------------------------------------------------------

    @db_connector
    def write_relay_data(self, data):
        self._write_relay_data(data)

    #-------------------------------------------------------------------------

    def disconnect(self):
        if self.db != None:
            self._disconnect()
        self.connected = False
        self.db = None

    #-------------------------------------------------------------------------


#*****************************************************************************


class DBaseMySQL(DBase):

    #-------------------------------------------------------------------------

    def _connect(self):
        return MySQLdb.connect(host = sys_config.DatabaseHost, user = sys_config.DatabaseUser, \
            passwd = sys_config.DatabasePassword, db = sys_config.DatabaseName)

    #-------------------------------------------------------------------------

    def _disconnect(self):
        self.db.close()

    #-------------------------------------------------------------------------

    def get_col_names(self, cursor):
        return [desc[0] for desc in cursor.description]

    #-------------------------------------------------------------------------

    def row_to_dict(self, cursor, row, col_names = None):
        import itertools
        if col_names == None:
            col_names = self.get_col_names(cursor)
        return dict(itertools.izip(col_names, row))

    #-------------------------------------------------------------------------
    # KROA no need to set session timezone as all times are saved as utc
    def _get_set_timezone_sql(self, time_zone):
        #return "SET SESSION time_zone='%s';" % (time_zone)
        return ""

    #-------------------------------------------------------------------------

    def _write_tag_values(self, records, time_zone):

        sql = self.get_set_timezone_sql(time_zone)
        sql += "INSERT INTO `%s` (`nad`,`tag`,`value`,`timestamp`) VALUES " % sys_config.DatabaseDataLoggerSamplesTable

        values = []
        for nad, tag, value in records:
            values.append('(%d,"%s","%s",UTC_TIMESTAMP())' % (nad, tag, value))

        sql += ",".join(values)

        c = self.db.cursor()
        c.execute(sql)

    #-------------------------------------------------------------------------

    def _update_tag_values(self, records, time_zone):

        sql = self.get_set_timezone_sql(time_zone)
        c = self.db.cursor()
        c.execute(sql)

        c = self.db.cursor()
        for rec in records:
            (nad, tag, value) = rec
            sql = "UPDATE `%s` SET `value`='%s', `timestamp`=UTC_TIMESTAMP() WHERE nad=%d AND tag='%s' ORDER BY `timestamp` DESC LIMIT 1" \
                % (sys_config.DatabaseDataLoggerSamplesTable, value, nad, tag)
            c.execute(sql)
            if self.db.affected_rows() == 0:
                sql = "INSERT INTO `%s` (`nad`,`tag`,`value`,`timestamp`) VALUES (%d,'%s','%s',UTC_TIMESTAMP())" % \
                    (sys_config.DatabaseDataLoggerSamplesTable, nad, tag, value)
                c.execute(sql)

    #-------------------------------------------------------------------------

    def _add_alarms_raised(self, records, task_type, time_zone):

        sql = self.get_set_timezone_sql(time_zone)
        sql += u"INSERT INTO `%s` (`type`, `nad`,`tag`,`value`,`timestamp_raise`,`class`,`message`,`priority`) VALUES " % sys_config.DatabaseDataLoggerAlarmsTable

        values = []
        for nad, tag, value, alarm_class, message, priority in records:
            values.append(u'(%d,%d,"%s","%s",UTC_TIMESTAMP(),"%s","%s",%d)' % (task_type, nad, tag, value, alarm_class, message, priority))

        sql += u",".join(values)

        c = self.db.cursor()
        c.execute(sql)

    #-------------------------------------------------------------------------

    def _update_alarms_gone(self, records, time_zone):

        sql = self.get_set_timezone_sql(time_zone)

        for nad, tag, value in records:
            sql += "UPDATE `%s` SET timestamp_gone=UTC_TIMESTAMP() WHERE nad=%d AND `tag`='%s' AND (`timestamp_gone`='0000-00-00 00:00:00' OR `timestamp_gone` IS NULL) ORDER BY `timestamp_raise` DESC LIMIT 1;" % \
                  (sys_config.DatabaseDataLoggerAlarmsTable, nad, tag)

        c = self.db.cursor()
        c.execute(sql)

    #-------------------------------------------------------------------------

    def _read_last_alarm_event_value(self, tag):

        sql = "SELECT `value`, `timestamp_gone` FROM `%s` WHERE `tag`='%s' ORDER BY `timestamp_raise` DESC LIMIT 1" % \
            (sys_config.DatabaseDataLoggerAlarmsTable, tag.name)

        c = self.db.cursor()
        c.execute(sql)

        row = c.fetchone()
        if row != None:
            (value, timestamp_gone) = row
            if timestamp_gone == None or timestamp_gone == "0000-00-00 00:00:00":
                return value

        return None

    #-------------------------------------------------------------------------

    def _get_relay_session_data(self, session_id):

        res = {
            "relay": None,
            "controllers": [],
        }
        c = self.db.cursor()

        c.execute("SELECT * FROM `%s` WHERE `session_id`=%d AND `enabled`=1" % (sys_config.DatabaseDataRelayDataTable, session_id))

        row = c.fetchone()
        if row != None:
            res["relay"] = self.row_to_dict(c, row)

            c.execute("SELECT * FROM `%s` WHERE `owner_id`=%d AND `active`=1" % (sys_config.DatabaseDataControllersTable, res["relay"]["user_id"]))
            col_names = self.get_col_names(c)

            for row in c.fetchall():
                res["controllers"].append(self.row_to_dict(c, row, col_names))

        return res

    #-------------------------------------------------------------------------

    def _get_relay_data(self):

        res = []

        c = self.db.cursor()
        c.execute("SELECT * FROM `%s` WHERE `enabled`=1" % (sys_config.DatabaseDataRelayDataTable))
        col_names = self.get_col_names(c)

        for row in c.fetchall():
            item = {
                "relay": self.row_to_dict(c, row, col_names),
                "controllers": [],
            }
            res.append(item)

        for item in res:
            c.execute("SELECT * FROM `%s` WHERE `owner_id`=%d AND `active`=1" % (sys_config.DatabaseDataControllersTable, item["relay"]["user_id"]))
            col_names = self.get_col_names(c)

            for row in c.fetchall():
                item["controllers"].append(self.row_to_dict(c, row, col_names))

        return res

    #-------------------------------------------------------------------------

    def _write_relay_data(self, data):

        import const

        last_message = data["last_message"].strftime(const.Timeformat) if data["last_message"] != None else "0000-00-00 00:00:00"

        c = self.db.cursor()
        sql = "UPDATE `%s` SET `message_count_tx`=`message_count_tx`+%d, `message_count_rx`=`message_count_rx`+%d, \
              `last_message`='%s', `last_controller_nad`=%d WHERE `user_id`=%d AND `session_id`=%d" % \
            (sys_config.DatabaseDataRelayDataTable, data["message_count_tx"], data["message_count_rx"], \
             last_message, data["last_controller_nad"], data["user_id"], data["session_id"])
        c.execute(sql)

    #-------------------------------------------------------------------------


#*****************************************************************************
