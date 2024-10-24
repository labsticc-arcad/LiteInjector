#!/usr/bin/env python3

from setuptools import setup
from setuptools import find_packages


setup(
    name="liteinjector",
    version="2.0",
    description="Small footprint and configurable embedded FPGA fault injection emulator",
    author="Adam Henault",
    author_email="adam.henault@univ-ubs.fr",
    url="http://adamhlt.com",
    download_url="https://github.com/labsticc-arcad/LiteInjector",
    python_requires="~=3.6",
    packages=find_packages(exclude=("test*", "sim*", "doc*", "examples*")),
    include_package_data=True,
    entry_points={
        "console_scripts": [
            "liteinjector_cli=liteinjector.software.liteinjector_cli:main"
        ],
    },
)
