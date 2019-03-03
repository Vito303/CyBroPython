import os
import sys
import re
import threading

import controllers
sys.path.append("../")
import sys_config
import globals


AlarmPriorityLow = 0
AlarmPriorityMedium = 1
AlarmPriorityHigh = 2

#*****************************************************************************


def get_key_value(node, key, default = ""):
    sub_node = node.getElementsByTagName(key)
    return sub_node[0].firstChild.data if len(sub_node) != 0 else default

#-----------------------------------------------------------------------------

def str_to_int(value, default = 0):
    try:
        return int(value)
    except:
        return default

#*****************************************************************************


class TagCfg:
    name = None
    updateonly = False

    #----------------------------------------------------------------------

    def __init__(self, name = ""):
        self.name = name

    #----------------------------------------------------------------------

    def __str__(self):
        return "%s [updateonly: %s]" % (self.name, self.updateonly)

    #----------------------------------------------------------------------

    def assign(self, source):
        self.name = source.name
        self.updateonly = source.updateonly

    #----------------------------------------------------------------------


#*****************************************************************************


class SampleTask:
    period = ""
    tags = None
    enabled = True

    #----------------------------------------------------------------------

    def __init__(self, node = None, lists = None):
        self.tags = []

        if node != None:
            self.assign_from_xml_node(node, lists)

    #----------------------------------------------------------------------

    def __str__(self):
        return "task period: %s\n" % self.period + \
               "tags: %s" % self.tags

    #----------------------------------------------------------------------

    def add_tag(self, tag):
        # check if tag is already added to task
        for t in self.tags:
            if tag.name == t.name:
                return
        self.tags.append(tag)

    #----------------------------------------------------------------------

    def create_tags_from_list(self, tag, list_group_name, list_group):
        subst = "{%s}" % list_group_name
        if tag.name.find(subst) != -1:
            res = []
            for s in list_group:
                new_tag = TagCfg()
                new_tag.assign(tag)
                new_tag.name = new_tag.name.replace(subst, s)
                res.append(new_tag)
            return res
        return []

    #----------------------------------------------------------------------

    def add_tags_ex(self, tags, lists):
        for tag in tags:
            # check if tag has lists
            if tag.name.find("{") != -1:
                for key in lists.iterkeys():
                    expanded_tags = self.create_tags_from_list(tag, key, lists[key])
                    self.add_tags_ex(expanded_tags, lists)
            else:
                # just add it
                self.add_tag(tag)

    #----------------------------------------------------------------------

    def add_tags(self, tags, lists):
        self.add_tags_ex(tags, lists)
        self.tags = sorted(self.tags, key = lambda tag: tag.name)

    #----------------------------------------------------------------------

    def assign_from_xml_node(self, node, lists):
        enabled = get_key_value(node, "enabled", "true")

        self.enabled = enabled.lower() in ["true", "1"]

        self.period = get_key_value(node, "period", "1min")
        tags = []
        for var in node.getElementsByTagName("variable"):
            tag = TagCfg(var.firstChild.data)
            tag.updateonly = var.attributes.has_key("updateonly") and var.attributes["updateonly"].value.lower() == "true"
            tags.append(tag)

        self.add_tags(tags, lists)

    #----------------------------------------------------------------------


#*****************************************************************************


class AlarmTask(SampleTask):
    alarm_class = ""
    message = ""
    lolimit = 0
    hilimit = 0
    hysteresis = 0
    priority = AlarmPriorityLow

    #----------------------------------------------------------------------

    def __str__(self):
        return "task period: %s\n" % self.period + \
               "alarm_class: %s\n" % self.alarm_class + \
               "lolimit: %d\n" % self.lolimit + \
               "hilimit: %d\n" % self.hilimit + \
               "hysteresis: %d\n" % self.hysteresis + \
               "priority: %d\n" % self.priority + \
               "tags: %s" % self.tags

    #----------------------------------------------------------------------

    def assign_from_xml_node(self, node, lists):
        self.alarm_class = get_key_value(node, "class", "warning")
        self.message = get_key_value(node, "message", "")
        self.lolimit = str_to_int(get_key_value(node, "lolimit"))
        self.hilimit = str_to_int(get_key_value(node, "hilimit"))
        self.hysteresis = str_to_int(get_key_value(node, "hysteresis"))

        try:
            self.priority = ["low", "medium", "high"].index(get_key_value(node, "priority", "low"))
        except:
            self.priority = AlarmPriorityLow

        SampleTask.assign_from_xml_node(self, node, lists)

    #----------------------------------------------------------------------


#*****************************************************************************


class EventTask(AlarmTask):
    pass


#*****************************************************************************

class ControllerConfig:
    nad = "";

#*****************************************************************************


class Config:

    terminating = False
    check_file_timer = None
    config_file_timestamp = 0
    controllers = None

    #-------------------------------------------------------------------------

    def __init__(self, controllers):
        self.controllers = controllers
        self.read()
        self.start_check_file_timer()

    #-------------------------------------------------------------------------

    def __del__(self):
        self.check_file_timer.cancel()

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

    def read_config_timestamp(self):
        old_timestamp = self.config_file_timestamp
        self.config_file_timestamp = os.stat(sys_config.DataLoggerConfig).st_mtime
        return self.config_file_timestamp == old_timestamp

    #-------------------------------------------------------------------------

    def read(self):
        globals.system_log.info("Reading %s" % sys_config.DataLoggerConfig)
        self.read_config_timestamp()

        globals.data_logger.stats.reset()

        try:
            data = open(sys_config.DataLoggerConfig).read()
        except:
            return

        from xml.dom import minidom
        try:
            xml = minidom.parseString(data)
        except Exception, e:
            globals.system_log.error("%s: %s" % (sys_config.DataLoggerConfig, e))
            return


        # read lists
        lists = {}
        for list in xml.getElementsByTagName("list"):
            for group in list.getElementsByTagName("group"):
                items = []
                for item in group.getElementsByTagName("item"):
                    items.append(item.firstChild.data)
                lists[get_key_value(group, "name")] = items

        # read samples
        samples = []
        for sample_node in xml.getElementsByTagName("sample"):
            for task_node in sample_node.getElementsByTagName("task"):
                task = SampleTask(node = task_node, lists = lists)
                if task.enabled:
                    samples.append(task)

        # read alarms
        alarms = []
        for alarm_node in xml.getElementsByTagName("alarm"):
            for task_node in alarm_node.getElementsByTagName("task"):
                task = AlarmTask(node = task_node, lists = lists)
                if task.enabled:
                    alarms.append(task)

        # read events
        events = []
        for event_node in xml.getElementsByTagName("event"):
            for task_node in event_node.getElementsByTagName("task"):
                task = EventTask(node = task_node, lists = lists)
                if task.enabled:
                    events.append(task)

        # read controller configuration
        controller_cfg = []
        for cfg_node in xml.getElementsByTagName("plc"):
            for controller_node in cfg_node.getElementsByTagName("cybro"):
                nad = get_key_value(controller_node, "name", "")
                if len(nad) != 0:
                    cfg = ControllerConfig()
                    cfg.nad = nad
                    controller_cfg.append(cfg)

        for task in samples:
            for tag in task.tags:
                self.controllers.add_tag(controllers.TaskTypeSamples, tag, task)
            globals.data_logger.stats.get_entry(controllers.TaskTypeSamples).tag_count += len(task.tags)

        for task in alarms:
            for tag in task.tags:
                self.controllers.add_tag(controllers.TaskTypeAlarms, tag, task)
            globals.data_logger.stats.get_entry(controllers.TaskTypeAlarms).tag_count += len(task.tags)

        for task in events:
            for tag in task.tags:
                self.controllers.add_tag(controllers.TaskTypeEvents, tag, task)
            globals.data_logger.stats.get_entry(controllers.TaskTypeEvents).tag_count += len(task.tags)

        globals.data_logger.stats.get_entry(controllers.TaskTypeSamples).task_count = len(samples)
        globals.data_logger.stats.get_entry(controllers.TaskTypeAlarms).task_count = len(alarms)
        globals.data_logger.stats.get_entry(controllers.TaskTypeEvents).task_count = len(events)

        for cfg in controller_cfg:
            self.controllers.set_config(cfg)

    #-------------------------------------------------------------------------

    def check_file_for_changes(self):

        if self.terminating:
            return

        if not self.read_config_timestamp():
            globals.system_log.info("DataLogger configuration file changed, reloading...")
            self.controllers.terminate()
            self.read()
            self.controllers.start()

        self.start_check_file_timer()

    #-------------------------------------------------------------------------


#*****************************************************************************
