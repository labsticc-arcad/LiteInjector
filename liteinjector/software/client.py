# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

"""High level Python API: connect to a SoC through litex_server and inject faults.

Example::

    from liteinjector.software import LiteInjectorClient, Trigger, Fault

    with LiteInjectorClient(csr_csv="csr.csv", config_csv="injector.csv") as inj:
        inj.inject([Trigger(when={"ibus_adr": "0x37A"}, offset=1,
                            faults=[Fault("bit-value", "ibus_dat_r", value="0x00050C63")])])
        inj.wait(timeout=5)
        print(inj.status())
"""

import os
import time

from liteinjector.software.layout import Layout
from liteinjector.software.driver.injector import LiteInjectorDriver

class LiteInjectorClient:
    def __init__(self, host="localhost", port=1234, csr_csv="csr.csv", config_csv="injector.csv",
        name=None, debug=False, bus=None):
        for path, hint in [(csr_csv, "the --csr-csv file of the SoC build"),
                           (config_csv, "the csr_csv file given to LiteInjector in the SoC")]:
            if bus is None and not os.path.exists(path):
                raise FileNotFoundError(f"{path} not found, expected {hint}.")
        self.layout = Layout.from_csv(config_csv)
        self.name   = name or os.path.splitext(os.path.basename(config_csv))[0]
        self.debug  = debug
        self._own_bus = bus is None
        if bus is None:
            from litex import RemoteClient
            bus = RemoteClient(host=host, port=port, csr_csv=csr_csv)
        self.bus    = bus
        self.driver = None

    def open(self):
        if self._own_bus:
            self.bus.open()
        self.driver = LiteInjectorDriver(self.bus.regs, self.name, layout=self.layout, debug=self.debug)
        return self

    def close(self):
        if self.driver is not None:
            self.driver = None
        if self._own_bus:
            self.bus.close()

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    # Injection ------------------------------------------------------------------------------------

    def configure(self, triggers, group=0, seed=None):
        """Drop pending triggers and load a sequence of triggers (one fault per trigger)."""
        self.driver.stop()
        self.driver.configure_group(group)
        if seed is not None:
            self.driver.set_seed(seed)
        self.driver.clear()
        return [self.driver.add(t) for t in triggers]

    def inject(self, triggers, group=0, seed=None):
        """Load the triggers and arm the injector."""
        entries = self.configure(triggers, group, seed)
        self.driver.arm()
        return entries

    def arm(self):
        self.driver.arm()

    def disarm(self):
        self.driver.stop()

    def clear(self):
        self.driver.stop()
        self.driver.clear()

    def wait(self, timeout=None):
        return self.driver.wait_done(timeout)

    def status(self):
        return self.driver.status()

    # Target control -------------------------------------------------------------------------------

    def reset_target(self, delay=0.5):
        """Reset the SoC through the LiteX ctrl_reset register (also resets the injector)."""
        regs = self.bus.regs
        if not hasattr(regs, "ctrl_reset"):
            raise RuntimeError("The SoC has no ctrl_reset register.")
        regs.ctrl_reset.write(1)
        time.sleep(delay)
