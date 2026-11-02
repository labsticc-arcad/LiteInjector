# Copyright (c) 2015-2018 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2019 kees.jongenburger <kees.jongenburger@gmail.com>
# Copyright (c) 2018 Sean Cross <sean@xobs.io>
# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

"""CSR transport of the LiteInjector core: the only module that touches the hardware registers."""

import time

from liteinjector.software import model
from liteinjector.software.layout import Layout, parse_value, LITEINJECTOR_VERSION
from liteinjector.software.encoder import encode, Entry, FLAG_RANDOM

# Legacy fault model numbers, kept for scripts using add_trigger().
FAULT_NONE            = 0
FAULT_BIT_SET         = 1
FAULT_BIT_RESET       = 2
FAULT_BIT_FLIP        = 3
FAULT_BIT_FLIP_RANDOM = 4
FAULT_BIT_VALUE       = 5

STATUS_REGISTERS = ["done", "busy", "hit_count", "fault_count", "hit_timestamp"]

class LiteInjectorDriver:
    def __init__(self, regs, name="injector", config_csv=None, debug=False, layout=None):
        self.regs   = regs
        self.name   = name
        self.debug  = debug
        self.group  = 0
        self.layout = layout or Layout.from_csv(config_csv or name + ".csv")
        self.layout.check_version()

        # Registers of this core, without the "<name>_" prefix.
        self.csrs = {}
        prefix = name + "_"
        for key, reg in regs.d.items():
            if key.startswith(prefix):
                self.csrs[key[len(prefix):]] = reg
        if "trigger_mem_write" not in self.csrs:
            raise RuntimeError(f"No '{name}' LiteInjector registers found in the CSR map.")

        self.stop()

    def _reg(self, name):
        return self.csrs[name]

    def _write(self, name, value):
        self._reg(name).write(value)

    def _read(self, name):
        return self._reg(name).read()

    # Configuration --------------------------------------------------------------------------------

    def configure_group(self, group):
        if group not in self.layout.groups:
            raise ValueError(f"Group {group} does not exist (groups: {sorted(self.layout.groups)}).")
        self.group = group
        self._write("mux_value", group)

    def clear(self):
        """Flush the pending triggers, reset the counters and reload the LFSR seed."""
        self._write("trigger_clear", 1)

    def set_seed(self, seed):
        """Seed of the random bit flip LFSR, applied by the next clear()."""
        self._write("trigger_seed", seed & 0xffffffff)

    def write_entry(self, entry):
        if self._read("trigger_mem_full"):
            raise RuntimeError("Trigger memory full, too many triggers for the core depth.")
        for field in Entry._fields:
            self._write(f"trigger_mem_{field}", getattr(entry, field))
        self._write("trigger_mem_write", 1)

    def add(self, trigger):
        """Encode and push a model.Trigger."""
        entry = encode(trigger, self.layout, self.group)
        if self.debug:
            print(f"[trigger] {trigger.describe()}")
        self.write_entry(entry)
        return entry

    # Run ------------------------------------------------------------------------------------------

    def arm(self):
        self._write("trigger_enable", 1)

    run = arm # Compatibility with the v1 driver.

    def stop(self):
        self._write("trigger_enable", 0)

    def done(self):
        return bool(self._read("trigger_done"))

    def wait_done(self, timeout=None, poll=0.01):
        start = time.time()
        while not self.done():
            if timeout is not None and time.time() - start > timeout:
                return False
            time.sleep(poll)
        return True

    def status(self):
        status = {name: self._read("trigger_" + name) for name in STATUS_REGISTERS}
        status["done"] = bool(status["done"])
        status["busy"] = bool(status["busy"])
        status["armed"] = bool(self._read("trigger_enable"))
        status["capture_before"] = self._read("capture_before")
        status["capture_after"]  = self._read("capture_after")
        return status

    # Legacy API -----------------------------------------------------------------------------------

    def add_trigger(self, value=0, mask=0, cond=None, rising_edge=None, falling_edge=None, offset=0,
        fault=None, fault_model=FAULT_NONE, duration=1):
        """v1 driver API: fault is a list of [signal, bits or value, id]."""
        faults = []
        for signal, arg, *_ in fault or []:
            name = model.LEGACY_FAULT_MODELS.get(fault_model)
            if name is None:
                raise ValueError(f"Unknown fault model {fault_model}.")
            if name == model.BIT_VALUE:
                faults.append(model.Fault(name, signal, value=str(arg)))
            else:
                faults.append(model.Fault(name, signal, model._bits(list(arg))))
        trigger = model.Trigger(
            when     = dict(cond or {}),
            rising   = {k: model._bits(list(v)) for k, v in (rising_edge or {}).items()},
            falling  = {k: model._bits(list(v)) for k, v in (falling_edge or {}).items()},
            offset   = offset,
            duration = duration,
            faults   = faults)
        return self.add(trigger)
