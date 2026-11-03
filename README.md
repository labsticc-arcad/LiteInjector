<div align="center">

# LiteInjector

**Fault injection emulation for LiteX Systems on Chip, directly on FPGA.**

[![License](https://img.shields.io/badge/license-BSD--2--Clause-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.7%2B-blue)](https://www.python.org)
[![LiteX](https://img.shields.io/badge/built%20with-LiteX-red)](https://github.com/enjoy-digital/litex)
[![Documentation](https://img.shields.io/badge/docs-online-brightgreen)](https://labsticc-arcad.github.io/LiteInjector/)

</div>

LiteInjector adds bit-accurate, cycle-accurate fault injection to SoCs built with [LiteX](https://github.com/enjoy-digital/litex). The faults are emulated on the FPGA, on the real SoC running its real software, up to **210× faster** than RTL simulation, and every attack parameter can be changed at runtime from the host.

📖 **Full documentation, tutorials and references: https://labsticc-arcad.github.io/LiteInjector/**

## Features

- Probe and fault any Migen signal, or an instrumented signal of a Verilog IP
- Triggers on values with "don't care" bits, rising and falling edges, with a delay and a duration in cycles
- Five fault models (bit set, reset, flip, random flip, value), combinable in a single trigger
- Chained triggers for multi-fault attacks, without rebuilding the bitstream
- Command line, Python API and campaign runner with target observation and CSV reports

## Quick start

```console
$ ./litex_setup.py --init --install --config=standard --tag=2022.08
$ git clone https://github.com/labsticc-arcad/LiteInjector.git
$ pip install -r LiteInjector/requirements.txt -e LiteInjector
```

Add the core to a LiteX SoC:

```python
from liteinjector import LiteInjector

self.submodules.injector = LiteInjector([ibus.adr, ibus.dat_r], depth=16, csr_csv="injector.csv")
self.add_uartbone("liteinjector")
```

Then drive it from the host, through `litex_server`:

```console
$ liteinjector_cli run --when ibus_adr=0x0000037A --offset 1 --fault bit-value:ibus_dat_r=0x00050C63 --wait 5
$ liteinjector_cli campaign examples/poc_basys3_vexriscv/campaign.toml
```

For a complete walkthrough, see the [online documentation](https://labsticc-arcad.github.io/LiteInjector/).

## Documentation

The documentation is available online at **[labsticc-arcad.github.io/LiteInjector](https://labsticc-arcad.github.io/LiteInjector/)**. It contains the tutorials, the guides and the references (command line, Python API, campaign files).

The sources of the documentation are in the [`website`](website) folder. To build and browse it locally:

```console
$ cd website && npm install && npm run dev
```

Tests run in simulation, no FPGA needed: `python3 -m pytest test`.

## Citation

```bibtex
@INPROCEEDINGS{Henault2025LiteInjector,
  author={Henault, Adam and Tanguy, Philippe and Lapôtre, Vianney},
  booktitle={2025 28th Euromicro Conference on Digital System Design (DSD)},
  title={LiteInjector: A LiteX Extension for Fault Injection},
  year={2025}
}
```

## Acknowledgements

LiteInjector is developed by the ARCAD team of the [Lab-STICC](https://labsticc.fr) laboratory (Lorient, France). It builds on [LiteX](https://github.com/enjoy-digital/litex) and [LiteScope](https://github.com/enjoy-digital/litescope) by Enjoy-Digital.

## Use of AI

AI assistance was used in this project, for code, tests and documentation. The authors reviewed the result and remain responsible for it.

## License

BSD-2-Clause, see [LICENSE](LICENSE).
