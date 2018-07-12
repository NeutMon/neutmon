#!/usr/bin/python

import argparse
import json
from neutmon import analysis


def main():
    parser = argparse.ArgumentParser(description="NeutMon traceroute data analyzer.")
    parser.add_argument("-o", "--output", type=str, help="Output file name. If not specified, the output file will be "
                                                         "output.txt")
    parser.add_argument("neutmon_files", metavar="FILE", type=str, nargs="+", help="NeutMon output file(s)")
    args = parser.parse_args()
    if not args.neutmon_files:
        exit(1)
    if not args.output:
        output_file = "output"
    else:
        output_file = args.output

    bt_ul_traceroutes = dict()
    ct_ul_traceroutes = dict()
    bt_dl_traceroutes = dict()
    ct_dl_traceroutes = dict()
    paris_traceroutes = dict()
    tracebox_6881_traceroutes = dict()
    tracebox_6881_mods = dict()
    tracebox_53674_traceroutes = dict()
    tracebox_53674_mods = dict()

    for file_name in args.neutmon_files:
        with open(file_name, "r") as json_file:
            json_data = json.loads(json_file.read())
        if "error" in json_data:
            print "Test failed. Error: %s" % json_data["error"]["message"]
            continue
        if json_data["results"][0]["finished"]:
            results_index = 0
        elif json_data["results"][1]["finished"]:
            print "Test failed on port %i" % json_data["results"][0]["port"]
            results_index = 1
        else:
            print "Test failed on port %i" % json_data["results"][1]["port"]
            continue
        paris_traceroute = analysis.parse_paris(json_data["meta_data"]["client_meta"]["paris"])
        analysis.update_traceroutes_dict(paris_traceroutes, paris_traceroute, True)
        tracebox_6881, tracebox_6881_mod = analysis.parse_tracebox(
            json_data["meta_data"]["client_meta"]["tracebox_6881"])
        analysis.update_traceroutes_dict(tracebox_6881_traceroutes, tracebox_6881)
        analysis.update_traceroutes_dict(tracebox_6881_mods, tracebox_6881_mod, True)
        tracebox_53674, tracebox_53674_mod = analysis.parse_tracebox(
            json_data["meta_data"]["client_meta"]["tracebox_6881"])
        analysis.update_traceroutes_dict(tracebox_53674_traceroutes, tracebox_53674)
        analysis.update_traceroutes_dict(tracebox_53674_mods, tracebox_53674_mod, True)
        bt_traceroute_ul_dict = analysis.order_dict(json_data["results"][results_index]["uplink"]["bt"]["traceroute"],
                                                    analysis.TRACEROUTE)
        ct_traceroute_ul_dict = analysis.order_dict(json_data["results"][results_index]["uplink"]["ct"]["traceroute"],
                                                    analysis.TRACEROUTE)
        analysis.update_traceroutes_dict(bt_ul_traceroutes, bt_traceroute_ul_dict)
        analysis.update_traceroutes_dict(ct_ul_traceroutes, ct_traceroute_ul_dict)
        bt_traceroute_dl_dict = analysis.order_dict(json_data["results"][results_index]["downlink"]["bt"]["traceroute"],
                                                    analysis.TRACEROUTE)
        ct_traceroute_dl_dict = analysis.order_dict(json_data["results"][results_index]["downlink"]["ct"]["traceroute"],
                                                    analysis.TRACEROUTE)
        analysis.update_traceroutes_dict(bt_dl_traceroutes, bt_traceroute_dl_dict)
        analysis.update_traceroutes_dict(ct_dl_traceroutes, ct_traceroute_dl_dict)
    ul_result = analysis.compare_traceroutes_dicts(bt_ul_traceroutes, ct_ul_traceroutes, set("*"), paris_traceroutes,
                                                   tracebox_6881_traceroutes, tracebox_53674_traceroutes)
    dl_result = analysis.compare_traceroutes_dicts(bt_dl_traceroutes, ct_dl_traceroutes, set("*"))
    analysis.print_traceroutes_result(ul_result, output_file + "_ul.txt")
    analysis.print_traceroutes_result(dl_result, output_file + "_dl.txt")
    print "UPLINK"
    analysis.print_traceroutes_result(ul_result)
    print
    print "DOWNLINK"
    analysis.print_traceroutes_result(dl_result)
    analysis.print_tracebox_mods(tracebox_6881_mods, tracebox_53674_mods, output_file + "_tracebox_ul.txt")
    # print tracebox_6881_mods
    # print tracebox_53674_mods


if __name__ == "__main__":
    main()
