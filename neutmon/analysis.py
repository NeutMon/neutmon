#!/usr/bin/python

import sys
import collections
import contextlib
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats


TRACEROUTE = 0
SPEEDTEST = 1
METADATA = 2

compact_keys = ["HT", "BT", "CT", "TT"]
compact_colors = ["b", "g", "r", "c"]
extended_keys = ["HTTP Downlink", "BT Uplink", "BT Downlink", "CT Uplink", "CT Downlink", "TT Uplink", "TT Downlink"]
extended_colors = ["b", "g", "r", "c", "m", "y", "k"]


def order_dict(d, dict_type):
    if dict_type == TRACEROUTE:
        d = {int(k): str(v) for k, v in d.items()}
    elif dict_type == SPEEDTEST:
        d = {float(k): int(v) for k, v in d.items()}
    else:
        d = {float(k): dict(v) for k, v in d.items()}
    ordered_dict = collections.OrderedDict()
    for key in sorted(d.keys()):
        ordered_dict[key] = d[key]
    return ordered_dict


def filter_by_operator(d, operator):
    dd = collections.OrderedDict()
    for k, v in d.items():
        if v["Operator"] == operator:
            dd[k] = d[k]
    return dd


def transfer_cumulative(speed_test_dict):
    speed_test = order_dict(speed_test_dict, SPEEDTEST)
    times = speed_test.keys()
    min_time = min(times)
    interval = max(times) - min_time
    times = [x - min_time for x in times]
    cumulative = np.cumsum(speed_test.values())
    total_bytes = sum(speed_test.values())
    return times, cumulative, (float(total_bytes) * 8) / (interval * 1e6)


def throughput_cdf(speed_test_dict, min_interval=0):
    speed_test = order_dict(speed_test_dict, SPEEDTEST)
    prev_key = 0
    interval = 0
    byte_amount = 0
    throughput = []
    for key in sorted(speed_test.keys()):
        if prev_key == 0:
            prev_key = key
            continue
        interval += key - prev_key
        byte_amount += speed_test[key]
        prev_key = key
        if interval > min_interval:
            throughput.append((float(byte_amount) * 8) / (interval * 1e6))
            interval = 0
            byte_amount = 0
    throughput = sorted(throughput)
    n = len(throughput)
    y = []
    if n == 1:
        return [throughput[0], throughput[0]], [0, 1]
    for x in range(n):
        y.append(float(x) / (n - 1))
    return throughput, y


def compute_ks(file_name, bt_x, ct_x, significance):
    d, p = stats.ks_2samp(bt_x, ct_x)
    if p < significance:
        risul = "DIFF"
    else:
        risul = "SAME"
    with open(file_name, "w") as f:
        f.write("%s\td, p\t%e\t%e\n" % (risul, d, p))


def plot_cumulative(file_name, **kwargs):
    for i in range(len(compact_keys)):
        if compact_keys[i] in kwargs:
            plt.plot(kwargs[compact_keys[i]][0], kwargs[compact_keys[i]][1], label=compact_keys[i],
                     color=compact_colors[i])
    plt.xlabel("Time (s)")
    plt.ylabel("Data (Bytes)")
    plt.legend()
    plt.savefig(file_name)
    plt.close()


def two_scales(ax1, time, datasx1, datasx2, **kwargs):
    ax2 = ax1.twinx()
    ax1.plot(time, datasx1, color='#e39d15', label='MODE')
    ax1.plot(time, datasx2, color='#438fc4', label='RSSI')
    ax1.set_xlabel('Time (s)')
    ax1.set_ylabel('Metadata')
    ax1.legend()
    # colors = ['b', 'y', 'm', 'c']
    for i in range(len(extended_keys)):
        if extended_keys[i] in kwargs:
            ax2.plot(kwargs[extended_keys[i]].keys(), kwargs[extended_keys[i]].values(), label=extended_keys[i],
                     color=extended_colors[i])
    ax2.set_ylabel('Speed')
    ax2.legend()
    return ax1, ax2


def plot_metadata(file_name, times, mode, rssi, **kwargs):
    # Create axes
    fig, ax = plt.subplots()
    mode2 = [x * 10 for x in mode]
    ax1, ax2 = two_scales(ax, times, mode2, rssi, **kwargs)
    plt.savefig(file_name)
    plt.close()


def plot_cdf(file_name, **kwargs):
    for i in range(len(compact_keys)):
        if compact_keys[i] in kwargs:
            plt.plot(kwargs[compact_keys[i]][0], kwargs[compact_keys[i]][1], label=compact_keys[i],
                     color=compact_colors[i])
    plt.xlabel("Throughput (Mbps)")
    plt.ylabel("CDF")
    plt.legend()
    plt.savefig(file_name)
    plt.close()


def update_traceroutes_dict(traceroutes, single_traceroute, paris=False):
    for key in single_traceroute:
        if key not in traceroutes:
            traceroutes[key] = set()
        if paris:
            traceroutes[key].update(single_traceroute[key])
        else:
            traceroutes[key].add(single_traceroute[key])


def compare_interfaces_sets(s1, s2):
    if s1 is None or s2 is None:
        intersection = None
        only_s1 = None
        only_s2 = None
    else:
        intersection = s1 & s2
        only_s1 = s1 - s2
        only_s2 = s2 - s1
    return intersection, only_s1, only_s2


def compare_traceroutes_dicts(t1, t2, ignore_interfaces_set, paris=None, tracebox_6881=None, tracebox_53674=None):
    result = dict()
    if not set(t1.keys()) == set(t2.keys()):
        # TODO better error handling
        return result
    for key in t1:
        set_t1 = t1[key] - ignore_interfaces_set
        set_t2 = t2[key] - ignore_interfaces_set

        if paris and key in paris:
            set_paris = paris[key] - ignore_interfaces_set
        elif paris and key not in paris:
            set_paris = set()
        elif paris is None:
            set_paris = None

        if tracebox_6881 and key in tracebox_6881:
            set_tracebox_6881 = tracebox_6881[key] - ignore_interfaces_set
        elif tracebox_6881 and key not in tracebox_6881:
            set_tracebox_6881 = set()
        elif tracebox_6881 is None:
            set_tracebox_6881 = None

        if tracebox_53674 and key in tracebox_53674:
            set_tracebox_53674 = tracebox_53674[key] - ignore_interfaces_set
        elif tracebox_53674 and key not in tracebox_53674:
            set_tracebox_53674 = set()
        elif tracebox_53674 is None:
            set_tracebox_53674 = None

        intersection, only_t1, only_t2 = compare_interfaces_sets(set_t1, set_t2)
        paris_inters, only_t1_paris, only_paris_t1 = compare_interfaces_sets(set_t1, set_paris)
        paris_inters, only_t2_paris, only_paris_t2 = compare_interfaces_sets(set_t2, set_paris)
        t6881_inters, only_t1_t6881, only_t6881_t1 = compare_interfaces_sets(set_t1, set_tracebox_6881)
        t6881_inters, only_t2_t6881, only_t6881_t2 = compare_interfaces_sets(set_t2, set_tracebox_6881)
        t53674_inters, only_t1_t53674, only_t53674_t1 = compare_interfaces_sets(set_t1, set_tracebox_53674)
        t53674_inters, only_t2_t53674, only_t53674_t2 = compare_interfaces_sets(set_t2, set_tracebox_53674)
        len_t1 = len(set_t1)
        len_t2 = len(set_t2)
        len_only_t1 = len(only_t1)
        len_only_t2 = len(only_t2)
        if len_t1 == 0:
            perc1 = 0
            if only_t1_paris is not None:
                perc1_paris = 0
            else:
                perc1_paris = "-"
            if only_t1_t6881 is not None:
                perc1_t6881 = 0
            else:
                perc1_t6881 = "-"
            if only_t1_t53674 is not None:
                perc1_t53674 = 0
            else:
                perc1_t53674 = "-"
        else:
            perc1 = float(len_only_t1) / len_t1
            if only_t1_paris is not None:
                len_only_t1_paris = len(only_t1_paris)
                perc1_paris = float(len_only_t1_paris) / len_t1
            else:
                perc1_paris = "-"
            if only_t1_t6881 is not None:
                len_only_t1_t6881 = len(only_t1_t6881)
                perc1_t6881 = float(len_only_t1_t6881) / len_t1
            else:
                perc1_t6881 = "-"
            if only_t1_t53674 is not None:
                len_only_t1_t53674 = len(only_t1_t53674)
                perc1_t53674 = float(len_only_t1_t53674) / len_t1
            else:
                perc1_t53674 = "-"
        if len_t2 == 0:
            perc2 = 0
            if only_t2_paris is not None:
                perc2_paris = 0
            else:
                perc2_paris = "-"
            if only_t2_t6881 is not None:
                perc2_t6881 = 0
            else:
                perc2_t6881 = "-"
            if only_t2_t53674 is not None:
                perc2_t53674 = 0
            else:
                perc2_t53674 = "-"
        else:
            perc2 = float(len_only_t2) / len_t2
            if only_t2_paris is not None:
                len_only_t2_paris = len(only_t2_paris)
                perc2_paris = float(len_only_t2_paris) / len_t2
            else:
                perc2_paris = "-"
            if only_t2_t6881 is not None:
                len_only_t2_t6881 = len(only_t2_t6881)
                perc2_t6881 = float(len_only_t2_t6881) / len_t2
            else:
                perc2_t6881 = "-"
            if only_t2_t53674 is not None:
                len_only_t2_t53674 = len(only_t2_t53674)
                perc2_t53674 = float(len_only_t2_t53674) / len_t2
            else:
                perc2_t53674 = "-"
        if set_paris is None:
            set_paris = "-"
            only_t1_paris = "-"
            only_t2_paris = "-"
        if set_tracebox_6881 is None:
            set_tracebox_6881 = "-"
            only_t1_t6881 = "-"
            only_t2_t6881 = "-"
        if set_tracebox_53674 is None:
            set_tracebox_53674 = "-"
            only_t1_t53674 = "-"
            only_t2_t53674 = "-"
        result[key] = (set_t1, set_t2, set_paris, set_tracebox_6881, set_tracebox_53674, intersection, only_t1, only_t2,
                       only_t1_paris, only_t2_paris, only_t1_t6881, only_t2_t6881, only_t1_t53674, only_t2_t53674,
                       perc1, perc2, perc1_paris, perc2_paris, perc1_t6881, perc1_t53674, perc2_t6881, perc2_t53674)
    return result


@contextlib.contextmanager
def traceroute_open(filename=None):
    if filename and filename != '-':
        fh = open(filename, 'w')
    else:
        fh = sys.stdout
    try:
        yield fh
    finally:
        if fh is not sys.stdout:
            fh.close()


def print_traceroutes_result(res, filename=None):
    if len(res) != 0:
        with traceroute_open(filename) as f:
            if filename is None:
                f.write("hop\tbt_ct_perc\tbt_ct_len\tct_bt_perc\tct_bt_len\tbt_par_perc\tbt_par_len\tct_par_perc\t"
                        "ct_par_len\tbt_t6_perc\tbt_t6_len\tct_t6_perc\tct_t6_len\tbt_t5_perc\tbt_t5_len\tct_t5_perc\t"
                        "ct_t5_len\n")
            else:
                f.write("hop\tbt\tct\tparis\ttracebox6881\ttracebox53674\tintersection\tonly bt\tonly ct\t"
                        "only bt paris\tonly ct paris\tonly bt t6881\tonly ct t6881\tonly bt t53674\tonly ct t53674\t"
                        "only bt perc\tonly bt len\tonly ct perc\tonly ct len\t"
                        "only bt paris perc\tonly bt paris len\tonly ct paris perc\t only ct paris len\t"
                        "only bt t6881 perc\tonly bt t6881 len\tonly ct t6881 perc\tonly ct t6881 len\t"
                        "only bt t53674 perc\tonly bt t53674 len\tonly ct t53674 perc\tonly ct t53674 len\n")
            for key in res:
                if filename is None:
                    f.write(str(key) + "\t" + 
                            str(res[key][14]) + "\t" + str(len(res[key][6])) + "\t" +
                            str(res[key][15]) + "\t" + str(len(res[key][7])) + "\t" +
                            str(res[key][16]) + "\t" + str(len(res[key][8])) + "\t" +
                            str(res[key][17]) + "\t" + str(len(res[key][9])) + "\t" +
                            str(res[key][18]) + "\t" + str(len(res[key][10])) + "\t" +
                            str(res[key][19]) + "\t" + str(len(res[key][11])) + "\t" +
                            str(res[key][20]) + "\t" + str(len(res[key][12])) + "\t" +
                            str(res[key][21]) + "\t" + str(len(res[key][13])) + "\n")
                else:
                    f.write(str(key) + "\t")
                    for i in range(14):
                        if res[key][i] == "-":
                            f.write(res[key][i] + "\t")
                            continue
                        first = True
                        f.write("{")
                        for ip in res[key][i]:
                            if first:
                                f.write(ip)
                                first = False
                            else:
                                f.write(", " + ip)
                        f.write("}\t")
                    f.write(str(res[key][14]) + "\t" + str(len(res[key][6])) + "\t" +
                            str(res[key][15]) + "\t" + str(len(res[key][7])) + "\t" +
                            str(res[key][16]) + "\t" + str(len(res[key][8])) + "\t" +
                            str(res[key][17]) + "\t" + str(len(res[key][9])) + "\t" +
                            str(res[key][18]) + "\t" + str(len(res[key][10])) + "\t" +
                            str(res[key][19]) + "\t" + str(len(res[key][11])) + "\t" +
                            str(res[key][20]) + "\t" + str(len(res[key][12])) + "\t" +
                            str(res[key][21]) + "\t" + str(len(res[key][13])) + "\n")


def parse_paris(paris_string):
    paris_string = paris_string.strip()
    result = dict()
    paris_list = paris_string.splitlines()
    for line in paris_list:
        line = line.strip()
        if line.startswith("#") or line.startswith("traceroute") or line.startswith("MPLS"):
            continue
        line_list = line.split()
        if len(line_list) == 3:
            result[int(line_list[0])] = set("*")
        else:
            interfaces_number = (len(line_list) - 3) / 4
            ip_set = set()
            for i in range(interfaces_number):
                ip = line_list[3 + i * 4 + 1]
                ip = ip.split(":")
                ip = ip[0].replace("(", "").replace(")", "")
                ip_set.add(ip)
            result[int(line_list[0])] = ip_set
    return result


def parse_tracebox(tracebox_json):
    trace_result = dict()
    difference_result = dict()
    if "Hops" in tracebox_json:
        for hop in tracebox_json["Hops"]:
            trace_result[int(hop["hop"])] = hop["from"]
            if "Modifications" in hop:
                difference_result[int(hop["hop"])] = set()
                for i in hop["Modifications"]:
                    difference_result[hop["hop"]].update(i.keys())
    return trace_result, difference_result


def print_tracebox_mods(tracebox_6881, tracebox_53674, filename):
    with open(filename, "w") as f:
        f.write("hop\ttracebox 6881\ttracebox 53674\n")
        for key in tracebox_6881:
            f.write(str(key) + "\t{")
            first = True
            for i in tracebox_6881[key]:
                if first:
                    f.write(i)
                    first = False
                else:
                    f.write(", " + i)
            f.write("}\t{")
            first = True
            for i in tracebox_53674[key]:
                if first:
                    f.write(i)
                    first = False
                else:
                    f.write(", " + i)
            f.write("}\n")
