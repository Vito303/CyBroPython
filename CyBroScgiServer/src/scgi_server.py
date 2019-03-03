import threading, socket
import SocketServer, Queue
import globals
import transaction_pool
import const
import sys_config
import cybrocomm



###########################################################################
#
#    SCGI server request handler

class ThreadedTCPRequestHandler(SocketServer.BaseRequestHandler):

    def handle(self):

        if globals.terminating:
            self.write_response("")

        import time
        start = time.time()

        cur_thread = threading.currentThread()
        data = self.request.recv(16 * 1024)

        if sys_config.DebugTcpServer:
            globals.tcp_log_server.info("ThreadedTCPRequestHandler request: " + data)

        if sys_config.UseHTTPProtocol:
            
            lines = data.split("\n")

            def get_param(lines, name):
                for line in lines:
                    n = line.find(name)
                    if n == 0:
                        return line[len(name) + 1 :].strip()
                return ""

            env = {}
            s = get_param(lines, "GET")
            # strip "HTTP/1.0" from the end of string
            params = s.split(" ")
            if len(params) > 0:
                s = params[0]

            env["REQUEST_URI"] = s
            # strip "/?" from the beginning
            if s.find("/?") == 0:
                s = s[2:]
            env["QUERY_STRING"] = s
            env["REMOTE_ADDR"] = get_param(lines, "X-Forwarded-For:")
            env["REMOTE_PORT"] = "0"
            
        else:
            # parse environment
            
            items = data.split("\0")
            items = items[:-1]

            assert len(items) % 2 == 0, "malformed headers"

            env = {}
            for i in range(0, len(items), 2):
                env[items[i]] = items[i+1]

        # Read arguments
        argstring = env['QUERY_STRING']
        # if len(argstring) == 0:
        #    argstring = str(env['REQUEST_URI']).replace("/scgi/?", "")

        # Break argument string into list of pairs like "name=value"
        arglist = argstring.split('&')

        response = ""

        globals.access_log.info("%s:%s %s" % (env["REMOTE_ADDR"], env["REMOTE_PORT"], env["REQUEST_URI"]))

        req_tags = []

        for arg in arglist:
            arg = arg.split('=')

            if len(arg) == 1:
                # read request
                tag_name = arg[0]

                if len(tag_name) != 0:
                    # check if tag is already on the list and add it if it's not
                    tag_exists = False
                    for tag in req_tags:
                        if tag.name.lower() == tag_name.lower() and tag.request == const.ReadRequest:
                            tag_exists = True
                            break
                    # ignore it if already exists
                    if not tag_exists:
                        tag = transaction_pool.RequestTag(tag_name, const.ReadRequest)
                        req_tags.append(tag)
            elif len(arg) == 2:
                # write request
                (tag_name, value) = arg

                if len(tag_name) != 0 and len(value) != 0:
                    tag_read_req_exists = False
                    for tag in req_tags:
                        if tag.name.lower() == tag_name.lower():
                            if tag.request == const.WriteRequest:
                                # if tag request exists, remove it
                                req_tags.remove(tag)
                            elif tag.request == const.ReadRequest:
                                tag_read_req_exists = True

                    tag = transaction_pool.RequestTag(tag_name, const.WriteRequest)
                    tag.value = value
                    req_tags.append(tag)

                    if not tag_read_req_exists:
                        tag = transaction_pool.RequestTag(tag_name, const.ReadRequest)
                        req_tags.append(tag)

        globals.sys_status.scgi_request_count += 1

        globals.sys_status.scgi_request_begin()
        try:
            globals.transaction_pool.create_request(req_tags)
        finally:
            globals.sys_status.scgi_request_end()

        response += self.values_to_xml(req_tags, time.time() - start)

        self.write_response(response)

    #-------------------------------------------------------------------------

    def values_to_xml(self, req_tags, time):
        xml = "<?xml version=\"1.0\" encoding=\"ISO-8859-1\"?>\r\n"
        xml += "<data>\r\n"

        if len(req_tags) == 0:
            tag = transaction_pool.RequestTag('', const.ReadRequest)
            tag.error_code = transaction_pool.ReqTagDeviceNotFound
            req_tags.append(tag)

        for tag in req_tags:
            if tag.request == const.ReadRequest:
                if tag.valid:
                    value = tag.value
                else:
                    value = "?"

                if tag.error_code != transaction_pool.ReqTagNoError:
                    error_code = "    <error_code>%d</error_code>\r\n" % tag.error_code
                else:
                    error_code = ""

                xml += "  <var>\r\n" \
                       "    <name>%s</name>\r\n" \
                       "    <value>%s</value>\r\n" \
                       "%s" \
                       "    <description>%s</description>\r\n" \
                       "  </var>\r\n" % \
                    (tag.name, value, error_code, tag.description)

        if sys_config.DebugPrints:
            xml += "  <request_time>%f</request_time>\r\n" % \
                   (time)

        xml += "</data>\r\n"
        return xml

    #-------------------------------------------------------------------------

    def write_response(self, content):
        self.request.send(content)

    #-------------------------------------------------------------------------


class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    allow_reuse_address = True



###########################################################################
#
#    SCGI server


class SCGIServer:

    server_thread = None
    server = None

    #-------------------------------------------------------------------------

    def start(self):

        HOST, PORT = "localhost", sys_config.ScgiServerPort

        self.server = ThreadedTCPServer((HOST, PORT), ThreadedTCPRequestHandler)
        ip, port = self.server.server_address

        # Start a thread with the server -- that thread will then start one
        # more thread for each request
        self.server_thread = threading.Thread(target = self.server.serve_forever)
        # Exit the server thread when the main thread terminates
        self.server_thread.daemon = True
        self.server.daemon_threads = True
        self.server_thread.start()

        globals.system_log.info("SCGIServer started.")

    #-------------------------------------------------------------------------

    def terminate(self):
        globals.system_log.info("SCGIServer stopped.")

    #-------------------------------------------------------------------------


#----------------------------------------------------------------------


###########################################################################
#
#    SCGI server


class SCGIServerRequest:

    #-------------------------------------------------------------------------

    @staticmethod
    def perform(params, timeout=1):

        data = None

        import socket
        query_string = "&".join(params)
        headers = [
            "CONTENT_LENGTH", "0",
            "QUERY_STRING", query_string,
            "REMOTE_ADDR", "localhost",
            "REMOTE_PORT", "%d" % sys_config.ScgiServerPort,
            "REQUEST_URI", "?" + query_string,
        ]

        headers = "\0".join(headers) + "\0"
        headers = "%d:%s," % (len(headers), headers)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            try:
                sock.connect(("localhost", sys_config.ScgiServerPort))
                sock.send(headers)
                data = ""

                while True:
                    rx = sock.recv(1024)
                    if len(rx):
                        data += rx
                    else:
                        break
                sock.close()
            except:
                pass
        except socket.error:
            pass

        if data and len(data):
            #reject HTTP header data if exists
            lines = data.split("\n")
            if len(lines) != 0 and lines[0].find("Status") == 0:
                lines = lines[3:]
                data = "\n".join(lines)

        return data

    #-------------------------------------------------------------------------


#----------------------------------------------------------------------
