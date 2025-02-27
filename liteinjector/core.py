# Copyright (c) 2016-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2018 bunnie <bunnie@kosagi.com>
# Copyright (c) 2016 Tim 'mithro' Ansell <mithro@mithis.com>
# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

from migen import *
from migen.genlib.misc import WaitTimer
from migen.genlib.cdc import MultiReg, PulseSynchronizer
from migen.genlib.fifo import *

from litex.build.tools import write_to_file

from litex.soc.interconnect.csr import *
from litex.soc.cores.gpio import GPIOInOut
from litex.soc.interconnect import stream

# LiteInjector -------------------------------------------------------------------------------------

def core_layout(data_width):
    return [("data", data_width), ("hit", 1), ("fault_value", data_width), ("fault_mask", data_width), ("fault_model", bits_for(6))]

class _Mux(Module, AutoCSR):
    def __init__(self, data_width, n):
        self.sinks  = sinks  = [stream.Endpoint(core_layout(data_width)) for i in range(n)]
        self.source = source = stream.Endpoint(core_layout(data_width))

        self.value = CSRStorage(bits_for(n))

        # # #

        value = Signal(bits_for(n))
        self.specials += MultiReg(self.value.storage, value, "scope")

        cases = {}
        for i in range(n):
            cases[i] = sinks[i].connect(source)
        self.comb += Case(value, cases)

class _RisingEdgeDetector(Module):
    def __init__(self, signal, data_width):
        signal_d = Signal(data_width)
        
        self.sync += signal_d.eq(signal)
        self.rising_edge = Signal(data_width)
        for i in range(data_width):
            self.comb += self.rising_edge[i].eq((signal[i] & ~signal_d[i]) != 0)

class _FallingEdgeDetector(Module):
    def __init__(self, signal, data_width):
        signal_d = Signal(data_width)
        
        self.sync += signal_d.eq(signal)
        self.falling_edge = Signal(data_width)
        for i in range(data_width):
            self.comb += self.falling_edge[i].eq(~signal[i] & signal_d[i])

class _HitShifter(Module):
    def __init__(self, offset_signal):
        self.wait = Signal()
        self.running = Signal()
        self.done = Signal()

        # # #
        count = Signal(len(offset_signal), reset=0)
        self.comb += self.done.eq(count == offset_signal)
        self.sync += [
            If(self.wait,
                self.running.eq(1),
                count.eq(1)
            ).Else(
                If(count == offset_signal,
                    self.running.eq(0)
                )
            ),
            If(~self.done & self.running,
                count.eq(count + 1)
            )
        ]

class _Trigger(Module, AutoCSR):
    def __init__(self, data_width, depth=16, offset_depth=500):
        self.sink   = sink   = stream.Endpoint(core_layout(data_width))
        self.source = source = stream.Endpoint(core_layout(data_width))

        self.enable = CSRStorage()
        self.done   = CSRStatus()

        self.mem_write       = CSR()
        self.mem_mask        = CSRStorage(data_width) # Mask, value selector
        self.mem_value       = CSRStorage(data_width) # Value to check 
        self.mem_r_edge_mask = CSRStorage(data_width) # Mask, to detect rising edge
        self.mem_f_edge_mask = CSRStorage(data_width) # Mask, to detect falling edge
        self.mem_fault_mask  = CSRStorage(data_width)
        self.mem_fault_value = CSRStorage(data_width)
        self.mem_fault_model = CSRStorage(bits_for(6))
        self.mem_offset      = CSRStorage(bits_for(offset_depth)) # Trigger offset deplay
        self.mem_full        = CSRStatus()

        self.mask        = Signal(data_width)
        self.value       = Signal(data_width)
        self.r_edge_mask = Signal(data_width)
        self.f_edge_mask = Signal(data_width)
        self.fault_mask  = Signal(data_width)
        self.fault_value = Signal(data_width)
        self.fault_model = Signal(bits_for(6))
        self.offset      = Signal(bits_for(offset_depth))

        self.trigger_hit = Signal()
        self.output_hit  = Signal()

        # # #

        # Fifo containing the triggers informations
        self.mem = AsyncFIFO(6*data_width+bits_for(6)+bits_for(offset_depth), depth)
        self.mem = ClockDomainsRenamer({"write": "sys", "read": "scope"})(self.mem)
        self.submodules += self.mem

        # Connect the Fifo to the registers
        self.comb += [
            self.mem.din.eq(Cat(self.mem_mask.storage, self.mem_value.storage, self.mem_r_edge_mask.storage, self.mem_f_edge_mask.storage, self.mem_fault_mask.storage, self.mem_fault_value.storage, self.mem_fault_model.storage, self.mem_offset.storage)),
            self.mem_full.status.eq(~self.mem.writable),
            self.done.status.eq(~self.mem.readable),
            self.mem.we.eq(self.mem_write.re)
        ]

        # Slice the Fifo output
        self.comb += [
            self.mask.eq(self.mem.dout[0:data_width]),
            self.value.eq(self.mem.dout[data_width:data_width*2]),
            self.r_edge_mask.eq(self.mem.dout[data_width*2:data_width*3]),
            self.f_edge_mask.eq(self.mem.dout[data_width*3:data_width*4]),
            self.fault_mask.eq(self.mem.dout[data_width*4:data_width*5]),
            self.fault_value.eq(self.mem.dout[data_width*5:data_width*6]),
            self.fault_model.eq(self.mem.dout[data_width*6:data_width*6+bits_for(6)]),
            self.offset.eq(self.mem.dout[data_width*6+bits_for(6):data_width*6+bits_for(6)+bits_for(offset_depth)])
        ]

        # Rising edge detector for the input signals
        self.rising_edge_detector = _RisingEdgeDetector(sink.data, data_width)
        self.submodules += self.rising_edge_detector

        # Falling edge detector for the input signals
        self.falling_edge_detector = _FallingEdgeDetector(sink.data, data_width)
        self.submodules += self.falling_edge_detector

        # Trigger hit logic
        self.comb += [
            If((self.enable.storage == 1) & (self.done.status == 0),
                If((self.mask != 0),
                    If((self.r_edge_mask != 0) & (self.f_edge_mask != 0),
                        self.trigger_hit.eq(((sink.data & self.mask) == (self.value & self.mask)) & ((self.rising_edge_detector.rising_edge & self.r_edge_mask) == self.r_edge_mask) & ((self.falling_edge_detector.falling_edge & self.f_edge_mask) == self.f_edge_mask))
                    ).Elif(self.r_edge_mask != 0,
                        self.trigger_hit.eq(((sink.data & self.mask) == (self.value & self.mask)) & ((self.rising_edge_detector.rising_edge & self.r_edge_mask) == self.r_edge_mask))
                    ).Elif(self.f_edge_mask != 0,
                        self.trigger_hit.eq(((sink.data & self.mask) == (self.value & self.mask)) & ((self.falling_edge_detector.falling_edge & self.f_edge_mask) == self.f_edge_mask))
                    ).Else(self.trigger_hit.eq((sink.data & self.mask) == (self.value & self.mask)))
                ).Else(
                    If((self.r_edge_mask != 0) & (self.f_edge_mask != 0),
                        self.trigger_hit.eq(((self.rising_edge_detector.rising_edge & self.r_edge_mask) == self.r_edge_mask) & ((self.falling_edge_detector.falling_edge & self.f_edge_mask) == self.f_edge_mask))
                    ).Elif(self.r_edge_mask != 0,
                        self.trigger_hit.eq((self.rising_edge_detector.rising_edge & self.r_edge_mask) == self.r_edge_mask)
                    ).Elif(self.f_edge_mask != 0,
                        self.trigger_hit.eq((self.falling_edge_detector.falling_edge & self.f_edge_mask) == self.f_edge_mask)
                    ).Else(self.trigger_hit.eq(0))
                )
            ).Else(self.trigger_hit.eq(0))
        ]

        # Adding delay on the hit signal with the offset
        self.shifter = _HitShifter(self.offset)
        self.submodules += self.shifter
        self.comb += [ 
            self.shifter.wait.eq(self.trigger_hit),
            If(self.offset == 0,
                self.output_hit.eq(self.trigger_hit)
            ).Else(self.output_hit.eq(self.shifter.done)),
            self.mem.re.eq(self.output_hit)
        ]

        # Output
        self.comb += [
            sink.connect(source),
            source.hit.eq(self.output_hit),
            source.fault_value.eq(self.fault_value),
            source.fault_mask.eq(self.fault_mask),
            source.fault_model.eq(self.fault_model)
        ]

class _Injector(Module, AutoCSR):
    def __init__(self, data_width):
        
        self.sink = sink = stream.Endpoint(core_layout(data_width))
        self.output = Signal(data_width)

        self.comb += [
            If((self.sink.fault_model == 1) & self.sink.hit,
                self.output.eq(self.sink.data | self.sink.fault_value)
            ).Elif((self.sink.fault_model == 2) & self.sink.hit,
                self.output.eq(self.sink.data & self.sink.fault_value)
            ).Elif(((self.sink.fault_model == 3) | (self.sink.fault_model == 4)) & self.sink.hit,
                self.output.eq(self.sink.data ^ self.sink.fault_value)
            ).Elif((self.sink.fault_model == 5) & self.sink.hit,
                self.output.eq((self.sink.data & self.sink.fault_mask) | self.sink.fault_value)
            ).Else(
                self.output.eq(self.sink.data)
            )
        ]

class LiteInjector(Module, AutoCSR):
    def __init__(self, groups, depth, clock_domain="sys", register=False, csr_csv="injector.csv"):
        self.groups     = groups = self.format_groups(groups)
        self.depth      = depth

        self.data_width = data_width = max([sum([len(s) for s in g]) for g in groups.values()])

        self.csr_csv = csr_csv

        # # #

        # Create scope clock domain
        self.clock_domains.cd_scope = ClockDomain()
        self.comb += self.cd_scope.clk.eq(ClockSignal(clock_domain))

        # Mux
        self.submodules.mux = _Mux(data_width, len(groups))
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
        self.submodules.trigger = _Trigger(data_width, depth=depth)
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

    def export_csv(self, vns, filename):
        def format_line(*args):
            return ",".join(args) + "\n"
        r = format_line("config", "None", "data_width", str(self.data_width))
        r += format_line("config", "None", "depth", str(self.depth))
        for i, signals in self.groups.items():
            for s in signals:
                r += format_line("signal", str(i), vns.get_name(s), str(len(s)))
        write_to_file(filename, r)

    def do_exit(self, vns):
        if self.csr_csv is not None:
            self.export_csv(vns, self.csr_csv)
