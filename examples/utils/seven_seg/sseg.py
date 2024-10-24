import os
from migen import *
from migen.genlib.misc import WaitTimer

from litex.soc.interconnect.csr import *
from litex.soc.interconnect import wishbone

class SSEG(Module, AutoCSR):
    def __init__(self, platform, value):

        platform.add_source_dir(path=os.path.dirname(__file__))

        self.segs = Cat(platform.request("seg0"), platform.request("seg1"), platform.request("seg2"), platform.request("seg3"), platform.request("seg4"), platform.request("seg5"), platform.request("seg6"))
        self.ans = Cat(platform.request("an0"), platform.request("an1"), platform.request("an2"), platform.request("an3"))

        self.seg0 = Signal(7)
        self.seg1 = Signal(7)
        self.seg2 = Signal(7)
        self.seg3 = Signal(7)

        self.ss7_0 = dict(
            i_hex = value[0:4],
            o_seg = self.seg0
        )

        self.ss7_1 = dict(
            i_hex = value[4:8],
            o_seg = self.seg1
        )

        self.ss7_2 = dict(
            i_hex = value[8:12],
            o_seg = self.seg2
        )

        self.ss7_3 = dict(
            i_hex = value[12:16],
            o_seg = self.seg3
        )

        self.specials += Instance("sseg_display", **self.ss7_0)
        self.specials += Instance("sseg_display", **self.ss7_1)
        self.specials += Instance("sseg_display", **self.ss7_2)
        self.specials += Instance("sseg_display", **self.ss7_3)

        self.ss7_mux = dict(
            i_clk = ClockSignal("sys"),
            i_rst = ResetSignal("sys"),
            i_dig0 = self.seg0,
            i_dig1 = self.seg1,
            i_dig2 = self.seg2,
            i_dig3 = self.seg3,
            o_an = self.ans,
            o_sseg = self.segs
        )

        self.specials += Instance("sseg_mux", **self.ss7_mux)