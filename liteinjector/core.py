# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2018 bunnie <bunnie@kosagi.com>
# Copyright (c) 2016 Tim 'mithro' Ansell <mithro@mithis.com>
# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.cdc import MultiReg, PulseSynchronizer
from migen.genlib.fifo import SyncFIFO, AsyncFIFO

from litex.build.tools import write_to_file

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import stream

# LiteInjector -------------------------------------------------------------------------------------

# Hardware/software interface version, exported in the configuration CSV. Bump it whenever the
# CSR map or the meaning of a field changes so that the driver can refuse an incompatible SoC.
LITEINJECTOR_VERSION = 2

# Trigger entry flags.
FLAG_RANDOM = 0 # Fault XOR vector is ANDed with the LFSR output (random bit flip).

def core_layout(data_width):
    # The fault is applied as: output = ((data & fault_and) | fault_or) ^ fault_xor
    return [
        ("data",      data_width),
        ("hit",       1),
        ("fault_and", data_width),
        ("fault_or",  data_width),
        ("fault_xor", data_width),
    ]

def entry_layout(data_width, offset_depth, duration_depth):
    return [
        ("mask",        data_width),     # Value condition mask.
        ("value",       data_width),     # Value condition.
        ("r_edge_mask", data_width),     # Bits that must have a rising edge.
        ("f_edge_mask", data_width),     # Bits that must have a falling edge.
        ("fault_and",   data_width),
        ("fault_or",    data_width),
        ("fault_xor",   data_width),
        ("offset",      bits_for(offset_depth)),   # Cycles between the trigger and the fault.
        ("duration",    bits_for(duration_depth)), # Fault duration in cycles (0 and 1: one cycle).
        ("flags",       1),
    ]

def _cdc_to(module, signal, src_domain, dst_domain):
    """Return `signal` as seen from `dst_domain` (level signals only)."""
    if src_domain == dst_domain:
        return signal
    synced = Signal.like(signal)
    module.specials += MultiReg(signal, synced, dst_domain)
    return synced

class _Mux(Module, AutoCSR):
    def __init__(self, data_width, n, clock_domain="sys"):
        self.sinks  = sinks  = [stream.Endpoint(core_layout(data_width)) for i in range(n)]
        self.source = source = stream.Endpoint(core_layout(data_width))

        self.value = CSRStorage(bits_for(n))

        # # #

        value = _cdc_to(self, self.value.storage, "sys", clock_domain)

        cases = {}
        for i in range(n):
            cases[i] = sinks[i].connect(source)
        self.comb += Case(value, cases)

class _LFSR(Module):
    """Free running xorshift32 lanes, one new `width`-bit random word per cycle."""
    def __init__(self, width, seed):
        self.load   = Signal()
        self.output = Signal(width)

        # # #

        lanes = []
        for i in range((width + 31)//32):
            state     = Signal(32, reset=(0x2545F491 ^ (0x9E3779B9*(i + 1))) & 0xffffffff or 1)
            lane_seed = Signal(32)
            x1, x2, x3 = Signal(32), Signal(32), Signal(32)
            self.comb += [
                # Each lane gets a different non-zero seed derived from the CSR seed.
                lane_seed.eq(seed ^ ((0x9E3779B9*(i + 1)) & 0xffffffff)),
                x1.eq(state ^ (state << 13)),
                x2.eq(x1 ^ (x1 >> 17)),
                x3.eq(x2 ^ (x2 << 5)),
            ]
            self.sync += If(self.load,
                state.eq(Mux(lane_seed == 0, 1, lane_seed))
            ).Else(
                state.eq(x3)
            )
            lanes.append(state)
        self.comb += self.output.eq(Cat(*lanes)[:width])

class _TriggerCore(Module):
    """Trigger sequencer, runs entirely in its own (renamed) "sys" clock domain.

    Entries are popped from a first-word-fall-through FIFO, one entry per injection, so that
    several triggers form a sequence (multi-fault attacks).
    """
    def __init__(self, data_width, offset_depth, duration_depth, with_lfsr):
        self.data     = Signal(data_width)
        self.entry    = Record(entry_layout(data_width, offset_depth, duration_depth))
        self.readable = Signal() # An entry is available.
        self.pop      = Signal() # Consume the current entry.
        self.enable   = Signal()
        self.clear    = Signal() # Pulse: flush the entries, reset counters, reload the LFSR seed.
        self.seed     = Signal(32)

        self.trigger_hit  = Signal() # Trigger condition accepted.
        self.output_hit   = Signal() # Fault applied on this cycle.
        self.inject_start = Signal() # First cycle of a fault.
        self.fault_and    = Signal(data_width)
        self.fault_or     = Signal(data_width)
        self.fault_xor    = Signal(data_width)

        self.busy          = Signal()
        self.done          = Signal()
        self.hit_count     = Signal(32)
        self.fault_count   = Signal(32)
        self.hit_timestamp = Signal(32)

        # # #

        entry = self.entry

        # Edge detectors.
        data_d = Signal(data_width)
        self.sync += data_d.eq(self.data)
        rising  = Signal(data_width)
        falling = Signal(data_width)
        self.comb += [
            rising.eq(self.data & ~data_d),
            falling.eq(~self.data & data_d),
        ]

        # Trigger condition: every masked bit matches, every requested edge is present. An entry
        # without any condition never matches.
        match = Signal()
        self.comb += match.eq(
            ((entry.mask | entry.r_edge_mask | entry.f_edge_mask) != 0) &
            ((self.data & entry.mask) == (entry.value & entry.mask)) &
            ((rising  & entry.r_edge_mask) == entry.r_edge_mask) &
            ((falling & entry.f_edge_mask) == entry.f_edge_mask)
        )

        # Sequencer.
        count     = Signal(bits_for(offset_depth))
        remaining = Signal(bits_for(duration_depth))

        # First cycle of a fault, shared by IDLE (offset 0) and DELAY.
        def start_fault():
            return [
                self.output_hit.eq(1),
                self.inject_start.eq(1),
                If(entry.duration > 1,
                    NextValue(remaining, entry.duration - 1),
                    NextState("INJECT")
                ).Else(
                    self.pop.eq(1),
                    NextState("IDLE")
                )
            ]

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            self.trigger_hit.eq(self.enable & self.readable & match & ~self.clear),
            If(self.clear,
                NextState("FLUSH")
            ).Elif(self.trigger_hit,
                If(entry.offset == 0,
                    *start_fault()
                ).Else(
                    NextValue(count, 1),
                    NextState("DELAY")
                )
            )
        )
        fsm.act("DELAY",
            If(self.clear,
                NextState("FLUSH")
            ).Elif(~self.enable,
                NextState("IDLE")
            ).Elif(count == entry.offset,
                *start_fault()
            ).Else(
                NextValue(count, count + 1)
            )
        )
        fsm.act("INJECT",
            If(self.clear,
                NextState("FLUSH")
            ).Elif(~self.enable,
                NextState("IDLE")
            ).Else(
                self.output_hit.eq(1),
                If(remaining == 1,
                    self.pop.eq(1),
                    NextState("IDLE")
                ).Else(
                    NextValue(remaining, remaining - 1)
                )
            )
        )
        fsm.act("FLUSH",
            self.pop.eq(self.readable),
            If(~self.readable,
                NextState("IDLE")
            )
        )
        self.comb += [
            self.busy.eq(fsm.ongoing("DELAY") | fsm.ongoing("INJECT") | fsm.ongoing("FLUSH")),
            self.done.eq(~self.readable & fsm.ongoing("IDLE")),
        ]

        # Fault vector.
        fault_xor = entry.fault_xor
        if with_lfsr:
            self.submodules.lfsr = lfsr = _LFSR(data_width, self.seed)
            self.comb += lfsr.load.eq(self.clear)
            fault_xor = Mux(entry.flags[FLAG_RANDOM], entry.fault_xor & lfsr.output, entry.fault_xor)
        self.comb += [
            self.fault_and.eq(entry.fault_and),
            self.fault_or.eq(entry.fault_or),
            self.fault_xor.eq(fault_xor),
        ]

        # Counters and timestamp (cycles since the injector was armed).
        cycles   = Signal(32)
        enable_d = Signal()
        self.sync += [
            enable_d.eq(self.enable),
            If(self.clear | (self.enable & ~enable_d),
                cycles.eq(0)
            ).Elif(self.enable,
                cycles.eq(cycles + 1)
            ),
            If(self.clear,
                self.hit_count.eq(0),
                self.fault_count.eq(0),
                self.hit_timestamp.eq(0),
            ).Else(
                If(self.trigger_hit, self.hit_count.eq(self.hit_count + 1)),
                If(self.inject_start,
                    self.fault_count.eq(self.fault_count + 1),
                    self.hit_timestamp.eq(cycles)
                )
            )
        ]

class _Trigger(Module, AutoCSR):
    def __init__(self, data_width, depth=16, offset_depth=500, duration_depth=255, with_lfsr=True, clock_domain="sys"):
        self.sink   = sink   = stream.Endpoint(core_layout(data_width))
        self.source = source = stream.Endpoint(core_layout(data_width))

        # Control.
        self.enable = CSRStorage()
        self.clear  = CSR()
        self.seed   = CSRStorage(32, reset=0x2545F491)

        # Trigger entry, pushed in the FIFO by writing mem_write.
        self.mem_write       = CSR()
        self.mem_mask        = CSRStorage(data_width)
        self.mem_value       = CSRStorage(data_width)
        self.mem_r_edge_mask = CSRStorage(data_width)
        self.mem_f_edge_mask = CSRStorage(data_width)
        self.mem_fault_and   = CSRStorage(data_width)
        self.mem_fault_or    = CSRStorage(data_width)
        self.mem_fault_xor   = CSRStorage(data_width)
        self.mem_offset      = CSRStorage(bits_for(offset_depth))
        self.mem_duration    = CSRStorage(bits_for(duration_depth))
        self.mem_flags       = CSRStorage(1)
        self.mem_full        = CSRStatus()

        # Status.
        self.done          = CSRStatus() # No entry left and no fault in progress.
        self.busy          = CSRStatus() # Waiting for the offset, injecting or flushing.
        self.hit_count     = CSRStatus(32)
        self.fault_count   = CSRStatus(32)
        self.hit_timestamp = CSRStatus(32) # Cycles between arming and the last fault.

        # # #

        layout = entry_layout(data_width, offset_depth, duration_depth)
        width  = layout_len(layout)

        # Entry FIFO: written from the CSRs ("sys"), read by the sequencer (clock_domain).
        if clock_domain == "sys":
            self.submodules.mem = mem = SyncFIFO(width, depth, fwft=True)
        else:
            mem = AsyncFIFO(width, depth)
            self.submodules.mem = mem = ClockDomainsRenamer({"write": "sys", "read": clock_domain})(mem)

        entry_w = Record(layout)
        self.comb += [
            entry_w.mask.eq(self.mem_mask.storage),
            entry_w.value.eq(self.mem_value.storage),
            entry_w.r_edge_mask.eq(self.mem_r_edge_mask.storage),
            entry_w.f_edge_mask.eq(self.mem_f_edge_mask.storage),
            entry_w.fault_and.eq(self.mem_fault_and.storage),
            entry_w.fault_or.eq(self.mem_fault_or.storage),
            entry_w.fault_xor.eq(self.mem_fault_xor.storage),
            entry_w.offset.eq(self.mem_offset.storage),
            entry_w.duration.eq(self.mem_duration.storage),
            entry_w.flags.eq(self.mem_flags.storage),
            mem.din.eq(entry_w.raw_bits()),
            mem.we.eq(self.mem_write.re),
            self.mem_full.status.eq(~mem.writable),
        ]

        # Sequencer.
        core = _TriggerCore(data_width, offset_depth, duration_depth, with_lfsr)
        if clock_domain != "sys":
            core = ClockDomainsRenamer(clock_domain)(core)
        self.submodules.core = core

        self.comb += [
            core.data.eq(sink.data),
            core.entry.raw_bits().eq(mem.dout),
            core.readable.eq(mem.readable),
            mem.re.eq(core.pop),
            core.enable.eq(_cdc_to(self, self.enable.storage, "sys", clock_domain)),
            core.seed.eq(_cdc_to(self, self.seed.storage, "sys", clock_domain)),
        ]
        if clock_domain == "sys":
            self.comb += core.clear.eq(self.clear.re)
        else:
            self.submodules.clear_ps = clear_ps = PulseSynchronizer("sys", clock_domain)
            self.comb += [
                clear_ps.i.eq(self.clear.re),
                core.clear.eq(clear_ps.o),
            ]

        self.comb += [
            self.done.status.eq(_cdc_to(self, core.done, clock_domain, "sys")),
            self.busy.status.eq(_cdc_to(self, core.busy, clock_domain, "sys")),
            self.hit_count.status.eq(_cdc_to(self, core.hit_count, clock_domain, "sys")),
            self.fault_count.status.eq(_cdc_to(self, core.fault_count, clock_domain, "sys")),
            self.hit_timestamp.status.eq(_cdc_to(self, core.hit_timestamp, clock_domain, "sys")),
        ]

        # Kept as attributes for LiteScope probes.
        self.trigger_hit  = core.trigger_hit
        self.output_hit   = core.output_hit
        self.inject_start = core.inject_start
        self.offset       = core.entry.offset

        # Output.
        self.comb += [
            source.valid.eq(sink.valid),
            sink.ready.eq(source.ready),
            source.data.eq(sink.data),
            source.hit.eq(core.output_hit),
            source.fault_and.eq(core.fault_and),
            source.fault_or.eq(core.fault_or),
            source.fault_xor.eq(core.fault_xor),
        ]

class _Injector(Module, AutoCSR):
    def __init__(self, data_width):
        self.sink   = sink = stream.Endpoint(core_layout(data_width))
        self.output = Signal(data_width)

        # # #

        self.comb += If(sink.hit,
            self.output.eq(((sink.data & sink.fault_and) | sink.fault_or) ^ sink.fault_xor)
        ).Else(
            self.output.eq(sink.data)
        )

class LiteInjector(Module, AutoCSR):
    def __init__(self, groups, depth, clock_domain="sys", register=False, csr_csv="injector.csv",
        offset_depth=500, duration_depth=255, with_lfsr=True):
        self.groups         = groups = self.format_groups(groups)
        self.depth          = depth
        self.offset_depth   = offset_depth
        self.duration_depth = duration_depth
        self.with_lfsr      = with_lfsr

        self.data_width = data_width = max([sum([len(s) for s in g]) for g in groups.values()])

        self.csr_csv = csr_csv

        # Data captured on the first cycle of the last fault (before and after injection).
        self.capture_before = CSRStatus(data_width)
        self.capture_after  = CSRStatus(data_width)

        # # #

        # Mux
        self.submodules.mux = _Mux(data_width, len(groups), clock_domain)
        sd = getattr(self.sync, clock_domain)
        for i, signals in groups.items():
            s = Cat(signals)
            if register:
                s_d = Signal(len(s))
                sd += s_d.eq(s)
                s = s_d
            self.comb += [
                self.mux.sinks[i].valid.eq(1),
                self.mux.sinks[i].data.eq(s)
            ]

        # Frontend
        self.submodules.trigger = _Trigger(data_width,
            depth          = depth,
            offset_depth   = offset_depth,
            duration_depth = duration_depth,
            with_lfsr      = with_lfsr,
            clock_domain   = clock_domain)
        self.submodules.injector = _Injector(data_width)

        self.output = self.injector.output

        for group in groups.values():
            size_sum = 0
            for signal in group:
                signal_name = signal.backtrace[len(signal.backtrace)-1][0]
                signal_size = len(signal)

                setattr(self, f"o_{signal_name}", Signal(signal_size, name=f"o_{signal_name}"))
                self.comb += getattr(self, f"o_{signal_name}").eq(self.injector.output[size_sum:size_sum+signal_size])
                size_sum += signal_size

        # Pipeline
        self.submodules.pipeline = stream.Pipeline(
            self.mux.source,
            self.trigger,
            self.injector.sink)

        # Capture
        before = Signal(data_width)
        after  = Signal(data_width)
        sd += If(self.trigger.inject_start,
            before.eq(self.injector.sink.data),
            after.eq(self.injector.output)
        )
        self.comb += [
            self.capture_before.status.eq(_cdc_to(self, before, clock_domain, "sys")),
            self.capture_after.status.eq(_cdc_to(self, after, clock_domain, "sys")),
        ]

    def format_groups(self, groups):
        if not isinstance(groups, dict):
            groups = {0 : groups}
        new_groups = {}
        for n, signals in groups.items():
            if not isinstance(signals, list):
                signals = [signals]

            split_signals = []
            for s in signals:
                if isinstance(s, Record):
                    split_signals.extend(s.flatten())
                elif isinstance(s, FSM):
                    s.do_finalize()
                    s.finalized = True
                    split_signals.append(s.state)
                else:
                    split_signals.append(s)
            split_signals = list(dict.fromkeys(split_signals)) # Remove duplicates.
            new_groups[n] = split_signals
        return new_groups

    def config(self):
        """Hardware capabilities exported to the driver."""
        return {
            "version"        : LITEINJECTOR_VERSION,
            "data_width"     : self.data_width,
            "depth"          : self.depth,
            "offset_depth"   : self.offset_depth,
            "duration_depth" : self.duration_depth,
            "lfsr"           : int(self.with_lfsr),
        }

    def export_csv(self, vns, filename):
        def format_line(*args):
            return ",".join(args) + "\n"
        r = ""
        for k, v in self.config().items():
            r += format_line("config", "None", k, str(v))
        for i, signals in self.groups.items():
            for s in signals:
                r += format_line("signal", str(i), vns.get_name(s), str(len(s)))
        write_to_file(filename, r)

    def do_exit(self, vns):
        if self.csr_csv is not None:
            self.export_csv(vns, self.csr_csv)
