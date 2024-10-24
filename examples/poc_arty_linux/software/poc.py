#!/usr/bin/env python3

#
# This file is part of LiteX.
#
# Copyright (c) 2020-2022 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

import os
import argparse

from litex.build.tools import replace_in_file

def main():
    parser = argparse.ArgumentParser(description="Linux PoC APP.")
    parser.add_argument("--build-path",                      help="Target's build path (ex build/board_name).", required=True)
    parser.add_argument("--with-cxx",   action="store_true", help="Enable CXX support.")
    parser.add_argument("--mem",        default="main_ram",  help="Memory Region where code will be loaded/executed.")
    args = parser.parse_args()

    # Create poc directory
    os.makedirs("poc", exist_ok=True)

    # Copy contents to poc directory
    os.system(f"cp {os.path.abspath(os.path.dirname(__file__))}/* poc")

    # Update memory region.
    replace_in_file("poc/linker.ld", "main_ram", args.mem)

    # Compile poc
    build_path = args.build_path if os.path.isabs(args.build_path) else os.path.join("..", args.build_path)
    os.system(f"export BUILD_DIR={build_path} && {'export WITH_CXX=1 &&' if args.with_cxx else ''} cd poc && make")

    # Copy poc.bin
    os.system("cp poc/poc.bin ./")

    # Prepare flash boot image.
    os.system("python3 -m litex.soc.software.crcfbigen poc.bin -o poc.fbi --fbi --little") # FIXME: Endianness.

if __name__ == "__main__":
    main()

