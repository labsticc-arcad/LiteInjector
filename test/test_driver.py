# SPDX-License-Identifier: BSD-2-Clause

# Tests of the LiteInjector driver encoding, with simulated CSRs (no hardware needed).

import pytest

from liteinjector.software.driver.injector import (LiteInjectorDriver, parse_value,
    FAULT_BIT_SET, FAULT_BIT_RESET, FAULT_BIT_FLIP, FAULT_BIT_FLIP_RANDOM, FAULT_BIT_VALUE, FLAG_RANDOM)

CSRS = ["mux_value", "trigger_enable", "trigger_clear", "trigger_seed", "trigger_mem_write",
    "trigger_mem_mask", "trigger_mem_value", "trigger_mem_r_edge_mask", "trigger_mem_f_edge_mask",
    "trigger_mem_fault_and", "trigger_mem_fault_or", "trigger_mem_fault_xor", "trigger_mem_offset",
    "trigger_mem_duration", "trigger_mem_flags", "trigger_mem_full", "trigger_done", "trigger_busy",
    "trigger_hit_count", "trigger_fault_count", "trigger_hit_timestamp", "capture_before", "capture_after"]

class FakeReg:
    def __init__(self):
        self.value = 0
    def write(self, value):
        self.value = value
    def read(self):
        return self.value

class FakeRegs:
    def __init__(self):
        self.d = {"injector_" + name: FakeReg() for name in CSRS}
    def __getitem__(self, name):
        return self.d["injector_" + name].value

def make_driver(tmp_path, version=2, lfsr=1):
    csv = tmp_path / "injector.csv"
    csv.write_text(
        f"config,None,version,{version}\n"
        "config,None,data_width,16\n"
        "config,None,depth,16\n"
        "config,None,offset_depth,500\n"
        "config,None,duration_depth,255\n"
        f"config,None,lfsr,{lfsr}\n"
        "signal,0,sig_a,8\n"
        "signal,0,sig_b,8\n"
    )
    regs = FakeRegs()
    return LiteInjectorDriver(regs, "injector", config_csv=str(csv)), regs

def test_parse_value():
    assert parse_value("0x3x", 8) == (0x30, 0xf0)
    assert parse_value("0b1x0", 3) == (0b100, 0b101)
    assert parse_value("12", 8) == (12, 0xff)

def test_condition_and_edges(tmp_path):
    drv, regs = make_driver(tmp_path)
    drv.add_trigger(cond={"sig_a": "0x1x"}, rising_edge={"sig_b": ["0", "7"]}, falling_edge={"sig_a": ["1"]})
    assert regs["trigger_mem_value"] == 0x0010
    assert regs["trigger_mem_mask"] == 0x00f0
    assert regs["trigger_mem_r_edge_mask"] == 0x8100
    assert regs["trigger_mem_f_edge_mask"] == 0x0002
    assert regs["trigger_mem_duration"] == 1

def test_bit_set(tmp_path):
    drv, regs = make_driver(tmp_path)
    drv.add_trigger(cond={"sig_a": "1"}, fault=[["sig_b", [0, 3], 0]], fault_model=FAULT_BIT_SET)
    assert (regs["trigger_mem_fault_and"], regs["trigger_mem_fault_or"], regs["trigger_mem_fault_xor"]) == (0xffff, 0x0900, 0)

def test_bit_reset_on_two_signals(tmp_path):
    # Regression: the old driver inverted the accumulated mask once per signal.
    drv, regs = make_driver(tmp_path)
    drv.add_trigger(cond={"sig_a": "1"}, fault=[["sig_a", [0], 0], ["sig_b", [1], 0]], fault_model=FAULT_BIT_RESET)
    assert regs["trigger_mem_fault_and"] == 0xffff & ~0x0201

def test_bit_flip_all_bits(tmp_path):
    drv, regs = make_driver(tmp_path)
    drv.add_trigger(cond={"sig_a": "1"}, fault=[["sig_b", [], 0]], fault_model=FAULT_BIT_FLIP)
    assert regs["trigger_mem_fault_xor"] == 0xff00
    assert regs["trigger_mem_flags"] == 0

def test_random_bit_flip_all_bits(tmp_path):
    # Regression: the old driver crashed when no bit list was given.
    drv, regs = make_driver(tmp_path)
    drv.add_trigger(cond={"sig_a": "1"}, fault=[["sig_b", [], 0]], fault_model=FAULT_BIT_FLIP_RANDOM)
    assert regs["trigger_mem_fault_xor"] == 0xff00
    assert regs["trigger_mem_flags"] == 1 << FLAG_RANDOM

def test_random_bit_flip_requires_lfsr(tmp_path):
    drv, _ = make_driver(tmp_path, lfsr=0)
    with pytest.raises(ValueError):
        drv.add_trigger(cond={"sig_a": "1"}, fault=[["sig_b", [], 0]], fault_model=FAULT_BIT_FLIP_RANDOM)

def test_bit_value_with_dont_care(tmp_path):
    # Regression: "x" digits of a value fault used to be written as zeros.
    drv, regs = make_driver(tmp_path)
    drv.add_trigger(cond={"sig_a": "1"}, fault=[["sig_b", "0xAx", 0]], fault_model=FAULT_BIT_VALUE)
    assert regs["trigger_mem_fault_and"] == 0x0fff
    assert regs["trigger_mem_fault_or"]  == 0xa000

def test_out_of_range_bit(tmp_path):
    drv, _ = make_driver(tmp_path)
    with pytest.raises(ValueError):
        drv.add_trigger(cond={"sig_a": "1"}, fault=[["sig_a", [8], 0]], fault_model=FAULT_BIT_FLIP)

def test_version_mismatch(tmp_path):
    with pytest.raises(RuntimeError):
        make_driver(tmp_path, version=1)

# Driver + gateware --------------------------------------------------------------------------------

def test_driver_encoding_matches_gateware(tmp_path):
    from migen import run_simulation
    from test_core import DUT, push, enable, play, faulted

    drv, regs = make_driver(tmp_path)
    # Force the high nibble of sig_b to 0xA when sig_a == 0x10.
    drv.add_trigger(cond={"sig_a": "0x10"}, fault=[["sig_b", "0xAx", 0]], fault_model=FAULT_BIT_VALUE)
    entry = dict(
        mask=regs["trigger_mem_mask"], value=regs["trigger_mem_value"],
        fault_and=regs["trigger_mem_fault_and"], fault_or=regs["trigger_mem_fault_or"],
        fault_xor=regs["trigger_mem_fault_xor"], duration=regs["trigger_mem_duration"])

    dut, log = DUT(), []
    def tb():
        yield from push(dut, **entry)
        yield from enable(dut)
        yield from play(dut, log, [0, 0x10], [0x05, 0x05])
    run_simulation(dut, tb())
    assert faulted(log) == [1]
    assert log[1][3] == 0xa5 # High nibble forced, "x" nibble kept.
