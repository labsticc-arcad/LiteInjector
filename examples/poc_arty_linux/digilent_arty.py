#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2015-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2020 Antmicro <www.antmicro.com>
# Copyright (c) 2022 Victor Suarez Rovere <suarezvictor@gmail.com>
# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

# Note: For now with --toolchain=yosys+nextpnr:
# - DDR3 should be disabled: ex --integrated-main-ram-size=8192
# - Clk Freq should be lowered: ex --sys-clk-freq=50e6

import sys
import json
sys.path.append('../utils')

from migen import *

from digilent_arty_platform import *
from litex.build.xilinx.vivado import vivado_build_args, vivado_build_argdict

from litex.soc.cores.clock import *
from litex.soc.integration.soc import SoCRegion
from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *
from litex.soc.cores.led import LedChaser
from litex.soc.cores.gpio import GPIOIn, GPIOTristate
from litex.soc.cores.xadc import XADC
from litex.soc.cores.dna  import DNA

from litedram.modules import MT41K128M16
from litedram.phy import s7ddrphy

from liteeth.phy.mii import LiteEthPHYMII

from liteinjector import LiteInjector
from litescope import LiteScopeAnalyzer

from litex.tools.litex_json2dts_linux import generate_dts

# CRG ----------------------------------------------------------------------------------------------

class _CRG(Module):
    def __init__(self, platform, sys_clk_freq, with_dram=True, with_rst=True):
        self.rst = Signal()
        self.clock_domains.cd_sys       = ClockDomain()
        self.clock_domains.cd_eth       = ClockDomain()
        if with_dram:
            self.clock_domains.cd_sys4x     = ClockDomain()
            self.clock_domains.cd_sys4x_dqs = ClockDomain()
            self.clock_domains.cd_idelay    = ClockDomain()


        # # #

        # Clk/Rst.
        clk100 = platform.request("clk100")
        rst    = ~platform.request("cpu_reset") if with_rst else 0

        # PLL.
        self.submodules.pll = pll = S7PLL(speedgrade=-1)
        self.comb += pll.reset.eq(rst | self.rst)
        pll.register_clkin(clk100, 100e6)
        pll.create_clkout(self.cd_sys, sys_clk_freq)
        pll.create_clkout(self.cd_eth, 25e6)
        self.comb += platform.request("eth_ref_clk").eq(self.cd_eth.clk)
        platform.add_false_path_constraints(self.cd_sys.clk, pll.clkin) # Ignore sys_clk to pll.clkin path created by SoC's rst.
        if with_dram:
            pll.create_clkout(self.cd_sys4x,     4*sys_clk_freq)
            pll.create_clkout(self.cd_sys4x_dqs, 4*sys_clk_freq, phase=90)
            pll.create_clkout(self.cd_idelay,    200e6)

        # IdelayCtrl.
        if with_dram:
            self.submodules.idelayctrl = S7IDELAYCTRL(self.cd_idelay)

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, variant="a7-100", toolchain="vivado", sys_clk_freq=int(100e6),
        with_ethernet   = False,
        with_etherbone  = False,
        eth_ip          = "192.168.1.50",
        eth_dynamic_ip  = False,
        with_led_chaser = True,
        with_jtagbone   = True,
        with_spi_flash  = False,
        with_buttons    = True,
        with_pmod_gpio  = False,
        **kwargs):
        platform = Platform(variant=variant, toolchain=toolchain)

        # CRG --------------------------------------------------------------------------------------
        with_dram = (kwargs.get("integrated_main_ram_size", 0) == 0)
        self.submodules.crg = _CRG(platform, sys_clk_freq, with_dram)

        # SoCCore ----------------------------------------------------------------------------------
        SoCCore.__init__(self, platform, sys_clk_freq, ident="LiteX SoC on Arty A7", **kwargs)

        # XADC -------------------------------------------------------------------------------------
        self.submodules.xadc = XADC()

        # DNA --------------------------------------------------------------------------------------
        self.submodules.dna = DNA()
        self.dna.add_timing_constraints(platform, sys_clk_freq, self.crg.cd_sys.clk)

        # DDR3 SDRAM -------------------------------------------------------------------------------
        if not self.integrated_main_ram_size:
            self.submodules.ddrphy = s7ddrphy.A7DDRPHY(platform.request("ddram"),
                memtype        = "DDR3",
                nphases        = 4,
                sys_clk_freq   = sys_clk_freq)
            self.add_sdram("sdram",
                phy           = self.ddrphy,
                module        = MT41K128M16(sys_clk_freq, "1:4"),
                l2_cache_size = kwargs.get("l2_size", 8192)
            )

        # Ethernet / Etherbone ---------------------------------------------------------------------
        if with_ethernet or with_etherbone:
            self.submodules.ethphy = LiteEthPHYMII(
                clock_pads = self.platform.request("eth_clocks"),
                pads       = self.platform.request("eth"))
            if with_ethernet:
                self.add_ethernet(phy=self.ethphy, dynamic_ip=eth_dynamic_ip)
            if with_etherbone:
                self.add_etherbone(phy=self.ethphy, ip_address=eth_ip)

        # Jtagbone ---------------------------------------------------------------------------------
        if with_jtagbone:
            self.add_jtagbone()

        # SPI Flash --------------------------------------------------------------------------------
        if with_spi_flash:
            from litespi.modules import S25FL128L
            from litespi.opcodes import SpiNorFlashOpCodes as Codes
            self.add_spi_flash(mode="4x", module=S25FL128L(Codes.READ_1_1_4), rate="1:2", with_master=True)

        # Leds -------------------------------------------------------------------------------------
        if with_led_chaser:
            self.submodules.leds = LedChaser(
                pads         = platform.request_all("user_led"),
                sys_clk_freq = sys_clk_freq,
            )

        # Buttons ----------------------------------------------------------------------------------
        if with_buttons:
            self.submodules.buttons = GPIOIn(
                pads     = platform.request_all("user_btn"),
                with_irq = self.irq.enabled
            )

        # GPIOs ------------------------------------------------------------------------------------
        if with_pmod_gpio:
            platform.add_extension(raw_pmod_io("pmoda"))
            self.submodules.gpio = GPIOTristate(
                pads     = platform.request("pmoda"),
                with_irq = self.irq.enabled
            )

        # LiteInjector -----------------------------------------------------------------------------

        # CPU Linux fault PoC

        injector_signals = [ self.cpu.pbus.dat_r, self.cpu.pbus.adr]

        self.submodules.injector = LiteInjector(injector_signals,
        depth        = 16,
        csr_csv      = "injector.csv")
        self.add_csr("injector")

        self.cpu.cpu_params["i_peripheral_DAT_MISO"] = self.injector.o_pbus_dat_r

        # LiteScopeAnalyzer ----------------------------------------------
        
        analyzer_signals = [
        self.cpu.pbus,
        self.injector.injector.sink.data,
        self.injector.injector.sink.fault_model,
        self.injector.injector.sink.fault_value,
        self.injector.injector.sink.fault_mask,
        self.injector.injector.output,
        self.injector.trigger.source.hit,
        self.injector.trigger.trigger_hit,
        self.injector.trigger.offset
        ]

        self.submodules.analyzer = LiteScopeAnalyzer(analyzer_signals,
        depth        = 256,
        samplerate   = self.sys_clk_freq,
        csr_csv      = "analyzer.csv")
        self.add_csr("analyzer")

        self.add_uartbone("liteinjector")

# DTS generation ---------------------------------------------------------------------------
def create_dts(board_name):
            json_src = "csr.json"
            dts = "{}.dts".format(board_name)

            with open(json_src) as json_file, open(dts, "w") as dts_file:
                dts_content = generate_dts(json.load(json_file), polling=False)
                dts_file.write(dts_content)

# DTS compilation --------------------------------------------------------------------------
def compile_dts(board_name, symbols=False):
    dts = "{}.dts".format(board_name)
    dtb = "{}.dtb".format(board_name)
    subprocess.check_call(
        "dtc {} -O dtb -o {} {}".format("-@" if symbols else "", dtb, dts), shell=True)

# DTB combination --------------------------------------------------------------------------
def combine_dtb(board_name, overlays=""):
    dtb_in = "{}.dtb".format(board_name)
    dtb_out = os.path.join("images", "rv32.dtb")
    if overlays == "":
        shutil.copyfile(dtb_in, dtb_out)
    else:
        subprocess.check_call(
            "fdtoverlay -i {} -o {} {}".format(dtb_in, dtb_out, overlays), shell=True)

# Build --------------------------------------------------------------------------------------------
def main():
    from litex.soc.integration.soc import LiteXSoCArgumentParser
    parser = LiteXSoCArgumentParser(description="LiteX SoC on Arty A7")
    target_group = parser.add_argument_group(title="Target options")
    target_group.add_argument("--toolchain",           default="vivado",                 help="FPGA toolchain (vivado, symbiflow or yosys+nextpnr).")
    target_group.add_argument("--build",               action="store_true",              help="Build design.")
    target_group.add_argument("--load",                action="store_true",              help="Load bitstream.")
    target_group.add_argument("--flash",               action="store_true",              help="Flash bitstream.")
    target_group.add_argument("--variant",             default="a7-100",                  help="Board variant (a7-35 or a7-100).")
    target_group.add_argument("--sys-clk-freq",        default=100e6,                    help="System clock frequency.")
    ethopts = target_group.add_mutually_exclusive_group()
    ethopts.add_argument("--with-ethernet",      action="store_true",              help="Enable Ethernet support.")
    ethopts.add_argument("--with-etherbone",     action="store_true",              help="Enable Etherbone support.")
    target_group.add_argument("--eth-ip",              default="192.168.1.50", type=str, help="Ethernet/Etherbone IP address.")
    target_group.add_argument("--eth-dynamic-ip",      action="store_true",              help="Enable dynamic Ethernet IP addresses setting.")
    sdopts = target_group.add_mutually_exclusive_group()
    sdopts.add_argument("--with-spi-sdcard",     action="store_true",              help="Enable SPI-mode SDCard support.")
    sdopts.add_argument("--with-sdcard",         action="store_true",              help="Enable SDCard support.")
    target_group.add_argument("--sdcard-adapter",      type=str,                         help="SDCard PMOD adapter (digilent or numato).")
    target_group.add_argument("--with-jtagbone",       action="store_true",              help="Enable JTAGbone support.")
    target_group.add_argument("--with-spi-flash",      action="store_true",              help="Enable SPI Flash (MMAPed).")
    target_group.add_argument("--with-pmod-gpio",      action="store_true",              help="Enable GPIOs through PMOD.") # FIXME: Temporary test.
    builder_args(parser)
    soc_core_args(parser)
    vivado_build_args(parser)
    args = parser.parse_args()

    assert not (args.with_etherbone and args.eth_dynamic_ip)

    soc = BaseSoC(
        variant        = args.variant,
        toolchain      = args.toolchain,
        sys_clk_freq   = int(float(args.sys_clk_freq)),
        with_ethernet  = args.with_ethernet,
        with_etherbone = args.with_etherbone,
        eth_ip         = args.eth_ip,
        eth_dynamic_ip = args.eth_dynamic_ip,
        with_jtagbone  = args.with_jtagbone,
        with_spi_flash = args.with_spi_flash,
        with_pmod_gpio = args.with_pmod_gpio,
        **soc_core_argdict(args)
    )
    if args.sdcard_adapter == "numato":
        soc.platform.add_extension(numato_sdcard_pmod_io("pmodd"))
    else:
        soc.platform.add_extension(sdcard_pmod_io("pmodd"))
    if args.with_spi_sdcard:
        soc.add_spi_sdcard()
    if args.with_sdcard:
        soc.add_sdcard()

    builder = Builder(soc, **builder_argdict(args))
    builder_kwargs = vivado_build_argdict(args) if args.toolchain == "vivado" else {}
    if args.build:
        builder.build(**builder_kwargs)
        create_dts("digilent_arty")
        compile_dts("digilent_arty", "")
        combine_dtb("digilent_arty", "")

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

    if args.flash:
        prog = soc.platform.create_programmer()
        prog.flash(0, builder.get_bitstream_filename(mode="flash"))

if __name__ == "__main__":
    main()
