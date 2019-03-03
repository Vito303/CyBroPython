#!/usr/bin/python

import os, sys, socket
import sys_config

if __name__ == "__main__":

    # assume command line if environment variable is not set
    cgi_request = os.environ.has_key("QUERY_STRING")

    if cgi_request:
        # cgi request, read query string from environment variables
        query_string = os.environ["QUERY_STRING"]
        remote_addr = os.environ["REMOTE_ADDR"]
        remote_port = os.environ["REMOTE_PORT"]
        request_uri = os.environ["REQUEST_URI"]
    else:
        # command line, use first parameter as query string and default for others
        if len(sys.argv) > 1:
            query_string = sys.argv[1]
            remote_addr = "localhost"
            remote_port = "0"
            request_uri = '%s "%s"' % (sys.argv[0], query_string)
        else:
            print "Error: query string empty."
            quit()

    # format scgi request using lambda function
    scgi_req_value = lambda key, value: key + "\0" + value + "\0"

    # build scgi request with required fields
    scgi_request =  scgi_req_value("QUERY_STRING", query_string) + \
                    scgi_req_value("REMOTE_ADDR", remote_addr) + \
                    scgi_req_value("REMOTE_PORT", remote_port) + \
                    scgi_req_value("REQUEST_URI", request_uri)
    print scgi_request
    # connect to scgi server, create request and receive answer
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(("localhost", sys_config.ScgiServerPort))
        sock.send(scgi_request)
        data = sock.recv(16384)
        sock.close()
    except:
        print "Error: SCGI server at %s:%s not responding." % ("localhost", sys_config.ScgiServerPort)
        quit()

    # remove scgi header ("Status: 200 OK", "content-type")
    data = data.splitlines()
    if len(data) > 3:
        del data[0:3]
    data = ("\n").join(data)

    # create header for cgi request
    if cgi_request:
        print "Content-type: text/xml"
        print

    print data
