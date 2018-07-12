#!/usr/bin/python

import logging
import os
import random
import socket
import struct
import time
from abc import ABCMeta, abstractmethod
from scapy.layers.inet import IP, IPerror, TCP, ICMP, TCPerror
from scapy.all import *

DEFAULT_TEST_DURATION = 10  # seconds
DEFAULT_TRANSFER_DIMENSION = 1024 * 1024  # Bytes
DEFAULT_BT_TRANSFER_DIMENSION = 16397  # Bytes
DEFAULT_HTTP_TRANSFER_DIMENSION = 260 + 9437184 + 2  # Bytes (header + file)
BITTORRENT_PORT = 6881
BITTORRENT_ALTERNATIVE_PORT = 51413
BITTORRENT_REQUEST_LENGTH = 13
BITTORRENT_REQUEST_TOTAL_LENGTH = 17
BITTORRENT_REQUEST_TYPE = 0x6
BITTORRENT_BLOCK_DIMENSION = 0x4000
BITTORRENT_PIECE_DIMENSION = 0x20000
BITTORRENT_START_INDEX = 0x0
BITTORRENT_START_OFFSET = 0x0
BITTORRENT_RESPONSE_LENGTH = 0x9
BITTORRENT_PIECE_TYPE = 0x7
NUMBER_OF_REQUESTS = 80
logger = logging.getLogger(__name__)


class Test(object):
    __metaclass__ = ABCMeta

    def __init__(self, transfer=DEFAULT_TRANSFER_DIMENSION):
        self.transfer_dimension = transfer

    @abstractmethod
    def send_on_socket(self, send_socket, data):
        pass

    @abstractmethod
    def receive_from_socket(self, receive_socket, length):
        pass

    @abstractmethod
    def uplink_test(self, send_socket, duration=DEFAULT_TEST_DURATION):
        pass

    @abstractmethod
    def downlink_test(self, receive_socket, intervals):
        pass

    @abstractmethod
    def uplink_traceroute(self, send_socket, icmp_socket, traceroute, stop_interfaces):
        pass

    @abstractmethod
    def downlink_traceroute(self, receive_socket):
        pass


class TCPTest(Test):
    __metaclass__ = ABCMeta

    def __init__(self, transfer=DEFAULT_TRANSFER_DIMENSION):
        Test.__init__(self, transfer)

    def send_on_socket(self, send_socket, data):
        to_send = len(data)
        i = 0
        while to_send != 0:
            sent = send_socket.send(data[i:])
            if sent == 0:
                break
            i += sent
            to_send -= sent

    def receive_from_socket(self, receive_socket, length, intervals=None):
        rec = ""
        while length > 0:
            try:
                msg = receive_socket.recv(length)
                if not msg:
                    logger.warning("Test: Receiving nothing, connection broken")
                    break
                if intervals is not None:
                    intervals[time.time()] = len(msg)
                length -= len(msg)
                rec += msg
            except socket.timeout as to:
                if intervals is None or len(rec) != 5:
                    raise to
                logger.info("Timeout occurred, measurement finished: %s" % to.message)
                break
        return rec

    def generate_random_bytes(self, n):
        rest = n % 4
        number = int(n / 4)
        string = ""
        for i in range(number):
            r = random.getrandbits(32)
            string += struct.pack("!I", r)
        if rest != 0:
            for i in range(rest):
                r = random.getrandbits(8)
                string += struct.pack("!B", r)
        return string


class TCPHTTPTest(TCPTest):
    def __init__(self, host, http_file, transfer_dimension=DEFAULT_HTTP_TRANSFER_DIMENSION):
        self.host = host
        self.http_file = http_file
        TCPTest.__init__(self, transfer_dimension)

    def downlink_test(self, receive_socket, intervals):
        receive_socket.settimeout(5)
        request = "GET /%s HTTP/1.1\r\nHost: %s\r\n\r\n" % (self.http_file, self.host)
        self.send_on_socket(receive_socket, request)
        start = time.time()
        intervals[start] = 0
        msg = self.receive_from_socket(receive_socket, self.transfer_dimension, intervals)
        stop = time.time()
        interval = stop - start
        total_rec = len(msg)
        logger.info("Received: %i, Interval: %f, Throughput: %f" % (total_rec, interval, (total_rec / interval)))

    def uplink_test(self, send_socket, duration=DEFAULT_TEST_DURATION):
        pass

    def downlink_traceroute(self, receive_socket):
        pass

    def uplink_traceroute(self, send_socket, icmp_socket, traceroute, stop_interfaces):
        pass


class TCPRandomTest(TCPTest):
    def __init__(self, transfer_dimension=DEFAULT_BT_TRANSFER_DIMENSION):
        Test.__init__(self, transfer_dimension)
        self.random_bytes_response = os.urandom(transfer_dimension * 1000)
        self.offset_response = 0
        self.random_bytes_request = os.urandom(BITTORRENT_REQUEST_TOTAL_LENGTH * NUMBER_OF_REQUESTS * 100)
        self.offset_request = 0

    def build_request(self):
        string = self.random_bytes_request[self.offset_request:self.offset_request + (BITTORRENT_REQUEST_TOTAL_LENGTH *
                                                                                      NUMBER_OF_REQUESTS)]
        self.offset_request += (BITTORRENT_REQUEST_TOTAL_LENGTH * NUMBER_OF_REQUESTS)
        if self.offset_request == len(self.random_bytes_request):
            self.offset_request = 0
        return string

    def build_response(self):
        string = ""
        for i in range(NUMBER_OF_REQUESTS):
            string += self.random_bytes_response[self.offset_response:self.offset_response +
                                                 DEFAULT_BT_TRANSFER_DIMENSION]
            self.offset_response += DEFAULT_BT_TRANSFER_DIMENSION
            if self.offset_response == len(self.random_bytes_response):
                self.offset_response = 0
        return string

    def __uplink_preparation(self, send_socket):
        self.receive_from_socket(send_socket, 68)
        handshake_send = self.generate_random_bytes(68)
        self.send_on_socket(send_socket, handshake_send)
        unchoke = self.generate_random_bytes(5)
        self.send_on_socket(send_socket, unchoke)
        self.receive_from_socket(send_socket, 5)

    def uplink_test(self, send_socket, duration=DEFAULT_TEST_DURATION):
        self.__uplink_preparation(send_socket)
        bytes_sent = 0
        stop = start = time.time()
        while stop - start < duration:
            # 80 pieces request
            self.receive_from_socket(send_socket, BITTORRENT_REQUEST_TOTAL_LENGTH * NUMBER_OF_REQUESTS)
            response = self.build_response()
            self.send_on_socket(send_socket, response)
            bytes_sent += len(response)
            stop = time.time()
        # stop test
        choke = self.generate_random_bytes(5)
        self.send_on_socket(send_socket, choke)

    def uplink_traceroute(self, send_socket, icmp_socket, traceroute, stop_interfaces):
        not_responding = 0
        send_socket.settimeout(5)
        icmp_socket.settimeout(2)
        unchoke = self.generate_random_bytes(5)
        self.send_on_socket(send_socket, unchoke)
        self.receive_from_socket(send_socket, 5)
        self.receive_from_socket(send_socket, 1360)
        response = self.build_response()
        ttl = send_socket.getsockopt(socket.SOL_IP, socket.IP_TTL)
        (peer_address, peer_port) = send_socket.getpeername()
        offset = 0
        for hop in range(1, 31):
            if not_responding > 3:
                break
            msg = response[offset:offset + 100]
            send_socket.setsockopt(socket.SOL_IP, socket.IP_TTL, hop)
            self.send_on_socket(send_socket, msg)
            send_socket.setsockopt(socket.SOL_IP, socket.IP_TTL, ttl)
            start = time.time()
            while True:
                try:
                    icmp_msg, address = icmp_socket.recvfrom(512)
                    host_address = address[0]
                    icmp_packet = IP(icmp_msg)
                    if ICMP in icmp_packet and icmp_packet[ICMP].type == 11:
                        if IPerror in icmp_packet and TCPerror in icmp_packet and \
                                icmp_packet[IPerror].dst == peer_address and icmp_packet[TCPerror].dport == peer_port:
                            if hop == len(traceroute) + 1:
                                traceroute[hop] = host_address
                                not_responding = 0
                    if time.time() - start > 2:
                        if hop == len(traceroute) + 1:
                            traceroute[hop] = "*"
                            if hop > 20:
                                not_responding += 1
                        break
                except (socket.error, socket.timeout):
                    if hop == len(traceroute) + 1:
                        traceroute[hop] = "*"
                        if hop > 20:
                            not_responding += 1
                    break
            offset = hop * 100
            if traceroute[hop] in stop_interfaces:
                break
        self.send_on_socket(send_socket, response[offset:])
        choke = self.generate_random_bytes(5)
        self.send_on_socket(send_socket, choke)
        return traceroute

    def __downlink_preparation(self, receive_socket):
        handshake_send = self.generate_random_bytes(68)
        self.send_on_socket(receive_socket, handshake_send)
        # receive handshake
        self.receive_from_socket(receive_socket, 68)
        # receive unchoke
        self.receive_from_socket(receive_socket, 5)
        # send interest
        interest = self.generate_random_bytes(5)
        self.send_on_socket(receive_socket, interest)

    def downlink_test(self, receive_socket, intervals):
        self.__downlink_preparation(receive_socket)
        receive_socket.settimeout(5)
        total_rec = 0
        start = time.time()
        intervals[start] = 0
        # send request (80 pieces of 0x4000 bytes) and receive response
        # if choke received (5 bytes), stop test
        while True:
            request = self.build_request()
            self.send_on_socket(receive_socket, request)
            rec = self.receive_from_socket(receive_socket, self.transfer_dimension * NUMBER_OF_REQUESTS, intervals)
            total_rec += len(rec)
            if len(rec) == 5:
                break
        stop = time.time() - 5
        interval = stop - start
        logger.info("Received: %i, Interval: %f, Throughput: %f" % (total_rec, interval, (total_rec / interval)))
        return intervals

    def downlink_traceroute(self, receive_socket):
        receive_socket.settimeout(15)
        # receive unchoke
        self.receive_from_socket(receive_socket, 5)
        # send interest
        interest = self.generate_random_bytes(5)
        self.send_on_socket(receive_socket, interest)
        request = self.build_request()
        self.send_on_socket(receive_socket, request)
        self.receive_from_socket(receive_socket, self.transfer_dimension * NUMBER_OF_REQUESTS)
        # receive choke
        self.receive_from_socket(receive_socket, 5)


class TCPBTTest(TCPTest):
    def __init__(self, transfer_dimension=DEFAULT_BT_TRANSFER_DIMENSION):
        Test.__init__(self, transfer_dimension)
        self.random_bytes = os.urandom(BITTORRENT_BLOCK_DIMENSION * 1000)
        self.offset = 0

    def build_request(self, index):
        offset = BITTORRENT_START_OFFSET
        request = ""
        for i in range(NUMBER_OF_REQUESTS):
            msg = struct.pack("!IBIII", BITTORRENT_REQUEST_LENGTH, BITTORRENT_REQUEST_TYPE, index, offset,
                              BITTORRENT_BLOCK_DIMENSION)
            request += msg
            offset += BITTORRENT_BLOCK_DIMENSION
            if offset == BITTORRENT_PIECE_DIMENSION:
                offset = BITTORRENT_START_OFFSET
                index += 0x1
        return index, request

    def generate_random_block(self):
        # return self.generate_random_bytes(BITTORRENT_BLOCK_DIMENSION)
        string = self.random_bytes[self.offset:self.offset + BITTORRENT_BLOCK_DIMENSION]
        self.offset += BITTORRENT_BLOCK_DIMENSION
        if self.offset == len(self.random_bytes):
            self.offset = 0
        return string

    def build_response(self, request):
        start = 0
        msg_len = BITTORRENT_RESPONSE_LENGTH + BITTORRENT_BLOCK_DIMENSION
        response = ""
        for i in range(len(request) / BITTORRENT_REQUEST_TOTAL_LENGTH):
            # Index and Offset positions in request, relatively to the start of the single request
            index = request[start + 5:start + 9]
            offset = request[start + 9:start + 13]
            response += struct.pack("!IB", msg_len, BITTORRENT_PIECE_TYPE) + index + offset +\
                        self.generate_random_block()
            start += BITTORRENT_REQUEST_TOTAL_LENGTH
        return response

    def uplink_test(self, send_socket, duration=DEFAULT_TEST_DURATION):
        send_socket.settimeout(5)
        self.__uplink_preparation(send_socket)
        bytes_sent = 0
        stop = start = time.time()
        while stop - start < duration:
            # 80 pieces request
            request = self.receive_from_socket(send_socket, 1360)
            response = self.build_response(request)
            self.send_on_socket(send_socket, response)
            bytes_sent += len(response)
            stop = time.time()
        # stop test
        choke = bytearray.fromhex("0000000100")
        self.send_on_socket(send_socket, choke)

    def __uplink_preparation(self, send_socket):
        self.receive_from_socket(send_socket, 68)
        handshake_send = bytearray.fromhex("13426974546f7272656e742070726f746f636f6c000000000000000031420a403f2ea" +
                                           "41c67aca80b46e956389a7f17b62d5452323832302d36333065666467316a677937")
        self.send_on_socket(send_socket, handshake_send)
        unchoke = bytearray.fromhex("0000000101")
        self.send_on_socket(send_socket, unchoke)
        self.receive_from_socket(send_socket, 5)

    def uplink_traceroute(self, send_socket, icmp_socket, traceroute, stop_interfaces):
        not_responding = 0
        send_socket.settimeout(5)
        icmp_socket.settimeout(2)
        unchoke = bytearray.fromhex("0000000101")
        self.send_on_socket(send_socket, unchoke)
        self.receive_from_socket(send_socket, 5)
        request = self.receive_from_socket(send_socket,  1360)
        response = self.build_response(request)
        ttl = send_socket.getsockopt(socket.SOL_IP, socket.IP_TTL)
        (peer_address, peer_port) = send_socket.getpeername()
        offset = 0
        for hop in range(1, 31):
            if not_responding > 3:
                break
            msg = response[offset:offset + 100]
            send_socket.setsockopt(socket.SOL_IP, socket.IP_TTL, hop)
            self.send_on_socket(send_socket, msg)
            send_socket.setsockopt(socket.SOL_IP, socket.IP_TTL, ttl)
            start = time.time()
            while True:
                try:
                    icmp_msg, address = icmp_socket.recvfrom(512)
                    host_address = address[0]
                    icmp_packet = IP(icmp_msg)
                    if ICMP in icmp_packet and icmp_packet[ICMP].type == 11:
                        if IPerror in icmp_packet and TCPerror in icmp_packet and \
                                icmp_packet[IPerror].dst == peer_address and icmp_packet[TCPerror].dport == peer_port:
                            if hop == len(traceroute) + 1:
                                traceroute[hop] = host_address
                                not_responding = 0
                    if time.time() - start > 2:
                        if hop == len(traceroute) + 1:
                            traceroute[hop] = "*"
                            if hop > 20:
                                not_responding += 1
                        break
                except (socket.error, socket.timeout):
                    if hop == len(traceroute) + 1:
                        traceroute[hop] = "*"
                        if hop > 20:
                            not_responding += 1
                    break
            offset = hop * 100
            if traceroute[hop] in stop_interfaces:
                break
        self.send_on_socket(send_socket, response[offset:])
        choke = bytearray.fromhex("0000000100")
        self.send_on_socket(send_socket, choke)
        return traceroute

    def downlink_test(self, receive_socket, intervals):
        receive_socket.settimeout(5)
        self.__downlink_preparation(receive_socket)
        index = 0x0
        total_rec = 0
        start = time.time()
        intervals[start] = 0
        # send request (80 pieces of 0x4000 bytes) and receive response
        # if choke received (5 bytes), stop test
        while True:
            index, requests = self.build_request(index)
            self.send_on_socket(receive_socket, requests)
            rec = self.receive_from_socket(receive_socket, self.transfer_dimension * NUMBER_OF_REQUESTS, intervals)
            total_rec += len(rec)
            if len(rec) == 5:
                break
        stop = time.time() - 5
        interval = stop - start
        logger.info("Received: %i, Interval: %f, Throughput: %f" % (total_rec, interval, (total_rec / interval)))
        return intervals

    def __downlink_preparation(self, receive_socket):
        handshake_send = bytearray.fromhex("13426974546f7272656e742070726f746f636f6c000000000000000031420a403f2ea" +
                                           "41c67aca80b46e956389a7f17b62d5452323832302d676b36317669687a6d623033")
        self.send_on_socket(receive_socket, handshake_send)
        # receive handshake
        self.receive_from_socket(receive_socket, 68)
        # receive unchoke
        self.receive_from_socket(receive_socket, 5)
        # send interest
        interest = bytearray.fromhex("0000000102")
        self.send_on_socket(receive_socket, interest)

    def downlink_traceroute(self, receive_socket):
        receive_socket.settimeout(15)
        # receive unchoke
        self.receive_from_socket(receive_socket, 5)
        # send interest
        interest = bytearray.fromhex("0000000102")
        self.send_on_socket(receive_socket, interest)
        index = 0x0
        index, requests = self.build_request(index)
        self.send_on_socket(receive_socket, requests)
        self.receive_from_socket(receive_socket, self.transfer_dimension * NUMBER_OF_REQUESTS)
        # receive choke
        self.receive_from_socket(receive_socket, 5)


class UDPTest(Test):
    def send_on_socket(self, send_socket, data):
        pass

    def receive_from_socket(self, receive_socket, length):
        pass

    def uplink_test(self):
        pass

    def downlink_test(self):
        pass


class UDPBTTest(UDPTest):
    def uplink_test(self):
        pass

    def downlink_test(self):
        pass
