#!/usr/bin/python

import sys
import sys_config

ScgiServerExecutable = "cybro_scgi_server.py"

#-----------------------------------------------------------------------------

def is_server_running():
    import scgi_server
    return scgi_server.SCGIServerRequest().perform(["scgi_port_status"], 1) != None

#-----------------------------------------------------------------------------

def get_process_ids(name):

    import subprocess, os

    command = "ps -ef"
    process = subprocess.Popen(command, stdout=subprocess.PIPE, shell=True)
    #os.waitpid(process.pid, 0)
    lines = process.stdout.read().strip().split("\n")

    pids = []

    for line in lines:
        if line.find(name) != -1:
            import re
            m = re.search("^(\w*)\s*(\d*)\s*(\d*)\s*(.*)", line)
            if len(m.groups()) > 2:
                try:
                    pids.append(int(m.group(2)))
                except:
                    pass

    return pids

#-----------------------------------------------------------------------------

if __name__ == "__main__":

    # exit if server already running
    if is_server_running():
        print "Server already running."
        sys.exit()

    import os, signal, time, subprocess

    # try to kill all cybro_scgi_server processes, if exists
    pids = get_process_ids(ScgiServerExecutable)
    for pid in pids:
        os.kill(pid, signal.SIGKILL)

    # rest for a while
    time.sleep(1)

    # start server in background
    exe = "%s/%s" % (os.path.dirname(__file__), ScgiServerExecutable)
    p = subprocess.Popen(exe + " -s &", shell=True)
    sys.exit(os.waitpid(p.pid, 0)[1])

#-----------------------------------------------------------------------------
