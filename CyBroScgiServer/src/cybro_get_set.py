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

controller = None
cybro_comm = None
alloce = None

def init_controller(controller_id):
    globals.system_log = logger.create("service")
    globals.access_log = logger.create("access")

    globals.tz_info = tz_info.TimezoneInfo()
    globals.sys_status = sys_status.SystemStatus()
    globals.controllers = cybrocontrollers.CybroControllers()
    globals.config = config.GlobalConfig()
    globals.transaction_pool = transaction_pool.TransactionPool()

    globals.udp_proxy = udp_proxy.UDPProxy()
    globals.udp_proxy.start()

    global controller
    controller = globals.controllers.create(controller_id, False)

    global cybro_comm
    cybro_comm = cybrocomm.CybroComm(1, controller_id)
    cybro_comm.controller = controller
    cybro_comm.data_received_event = threading.Event()

    global alloce
    # read file alloc always
    controller.read_alloc_file_immediately()
    alloce = alloc.Allocation(controller_id)
    alloce.read()

def ping():
    return cybro_comm.pin

def read_status():
    return cybro_comm.read_status()

def create_tags(tag_name):
    req_tag = transaction_pool.RequestTag(tag_name, const.ReadRequest)
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

    # cybro_comm.controller.__read_tags()
    tags = []
    tags.append(tag)
    return tags

def read_tag(tag_name):
    tags = create_tags(tag_name)
    cybro_comm.read_tag_values(tags)
    return tags[0].value

def write_tag(tag_name, value):
    tags = create_tags(tag_name)
    result = cybro_comm.write_tag_values(tags, [value])
    return result

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Script command line tool.')
    parser.add_argument('tag', metavar='c17598.cybro_iw03', nargs='?', help='Tag value name')
    parser.add_argument('--value', nargs='?', default=None, help='Tag value to set')

    args = parser.parse_args()

    tag = args.tag
    cybro_id = tag.split(".")[0][1:]
    tagValue = args.value

    init_controller(int(cybro_id))

    data = {}
    data['tag'] = tag
    tag_value_readed = None
    if tagValue is not None:
        write_tag(tag, int(tagValue))
        data['value'] = "Value is written."
    else:
        tag_value_readed = read_tag(tag)
        data['value'] = tag_value_readed

    json_data = json.dumps(data)
    print(json_data)


