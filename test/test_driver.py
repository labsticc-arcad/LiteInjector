# SPDX-License-Identifier: BSD-2-Clause

# LiteInjector driver with simulated CSRs, and driver encoding checked against the gateware.

import pytest

from conftest import FakeRegs
from liteinjector.software.driver.injector import LiteInjectorDriver, FAULT_BIT_VALUE, FAULT_BIT_RESET
from liteinjector.software.model import Trigger, Fault

def make_driver(config_csv, **kwargs):
    regs = FakeRegs()
    return LiteInjectorDriver(regs, "injector", config_csv=config_csv(**kwargs)), regs

def test_add_writes_entry_then_pushes(config_csv):
    drv, regs = make_driver(config_csv)
    regs.log.clear()
    drv.add(Trigger(when={"sig_a": "0x10"}, offset=3, faults=[Fault("bit-flip", "sig_b", [0])]))
    assert regs.log[-1] == ("trigger_mem_write", 1)
    assert regs["trigger_mem_value"] == 0x10 and regs["trigger_mem_mask"] == 0xff
    assert regs["trigger_mem_offset"] == 3 and regs["trigger_mem_fault_xor"] == 0x0100

def test_memory_full(config_csv):
    drv, regs = make_driver(config_csv)
    regs.d["injector_trigger_mem_full"].value = 1
    with pytest.raises(RuntimeError, match="full"):
        drv.add(Trigger(when={"sig_a": "1"}))

def test_group_selection(config_csv):
    drv, regs = make_driver(config_csv)
    drv.configure_group(1)
    assert regs["mux_value"] == 1
    with pytest.raises(ValueError):
        drv.configure_group(5)

def test_status(config_csv):
    drv, regs = make_driver(config_csv)
    regs.d["injector_trigger_fault_count"].value = 2
    regs.d["injector_capture_after"].value = 0x1234
    status = drv.status()
    assert status["fault_count"] == 2 and status["capture_after"] == 0x1234 and status["armed"] is False

def test_wait_done_timeout(config_csv):
    drv, regs = make_driver(config_csv)
    assert drv.wait_done(timeout=0.02) is False
    regs.d["injector_trigger_done"].value = 1
    assert drv.wait_done(timeout=0.02) is True

def test_version_mismatch(config_csv):
    with pytest.raises(RuntimeError, match="Rebuild"):
        make_driver(config_csv, version=1)

def test_missing_registers(config_csv):
    with pytest.raises(RuntimeError, match="registers"):
        LiteInjectorDriver(FakeRegs(prefix="other"), "injector", config_csv=config_csv())

def test_legacy_add_trigger(config_csv):
    drv, regs = make_driver(config_csv)
    drv.add_trigger(cond={"sig_a": "1"}, fault=[["sig_a", [0], 0], ["sig_b", [1], 0]], fault_model=FAULT_BIT_RESET)
    assert regs["trigger_mem_fault_and"] == 0xffff & ~0x0201

# Driver + gateware --------------------------------------------------------------------------------

def test_driver_encoding_matches_gateware(config_csv):
    from migen import run_simulation
    from test_core import DUT, push, enable, play, faulted

    drv, regs = make_driver(config_csv)
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
