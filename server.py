#!/usr/bin/python

import argparse
import json
import logging
import sys
import time
import traceback
import uuid

from neutmon import handlers
from neutmon import test


def init_current_test(port, three_way_test=False, third_port=0):
    current_test = dict()
    current_test["port"] = port
    current_test["finished"] = False
    current_test["uplink"] = dict()
    current_test["uplink"]["bt"] = dict()
    current_test["uplink"]["ct"] = dict()
    current_test["downlink"] = dict()
    current_test["downlink"]["bt"] = dict()
    current_test["downlink"]["ct"] = dict()
    if three_way_test:
        current_test["uplink"]["third"] = dict()
        current_test["downlink"]["third"] = dict()
        current_test["third_port"] = third_port
    return current_test


class Client(object):
    def __init__(self, control_socket, address, cid):
        self.control_socket = control_socket
        self.address = address
        self.id = cid

    def close_connection(self):
        self.control_socket.close()


def client_handler(client, meta_data, results, error, logger, three_way_test=False, duration=0):
    # Uplink and downlink are referred to client. Uplink here is downlink for server and vice versa.
    logger.info("C: Initializing controller")
    controller = handlers.Controller(client.control_socket)
    bt_test = test.TCPBTTest()
    ct_test = test.TCPRandomTest()
    port = handlers.BT_PORT
    current_test = init_current_test(port, three_way_test, handlers.TT_PORT)
    results.append(current_test)
    try:
        tester = handlers.Tester(port)
        command = handlers.CONTROLLER_START_UB_MSG
        if three_way_test:
            last_command = handlers.CONTROLLER_START_DT_MSG
        else:
            last_command = handlers.CONTROLLER_START_DC_MSG
        while command in range(handlers.CONTROLLER_START_UB_MSG, last_command + 1):
            logger.info("C: Trying phase %i with port %i" % (command, port))
            if command == handlers.CONTROLLER_START_UB_MSG or command == handlers.CONTROLLER_START_UC_MSG or\
               command == handlers.CONTROLLER_START_UT_MSG:
                phase = handlers.TEST_DOWNLINK_PHASE
                phase_index = "uplink"
            else:
                phase = handlers.TEST_UPLINK_PHASE
                phase_index = "downlink"
            if command == handlers.CONTROLLER_START_UB_MSG or command == handlers.CONTROLLER_START_DB_MSG:
                test_var = bt_test
                test_index = "bt"
            elif command == handlers.CONTROLLER_START_UC_MSG or command == handlers.CONTROLLER_START_DC_MSG:
                test_var = ct_test
                test_index = "ct"
            else:
                test_var = ct_test
                test_index = "third"
            logger.info("C: Sending control message %i port %i" % (command, port))
            controller.send_control_msg(command, port)
            try:
                logger.info("C: Doing test")
                result = dict()
                tester.accept_test_connection()
                for test_type in [handlers.TEST_SPEEDTEST_TYPE, handlers.TEST_TRACEROUTE_TYPE]:
                    logger.info("C: Starting %i test, phase %s %s" % (test_type, test_index, phase_index))
                    tester.do_test(test_var, phase, test_type, result, [], duration)
                    current_test[phase_index][test_index]["server_status"] = handlers.TESTER_OK
                    if phase == handlers.TEST_UPLINK_PHASE and test_type == handlers.TEST_SPEEDTEST_TYPE:
                        logger.info("C: Sleeping")
                        time.sleep(10)
                    if command == handlers.CONTROLLER_START_UT_MSG or command == handlers.CONTROLLER_START_DT_MSG:
                        break
                logger.info("C: Closing test connection")
                tester.close_test_connection()
            except handlers.TesterException as te:
                current_test[phase_index][test_index]["server_status"] = te.error
                if te.errno is None:
                    logger.error("C: Error in test on port %i: %s" % (port, te.message))
                else:
                    logger.error("C: Error in test on port %i: %s %i" % (port, te.message, te.errno))
                tester.close_test_connection()
            if phase == handlers.TEST_DOWNLINK_PHASE:
                current_test[phase_index][test_index]["speedtest"] = result
            elif phase == handlers.TEST_UPLINK_PHASE:
                current_test[phase_index][test_index]["traceroute"] = result
            logger.info("C: Receiving status and result from client")
            resp, extra = controller.recv_control_msg()
            logger.info("C: Client status is %i" % resp)
            current_test[phase_index][test_index]["client_status"] = resp
            if extra is not None:
                logger.info("C: client result is not empty")
                if phase == handlers.TEST_UPLINK_PHASE:
                    current_test[phase_index][test_index]["speedtest"] = extra
                elif phase == handlers.TEST_DOWNLINK_PHASE:
                    current_test[phase_index][test_index]["traceroute"] = extra
            if resp != handlers.CONTROLLER_OK_MSG:
                if command == handlers.CONTROLLER_START_UB_MSG and port == handlers.BT_PORT:
                    tester.finish_test()
                    port = handlers.ALT_BT_PORT
                    current_test = init_current_test(port, three_way_test, handlers.TT_PORT)
                    results.append(current_test)
                    logger.info("C: First port failed, trying uplink BitTorrent with port %i" % port)
                    tester = handlers.Tester(port)
                else:
                    command += 1
                    if command == handlers.CONTROLLER_START_UT_MSG and three_way_test:
                        tester.finish_test()
                        port = current_test["third_port"]
                        tester = handlers.Tester(port)
            else:
                command += 1
                if command == handlers.CONTROLLER_START_UT_MSG and three_way_test:
                    tester.finish_test()
                    port = current_test["third_port"]
                    tester = handlers.Tester(port)
        current_test["finished"] = True
        logger.info("C: Finishing test and closing test connection")
        tester.finish_test()
        logger.info("C: Sending control message send meta data")
        controller.send_control_msg(handlers.CONTROLLER_SEND_META_DATA_MSG)
        logger.info("C: Receiving status and result from client")
        resp, extra = controller.recv_control_msg()
        if resp == handlers.CONTROLLER_OK_MSG and extra is not None:
            meta_data["client_meta"] = extra
        else:
            logger.warning("C: meta data not received")
            meta_data["client_meta"] = {}
        controller.finish_measure()
    except handlers.ControllerException as ce:
        logger.error("C: Error in controller: %s" % ce.message)
        error["message"] = ce.message
        tester.finish_test()
        try:
            controller.abort_measure()
        except handlers.ControllerException:
            pass
    except handlers.TesterException as te:
        logger.error("C: Error in tester: %s %i %i" % (te.message, te.error, te.errno))
        error["message"] = te.error
        tester.finish_test()
        try:
            controller.abort_measure()
        except handlers.ControllerException:
            pass
    except Exception as e:
        error["message"] = "%s: %s" % (type(e).__name__, e.message)
        logger.error("C: Unexpected error %s %s %s" % (type(e).__name__, e.message, e.args))
        logger.error(traceback.format_exc())
        tester.finish_test()
        try:
            controller.abort_measure()
        except handlers.ControllerException:
            pass
    finally:
        client.close_connection()


def main(argv):
    parser = argparse.ArgumentParser(description="NeutMon client. Performs speed and traceroute tests to check if "
                                                 "ISPs are differentiating traffic.")
    parser.add_argument("-d", "--duration", help="specify speedtest duration (in seconds)", type=int)
    parser.add_argument("-t", "--three_way_test", help="enable three way testing", action="store_true")
    parser.add_argument("-l", "--log", help="set the logging level. possible values are DEBUG, INFO, WARNING, ERROR,"
                                            "and CRITICAL. if not specified the default value is WARNING")
    parser.add_argument("-g", "--logfile", help="set the output file for logs. the default value is neutmon_server.log")
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
        log_file = "neutmon_server.log"
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
    logger.info("Neutmon server started")
    if args.duration:
        duration = args.duration
    else:
        duration = 0
    if args.three_way_test:
        three_way_test = True
    else:
        three_way_test = False
    logger.info("P: Initializing listener")
    listener = handlers.Listener()
    while True:
        logger.info("P: Accepting incoming connection")
        client_socket, address = listener.accept_connection()
        client_socket.settimeout(30)
        client_id = str(uuid.uuid4())
        client = Client(client_socket, address, client_id)
        meta_data = dict()
        error = dict()
        results = []
        meta_data["client_id"] = client_id
        meta_data["client_ip"] = address
        meta_data["start"] = time.time()
        logger.info("P: Passing client connection to handler")
        client_handler(client, meta_data, results, error, logger, three_way_test, duration)
        meta_data["stop"] = time.time()
        result = dict()
        result["meta_data"] = meta_data
        result["results"] = results
        if error:
            result["error"] = error
        logger.info("P: Writing results on file")
        with open("output-" + str(int(time.time())) + "-" + client_id + ".json", "w") as f:
            f.write(json.dumps(result, indent=4))


if __name__ == "__main__":
    main(sys.argv)
