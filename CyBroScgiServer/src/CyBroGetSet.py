import sys, time
import json
import threading
import logger
import cybrocomm
import globals
import sys_status
import const
import cybrocontrollers
import udp_proxy

import alloc

import config
import tz_info

import transaction_pool

def pinger():
    globals.system_log = logger.create("service")
    globals.access_log = logger.create("access")

    globals.tz_info = tz_info.TimezoneInfo()
    globals.sys_status = sys_status.SystemStatus()
    globals.controllers = cybrocontrollers.CybroControllers()
    globals.config = config.GlobalConfig()
    globals.transaction_pool = transaction_pool.TransactionPool()

    globals.udp_proxy = udp_proxy.UDPProxy()
    globals.udp_proxy.start()

    controller = globals.controllers.create(17598, False)

    cybro_comm = cybrocomm.CybroComm(1, 17598)
    cybro_comm.controller = controller
    cybro_comm.data_received_event = threading.Event()

    # print("ping start")
    # cybro_comm.ping()
    # print("ping done")
    #
    # print("read status start")
    # cybro_comm.read_status()
    # print("read status done")

    print("read variable start")
    req_tag = transaction_pool.RequestTag("c17598.MyInt", const.ReadRequest)
    tag = controller.alloc.tags.get_by_name(req_tag.tag_name)
    if tag:
        req_tag.description = tag.description
        # add controller to list for later access triggering
        # try:
        #     controllers_to_trigger_read.index(controller)
        # except ValueError:
        #     controllers_to_trigger_read.append(controller)

        # set flags
        tag.read_request = True
        if req_tag.wait_for_request_complete:
            req_tag.request_pending = True
    else:
        req_tag.error_code = "ReqTagUnknownTag"

    alloce=None
    alloce = alloc.Allocation(17598)
    alloce.read()

    # cybro_comm.controller.__read_tags()
    tags = []
    tags.append(tag)
    result = cybro_comm.read_tag_values(tags)
    #print "Value %s" % (tags[0].value)
    result = cybro_comm.write_tag_values(tags, ["42"])
    result = cybro_comm.read_tag_values(tags)
    #print "Value %s" % (tags[0].value)
    #controller.read_alloc_file_immediately()
    #print "read variable done"


if __name__ == "__main__":
    #pinger()
    import argparse

    parser = argparse.ArgumentParser(description='Script command line tool.')
    parser.add_argument('tag', metavar='c17598.cybro_iw03', nargs='?',
                       help='Tag value name')
    parser.add_argument('--value', nargs='?', default='None',
                       help='Tag value to set')

    args = parser.parse_args()
    # print args

    tag = args.tag
    cybro_id = tag.split(".")[0][1:]
    tagValue = args.value

    data = {}
    data['tag'] = 
    data['value'] = 
    json_data = json.dumps(data)
    print(json_data)
