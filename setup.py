#!/usr/bin/env python3

from pathlib import Path

from setuptools import setup
from setuptools import find_packages


setup(
    name="liteinjector",
    version="2.0",
    description="Small footprint and configurable embedded FPGA fault injection emulator",
    long_description=Path(__file__).with_name("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    author="Adam Henault",
    author_email="adam.henault@univ-ubs.fr",
    url="https://github.com/labsticc-arcad/LiteInjector",
    download_url="https://github.com/labsticc-arcad/LiteInjector",
    license="BSD-2-Clause",
    python_requires=">=3.7",
    # Migen and LiteX are expected to be installed beforehand with litex_setup.py
    # (see the Installation page of the website), pip only checks that they are present.
    install_requires=[
        "migen",
        "litex",
        "pyserial",                                  # Campaign observation over UART.
        "tomli>=1.1; python_version < '3.11'",       # TOML campaign files.
    ],
    packages=find_packages(exclude=("test*", "sim*", "doc*", "examples*")),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "liteinjector_cli=liteinjector.software.liteinjector_cli:main"
        ],
    },
)
