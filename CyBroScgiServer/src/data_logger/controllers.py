import sys
import threading
import datetime, time
import re
from xml.dom import minidom

sys.path.append("../")
import sys_config
import globals
from scgi_server import SCGIServerRequest


#*****************************************************************************


TaskTypeSamples = 0
TaskTypeAlarms = 1
TaskTypeEvents = 2

ReadTypePeriod_sec = 0
ReadTypePeriod_min = 1
ReadTypePeriod_hour = 2
ReadTypePeriod_day = 3

PeriodStr = ['s', 'min', 'h', 'd']

MaxReadTagCount = 100


#*****************************************************************************


class Tag:
    name = ""
    cfg_task = None
    updateonly = False

    value = "0"
    prev_value = ""
    alarm_lo_active = False
    alarm_hi_active = False
    hash = 0

    #----------------------------------------------------------------------

    def __init__(self, name = ""):
        self.name = name
        self.hash = self.calc_hash(name)

    #-------------------------------------------------------------------------

    @staticmethod
    def calc_hash(name):
        import zlib
        return zlib.crc32(name)

    #----------------------------------------------------------------------

    def set_value(self, value):
        self.prev_value = self.value
        self.value = value

    #----------------------------------------------------------------------

    def is_binary_event(self):
        return self.cfg_task.lolimit == 0 and self.cfg_task.hilimit == 0

    #----------------------------------------------------------------------


#*****************************************************************************


class Task:
    tags = None
    type = 0
    period = 0
    period_type = 0
    last_trigger_time = 0
    tag_read_index = 0

    #----------------------------------------------------------------------

    def __init__(self, type, period, period_type):
        self.tags = []
        self.type = type
        self.period = period
        self.period_type = period_type

    #----------------------------------------------------------------------

    def add_tag(self, tag_cfg, cfg_task):
        tag = Tag(tag_cfg.name)
        tag.updateonly = tag_cfg.updateonly

        # check if exists
        for t in self.tags:
            if tag.hash == t.hash:
                return

        # add to list if not
        tag.cfg_task = cfg_task
        self.tags.append(tag)

    #----------------------------------------------------------------------

    def get_tags(self):
        cnt = len(self.tags)
        if cnt <= MaxReadTagCount:
            return self.tags
        else:
            if self.tag_read_index + MaxReadTagCount < cnt:
                res = self.tags[self.tag_read_index : self.tag_read_index + MaxReadTagCount]
                self.tag_read_index += MaxReadTagCount
            else:
                res = self.tags[self.tag_read_index : cnt] + self.tags[0 : MaxReadTagCount - cnt + self.tag_read_index]
                self.tag_read_index = MaxReadTagCount - cnt + self.tag_read_index

            return res

    #----------------------------------------------------------------------


#*****************************************************************************


class Tasks:
    items = None

    #----------------------------------------------------------------------

    def __init__(self):
        self.items = []

    #----------------------------------------------------------------------

    def get_task(self, type, period, period_type):
        for item in self.items:
            if item.type == type and item.period == period and item.period_type == period_type:
                return item

        item = Task(type, period, period_type)
        self.items.append(item)
        return item

    #----------------------------------------------------------------------

    def get_tasks_for_period(self, period_type):
        res = []
        for task in self.items:
            if task.period_type == period_type:
                res.append(task)
        return res

    #----------------------------------------------------------------------


#*****************************************************************************


class Controllers:
    list = None
    db = None
    req_count = 0
    last_request = None

    #----------------------------------------------------------------------

    def __init__(self, db):
        self.db = db
        self.clear()

    #----------------------------------------------------------------------

    def clear(self):
        self.list = []

    #----------------------------------------------------------------------

    def get_controller(self, nad):
        for c in self.list:
            if c.nad == nad:
                return c
        return None

    #----------------------------------------------------------------------

    def add_tag(self, type, tag, cfg_task):

        period = cfg_task.period
        try:
            nad = int(re.match("^c(\d+)\.", tag.name).group(1))
        except:
            nad = 0

        match = re.match("^(\d+)\s*(\w+)", period)
        if match:
            period = int(match.group(1))
            try:
                period_type = PeriodStr.index(match.group(2).lower())
            except:
                return
        else:
            return

        c = self.get_controller(nad)
        if c == None:
            c = Controller(nad, self.db)
            self.list.append(c)

        task = c.tasks.get_task(type, period, period_type)
        task.add_tag(tag, cfg_task)

    #----------------------------------------------------------------------

    def add_task(self, task):
        pass

    #----------------------------------------------------------------------

    def set_config(self, config):
        try:
            nad = int(re.match("^c(\d+)", config.nad).group(1))
        except:
            nad = 0

        c = self.get_controller(nad)
        if c != None:
            c.config = config

    #----------------------------------------------------------------------
    def start(self):
        for c in self.list:
            c.start()

    #----------------------------------------------------------------------

    def terminate(self):
        for c in self.list:
            c.terminate()
        self.clear()

    #----------------------------------------------------------------------


#*****************************************************************************


class Controller(threading.Thread):

    terminate_event = None
    nad = 0
    db = None
    tasks = None
    config = None

    #-------------------------------------------------------------------------

    def __init__(self, nad, db):
        self.nad = nad
        self.db = db
        self.tasks = Tasks()

        from config import ControllerConfig
        self.config = ControllerConfig()

        self.terminate_event = threading.Event()
        threading.Thread.__init__(self)

    #-------------------------------------------------------------------------

    def read_alarm_events_db_init_states(self):
        for task in self.tasks.items:
            if task.type in [TaskTypeAlarms, TaskTypeEvents]:
                for tag in task.tags:
                    value = self.db.read_last_alarm_event_value(tag)
                    if value != None:
                        tag.prev_value = value
                        tag.value = value
                        if not tag.is_binary_event():
                            # define which alarm limit is active if it's analog value
                            tag.alarm_lo_active = value < tag.cfg_task.lolimit
                            tag.alarm_hi_active = value > tag.cfg_task.hilimit

    #-------------------------------------------------------------------------

    def read_tags(self, tags):

        param_list = []
        updateonly_tags = []

        for tag in tags:
            # add only if not exists
            try:
                param_list.index(tag.name)
            except:
                param_list.append(tag.name)
                if tag.updateonly:
                    updateonly_tags.append(tag.name)

        if sys_config.DebugTcpServer:
            globals.tcp_log_server.info("datalogger:read_tags: %s" % param_list)

        try:
            # read data from scgi server
            data = SCGIServerRequest().perform(param_list, 5)

            if data == None:
                raise

            def get_key_value(node, key):
                sub_node = node.getElementsByTagName(key)
                return sub_node[0].firstChild.data if len(sub_node) != 0 else ""

            res_write = []
            res_update = []

            # parse xml data
            xml = minidom.parseString(data)

            tags_ok = 0
            tags_err = 0

            for var_node in xml.getElementsByTagName("var"):
                name = get_key_value(var_node, "name")
                value = get_key_value(var_node, "value")
                if value != "?":
                    try:
                        updateonly_tags.index(name)
                        res_update.append((name, value))
                    except:
                        res_write.append((name, value))

                    hash = Tag.calc_hash(name)
                    for tag in tags:
                        if tag.hash == hash:
                            tag.set_value(value)
                            tags_ok += 1
                            break
                else:
                    tags_err += 1

            return (res_write, res_update, tags_ok, tags_err)
        except:
            return ([], [], 0, 0)

    #-------------------------------------------------------------------------

    def read_sample_tags(self, tags):

        stats = globals.data_logger.stats.get_entry(TaskTypeSamples)
        stats.last_request_timestamp = globals.tz_info.get_utc_datetime()
        stats.trigger_count += 1

        total_tags_ok = 0
        total_tags_err = 0
        t_start = time.time()

        time_zone = globals.tz_info.get_timezone_str(self.nad)

        # if tag count less than max tag count, read it in one block
        if len(tags) <= MaxReadTagCount:
            (db_records_write, db_records_update, total_tags_ok, total_tags_err) = self.read_tags(tags)
            if len(db_records_write) != 0:
                self.db.write_tag_values(db_records_write, time_zone)
            if len(db_records_update) != 0:
                self.db.update_tag_values(db_records_update, time_zone)
        else:
            tag_list = tags
            while True:
                if len(tag_list) != 0:
                    (db_records_write, db_records_update, tags_ok, tags_err) = self.read_tags(tag_list[0 : MaxReadTagCount])
                    if len(db_records_write) != 0:
                        self.db.write_tag_values(db_records_write, time_zone)
                    if len(db_records_update) != 0:
                        self.db.update_tag_values(db_records_update, time_zone)
                    tag_list = tag_list[MaxReadTagCount :]
                    total_tags_ok += tags_ok
                    total_tags_err += tags_err
                else:
                    break

        stats.tags_ok = total_tags_ok
        stats.tags_err = total_tags_err
        stats.duration = int((time.time() - t_start) * 1000.0)
        stats.status = "error" if total_tags_ok == 0 and total_tags_err == 0 else "ok"

    #-------------------------------------------------------------------------

    def read_alarm_tags(self, tags, task_type):

        alarms_gone = []
        alarms_raised = []
        t_start = time.time()

        (db_records_write, db_records_update, tags_ok, tags_err) = self.read_tags(tags)

        stats = globals.data_logger.stats.get_entry(task_type)
        stats.last_request_timestamp = globals.tz_info.get_utc_datetime()
        stats.tags_ok = tags_ok
        stats.tags_err = tags_err
        stats.trigger_count += 1
        stats.status = "error" if tags_ok == 0 and tags_err == 0 else "ok"

        time_zone = globals.tz_info.get_timezone_str(self.nad)

        for tag_name, value in db_records_write:
            hash = Tag.calc_hash(tag_name)
            for t in tags:
                if t.hash == hash:
                    if t.prev_value != t.value:
                        if t.is_binary_event():
                            # assume it's binary tag
                            try:
                                value = int(t.value)
                            except:
                                value = 0

                            if value == 0:
                                alarms_gone.append((tag_name, value))
                            else:
                                alarms_raised.append((tag_name, value, t.cfg_task.alarm_class, t.cfg_task.message, t.cfg_task.priority))
                        else:
                            try:
                                value = float(t.value)
                            except:
                                value = 0

                            if t.alarm_lo_active or t.alarm_hi_active:
                                t.alarm_lo_active = t.alarm_lo_active and value < t.cfg_task.lolimit + t.cfg_task.hysteresis
                                t.alarm_hi_active = t.alarm_hi_active and value > t.cfg_task.hilimit - t.cfg_task.hysteresis
                                if not (t.alarm_lo_active or t.alarm_hi_active):
                                    alarms_gone.append((tag_name, value))
                            else:
                                t.alarm_lo_active = value < t.cfg_task.lolimit
                                t.alarm_hi_active = value > t.cfg_task.hilimit
                                if t.alarm_lo_active or t.alarm_hi_active:
                                    alarms_raised.append((tag_name, value, t.cfg_task.alarm_class, t.cfg_task.message))

                    break

        if len(alarms_raised) != 0:
            self.db.add_alarms_raised(alarms_raised, task_type, time_zone)

        if len(alarms_gone) != 0:
            self.db.update_alarms_gone(alarms_gone, time_zone)

        stats.duration = int((time.time() - t_start) * 1000.0)

    #-------------------------------------------------------------------------

    def run(self):

        terminated = False

        now = globals.tz_info.get_utc_datetime()
        last_trigger_1s = last_trigger_10s = last_trigger_30s = now.second
        last_trigger_1min = last_trigger_10min = now.minute
        last_trigger_1h = now.hour
        last_trigger_1d = now.day

        # read last alarms and events states from db
        self.read_alarm_events_db_init_states()

        while not terminated:
            now = globals.tz_info.get_utc_datetime()

            sample_tags = []

            # process seconds tasks
            if last_trigger_1s != now.second:
                for task in self.tasks.get_tasks_for_period(ReadTypePeriod_sec):
                    if (now.minute * 60 + now.second) % task.period == 0 and task.last_trigger_time != now.second:
                        if task.type == TaskTypeSamples:
                            sample_tags += task.tags
                        elif task.type == TaskTypeAlarms or task.type == TaskTypeEvents:
                            self.read_alarm_tags(task.get_tags(), task.type)
                        task.last_trigger_time = now.second
                last_trigger_1s = now.second

            # process minutes tasks
            if last_trigger_1min != now.minute:
                for task in self.tasks.get_tasks_for_period(ReadTypePeriod_min):
                    if (now.hour * 60 + now.minute) % task.period == 0 and task.last_trigger_time != now.minute:
                        if task.type == TaskTypeSamples:
                            sample_tags += task.tags
                        elif task.type == TaskTypeAlarms or task.type == TaskTypeEvents:
                            self.read_alarm_tags(task.get_tags(), task.type)
                        task.last_trigger_time = now.minute
                last_trigger_1min = now.minute

            # process hour tasks
            if last_trigger_1h != now.hour:
                for task in self.tasks.get_tasks_for_period(ReadTypePeriod_hour):
                    if (now.day * 24 + now.hour) % task.period == 0 and task.last_trigger_time != now.hour:
                        if task.type == TaskTypeSamples:
                            sample_tags += task.tags
                        elif task.type == TaskTypeAlarms or task.type == TaskTypeEvents:
                            self.read_alarm_tags(task.get_tags(), task.type)
                        task.last_trigger_time = now.hour
                last_trigger_1h = now.hour

            # process day tasks
            if last_trigger_1d != now.day:
                for task in self.tasks.get_tasks_for_period(ReadTypePeriod_day):
                    if now.day % task.period == 0 and task.last_trigger_time != now.day:
                        if task.type == TaskTypeSamples:
                            sample_tags += task.tags
                        elif task.type == TaskTypeAlarms or task.type == TaskTypeEvents:
                            self.read_alarm_tags(task.get_tags(), task.type)
                        task.last_trigger_time = now.day
                last_trigger_1d = now.day

            if len(sample_tags) != 0:
                self.read_sample_tags(sample_tags)

            self.terminate_event.wait(0.5)
            terminated = self.terminate_event.is_set()

    #----------------------------------------------------------------------

    def terminate(self):
        self.terminate_event.set()

    #-------------------------------------------------------------------------


#*****************************************************************************
