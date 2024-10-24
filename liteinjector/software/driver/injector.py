# Copyright (c) 2015-2018 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2019 kees.jongenburger <kees.jongenburger@gmail.com>
# Copyright (c) 2018 Sean Cross <sean@xobs.io>
# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

import os
import sys
import re
import math
import random

from migen import *

import csv

class LiteInjectorDriver:
    def __init__(self, regs, name, config_csv=None, debug=False):
        self.regs = regs
        self.name = name
        self.config_csv = config_csv
        if self.config_csv is None:
            self.config_csv = name + ".csv"
        self.debug = debug
        self.get_config()
        self.get_layouts()
        self.build()
        self.group = 0

        self.trigger_enable.write(0)

    def get_config(self):
        csv_reader = csv.reader(open(self.config_csv), delimiter=',', quotechar='#')
        for item in csv_reader:
            t, g, n, v = item
            if t == "config":
                setattr(self, n, int(v))

    def get_layouts(self):
        self.layouts = {}
        csv_reader = csv.reader(open(self.config_csv), delimiter=',', quotechar='#')
        for item in csv_reader:
            t, g, n, v = item
            if t == "signal":
                try:
                    self.layouts[int(g)].append((n, int(v)))
                except:
                    self.layouts[int(g)] = [(n, int(v))]

    def get_signal_size(self, layout, signal_name, index):
        for name, size in layout[index]:
            if signal_name == name:
                return size
        
        return None
    
    def get_data_width(self, layout, index):
        total_size = 0
        for name, size in layout[index]:
            total_size += size
        return total_size

    def build(self):
        for key, value in self.regs.d.items():
            if self.name == key[:len(self.name)]:
                key = key.replace(self.name + "_", "")
                setattr(self, key, value)
        for signals in self.layouts.values():
            value = 1
            for name, length in signals:
                setattr(self, name + "_o", value)
                value = value*(2**length)
        for signals in self.layouts.values():
            value = 0
            for name, length in signals:
                setattr(self, name + "_m", (2**length-1) << value)
                value += length

    def configure_group(self, value):
        self.group = value
        self.mux_value.write(value)

    def add_trigger(self, value=0, mask=0, cond=None, rising_edge=None, falling_edge=None, offset=0, fault=None, fault_model=0):
        rising_edge_mask  = 0
        falling_edge_mask  = 0
        fault_mask = 0
        fault_value = 0

        data_width = self.get_data_width(self.layouts, 0)

        if self.trigger_mem_full.read():
            raise ValueError("Trigger memory full, too much conditions")
        if cond is not None:
            for k, v in cond.items():
                # Check for binary/hexa expressions
                mb = re.match("0b([01x]+)",  v)
                mx = re.match("0x([0-fx]+)", v)
                m  = mb or mx
                if m is not None:
                    b = m.group(1)
                    v = 0
                    m = 0
                    for c in b:
                        v <<= 4 if mx is not None else 1
                        m <<= 4 if mx is not None else 1
                        if c != "x":
                            v |= int(c, 16 if mx is not None else 2 )
                            m |= 0xf if mx is not None else 0b1
                    value |= getattr(self, k + "_o")*v
                    mask  |= getattr(self, k + "_m") & (getattr(self, k + "_o")*m)
                # Else convert to int
                else:
                    value |= getattr(self, k + "_o")*int(v, 0)
                    mask  |= getattr(self, k + "_m")

        if rising_edge is not None:
            for signal_name, locations in rising_edge.items():
                signal_size = self.get_signal_size(self.layouts, signal_name, 0)
                if signal_size is None:
                    raise Exception("Cannot find the size of the signal !")
                signal_start = int(math.log2(getattr(self, signal_name + "_o")))
                for location in locations:
                    if signal_size < int(location):
                        raise Exception("You are trying to shift beyond the size of the signal !")
                    rising_edge_mask |= 1<<signal_start+int(location)

        if falling_edge is not None:
            for signal_name, locations in falling_edge.items():
                signal_size = self.get_signal_size(self.layouts, signal_name, 0)
                if signal_size is None:
                    raise Exception("Cannot find the size of the signal !")
                signal_start = int(math.log2(getattr(self, signal_name + "_o")))
                for location in locations:
                    if signal_size < int(location):
                        raise Exception("You are trying to shift beyond the size of the signal !")
                    falling_edge_mask |= 1<<signal_start+int(location)

        if fault is not None and fault_model in [1,2,3]:
            for signal_name, locations, _ in fault:
                signal_size = self.get_signal_size(self.layouts, signal_name, 0)
                if signal_size is None:
                    raise Exception("Cannot find the size of the signal !")
                signal_start = int(math.log2(getattr(self, signal_name + "_o")))
                if len(locations) == 0:
                    fault_value |= getattr(self, signal_name + "_m")
                else:
                    for location in locations:
                        if signal_size < int(location):
                            raise Exception("You are trying to shift beyond the size of the signal !")
                        fault_value |= 1<<signal_start+int(location)

                # Flip the entire mask for the bit reset fault model
                if fault_model == 2:
                    mask_flip = (1 << data_width) - 1
                    fault_value = fault_value ^ mask_flip

        if fault is not None and fault_model == 4:
            for signal_name, locations, _ in fault:
                signal_size = self.get_signal_size(self.layouts, signal_name, 0)
                if signal_size is None:
                    raise Exception("Cannot find the size of the signal !")
                signal_start = int(math.log2(getattr(self, signal_name + "_o")))
                if len(locations) == 0:
                    for i in range(self.get_signal_size(signal_name)):
                        random_bit = random.randint(0, 1)
                        fault_value |= random_bit<<signal_start+int(location)
                else:
                    for location in locations:
                        if signal_size < int(location):
                            raise Exception("You are trying to shift beyond the size of the signal !")
                        random_bit = random.randint(0, 1)
                        fault_value |= random_bit<<signal_start+int(location)

        if fault is not None and fault_model == 5:
            for signal_name, current_value, _ in fault:
                # Check for binary/hexa expressions
                mb = re.match("0b([01x]+)",  current_value)
                mx = re.match("0x([0-fx]+)", current_value)
                m  = mb or mx
                if m is not None:
                    b = m.group(1)
                    current_value = 0
                    m = 0
                    for c in b:
                        current_value <<= 4 if mx is not None else 1
                        m <<= 4 if mx is not None else 1
                        if c != "x":
                            current_value |= int(c, 16 if mx is not None else 2 )
                            m |= 0xf if mx is not None else 0b1
                    fault_value |= getattr(self, signal_name + "_o")*current_value
                    fault_mask  |= getattr(self, signal_name + "_m")
                # Else convert to int
                else:
                    fault_value |= getattr(self, signal_name + "_o")*int(current_value, 0)
                    fault_mask  |= getattr(self, signal_name + "_m")
            
            mask_flip = (1 << data_width) - 1
            fault_mask = fault_mask ^ mask_flip

        if fault is None:
            fault_mask = 0
            fault_value = 0
            fault_model = 0

        self.trigger_mem_offset.write(offset)
        self.trigger_mem_mask.write(mask)
        self.trigger_mem_value.write(value)
        self.trigger_mem_r_edge_mask.write(rising_edge_mask)
        self.trigger_mem_f_edge_mask.write(falling_edge_mask)
        self.trigger_mem_fault_mask.write(fault_mask)
        self.trigger_mem_fault_value.write(fault_value)
        self.trigger_mem_fault_model.write(fault_model)
        self.trigger_mem_write.write(1)

    def run(self, length=None):
        if length is None:
            length = self.depth
        assert length <= self.depth
        self.length = length
        if self.debug:
            print("[The injector has been configured]...")
        self.trigger_enable.write(1)

    def done(self):
        return self.storage_done.read()

    def wait_done(self):
        while not self.done():
            pass
