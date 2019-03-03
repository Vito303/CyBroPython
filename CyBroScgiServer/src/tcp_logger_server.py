import logging
import socket
import threading
import time
import thread
import globals

#*****************************************************************************


class TcpServerHandler(logging.Handler):

    queue = None
    queue_lock = None
    sock = None
    connection_list = None
    terminating = False

    #-------------------------------------------------------------------------

    def __init__(self, port):
        logging.Handler.__init__(self)

        self.queue = []
        self.queue_lock = threading.Lock()
        self.connection_list = []

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("localhost", port))
        self.sock.listen(10)
        self.sock.setblocking(0)
        self.sock.settimeout(0.2)

        thread.start_new_thread(self.accept_connection, ())
        thread.start_new_thread(self.process_connection, ())

    #-------------------------------------------------------------------------

    def emit(self, record):
        self.queue_lock.acquire()
        try:
            self.queue.append(self.format(record))
        finally:
            self.queue_lock.release()

    #-------------------------------------------------------------------------

    def close(self):
        self.terminating = True
        self.sock.close()

    #-------------------------------------------------------------------------

    def accept_connection(self):
        while not self.terminating:
            try:
                sockfd, addr = self.sock.accept()
                sockfd.setblocking(0)
                self.connection_list.append(sockfd)

                # send help text
                s = "\n" + "*" * 80 + "\n" + \
                    "Press Q <ENTER> to quit\n" + \
                    "Pres 1-5 <enter> to change reporting level (debug, info, warning, error, critical)\n" + \
                    "*" * 80 + "\n\n"
                sockfd.send(s)
            except:
                pass

            time.sleep(0.5)

    #-------------------------------------------------------------------------

    def close_connection(self, sock):
        self.connection_list.remove(sock)
        sock.close()

    #-------------------------------------------------------------------------

    def process_connection(self):

        while not self.terminating:

            # receive
            for sock in self.connection_list:
                try:
                    data = sock.recv(2048)
                    if data.strip().lower() == "q":
                        self.close_connection(sock)
                        continue
                    if data.strip() == "1":
                        globals.tcp_log_server.setLevel(logging.DEBUG)
                    elif data.strip() == "2":
                        globals.tcp_log_server.setLevel(logging.INFO)
                    elif data.strip() == "3":
                        globals.tcp_log_server.setLevel(logging.WARNING)
                    elif data.strip() == "4":
                        globals.tcp_log_server.setLevel(logging.ERROR)
                    elif data.strip() == "5":
                        globals.tcp_log_server.setLevel(logging.CRITICAL)
                except:
                    pass

            if len(self.queue):
                self.queue_lock.acquire()

                for sock in self.connection_list:
                    try:
                        for s in self.queue:
                            sock.send(s + "\n")
                    except:
                        self.close_connection(sock)
                        continue

                del self.queue[:]
                self.queue_lock.release()

            time.sleep(0.5)

    #-------------------------------------------------------------------------


#*****************************************************************************


#-----------------------------------------------------------------------------

def create(port):

    log = logging.getLogger("tcp_log_server")
    handler = TcpServerHandler(port)
    msg_format = "%(levelname)s: %(message)s"
    formatter = logging.Formatter(msg_format)
    handler.setFormatter(formatter)
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)

    return log

#-----------------------------------------------------------------------------
