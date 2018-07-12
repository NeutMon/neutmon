#!/usr/bin/python

import errno
import json
import logging
import socket
import struct
import traceback

DEFAULT_SERVER_ADDRESS = "localhost"
DEFAULT_HTTP_TEST_PATH = "http_test.txt"
SERVER_BINDING_ADDRESS = "0.0.0.0"
SERVER_PORT = 10000
BT_PORT = 6881
ALT_BT_PORT = 53674
TT_PORT = 54894
# ALT_BT_PORTS = range(50000, 65536)
BACKLOG_QUEUE_SIZE = 5
ROLE_SERVER = 0
ROLE_CLIENT = 1

CONTROLLER_START_UB_MSG = 0
CONTROLLER_START_UC_MSG = 1
CONTROLLER_START_DB_MSG = 2
CONTROLLER_START_DC_MSG = 3
CONTROLLER_START_UT_MSG = 4
CONTROLLER_START_DT_MSG = 5
CONTROLLER_SEND_META_DATA_MSG = 6
CONTROLLER_ABORT_MEASURE_MSG = 7
CONTROLLER_FINISH_MEASURE_MSG = 8
CONTROLLER_OK_MSG = 9
CONTROLLER_CLIENT_CONNECT_REFUSED_ERROR = 10  # Connection refused or reset or abort timeout on selected port
CONTROLLER_CLIENT_CONNECT_TIMEOUT_ERROR = 11  # Connection timeout on selected port
CONTROLLER_CLIENT_CONNECT_GENERIC_ERROR = 12  # Connection generic error
CONTROLLER_CLIENT_TEST_RESET_ERROR = 13  # Connection reset when testing
CONTROLLER_CLIENT_TEST_ABORT_ERROR = 14  # Connection aborted when testing
CONTROLLER_CLIENT_TEST_TIMEOUT_ERROR = 15  # Connection timeout when testing
CONTROLLER_CLIENT_TEST_GENERIC_ERROR = 16  # Generic error when testing
CONTROLLER_CLIENT_TEST_INIT_ERROR = 17  # Generic error when initialising tester

TESTER_OK = 9
TESTER_CONNECT_REFUSED_ERROR = 10
TESTER_CONNECT_TIMEOUT_ERROR = 11
TESTER_CONNECT_GENERIC_ERROR = 12
TESTER_TEST_RESET_ERROR = 13
TESTER_TEST_ABORT_ERROR = 14
TESTER_TEST_TIMEOUT_ERROR = 15
TESTER_TEST_GENERIC_ERROR = 16
TESTER_INIT_CLIENT_ERROR = 17
TESTER_INIT_SERVER_ERROR = 18
TESTER_ACCEPT_TIMEOUT_ERROR = 19
TESTER_ACCEPT_GENERIC_ERROR = 20

TEST_UPLINK_PHASE = 0
TEST_DOWNLINK_PHASE = 1

TEST_SPEEDTEST_TYPE = 0
TEST_TRACEROUTE_TYPE = 1

logger = logging.getLogger(__name__)


class Connector(object):
    def __init__(self):
        try:
            self.connector_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error:
            raise ConnectorException("Couldn't initialize socket")

    def connect(self, address, port, interface="", timeout=None):
        try:
            if timeout:
                self.connector_socket.settimeout(timeout)
            # Bind socket to interface
            if interface != "":
                self.connector_socket.setsockopt(socket.SOL_SOCKET, 25, interface)
            self.connector_socket.connect((address, port))
        except (socket.error, socket.timeout):
            raise ConnectorException("Couldn't connect to server %s on port %i" % (address, port))

    def close_connection(self):
        self.connector_socket.close()


class ConnectorException(Exception):
    pass


class Listener(object):
    def __init__(self):
        try:
            self.listening_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.listening_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.listening_socket.bind((SERVER_BINDING_ADDRESS, SERVER_PORT))
            self.listening_socket.listen(BACKLOG_QUEUE_SIZE)
        except socket.error:
            raise ListenerException("Couldn't initialize listener socket")

    def accept_connection(self):
        try:
            (client_socket, address) = self.listening_socket.accept()
        except socket.error:
            raise ListenerException("Error while accepting incoming connection")
        return client_socket, address

    def close_socket(self):
        self.listening_socket.close()


class ListenerException(Exception):
    pass


class Controller(object):
    def __init__(self, control_socket, role=ROLE_SERVER):
        if role != ROLE_SERVER and role != ROLE_CLIENT:
            raise WrongRoleException("Role %s does not exist" % role)
        self.__role = role
        self.control_socket = control_socket

    def send_control_msg(self, msg, extra=None):
        if msg not in range(CONTROLLER_START_UB_MSG, CONTROLLER_CLIENT_TEST_INIT_ERROR + 1):
            raise ControllerException("Message is not valid")
        if msg in range(CONTROLLER_START_UB_MSG, CONTROLLER_START_DT_MSG + 1):
            # extra is port number (integer)
            if self.__role != ROLE_SERVER:
                raise WrongRoleException("Trying to send a server message without being server")
            if extra is None or (extra != BT_PORT and extra != BT_PORT + 1 and extra not in [ALT_BT_PORT, TT_PORT]):
                raise ControllerException("Illegal or missing port number")
            try:
                Controller.send_msg_on_tcp_socket(self.control_socket, msg, str(extra))
            except socket.error, se:
                raise ControllerException("Controller socket error on sending message %i" % se.errno)
        elif msg in range(CONTROLLER_OK_MSG, CONTROLLER_CLIENT_TEST_INIT_ERROR + 1):
            # extra is result dictionary
            if self.__role != ROLE_CLIENT:
                raise WrongRoleException("Trying to send a client message without being client")
            try:
                if extra is None:
                    Controller.send_msg_on_tcp_socket(self.control_socket, msg)
                else:
                    Controller.send_msg_on_tcp_socket(self.control_socket, msg, json.dumps(extra, encoding="utf-8"))
            except socket.error, se:
                logger.error(traceback.format_exc())
                raise ControllerException("Controller socket error on sending message %i" % se.errno)
        elif msg in range(CONTROLLER_SEND_META_DATA_MSG, CONTROLLER_FINISH_MEASURE_MSG + 1):
            # no extra
            if self.__role != ROLE_SERVER:
                raise WrongRoleException("Trying to send a server message without being server")
            try:
                Controller.send_msg_on_tcp_socket(self.control_socket, msg)
            except socket.error, se:
                raise ControllerException("Controller socket error on sending message %i", se.errno)

    def abort_measure(self):
        self.send_control_msg(CONTROLLER_ABORT_MEASURE_MSG)

    def finish_measure(self):
        self.send_control_msg(CONTROLLER_FINISH_MEASURE_MSG)

    def recv_control_msg(self):
        try:
            msg, extra = Controller.recv_msg_from_tcp_socket(self.control_socket)
            if msg not in range(CONTROLLER_START_UB_MSG, CONTROLLER_CLIENT_TEST_INIT_ERROR + 1):
                raise ControllerException("Received message is not valid")
            if msg in range(CONTROLLER_START_UB_MSG, CONTROLLER_START_DT_MSG + 1):
                if extra is None:
                    raise ControllerException("Received message is %i but doesn't contain port" % msg)
                extra = int(extra)
                if extra != BT_PORT and extra != BT_PORT + 1 and extra not in [ALT_BT_PORT, TT_PORT]:
                    raise ControllerException("The specified port for a start measure message is not valid")
            elif msg in range(CONTROLLER_OK_MSG, CONTROLLER_CLIENT_TEST_INIT_ERROR + 1) and extra is not None:
                extra = json.loads(extra, encoding="utf-8")
        except socket.timeout, t:
            raise ControllerException("Controller socket timeout on receiving message: %s" % t.message)
        except socket.error, e:
            raise ControllerException("Controller socket error on receiving message: %s %i" % (e.message, e.errno))
        return msg, extra

    @staticmethod
    def recv_msg_from_tcp_socket(sock):
        to_recv_size = 4
        length = ""
        while to_recv_size != 0:
            msg = sock.recv(to_recv_size)
            if not msg:
                raise ControllerException("Receiving nothing, connection broken")
            length += msg
            to_recv_size -= len(msg)
        length = struct.unpack("!I", length)[0]
        logger.debug("Received message length: %i" % length)
        # if length not in [4, 8, 9]:
        #     raise ControllerException("Received message is not valid")
        op = ""
        to_recv_size = 4
        while to_recv_size != 0:
            msg = sock.recv(to_recv_size)
            if not msg:
                raise ControllerException("Receiving nothing, connection broken")
            op += msg
            to_recv_size -= len(msg)
        op = struct.unpack("!I", op)[0]
        logger.debug("Received operation: %i" % op)
        length -= 4
        if length != 0:
            port = ""
            while length != 0:
                msg = sock.recv(length)
                if not msg:
                    raise ControllerException("Receiving nothing, connection broken")
                port += msg
                length -= len(msg)
            if len(port) < 500:
                logger.debug("Received port: %s" % port)
        else:
            port = None
        return op, port

    @staticmethod
    def send_msg_on_tcp_socket(sock, op, port=None):
        if port is None:
            msg = struct.pack("!II", 4, op)
        else:
            msg = struct.pack("!II", 4 + len(port), op) + port
        to_send_size = len(msg)
        sent = 0
        logger.debug("Bytes to send: %i" % to_send_size)
        while sent != to_send_size:
            sent += sock.send(msg[sent:to_send_size])
            logger.debug("Bytes sent: %i" % sent)
            if not sent:
                raise ControllerException("Sending nothing, connection broken")


class WrongRoleException(Exception):
    pass


class ControllerException(Exception):
    pass


class Tester(object):
    def __init__(self, port, role=ROLE_SERVER, interface=""):
        if role != ROLE_SERVER and role != ROLE_CLIENT:
            raise WrongRoleException("Role %s does not exist" % role)
        self.__role = role
        self.__port = port
        if role == ROLE_SERVER:
            try:
                self.__listening_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.__listening_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self.__listening_socket.bind((SERVER_BINDING_ADDRESS, self.__port))
                self.__listening_socket.listen(1)
                self.__test_socket = None
                self.__test_address = None
            except socket.error, e:
                raise TesterException(TESTER_INIT_SERVER_ERROR,
                                      "Unable to open listening socket on port: %i" % self.__port, e.errno)
        else:
            try:
                self.__test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.__test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                # self.__test_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except socket.error, e:
                raise TesterException(TESTER_INIT_CLIENT_ERROR, "Unable to create socket for tests", e.errno)
        self.__icmp_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        self.__icmp_socket.setsockopt(socket.SOL_IP, socket.IP_HDRINCL, 1)
        if interface != "":
            self.__icmp_socket.setsockopt(socket.SOL_SOCKET, 25, interface)
        else:
            self.__icmp_socket.bind(("", port))
        self.__icmp_socket.settimeout(5)

    def accept_test_connection(self):
        if self.__role != ROLE_SERVER:
            raise WrongRoleException("Trying to accept not being server")
        try:
            self.__listening_socket.settimeout(5)
            (self.__test_socket, test_address) = self.__listening_socket.accept()
        except socket.timeout, t:
            raise TesterTimeoutException(TESTER_ACCEPT_TIMEOUT_ERROR, "No incoming connection on port %i" % self.__port,
                                         t.errno)
        except socket.error, e:
            raise TesterException(TESTER_ACCEPT_GENERIC_ERROR, "Error occurred in accepting incoming connection",
                                  e.errno)
        return self.__test_socket, test_address

    def connect(self, address, interface=""):
        if self.__role != ROLE_CLIENT:
            raise WrongRoleException("Trying to connect not being client")
        try:
            # self.__test_socket.bind(("", ALT_BT_PORT))
            if interface != "":
                self.__test_socket.setsockopt(socket.SOL_SOCKET, 25, interface)
            self.__test_socket.connect((address, self.__port))
        except socket.timeout, t:
            raise TesterTimeoutException(TESTER_CONNECT_TIMEOUT_ERROR, "Connection timeout for port %i" % self.__port,
                                         t.errno)
        except socket.error, e:
            if e.errno == errno.ECONNREFUSED or e.errno == errno.ECONNRESET or e.errno == errno.ECONNABORTED:
                raise TesterException(TESTER_CONNECT_REFUSED_ERROR,
                                      "Connection refused on port %i" % self.__port, e.errno)
            else:
                raise TesterException(TESTER_CONNECT_GENERIC_ERROR,
                                      "Unable to connect to server on port %i" % self.__port, e.errno)

    def do_test(self, test, phase, test_type, result, stop_interfaces, duration=0):
        try:
            if phase == TEST_UPLINK_PHASE:
                if test_type == TEST_SPEEDTEST_TYPE:
                    if duration == 0:
                        test.uplink_test(self.__test_socket)
                    else:
                        test.uplink_test(self.__test_socket, duration)
                elif test_type == TEST_TRACEROUTE_TYPE:
                    test.uplink_traceroute(self.__test_socket, self.__icmp_socket, result, stop_interfaces)
            elif phase == TEST_DOWNLINK_PHASE:
                if test_type == TEST_SPEEDTEST_TYPE:
                    test.downlink_test(self.__test_socket, result)
                elif test_type == TEST_TRACEROUTE_TYPE:
                    test.downlink_traceroute(self.__test_socket)
        except socket.timeout, e:
            raise TesterTimeoutException(TESTER_TEST_TIMEOUT_ERROR, "Connection timeout when receiving on port %i"
                                         % self.__port, e.errno)
        except socket.error, e:
            if e.errno == errno.ECONNRESET:
                raise TesterException(TESTER_TEST_RESET_ERROR, "Test failed due to connection reset", e.errno)
            elif e.errno == errno.ECONNABORTED:
                raise TesterException(TESTER_TEST_RESET_ERROR, "Test failed due to connection abort", e.errno)
            else:
                raise TesterException(TESTER_TEST_GENERIC_ERROR, "Test failed", e.errno)

    def close_test_connection(self):
        try:
            if self.__test_socket is not None:
                self.__test_socket.shutdown(socket.SHUT_RDWR)
                self.__test_socket.close()
        except socket.error as se:
            logger.warning("Error on shutdown: %s, %i" % (se.message, se.errno))

    def finish_test(self):
        try:
            if self.__test_socket is not None:
                self.__test_socket.close()
            if self.__role == ROLE_SERVER and self.__listening_socket is not None:
                self.__listening_socket.close()
        except socket.error as se:
            logger.warning("Error on shutdown: %s, %i" % (se.message, se.errno))


class TesterException(Exception):
    def __init__(self, error_code, message, error_errno):
        self.error = error_code
        self.errno = error_errno
        Exception.__init__(self, message)


class TesterTimeoutException(TesterException):
    pass
