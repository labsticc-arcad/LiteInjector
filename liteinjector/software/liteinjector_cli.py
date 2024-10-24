#!/usr/bin/env python3

# Copyright (c) 2020 Antmicro <www.antmicro.com>
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

import os
import re
import csv
import sys
import time
import threading
import argparse
import ast

from litex import RemoteClient
from liteinjector.software.driver.injector import LiteInjectorDriver

# Helpers ------------------------------------------------------------------------------------------

# Return the list of the trigger IDs
def get_trigger_ids(trigger_list, index):
    list_id = []
    for trigger in trigger_list:
        if len(trigger) >= index:
            id = trigger[index-1]
            if int(id) not in list_id:
                list_id.append(int(id))
    return list_id

def get_trigger_by_id(trigger_list, index, id):
    filtered_list = []
    for trigger in trigger_list:
        if len(trigger) >= index:
            trigger_id = int(trigger[index-1])
            if trigger_id == id:
                filtered_list.append(trigger)
    return filtered_list

def get_signals(csvname, group):
    signals = []
    with open(csvname) as f:
        reader = csv.reader(f, delimiter=",", quotechar="#")
        for t, g, n, v in reader:
            if t == "signal" and g == str(group):
                signals.append(n)
    return signals

class Finder:
    def __init__(self, signals):
        self.signals = signals

    def __getitem__(self, name):
        scores = {s: 0 for s in self.signals}
        # Exact match
        if name in scores:
            #print("Exact:", name)
            return name
        # Substring
        pattern = re.compile(name)
        max_score = 0
        for s in self.signals:
            match = pattern.search(s)
            if match:
                scores[s] = match.end() - match.start()
        max_score = max(scores.values())
        best = list(filter(lambda kv: kv[1] == max_score, scores.items()))
        assert len(best) == 1, f"Found multiple candidates: {best}"
        name, score = best[0]
        return name

def add_triggers(args, injector, signals):
    added  = False
    finder = Finder(signals)

    # Retrieve all IDs from value trigger and edge trigger
    trigger_ids = []
    if args.value_trigger is not None:
        for id in get_trigger_ids(args.value_trigger, 3):
            if id not in trigger_ids:
                trigger_ids.append(id)

    if args.rising_edge is not None:
        for id in get_trigger_ids(args.rising_edge, 3):
            if id not in trigger_ids:
                trigger_ids.append(id)
    
    if args.falling_edge is not None:
        for id in get_trigger_ids(args.falling_edge, 3):
            if id not in trigger_ids:
                trigger_ids.append(id)

    # Empty paramter for the trigger configuration
    cond_value = {}
    cond_rising_edge = {}
    cond_falling_edge = {}
    list_trigger_value = {}
    list_trigger_rising_edge = {}
    list_trigger_falling_edge= {}
    offset_list = {}
    offset = 0
    fault_added = False
    fault_model = 0
    fault = {}

    for id in trigger_ids:

        # Retrieve all the value condition for the current trigger
        if args.value_trigger is not None:
            list_trigger_value = get_trigger_by_id(args.value_trigger, 3, id)
            for signal, value, _ in list_trigger_value or []:
                name = finder[signal]
                cond_value[finder[signal]] = value
                print(f"Condition : {name} == {value} for trigger number {id}")
                added = True

        # Retrieve all the rising edge condition for the current trigger
        if args.rising_edge is not None:
            list_trigger_rising_edge = get_trigger_by_id(args.rising_edge, 3, id)
            for signal, value, _ in list_trigger_rising_edge or []:
                name = finder[signal]
                cond = cond_rising_edge.get(finder[signal], [])
                cond.append(value)
                cond_rising_edge[finder[signal]] = cond
                print(f"Rising edge : {name} on bit {value} for trigger number {id}")
                added = True

        # Retrieve all the falling edge condition for the current trigger
        if args.falling_edge is not None:
            list_trigger_falling_edge = get_trigger_by_id(args.falling_edge, 3, id)
            for signal, value, _ in list_trigger_falling_edge or []:
                name = finder[signal]
                cond = cond_falling_edge.get(finder[signal], [])
                cond.append(value)
                cond_falling_edge[finder[signal]] = cond
                print(f"Falling edge : {name} on bit {value} for trigger number {id}")
                added = True
        
        # Retrieve the offset for the current trigger
        if args.offset is not None:
            offset_list = get_trigger_by_id(args.offset, 2, id)
            if len(offset_list) != 0:
                offset = int(offset_list[0][0])
                print(f"Offset : {offset} for trigger number {id}")
        
        # Retrieve all the bit set fault for the current trigger
        if args.bit_set is not None and fault_added is False:
            bit_set_fault = get_trigger_by_id(args.bit_set, 3, id)
            if len(bit_set_fault) != 0:
                fault_model = 1
                fault = bit_set_fault
                fault_added = True
                for i in range(len(fault)):
                    location_list = ast.literal_eval(fault[i][1])
                    print(f"Bit Set Fault : signal {fault[i][0]} on bit(s) {'all' if len(location_list) == 0 else fault[i][1]} for trigger number {id}")
                    fault[i][1] = location_list
                    fault[i][0] = finder[fault[i][0]]

        # Retrieve all the bit reset fault for the current trigger
        if args.bit_reset is not None and fault_added is False:
            bit_reset_fault = get_trigger_by_id(args.bit_reset, 3, id)
            if len(bit_reset_fault) != 0:
                fault_model = 2
                fault = bit_reset_fault
                fault_added = True
                for i in range(len(fault)):
                    location_list = ast.literal_eval(fault[i][1])
                    print(f"Bit Reset Fault : signal {fault[i][0]} on bit(s) {'all' if len(location_list) == 0 else fault[i][1]} for trigger number {id}")
                    fault[i][1] = location_list
                    fault[i][0] = finder[fault[i][0]]

        # Retrieve all the bit flip fault for the current trigger
        if args.bit_flip is not None and fault_added is False:
            bit_flip_fault = get_trigger_by_id(args.bit_flip, 3, id)
            if len(bit_flip_fault) != 0:
                fault_model = 3
                fault = bit_flip_fault
                fault_added = True
                for i in range(len(fault)):
                    location_list = ast.literal_eval(fault[i][1])
                    print(f"Bit Flip Fault : signal {fault[i][0]} on bit(s) {'all' if len(location_list) == 0 else fault[i][1]} for trigger number {id}")
                    fault[i][1] = location_list
                    fault[i][0] = finder[fault[i][0]]

        # Retrieve all the random bit flip fault for the current trigger
        if args.bit_flip_random is not None and fault_added is False:
            bit_flip_random_fault = get_trigger_by_id(args.bit_flip_random, 3, id)
            if len(bit_flip_random_fault) != 0:
                fault_model = 4
                fault = bit_flip_random_fault
                fault_added = True
                for i in range(len(fault)):
                    location_list = ast.literal_eval(fault[i][1])
                    print(f"Random Bit Flip Fault : signal {fault[i][0]} on bit(s) {'all' if len(location_list) == 0 else fault[i][1]} for trigger number {id}")
                    fault[i][1] = location_list
                    fault[i][0] = finder[fault[i][0]]

        # Retrieve all the bit value fault for the current trigger
        if args.bit_value is not None and fault_added is False:
            bit_value_fault = get_trigger_by_id(args.bit_value, 3, id)
            if len(bit_value_fault) != 0:
                fault_model = 5
                fault = bit_value_fault
                fault_added = True
                for i in range(len(fault)):
                    print(f"Bit Value Fault : signal {fault[i][0]} value {fault[i][1]} for trigger number {id}")
                    fault[i][0] = finder[fault[i][0]]

        injector.add_trigger(cond=cond_value, rising_edge=cond_rising_edge, falling_edge=cond_falling_edge, offset=offset, fault=fault, fault_model=fault_model)

        # Clear the current trigger to add another one
        fault.clear()
        fault_added = False
        offset = 0
        offset_list.clear()
        cond_value.clear()
        cond_rising_edge.clear()
        cond_falling_edge.clear()
        list_trigger_value.clear()
        list_trigger_rising_edge.clear()
        list_trigger_falling_edge.clear()

    return added

# Run Batch/GUI  -----------------------------------------------------------------------------------

def run_batch(args):
    bus = RemoteClient(host=args.host, csr_csv=args.csr_csv)
    bus.open()

    basename = os.path.splitext(os.path.basename(args.csv))[0]
    signals  = get_signals(args.csv, args.group)
    
    # Configure and run LiteInjector injector.
    injector = LiteInjectorDriver(bus.regs, basename, config_csv=args.csv, debug=True)
    injector.configure_group(args.group)
    if not add_triggers(args, injector, signals):
        raise Exception("You have not added any triggers !")
    injector.run()
    # Close remove control.
    bus.close()

# Main ---------------------------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="""LiteInjector Client utility""")
    parser.add_argument("-r", "--rising-edge",   action="append", nargs=3, help="Add rising edge trigger.", 
        metavar=("TRIGGER", "LOCATION", "ID"))
    parser.add_argument("-f", "--falling-edge",  action="append", nargs=3, help="Add falling edge trigger.",
        metavar=("TRIGGER", "LOCATION", "ID"))
    parser.add_argument("-v", "--value-trigger", action="append", nargs=3, help="Add conditional trigger with given value.",
        metavar=("TRIGGER", "VALUE", "ID"))
    parser.add_argument("-o", "--offset", action="append", nargs=2, help="Add an offset to the trigger.",
        metavar=("VALUE", "ID"))
    parser.add_argument("-bs", "--bit-set", action="append", nargs=3, help="Add a bit set fault to a trigger.",
        metavar=("SIGNAL", "LOCATION", "ID"))
    parser.add_argument("-br", "--bit-reset", action="append", nargs=3, help="Add a bit reset fault to a trigger.",
        metavar=("SIGNAL", "LOCATION", "ID"))
    parser.add_argument("-bf", "--bit-flip", action="append", nargs=3, help="Add a bit flip fault to a trigger.",
        metavar=("SIGNAL", "LOCATION", "ID"))
    parser.add_argument("-bfr", "--bit-flip-random", action="append", nargs=3, help="Add a random bit flip fault to a trigger.",
        metavar=("SIGNAL", "LOCATION", "ID"))
    parser.add_argument("-bv", "--bit-value", action="append", nargs=3, help="Add a bit value fault to a trigger.",
        metavar=("SIGNAL", "VALUE", "ID"))
    parser.add_argument("-l", "--list",          action="store_true",      help="List signal choices.")
    parser.add_argument("--host",                default="localhost",      help="Host ip address")
    parser.add_argument("--csv",                 default="injector.csv",   help="Analyzer CSV file.")
    parser.add_argument("--csr-csv",             default="csr.csv",        help="SoC CSV file.")
    parser.add_argument("--group",               default=0, type=int,      help="Signal Group.")
    args = parser.parse_args()
    return args

def main():
    args = parse_args()

    # Check if analyzer file is present and exit if not.
    if not os.path.exists(args.csv):
        raise ValueError("{} not found. This is necessary to load the wires which have been tapped to scope."
                         "Try setting --csv to value of the csr_csv argument to LiteInjector in the SoC.".format(args.csv))
        sys.exit(1)

    # If in list mode, list signals and exit.
    if args.list:
        signals = get_signals(args.csv, args.group)
        for signal in signals:
            print(signal)
        sys.exit(0)

    # Create and open remote control.
    if not os.path.exists(args.csr_csv):
        raise ValueError("{} not found. This is necessary to load the 'regs' of the remote. Try setting --csr-csv here to "
                         "the path to the --csr-csv argument of the SoC build.".format(args.csr_csv))

    # Run
    run_batch(args)


if __name__ == "__main__":
    main()