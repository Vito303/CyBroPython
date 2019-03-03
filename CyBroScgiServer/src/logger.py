import os
import sys_config
import globals
import logging
import logging.handlers


###########################################################################
#
#    Logger class

class DummyLogger:
    def info(self, s):
        pass

    def error(self, s):
        pass

    def warning(self, s):
        pass


def create(name):

    # normalize path name - on Win it will convert slashes to backslashes
    log_path = os.path.normpath(sys_config.LogDirectory)

    # make absolute path
    log_path = os.path.abspath(log_path)

    # add slash at the end of the path
    if (len(log_path) != 0) and (log_path[len(log_path) - 1] != os.path.sep):
        log_path += os.path.sep

    filename = log_path + name + ".log"

    log = logging.getLogger(name)

    # define custom levelnames
    logging.addLevelName(20, "Info")
    logging.addLevelName(30, "Warn")
    logging.addLevelName(40, "Err ")

    if len(log.handlers) == 0:
        msg_format = "%(asctime)s, %(levelname)s: %(message)s"

        if sys_config.LogEnable:
            # write to log file
            handler = logging.handlers.RotatingFileHandler(filename, \
                maxBytes = sys_config.MaxLogFilesize * 1024, backupCount = sys_config.LogBackupCount)

            formatter = logging.Formatter(msg_format)
            handler.setFormatter(formatter)
            log.addHandler(handler)

        #write to console
        if globals.enable_logged_console_output:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(msg_format)
            handler.setFormatter(formatter)
            log.addHandler(handler)

    log.setLevel(logging.DEBUG)

    return log
