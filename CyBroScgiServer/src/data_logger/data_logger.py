#!/usr/bin/python

import sys
import threading

sys.path.append("../db")
sys.path.append("../")
import db
import sys_config
import globals
import logger
import config
import controllers

#*****************************************************************************


class DataLoggerStatsEntry:

    type = 0
    tag_count = 0
    task_count = 0
    trigger_count = 0
    last_request_timestamp = None
    tags_ok = 0
    tags_err = 0
    status = "-"
    duration = 0

    #-------------------------------------------------------------------------

    def __init__(self, type):
        self.type = type

    #-------------------------------------------------------------------------

    def reset(self):
        self.tag_count = 0
        self.task_count = 0
        self.trigger_count = 0
        self.last_request_timestamp = None
        self.tags_ok = 0
        self.tags_err = 0
        self.status = "-"
        self.duration = 0

    #-------------------------------------------------------------------------


#*****************************************************************************


class DataLoggerStats:

    items = None

    #-------------------------------------------------------------------------

    def __init__(self):
        self.items = [
                DataLoggerStatsEntry(controllers.TaskTypeSamples),
                DataLoggerStatsEntry(controllers.TaskTypeAlarms),
                DataLoggerStatsEntry(controllers.TaskTypeEvents),
        ]

    #-------------------------------------------------------------------------

    def get_entry(self, type):
        return self.items[type]

    #-------------------------------------------------------------------------

    def reset(self):
        for item in self.items:
            item.reset()

    #-------------------------------------------------------------------------


#*****************************************************************************


class DataLogger(threading.Thread):

    db = None
    terminate_event = None
    cfg = None
    controllers = None
    stats = None

    #-------------------------------------------------------------------------

    def __init__(self):
        if globals.system_log == None:
            globals.system_log = logger.create("service")

        self.db = db.create_db_connection()

        self.controllers = controllers.Controllers(self.db)
        self.stats = DataLoggerStats()

        self.terminate_event = threading.Event()
        threading.Thread.__init__(self)

    #-------------------------------------------------------------------------

    def run(self):
        globals.system_log.info("DataLogger started.")

        self.cfg = config.Config(self.controllers)
        self.controllers.start()

        terminated = False
        while not terminated:
            self.terminate_event.wait(1)
            terminated = self.terminate_event.is_set()

        self.cfg.terminate()

        globals.system_log.info("DataLogger stopped.")

    #----------------------------------------------------------------------

    def terminate(self):
        self.controllers.terminate()
        self.terminate_event.set()

    #-------------------------------------------------------------------------

    def get_task_count(self, type):
        return self.stats.get_entry(type).task_count

    #-------------------------------------------------------------------------

    def get_tag_count(self, type):
        return self.stats.get_entry(type).tag_count

    #-------------------------------------------------------------------------

    def get_last_request_timestamp(self, type):
        return self.stats.get_entry(type).last_request_timestamp

    #-------------------------------------------------------------------------

    def get_tags_ok(self, type):
        return self.stats.get_entry(type).tags_ok

    #-------------------------------------------------------------------------

    def get_tags_err(self, type):
        return self.stats.get_entry(type).tags_err

    #-------------------------------------------------------------------------

    def get_trigger_count(self, type):
        return self.stats.get_entry(type).trigger_count

    #-------------------------------------------------------------------------

    def get_status(self, type):
        return self.stats.get_entry(type).status

    #-------------------------------------------------------------------------

    def get_duration(self, type):
        return self.stats.get_entry(type).duration

    #-------------------------------------------------------------------------


#*****************************************************************************


class DataLoggerIgniter:

    #-------------------------------------------------------------------------

    def __init__(self):
        import time

        data_logger = DataLogger()
        data_logger.start()

        try:
            while 1:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            pass

        data_logger.terminate()

    #-------------------------------------------------------------------------


#*****************************************************************************



if __name__ == "__main__":

    print
    print "CybroDataLogger (c) 2010-2013 Cybrotech Ltd. All rights reserved."
    print "-----------------------------------------------------------------"

    DataLoggerIgniter()

    """
    # How to use Django app from cybro_scgi_server
    import os
    sys.path.append("/home/eden/www/solar-cybro.com")
    os.environ['DJANGO_SETTINGS_MODULE'] = 'project.settings'
    from django.conf import settings
    from project.main.models import Plant, Page
    for p in Plant.objects.all():
        print p
    for p in Page.objects.all():
        print p
    """