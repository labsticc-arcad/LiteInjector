<div align="center">

# LiteInjector

**Fault injection emulation for LiteX Systems on Chip, directly on FPGA.**

[![License](https://img.shields.io/badge/license-BSD--2--Clause-blue)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.7%2B-blue)](https://www.python.org)
[![LiteX](https://img.shields.io/badge/built%20with-LiteX-red)](https://github.com/enjoy-digital/litex)

</div>

LiteInjector adds bit-accurate, cycle-accurate fault injection to SoCs built with [LiteX](https://github.com/enjoy-digital/litex). The faults are emulated on the FPGA, on the real SoC running its real software, up to **210× faster** than RTL simulation, and every attack parameter can be changed at runtime from the host.

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

## Documentation

The documentation, the tutorials and the references are in the [`website`](website) folder:

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

Parts of this project, including the refactoring of the gateware and host software, the tests, the documentation website and its diagrams, were developed with the assistance of AI tools ([Claude Code](https://www.anthropic.com/claude-code) by Anthropic). This work was directed and reviewed by the authors, who remain responsible for its content.

## License

BSD-2-Clause, see [LICENSE](LICENSE).
