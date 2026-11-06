# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

"""Signal layout of a LiteInjector core, read from the configuration CSV (injector.csv)."""

import re
import csv

# Hardware/software interface version supported by this package (see liteinjector.core).
LITEINJECTOR_VERSION = 2

def parse_value(text, width):
    """Parse an integer or a 0b/0x pattern where "x" digits are "don't care".

    Returns (value, mask), mask selecting the bits that are not "don't care".
    """
    text = str(text).strip()
    mb = re.fullmatch("0b([01x_]+)", text)
    mx = re.fullmatch("0x([0-9a-fA-Fx_]+)", text)
    m  = mb or mx
    if m is None:
        return int(text, 0), (1 << width) - 1
    digit_bits = 4 if mx is not None else 1
    value = 0
    mask  = 0
    for c in m.group(1).replace("_", ""):
        value <<= digit_bits
        mask  <<= digit_bits
        if c != "x":
            value |= int(c, 16 if mx is not None else 2)
            mask  |= (1 << digit_bits) - 1
    return value, mask

class Layout:
    """Position of every probed signal in the data word of each group."""

    def __init__(self, config, groups):
        self.config = config # {"version": 2, "data_width": ..., ...}
        self.groups = groups # {group: [(name, width), ...]}
        self.fields = {}     # {(group, name): (start, width)}
        for group, signals in groups.items():
            start = 0
            for name, width in signals:
                self.fields[(group, name)] = (start, width)
                start += width

    @classmethod
    def from_csv(cls, filename):
        config, groups = {}, {}
        with open(filename) as f:
            for row in csv.reader(f, delimiter=",", quotechar="#"):
                if len(row) != 4:
                    continue
                t, g, n, v = row
                if t == "config":
                    config[n] = int(v)
                elif t == "signal":
                    groups.setdefault(int(g), []).append((n, int(v)))
        return cls(config, groups)

    # Capabilities ---------------------------------------------------------------------------------

    @property
    def version(self):
        return self.config.get("version", 1)

    def check_version(self):
        if self.version != LITEINJECTOR_VERSION:
            raise RuntimeError(f"The configuration CSV comes from a LiteInjector v{self.version} core, this "
                f"software supports v{LITEINJECTOR_VERSION}. Rebuild the SoC with the current LiteInjector.")

    @property
    def offset_depth(self):
        return self.config.get("offset_depth", 500)

    @property
    def duration_depth(self):
        return self.config.get("duration_depth", 1)

    @property
    def with_lfsr(self):
        return bool(self.config.get("lfsr", 0))

    @property
    def depth(self):
        return self.config.get("depth", 16)

    @property
    def with_history(self):
        return bool(self.config.get("history", 0))

    # Signals --------------------------------------------------------------------------------------

    def signals(self, group=0):
        return list(self.groups.get(group, []))

    def data_width(self, group=0):
        return sum(width for _, width in self.groups.get(group, []))

    def resolve(self, name, group=0):
        """Full signal name from an exact name, or a unique substring/regex match."""
        names = [n for n, _ in self.groups.get(group, [])]
        if name in names:
            return name
        try:
            pattern = re.compile(name)
        except re.error:
            pattern = re.compile(re.escape(name))
        candidates = [n for n in names if pattern.search(n)]
        if not candidates:
            raise ValueError(f"No signal matches '{name}' in group {group} (see the 'list' command).")
        if len(candidates) > 1:
            # Prefer a candidate ending with the requested name (e.g. "dat_r" -> "..._ibus_dat_r").
            suffix = [n for n in candidates if n.endswith(name)]
            if len(suffix) == 1:
                return suffix[0]
            raise ValueError(f"'{name}' is ambiguous in group {group}: {', '.join(candidates)}.")
        return candidates[0]

    def field(self, name, group=0):
        """(start, width) of a signal in the data word."""
        name = self.resolve(name, group)
        return self.fields[(group, name)]

    def bits_mask(self, name, bits=None, group=0):
        """Mask of some bits of a signal, all its bits when bits is None or empty."""
        start, width = self.field(name, group)
        if not bits:
            return ((1 << width) - 1) << start
        mask = 0
        for bit in bits:
            bit = int(bit)
            if not 0 <= bit < width:
                raise ValueError(f"Bit {bit} is out of range for {name} ({width} bits).")
            mask |= 1 << (start + bit)
        return mask

    def value_mask(self, name, text, group=0):
        """(value, mask) of a value pattern applied to a signal, in data word position."""
        start, width = self.field(name, group)
        value, mask = parse_value(text, width)
        if value >> width:
            raise ValueError(f"Value {text} does not fit in {name} ({width} bits).")
        return value << start, (mask & ((1 << width) - 1)) << start
