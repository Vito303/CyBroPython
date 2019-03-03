#!/usr/bin/python

import sys
import threading

sys.path.append("../db")
sys.path.append("../")
import db
import sys_config
import globals
import logger

#*****************************************************************************


class DataDigger(threading.Thread):

    db = None
    terminate_event = None

    #-------------------------------------------------------------------------

    def __init__(self):
        if globals.system_log == None:
            globals.system_log = logger.create("service")

        if sys_config.DatabaseEngine == "mysql":
            self.db = db.DBaseMySQL()
        else:
            globals.system_log.error("Unknown DataLogger database engine: %s." % sys_config.DatabaseEngine)
            quit()

        self.terminate_event = threading.Event()
        threading.Thread.__init__(self)

    #-------------------------------------------------------------------------

    def run(self):
        globals.system_log.info("DataDigger started.")

        terminated = False
        while not terminated:
            self.terminate_event.wait(1)
            terminated = self.terminate_event.is_set()

        globals.system_log.info("DataDigger stopped.")

    #----------------------------------------------------------------------

    def terminate(self):
        self.terminate_event.set()

    #-------------------------------------------------------------------------


#*****************************************************************************


class DataDiggerIgniter():

    #-------------------------------------------------------------------------

    def __init__(self):
        import time

        data_digger = DataDigger()
        data_digger.start()

        try:
            while 1:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            pass

        data_digger.terminate()

    #-------------------------------------------------------------------------


#*****************************************************************************



if __name__ == "__main__":

    print
    print "CybroDataDigger (c) 2010 Cybrotech Ltd. All rights reserved."
    print "------------------------------------------------------------"

    DataDiggerIgniter()
