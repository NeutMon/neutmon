#!/usr/bin/python

import argparse
import json
import logging
import multiprocessing
import Queue
import sys
import time
import zmq

from neutmon import handlers
from neutmon import test


class MetadataProducer(multiprocessing.Process):
    def __init__(self, interface, execution, commands_queue, results_queue):
        multiprocessing.Process.__init__(self)
        self.interface = interface
        self.execution = execution
        self.commands = commands_queue
        self.results = results_queue

    def run(self):
        context = zmq.Context()
        socket = context.socket(zmq.SUB)
        socket.connect("tcp://172.17.0.1:5556")
        topic_filter = ""  # ""MONROE.META.DEVICE.MODEM"
        socket.setsockopt(zmq.SUBSCRIBE, topic_filter)
        socket.setsockopt(zmq.RCVTIMEO, 1000)
        meta_data = dict()
        interface_meta = dict()
        gps_meta = dict()
        while True:
            msg = ""
            try:
                msg = socket.recv()
            except Exception as e:
                print e.message
            msg = msg.split(None, 1)
            if len(msg) == 2:
                if "MODEM" in msg[0]:
                    interface = json.loads(msg[1])
                    if "InternalInterface" in interface:
                        interface_meta[time.time()] = interface
                elif "GPS" in msg[0]:
                    gps_meta[time.time()] = json.loads(msg[1])
            try:
                command = self.commands.get(False)
                if command:
                    break
            except Queue.Empty:
                pass
        meta_data["interface"] = interface_meta
        meta_data["gps"] = gps_meta
        try:
            with open("/tmp/paris_" + self.interface + "_" + str(self.execution) + ".txt", "r") as f:
                paris = f.read()
                meta_data["paris"] = paris
        except IOError, ioe:
            print ioe.message
        try:
            with open("/tmp/tracebox_6881_" + self.interface + "_" + str(self.execution) + ".txt", "r") as f:
                tracebox = f.read()
                meta_data["tracebox_6881"] = json.loads(tracebox)
        except IOError, ioe:
            print ioe.message
        try:
            with open("/tmp/tracebox_53674_" + self.interface + "_" + str(self.execution) + ".txt", "r") as f:
                tracebox = f.read()
                meta_data["tracebox_53674"] = json.loads(tracebox)
        except IOError, ioe:
            print ioe.message
        self.results.put(meta_data)


def main(argv):
    parser = argparse.ArgumentParser(description="NeutMon client. Performs speed and traceroute tests to check if "
                                                 "ISPs are differentiating traffic.")
    parser.add_argument("-m", "--monroe", help="run on monroe node with interface discovery", action="store_true")
    parser.add_argument("-i", "--interface", help="specify the network interface for tests. mandatory if -m is"
                                                  " specified")
    parser.add_argument("-o", "--operator", help="specify the network operator. currently not implemented")
    parser.add_argument("-d", "--duration", help="specify speedtest duration (in seconds)", type=int)
    parser.add_argument("-e", "--execution", help="when executed in monroe, specifies the execution number", type=int)
    parser.add_argument("-s", "--server", help="server address. if not specified server defaults to localhost")
    parser.add_argument("-p", "--port", help="server port. if not specified server port defaults to 10000")
    parser.add_argument("-S", "--stop", help="stop traceroute when the interface(s) specified is (are) encountered")
    parser.add_argument("-t", "--http", help="execute HTTP test before the NeutMon tests", action="store_true")
    parser.add_argument("-f", "--file", help="http test file. if not specified file defaults to http_test.txt")
    parser.add_argument("-l", "--log", help="set the logging level. possible values are DEBUG, INFO, WARNING, ERROR,"
                                            "and CRITICAL. if not specified the default value is WARNING")
    parser.add_argument("-g", "--logfile", help="set the output file for logs. the default value is neutmon_client.log")
    parser.add_argument("-v", "--verbose", help="if set logs are also printed on the standard output",
                        action="store_true")
    args = parser.parse_args()
    if args.log:
        if args.log == "DEBUG":
            log_level = logging.DEBUG
        elif args.log == "INFO":
            log_level = logging.INFO
        elif args.log == "WARNING":
            log_level = logging.WARNING
        elif args.log == "ERROR":
            log_level = logging.ERROR
        elif args.log == "CRITICAL":
            log_level = logging.CRITICAL
        else:
            log_level = logging.WARNING
    else:
        log_level = logging.WARNING
    if args.logfile:
        log_file = args.logfile
    else:
        log_file = "neutmon_client.log"
    logger = logging.getLogger("neutmon")
    logger.setLevel(log_level)
    log_formatter = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] \t%(message)s')
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)
    if args.verbose:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(log_formatter)
        logger.addHandler(console_handler)
    logger.info("Neutmon client started")

    if args.interface:
        interfaces = args.interface.split("|")
        for i in interfaces:
            logger.info("Testing interface %s" % i)
        if args.monroe:
            if len(interfaces) == 1 and interfaces[0] == "":
                logger.critical("No interfaces are provided")
                exit(1)
    else:
        if args.monroe:
            logger.critical("No interfaces are provided")
            exit(1)
        else:
            interfaces = [""]
    if args.server:
        server_address = args.server
    else:
        server_address = handlers.DEFAULT_SERVER_ADDRESS
    if args.port:
        server_port = args.port
    else:
        server_port = handlers.SERVER_PORT
    if args.duration:
        duration = args.duration
    else:
        duration = 0
    if args.stop:
        stop_interfaces = args.stop.split("|")
    else:
        stop_interfaces = []
    if args.monroe and not args.execution:
        logger.critical("In MONROE mode the execution number must be provided")
        exit(1)

    for interface in interfaces:
        bt_test = test.TCPBTTest()
        ct_test = test.TCPRandomTest()
        if args.monroe:
            manager = multiprocessing.Manager()
            commands_queue = manager.Queue()
            results_queue = manager.Queue()
            mp = MetadataProducer(interface, args.execution, commands_queue, results_queue)
            mp.start()
        http_result = dict()
        if args.http:
            if args.file:
                http_file = args.file
            else:
                http_file = handlers.DEFAULT_HTTP_TEST_PATH
            http_test = test.TCPHTTPTest(server_address, http_file)
            try:
                logger.info("Instantiate HTTP tester")
                tester = handlers.Tester(80, handlers.ROLE_CLIENT, interface=interface)
                logger.info("Connecting tester to server")
                tester.connect(server_address, interface=interface)
                logger.info("Starting test")
                tester.do_test(http_test, handlers.TEST_DOWNLINK_PHASE, handlers.TEST_SPEEDTEST_TYPE, http_result, [])
                logger.info("Closing test connection")
                tester.close_test_connection()
            except handlers.TesterException as test_exc:
                if test_exc.errno is None:
                    logger.error("Test failed %s, %i" % (test_exc.message, test_exc.error))
                else:
                    logger.error("Test failed %s, %i, %i" % (test_exc.message, test_exc.error, test_exc.errno))
                http_result["error"] = "Test failed %s, %i" % (test_exc.message, test_exc.error)
        else:
            logger.info("HTTP test not requested")
        logger.info("Initializing control connection to server")
        connector = handlers.Connector()
        connector.connect(server_address, server_port, interface=interface, timeout=30)
        controller = handlers.Controller(connector.connector_socket, handlers.ROLE_CLIENT)
        while True:
            try:
                msg, port = controller.recv_control_msg()
            except handlers.ControllerException as ce:
                logger.critical(" Controller error, exiting: %s" % ce.message)
                if args.monroe:
                    commands_queue.put(True)
                break
            if msg == handlers.CONTROLLER_ABORT_MEASURE_MSG:
                logger.info("Received abort measure message")
                if args.monroe:
                    try:
                        commands_queue.put(True)
                    except IOError:
                        pass
                break
            elif msg == handlers.CONTROLLER_FINISH_MEASURE_MSG:
                logger.info("Received finish measure message")
                if args.monroe:
                    try:
                        commands_queue.put(True)
                    except IOError:
                        pass
                break
            elif msg == handlers.CONTROLLER_START_UB_MSG:
                if port is None:
                    logger.error("Error: port is None")
                    continue
                logger.info("Received message start UB, port %i" % port)
                test_var = bt_test
                phase = handlers.TEST_UPLINK_PHASE
            elif msg == handlers.CONTROLLER_START_UC_MSG:
                if port is None:
                    logger.error("Error: port is None")
                    continue
                logger.info("Received message start UC, port %i" % port)
                test_var = ct_test
                phase = handlers.TEST_UPLINK_PHASE
            elif msg == handlers.CONTROLLER_START_DB_MSG:
                if port is None:
                    logger.error("Error: port is None")
                    continue
                logger.info("Received message start DB, port %i" % port)
                test_var = bt_test
                phase = handlers.TEST_DOWNLINK_PHASE
            elif msg == handlers.CONTROLLER_START_DC_MSG:
                if port is None:
                    logger.error("Error: port is None")
                    continue
                logger.info("Received message start DC, port %i" % port)
                test_var = ct_test
                phase = handlers.TEST_DOWNLINK_PHASE
            elif msg == handlers.CONTROLLER_START_UT_MSG:
                if port is None:
                    logger.error("Error: port is None")
                    continue
                logger.info("Received message start UT, port %i" % port)
                test_var = ct_test
                phase = handlers.TEST_UPLINK_PHASE
            elif msg == handlers.CONTROLLER_START_DT_MSG:
                if port is None:
                    logger.error("Error: port is None")
                    continue
                logger.info("Received message start DT, port %i" % port)
                test_var = ct_test
                phase = handlers.TEST_DOWNLINK_PHASE
            elif msg == handlers.CONTROLLER_SEND_META_DATA_MSG:
                logger.info("Received message send meta data")
                if args.monroe:
                    commands_queue.put(True)
                    meta_data = results_queue.get()
                else:
                    meta_data = dict()
                meta_data["http_test"] = http_result
                logger.info("Metadata: %s" % meta_data)
                logger.info("Sending data to server")
                controller.send_control_msg(handlers.CONTROLLER_OK_MSG, meta_data)
                continue
            try:
                result = dict()
                logger.info("Instantiate tester")
                tester = handlers.Tester(port, handlers.ROLE_CLIENT, interface=interface)
                try:
                    logger.info("Connecting tester to server")
                    tester.connect(server_address, interface=interface)
                    logger.info("Starting test")
                    for test_type in [handlers.TEST_SPEEDTEST_TYPE, handlers.TEST_TRACEROUTE_TYPE]:
                        logger.info("Starting test %i" % test_type)
                        tester.do_test(test_var, phase, test_type, result, stop_interfaces, duration)
                        if phase == handlers.TEST_UPLINK_PHASE and test_type == handlers.TEST_SPEEDTEST_TYPE:
                            logger.info("Sleeping")
                            time.sleep(10)
                        if msg == handlers.CONTROLLER_START_UT_MSG or msg == handlers.CONTROLLER_START_DT_MSG:
                            break
                    logger.info("Sending result to server")
                    controller.send_control_msg(handlers.CONTROLLER_OK_MSG, result)
                except handlers.TesterException as test_exc:
                    if test_exc.errno is None:
                        logger.error("Test failed %s, %i" % (test_exc.message, test_exc.error))
                    else:
                        logger.error("Test failed %s, %i, %i" % (test_exc.message, test_exc.error, test_exc.errno))
                    if test_exc.error == handlers.TESTER_CONNECT_TIMEOUT_ERROR:
                        controller.send_control_msg(handlers.CONTROLLER_CLIENT_CONNECT_TIMEOUT_ERROR)
                    elif test_exc.error == handlers.TESTER_CONNECT_REFUSED_ERROR:
                        controller.send_control_msg(handlers.CONTROLLER_CLIENT_CONNECT_REFUSED_ERROR)
                    elif test_exc.error == handlers.TESTER_CONNECT_GENERIC_ERROR:
                        controller.send_control_msg(handlers.CONTROLLER_CLIENT_CONNECT_GENERIC_ERROR)
                    elif test_exc.error == handlers.TESTER_TEST_RESET_ERROR:
                        controller.send_control_msg(handlers.CONTROLLER_CLIENT_TEST_RESET_ERROR, result)
                    elif test_exc.error == handlers.TESTER_TEST_ABORT_ERROR:
                        controller.send_control_msg(handlers.CONTROLLER_CLIENT_TEST_ABORT_ERROR, result)
                    elif test_exc.error == handlers.TESTER_TEST_TIMEOUT_ERROR:
                        controller.send_control_msg(handlers.CONTROLLER_CLIENT_TEST_TIMEOUT_ERROR, result)
                    elif test_exc.error == handlers.TESTER_TEST_GENERIC_ERROR:
                        controller.send_control_msg(handlers.CONTROLLER_CLIENT_TEST_GENERIC_ERROR, result)
                finally:
                    logger.info("Closing test connection")
                    tester.close_test_connection()
            except handlers.TesterException as te:
                if te.errno is None:
                    logger.error("Test failed %s, %i" % (te.message, te.error))
                else:
                    logger.error("Test failed %s, %i, %i" % (te.message, te.error, te.errno))
                if te.error == handlers.TESTER_INIT_CLIENT_ERROR:
                    controller.send_control_msg(handlers.CONTROLLER_CLIENT_TEST_INIT_ERROR)
        if args.monroe:
            # commands_queue.close()
            # results_queue.close()
            mp.join()
        logger.info("Ending")
        connector.close_connection()


if __name__ == "__main__":
    main(sys.argv)
