#!/usr/bin/python

import argparse
import json
import os
import sys
from neutmon import analysis


def traceroute_analyzer(bt_traceroute_dict, ct_traceroute_dict):
    bt_traceroute = analysis.order_dict(bt_traceroute_dict, analysis.TRACEROUTE)
    ct_traceroute = analysis.order_dict(ct_traceroute_dict, analysis.TRACEROUTE)
    bt_trace_length = len(bt_traceroute)
    ct_trace_length = len(ct_traceroute)
    max_length = max(bt_trace_length, ct_trace_length)
    output_string = "hop\tbt\tct\n"
    for i in range(1, max_length + 1):
        if i > bt_trace_length:
            bt_interface = "-"
        else:
            bt_interface = bt_traceroute[i]
        if i > ct_trace_length:
            ct_interface = "-"
        else:
            ct_interface = ct_traceroute[i]
        # if bt_interface == "*" or ct_interface == "*":
        #     difference = INDEFINITE
        # elif bt_interface == "-" and ct_interface != "*" or ct_interface == "-" and bt_interface != "*":
        #
        #         difference = "P"
        # elif bt_interface != "-":
        #     if ct_interface == "*":
        #         difference = "P"
        #     elif bt_interface == ct_interface:
        #         difference = "N"
        #     elif ct_interface != "-":
        #         difference = "Y"
        output_string += "%i\t%s\t%s\n" % (i, bt_interface, ct_interface)
    return output_string


def main(argv):
    parser = argparse.ArgumentParser(description="NeutMon data analyzer. Produces plots from Neutmon output file")
    parser.add_argument("-i", "--interval", type=float, help="minimum interval for throughput calculation")
    parser.add_argument("-o", "--operator", help="name of operator for extracting relevant metadata")
    parser.add_argument("-s", "--significance", type=float, default=0.05, help="significance level of KS test")
    parser.add_argument("neutmon_file", metavar="FILE", type=str, nargs=1, help="Neutmon output file")
    args = parser.parse_args()
    if args.interval:
        min_interval = args.interval
    else:
        min_interval = 0
    if args.operator:
        operator = args.operator
    else:
        operator = ""
    #     print "Operator not specified. Exiting."
    #     sys.exit(0)
    dir_name = args.neutmon_file[0].replace(".json", "")
    try:
        os.mkdir(dir_name)
    except OSError as ose:
        if ose.errno != 17:
            raise ose
    with open(args.neutmon_file[0], "r") as json_file:
        json_data = json.loads(json_file.read())
    if "error" in json_data:
        print "Test failed. Error: %s" % json_data["error"]["message"]
        sys.exit(0)
    if json_data["results"][0]["finished"]:
        results_index = 0
    elif json_data["results"][1]["finished"]:
        print "Test failed on port %i" % json_data["results"][0]["port"]
        results_index = 1
    else:
        print argv[1], "Test failed on port %i" % json_data["results"][1]["port"]
        sys.exit(0)

    # plot cumulatives and write mean throughputs
    with open(dir_name + "/mean_throughput.dat", "w") as f:
        kwargs = dict()
        f.write("\tbt\tct\ttt\tht\n")
        # plot uplink transfer cumulative
        bt_x, bt_y, bt_mean = analysis.transfer_cumulative(
            json_data["results"][results_index]["uplink"]["bt"]["speedtest"])
        kwargs["BT"] = (bt_x, bt_y)
        ct_x, ct_y, ct_mean = analysis.transfer_cumulative(
            json_data["results"][results_index]["uplink"]["ct"]["speedtest"])
        kwargs["CT"] = (ct_x, ct_y)
        if "third" in json_data["results"][results_index]["uplink"]:
            tt_x, tt_y, tt_mean = analysis.transfer_cumulative(
                json_data["results"][results_index]["uplink"]["third"]["speedtest"])
            kwargs["TT"] = (tt_x, tt_y)
        analysis.plot_cumulative(dir_name + "/uplink_cumulative.pdf", **kwargs)
        if "third" in json_data["results"][results_index]["uplink"]:
            f.write("uplink\t%f\t%f\t%f\t-\n" % (bt_mean, ct_mean, tt_mean))
        else:
            f.write("uplink\t%f\t%f\t-\t-\n" % (bt_mean, ct_mean))
        # plot downlink transfer cumulative
        kwargs = dict()
        bt_x, bt_y, bt_mean = analysis.transfer_cumulative(
            json_data["results"][results_index]["downlink"]["bt"]["speedtest"])
        kwargs["BT"] = (bt_x, bt_y)
        ct_x, ct_y, ct_mean = analysis.transfer_cumulative(
            json_data["results"][results_index]["downlink"]["ct"]["speedtest"])
        kwargs["CT"] = (ct_x, ct_y)
        if "third" in json_data["results"][results_index]["downlink"]:
            tt_x, tt_y, tt_mean = analysis.transfer_cumulative(
                json_data["results"][results_index]["downlink"]["third"]["speedtest"])
            kwargs["TT"] = (tt_x, tt_y)
        if "meta_data" in json_data and "client_meta" in json_data["meta_data"]\
                and "http_test" in json_data["meta_data"]["client_meta"]\
                and len(json_data["meta_data"]["client_meta"]["http_test"]) > 0:
            speedtest = json_data["meta_data"]["client_meta"].pop("http_test", None)
            if speedtest is not None:
                json_data["meta_data"]["client_meta"]["http_test"] = dict()
                json_data["meta_data"]["client_meta"]["http_test"]["speedtest"] = speedtest
                error = json_data["meta_data"]["client_meta"]["http_test"]["speedtest"].pop("error", None)
                if error is not None:
                    json_data["meta_data"]["client_meta"]["http_test"]["error"] = error
            ht_x, ht_y, ht_mean = analysis.transfer_cumulative(
                json_data["meta_data"]["client_meta"]["http_test"]["speedtest"])
            kwargs["HT"] = (ht_x, ht_y)
            if "third" in json_data["results"][results_index]["downlink"]:
                f.write("downlink\t%f\t%f\t%f\t%f\n" % (bt_mean, ct_mean, tt_mean, ht_mean))
            else:
                f.write("downlink\t%f\t%f\t-\t%f\n" % (bt_mean, ct_mean, ht_mean))
        else:
            if "third" in json_data["results"][results_index]["downlink"]:
                f.write("downlink\t%f\t%f\t%f\t-\n" % (bt_mean, ct_mean, tt_mean))
            else:
                f.write("uplink\t%f\t%f\t-\t-\n" % (bt_mean, ct_mean))
        analysis.plot_cumulative(dir_name + "/downlink_cumulative.pdf", **kwargs)

    # metadata
    if operator != "":
        d = analysis.order_dict(json_data["meta_data"]["client_meta"]["interface"], analysis.METADATA)
        fd = analysis.filter_by_operator(d, operator)
        btd = analysis.order_dict(json_data["results"][results_index]["downlink"]["bt"]["speedtest"],
                                  analysis.SPEEDTEST)
        ctd = analysis.order_dict(json_data["results"][results_index]["downlink"]["ct"]["speedtest"],
                                  analysis.SPEEDTEST)
        btu = analysis.order_dict(json_data["results"][results_index]["uplink"]["bt"]["speedtest"],
                                  analysis.SPEEDTEST)
        ctu = analysis.order_dict(json_data["results"][results_index]["uplink"]["ct"]["speedtest"],
                                  analysis.SPEEDTEST)
        if "third" in json_data["results"][results_index]["downlink"]:
            ttd = analysis.order_dict(json_data["results"][results_index]["downlink"]["third"]["speedtest"],
                                      analysis.SPEEDTEST)
        if "third" in json_data["results"][results_index]["uplink"]:
            ttu = analysis.order_dict(json_data["results"][results_index]["uplink"]["third"]["speedtest"],
                                      analysis.SPEEDTEST)
        tempi = fd.keys()
        mode = []
        rssi = []
        for t in tempi:
            mode.append(fd[t]["DeviceMode"])
            rssi.append(fd[t]["RSSI"])
        # min_time = min(tempi)
        # tempi = [x - min_time for x in tempi]
        kwargs = dict()
        kwargs["BT Uplink"] = btu
        kwargs["BT Downlink"] = btd
        kwargs["CT Uplink"] = ctu
        kwargs["CT Downlink"] = ctd
        if "third" in json_data["results"][results_index]["uplink"]:
            kwargs["TT Uplink"] = ttu
        if "third" in json_data["results"][results_index]["downlink"]:
            kwargs["TT Downlink"] = ttd
        if "meta_data" in json_data and "client_meta" in json_data["meta_data"] \
                and "http_test" in json_data["meta_data"]["client_meta"]\
                and len(json_data["meta_data"]["client_meta"]["http_test"]) > 0:
            htd = analysis.order_dict(json_data["meta_data"]["client_meta"]["http_test"]["speedtest"],
                                      analysis.SPEEDTEST)
            kwargs["HTTP Downlink"] = htd
        analysis.plot_metadata(dir_name + "/metadata.pdf", tempi, mode, rssi, **kwargs)

    # plot uplink throughput cdf
    kwargs = dict()
    bt_x, bt_y = analysis.throughput_cdf(json_data["results"][results_index]["uplink"]["bt"]["speedtest"], min_interval)
    kwargs["BT"] = (bt_x, bt_y)
    ct_x, ct_y = analysis.throughput_cdf(json_data["results"][results_index]["uplink"]["ct"]["speedtest"], min_interval)
    kwargs["CT"] = (ct_x, ct_y)
    if "third" in json_data["results"][results_index]["uplink"]:
        tt_x, tt_y = analysis.throughput_cdf(json_data["results"][results_index]["uplink"]["third"]["speedtest"],
                                             min_interval)
        kwargs["TT"] = (tt_x, tt_y)
    analysis.plot_cdf(dir_name + "/uplink_throughput_cdf.pdf", **kwargs)
    
    # compute statistics
    analysis.compute_ks(dir_name + "/uplink_statistics_btct.txt", bt_x, ct_x, args.significance)
    if "third" in json_data["results"][results_index]["uplink"]:
        analysis.compute_ks(dir_name + "/uplink_statistics_bttt.txt", bt_x, tt_x, args.significance)

    # plot downlink throughput cdf
    kwargs = dict()
    bt_x, bt_y = analysis.throughput_cdf(json_data["results"][results_index]["downlink"]["bt"]["speedtest"],
                                         min_interval)
    kwargs["BT"] = (bt_x, bt_y)
    ct_x, ct_y = analysis.throughput_cdf(json_data["results"][results_index]["downlink"]["ct"]["speedtest"],
                                         min_interval)
    kwargs["CT"] = (ct_x, ct_y)
    if "third" in json_data["results"][results_index]["downlink"]:
        tt_x, tt_y = analysis.throughput_cdf(json_data["results"][results_index]["downlink"]["third"]["speedtest"],
                                             min_interval)
        kwargs["TT"] = (tt_x, tt_y)
    if "meta_data" in json_data and "client_meta" in json_data["meta_data"] \
            and "http_test" in json_data["meta_data"]["client_meta"]\
            and len(json_data["meta_data"]["client_meta"]["http_test"]) > 0:
        ht_x, ht_y = analysis.throughput_cdf(json_data["meta_data"]["client_meta"]["http_test"]["speedtest"],
                                             min_interval)
        kwargs["HT"] = (ht_x, ht_y)
    analysis.plot_cdf(dir_name + "/downlink_throughput_cdf.pdf", **kwargs)

    # compute statistics
    analysis.compute_ks(dir_name + "/downlink_statistics_btct.txt", bt_x, ct_x, args.significance)
    if "third" in json_data["results"][results_index]["downlink"]:
        analysis.compute_ks(dir_name + "/downlink_statistics_bttt.txt", bt_x, tt_x, args.significance)
    if "HT" in kwargs:
        analysis.compute_ks(dir_name + "/downlink_statistics_btht.txt", bt_x, ht_x, args.significance)

    # write traceroute analysis downlink
    to_write = traceroute_analyzer(json_data["results"][results_index]["downlink"]["bt"]["traceroute"],
                                   json_data["results"][results_index]["downlink"]["ct"]["traceroute"])
    with open(dir_name + "/downlink_traceroute.dat", "w") as f:
        f.write(to_write)
    # write traceroute analysis uplink
    to_write = traceroute_analyzer(json_data["results"][results_index]["uplink"]["bt"]["traceroute"],
                                   json_data["results"][results_index]["uplink"]["ct"]["traceroute"])
    with open(dir_name + "/uplink_traceroute.dat", "w") as f:
        f.write(to_write)


if __name__ == '__main__':
    main(sys.argv)
