# SPDX-License-Identifier: BSD-2-Clause

# Simulation tests of the LiteInjector gateware (run with: python -m pytest test).

import os
import tempfile

import pytest

from migen import *
from migen.fhdl import verilog

from liteinjector.core import LiteInjector, LITEINJECTOR_VERSION, FLAG_RANDOM

ALL = 0xffff # All ones for the 16-bit group 0 (a: bits 0-7, b: bits 8-15).

class DUT(Module):
    def __init__(self, depth=8, **kwargs):
        self.a = Signal(8)
        self.b = Signal(8)
        self.c = Signal(16)
        self.submodules.inj = LiteInjector({0: [self.a, self.b], 1: [self.c]}, depth=depth, csr_csv=None, **kwargs)

# Helpers ------------------------------------------------------------------------------------------

def push(dut, mask=0, value=0, r_edge=0, f_edge=0, fault_and=ALL, fault_or=0, fault_xor=0,
    offset=0, duration=0, flags=0):
    t = dut.inj.trigger
    yield t.mem_mask.storage.eq(mask)
    yield t.mem_value.storage.eq(value)
    yield t.mem_r_edge_mask.storage.eq(r_edge)
    yield t.mem_f_edge_mask.storage.eq(f_edge)
    yield t.mem_fault_and.storage.eq(fault_and)
    yield t.mem_fault_or.storage.eq(fault_or)
    yield t.mem_fault_xor.storage.eq(fault_xor)
    yield t.mem_offset.storage.eq(offset)
    yield t.mem_duration.storage.eq(duration)
    yield t.mem_flags.storage.eq(flags)
    yield t.mem_write.re.eq(1)
    yield
    yield t.mem_write.re.eq(0)
    yield

def enable(dut, value=1):
    yield dut.inj.trigger.enable.storage.eq(value)
    yield

def clear(dut):
    yield dut.inj.trigger.clear.re.eq(1)
    yield
    yield dut.inj.trigger.clear.re.eq(0)
    yield

def play(dut, log, a_values, b_values=None):
    """Drive one value per cycle and log (a_in, b_in, a_out, b_out, hit)."""
    b_values = b_values or [0]*len(a_values)
    for a, b in zip(a_values, b_values):
        yield dut.a.eq(a)
        yield dut.b.eq(b)
        yield
        log.append((
            (yield dut.a), (yield dut.b),
            (yield dut.inj.o_a), (yield dut.inj.o_b),
            (yield dut.inj.trigger.output_hit),
        ))

def run(dut, *generators, **kwargs):
    def tb():
        for g in generators:
            yield from g
    run_simulation(dut, tb(), **kwargs)

def faulted(log):
    return [i for i, (a, b, oa, ob, hit) in enumerate(log) if hit]

def status(dut, name):
    return getattr(dut.inj.trigger, name).status

# Trigger timing -----------------------------------------------------------------------------------

def test_offset_zero_faults_matching_cycle():
    dut, log = DUT(), []
    run(dut,
        push(dut, mask=0x00ff, value=0x10, fault_xor=0x0001),
        enable(dut),
        play(dut, log, [0, 0, 0x10, 0, 0]))
    assert faulted(log) == [2]
    assert log[2][2] == 0x11
    assert [l[2] for l in log if not l[4]] == [0, 0, 0, 0]

def test_offset_delays_fault():
    dut, log = DUT(), []
    run(dut,
        push(dut, mask=0x00ff, value=0x10, fault_xor=0x0001, offset=3),
        enable(dut),
        play(dut, log, [0, 0x10] + [0]*6))
    # Same latency as the original core: fault applied `offset` cycles after the match.
    assert faulted(log) == [1 + 3]

def test_sequence_waits_for_each_condition():
    # Regression: the original offset counter stayed "done" after the first fault, so the next
    # trigger with the same offset fired without its condition.
    dut, log = DUT(), []
    run(dut,
        push(dut, mask=0x00ff, value=0x10, fault_xor=0x0001, offset=3),
        push(dut, mask=0x00ff, value=0x20, fault_xor=0x0002, offset=3),
        enable(dut),
        play(dut, log, [0]*3 + [0x10] + [0]*12))
    assert faulted(log) == [3 + 3]
    assert log[6][2] == 0x01

def test_sequence_two_triggers():
    dut, log, done = DUT(), [], []
    def check():
        done.append((yield status(dut, "done")))
    run(dut,
        push(dut, mask=0x00ff, value=0x10, fault_xor=0x0001, offset=2),
        push(dut, mask=0x00ff, value=0x20, fault_xor=0x0002, offset=2),
        enable(dut),
        play(dut, log, [0, 0x10, 0, 0, 0, 0x20, 0, 0, 0, 0]),
        check())
    assert faulted(log) == [3, 7]
    assert done == [1]

def test_entry_without_condition_never_fires():
    dut, log = DUT(), []
    run(dut,
        push(dut, fault_xor=0x0001),
        enable(dut),
        play(dut, log, [0, 1, 2, 3]))
    assert faulted(log) == []

def test_disabled_injector_does_not_fire():
    dut, log = DUT(), []
    run(dut,
        push(dut, mask=0x00ff, value=0x10, fault_xor=0x0001),
        play(dut, log, [0x10, 0x10, 0]),
        enable(dut),
        play(dut, log, [0x10]))
    assert faulted(log) == [3]

def test_dont_care_mask():
    dut, log = DUT(), []
    run(dut,
        push(dut, mask=0x00f0, value=0x0030, fault_xor=0x0001),
        enable(dut),
        play(dut, log, [0x4a, 0x3a, 0x3a]))
    assert faulted(log) == [1]

def test_rising_and_falling_edges():
    dut, log = DUT(), []
    run(dut,
        push(dut, r_edge=0x0001, fault_xor=0x0100),
        push(dut, f_edge=0x0001, fault_xor=0x0200),
        enable(dut),
        play(dut, log, [0, 1, 1, 0, 0]))
    assert faulted(log) == [1, 3]
    assert log[1][3] == 0x01 and log[3][3] == 0x02

# Fault models -------------------------------------------------------------------------------------

@pytest.mark.parametrize("fault, a_out", [
    (dict(fault_or=0x0001),          0x11), # Bit set.
    (dict(fault_and=ALL & ~0x0010),  0x00), # Bit reset.
    (dict(fault_xor=0x0003),         0x13), # Bit flip.
    (dict(fault_and=0xff00, fault_or=0x00ab), 0xab), # Value.
])
def test_fault_models(fault, a_out):
    dut, log = DUT(), []
    run(dut,
        push(dut, mask=0x00ff, value=0x10, **fault),
        enable(dut),
        play(dut, log, [0x10], [0x0f]))
    assert log[0][2] == a_out
    assert log[0][3] == 0x0f

def test_several_fault_models_in_one_trigger():
    dut, log = DUT(), []
    run(dut,
        # Set bit 0 of a and flip every bit of b at the same cycle.
        push(dut, mask=0x00ff, value=0x10, fault_or=0x0001, fault_xor=0xff00),
        enable(dut),
        play(dut, log, [0x10], [0x0f]))
    assert log[0][2:4] == (0x11, 0xf0)

def test_duration():
    dut, log = DUT(), []
    run(dut,
        push(dut, mask=0x00ff, value=0x10, fault_xor=0x0001, offset=1, duration=3),
        enable(dut),
        play(dut, log, [0x10] + [0]*6))
    assert faulted(log) == [1, 2, 3]

def test_random_bit_flip():
    dut, log = DUT(depth=8), []
    entries = [push(dut, mask=0x00ff, value=0x10, fault_xor=0x00ff, flags=1 << FLAG_RANDOM) for _ in range(6)]
    run(dut, *entries, enable(dut), play(dut, log, [0x10, 0]*6))
    outputs = [log[i][2] ^ 0x10 for i in faulted(log)]
    assert len(outputs) == 6
    assert len(set(outputs)) > 1                 # A new random vector for each fault.
    assert all(l[3] == 0 for l in log)           # Bits outside the XOR mask are untouched.

# Control and status -------------------------------------------------------------------------------

def test_clear_flushes_entries_and_counters():
    dut, values = DUT(), {}
    def check():
        for _ in range(12): # Flushing pops one entry per cycle.
            yield
        for name in ["done", "busy", "hit_count", "fault_count", "mem_full"]:
            values[name] = (yield status(dut, name))
    log = []
    run(dut,
        *[push(dut, mask=0x00ff, value=0x10, fault_xor=0x0001) for _ in range(8)],
        enable(dut),
        play(dut, log, [0x10]),
        clear(dut),
        check())
    assert values == {"done": 1, "busy": 0, "hit_count": 0, "fault_count": 0, "mem_full": 0}

def test_counters_timestamp_and_capture():
    dut, values = DUT(), {}
    def check():
        yield
        for name in ["hit_count", "fault_count", "hit_timestamp"]:
            values[name] = (yield status(dut, name))
        values["before"] = (yield dut.inj.capture_before.status)
        values["after"]  = (yield dut.inj.capture_after.status)
    log = []
    run(dut,
        push(dut, mask=0x00ff, value=0x10, fault_xor=0x0001, offset=2),
        enable(dut),
        play(dut, log, [0]*5 + [0x10] + [0]*3, [0x55]*9),
        check())
    assert values["hit_count"] == 1 and values["fault_count"] == 1
    assert values["hit_timestamp"] > 0
    assert values["before"] == 0x5500
    assert values["after"]  == 0x5501

def test_loaded_counter():
    dut, values = DUT(), []
    def check():
        yield
        values.append((yield dut.inj.trigger.loaded.status))
    run(dut,
        *[push(dut, mask=0x00ff, value=0x10, fault_xor=0x0001) for _ in range(3)],
        check(),
        clear(dut),
        check())
    assert values == [3, 0]

def test_history_records_every_fault():
    dut, log, events = DUT(depth=4), [], []
    def read_history():
        for _ in range(3):
            yield
        for index in range(3):
            yield dut.inj.history_index.storage.eq(index)
            yield
            yield
            events.append((
                (yield dut.inj.history_timestamp.status),
                (yield dut.inj.history_before.status),
                (yield dut.inj.history_after.status)))
    run(dut,
        push(dut, mask=0x00ff, value=0x10, fault_xor=0x0001),
        push(dut, mask=0x00ff, value=0x20, fault_xor=0x0002, offset=2),
        enable(dut),
        play(dut, log, [0, 0x10, 0, 0x20, 0, 0, 0, 0], [0x55]*8),
        read_history())
    assert faulted(log) == [1, 5]
    # Cycles increase and the data before/after of each fault is recorded (the 3rd slot is unused).
    assert events[0][1:] == (0x5510, 0x5511)
    assert events[1][1:] == (0x5500, 0x5502)
    assert 0 < events[0][0] < events[1][0]

def test_history_cleared_by_new_sequence():
    dut, log, values = DUT(depth=4), [], []
    def check():
        yield
        values.append((yield dut.inj.trigger.fault_count.status))
    run(dut,
        push(dut, mask=0x00ff, value=0x10, fault_xor=0x0001),
        enable(dut),
        play(dut, log, [0x10]),
        clear(dut),
        check())
    assert values == [0] # History slots are only valid below fault_count.

def test_history_can_be_disabled():
    dut = DUT(with_history=False)
    assert not hasattr(dut.inj, "history_index")
    assert dut.inj.config()["history"] == 0
    assert DUT().inj.config()["history"] == 1

def test_group_selection():
    dut, out = DUT(), []
    def tb():
        yield dut.inj.mux.value.storage.eq(1)
        yield from push(dut, mask=0xffff, value=0x1234, fault_xor=0x8000)
        yield from enable(dut)
        yield dut.c.eq(0x1234)
        yield
        out.append((yield dut.inj.o_c))
    run_simulation(dut, tb())
    assert out == [0x9234]

# Build --------------------------------------------------------------------------------------------

def test_export_capabilities():
    dut = DUT(offset_depth=100, duration_depth=15, with_lfsr=False)
    out = verilog.convert(dut)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "injector.csv")
        dut.inj.export_csv(out.ns, path)
        lines = open(path).read().splitlines()
    assert f"config,None,version,{LITEINJECTOR_VERSION}" in lines
    assert "config,None,data_width,16" in lines
    assert "config,None,offset_depth,100" in lines
    assert "config,None,duration_depth,15" in lines
    assert "config,None,lfsr,0" in lines
    assert sum(l.startswith("signal,0,") for l in lines) == 2

class CDCDUT(Module):
    def __init__(self):
        self.clock_domains.cd_fast = ClockDomain()
        self.a = Signal(8)
        self.b = Signal(8)
        self.submodules.inj = LiteInjector([self.a, self.b], depth=4, clock_domain="fast", csr_csv=None)

def test_other_clock_domain_builds():
    verilog.convert(CDCDUT())

def test_other_clock_domain_injects():
    dut, log = CDCDUT(), []
    def drive():
        for _ in range(40):
            yield dut.a.eq(0x10)
            yield
            log.append(((yield dut.inj.o_a), (yield dut.inj.trigger.output_hit)))
    def tb():
        yield from push(dut, mask=0x00ff, value=0x10, fault_xor=0x0001)
        yield from enable(dut)
        for _ in range(10):
            yield
        yield from drive_sync()
    hits = []
    def drive_sync():
        for _ in range(40):
            yield
            hits.append((yield dut.inj.trigger.fault_count.status))
    run_simulation(dut, {"sys": [tb()], "fast": [drive()]}, clocks={"sys": 10, "fast": 7})
    assert sum(hit for _, hit in log) == 1
    assert hits[-1] == 1
