#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2020-2021 Xuanyu Hu <xuanyu.hu@whu.edu.cn>
# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

import sys
sys.path.append('../utils')
sys.path.append('../utils/seven_seg')

from migen import *

from digilent_basys3_platform import *
from sseg import *

from litex.soc.cores.clock import *
from litex.soc.integration.soc import SoCRegion
from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *
from litex.soc.cores.video import VideoVGAPHY
from litex.soc.cores.led import LedChaser
from litex.soc.interconnect import wishbone

from liteinjector.core import LiteInjector
from litescope.core import LiteScopeAnalyzer

# CRG ----------------------------------------------------------------------------------------------

class _CRG(Module):
    def __init__(self, platform, sys_clk_freq):
        self.rst = Signal()
        self.clock_domains.cd_sys         = ClockDomain()
        self.clock_domains.cd_vga         = ClockDomain()

        self.submodules.pll = pll = S7MMCM(speedgrade=-1)
        self.comb += pll.reset.eq(platform.request("user_btnc") | self.rst)

        pll.register_clkin(platform.request("clk100"), 100e6)
        pll.create_clkout(self.cd_sys, sys_clk_freq)
        pll.create_clkout(self.cd_vga, 40e6)
        platform.add_false_path_constraints(self.cd_sys.clk, pll.clkin) # Ignore sys_clk to pll.clkin path created by SoC's rst.

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, sys_clk_freq=int(75e6), with_led_chaser=True, with_video_terminal=False, **kwargs):
        platform = Platform()

        # CRG --------------------------------------------------------------------------------------
        self.submodules.crg = _CRG(platform, sys_clk_freq)

        # SoCCore ----------------------------------_-----------------------------------------------
        SoCCore.__init__(self, platform, sys_clk_freq, ident="LiteX SoC on Basys3", **kwargs)

        # Video ------------------------------------------------------------------------------------
        if with_video_terminal:
            self.submodules.videophy = VideoVGAPHY(platform.request("vga"), clock_domain="vga")
            if with_video_terminal:
                self.add_video_terminal(phy=self.videophy, timings="800x600@60Hz", clock_domain="vga")

        # Leds -------------------------------------------------------------------------------------
        if with_led_chaser:
            self.submodules.leds = LedChaser(
                pads         = platform.request_all("user_led"),
                sys_clk_freq = sys_clk_freq)
            
        # Counter PoC ------------------------------------------------------------------------------
        count_result = Signal(16)
        count_clk_divider = Signal(26)
        injector_output = Signal(16)

        self.sync += count_clk_divider.eq(count_clk_divider + 1)
        self.sync += [
            If(count_clk_divider == 0b11111111111111111111111111,
                count_result.eq(injector_output + 1)
            )
        ]

        self.submodules.sseg = SSEG(platform, count_result)

        # LiteInjector -----------------------------------------------------------------------------
        injector_signals = [count_result, count_clk_divider]

        self.submodules.injector = LiteInjector(injector_signals,
            depth        = 16,
            csr_csv = "injector.csv")
        self.add_csr("injector")

        self.comb += [
            injector_output.eq(self.injector.o_count_result)
        ]

        # LiteScopeAnalyzer ------------------------------------------------------------------------
        analyzer_signals = [
            count_result,
            count_clk_divider,
            injector_output,
            self.injector.trigger.output_hit,
        ]

        self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals,
            depth        = 512,
            csr_csv      = "analyzer.csv")
        self.add_csr("analyzer")

        self.add_uartbone("liteinjector")

# Build --------------------------------------------------------------------------------------------
def main():
    from litex.soc.integration.soc import LiteXSoCArgumentParser
    parser = LiteXSoCArgumentParser(description="LiteX SoC on Basys3")
    target_group = parser.add_argument_group(title="Target options")
    target_group.add_argument("--build",               action="store_true", help="Build design.")
    target_group.add_argument("--load",                action="store_true", help="Load bitstream.")
    target_group.add_argument("--sys-clk-freq",        default=75e6,        help="System clock frequency.")
    sdopts = target_group.add_mutually_exclusive_group()
    sdopts.add_argument("--with-spi-sdcard",     action="store_true", help="Enable SPI-mode SDCard support.")
    sdopts.add_argument("--with-sdcard",         action="store_true", help="Enable SDCard support.")
    target_group.add_argument("--sdcard-adapter",      type=str,            help="SDCard PMOD adapter (digilent or numato).")
    viopts = target_group.add_mutually_exclusive_group()
    viopts.add_argument("--with-video-terminal", action="store_true", help="Enable Video Terminal (VGA).")
    builder_args(parser)
    soc_core_args(parser)
    args = parser.parse_args()

    soc = BaseSoC(
        sys_clk_freq           = int(float(args.sys_clk_freq)),
        with_video_terminal    = args.with_video_terminal,
        **soc_core_argdict(args)
    )
    soc.platform.add_extension(sdcard_pmod_io("pmoda"))
    if args.with_spi_sdcard:
        soc.add_spi_sdcard()
    if args.with_sdcard:
        soc.add_sdcard()
    builder = Builder(soc, **builder_argdict(args))
    if args.build:
        builder.build()

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

if __name__ == "__main__":
    main()
