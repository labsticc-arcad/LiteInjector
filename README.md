<div align="center">

```
    __    _ __       ____        _           __            
   / /   (_) /____  /  _/___    (_)__  _____/ /_____  _____
  / /   / / __/ _ \ / // __ \  / / _ \/ ___/ __/ __ \/ ___/
 / /___/ / /_/  __// // / / / / /  __/ /__/ /_/ /_/ / /    
/_____/_/\__/\___/___/_/ /_/_/ /\___/\___/\__/\____/_/     
                          /___/                            


A LiteX based tool for emulating logical faults on Systems on Chips

```

[![Ubtuntu](https://img.shields.io/badge/platform-Ubuntu%2020.04-0078d7.svg?style=for-the-badge&logo=appveyor)](https://www.ubuntu-fr.org) 
[![Python](https://img.shields.io/badge/language-Python3-%23f34b7d.svg?style=for-the-badge&logo=appveyor)](https://www.python.org) 
[![LiteX](https://img.shields.io/badge/Library-LiteX-red.svg?style=for-the-badge&logo=appveyor)](https://github.com/enjoy-digital/litex) 
[![Migen](https://img.shields.io/badge/Library-Migen-green.svg?style=for-the-badge&logo=appveyor)](https://m-labs.hk/gateware/migen/)

</div>

# :book: Project Overview

LiteInjector is an open source logic fault injection tool designed for security evaluation campaigns on systems on chip (SoC) generated with the LiteX framework. Developed in Python using Migen, LiteInjector enables precise, bit-by-bit and cycle-by-cycle fault injection directly on FPGA.

### ✨ Features

- Seamless integration with LiteX / Migen-based SoCs
- Logic fault injection with 5 supported fault models (bit set, reset, flip, random flip, write)
- Event-based trigger system with dynamic masking (value match, rising/falling edge, configurable delay)
- CLI and Python API for automating injection campaigns
- Up to **210× faster** than traditional RTL simulation

### 🔧 Usage

LiteInjector integrates as a hardware module into the SoC and is configured via the software controller (`liteinjector_cli`) through UART, JTAG, USB, or other supported interfaces.

### 🧪 Use Cases

- Bypassing PIN code verification (VerifyPin benchmark)
- Circumventing Physical Memory Protection (PMP) in VexRiscV cores
- Multi-fault injection campaigns against protected code sequences

# :rocket: Getting Started

### Generate the documentation

```console
$ git clone https://github.com/labsticc-arcad/LiteInjector.git
$ cd LiteInjector
$ pip3 install -r requirements.txt
$ cd docs
$ make html
$ cd _build/html
```
