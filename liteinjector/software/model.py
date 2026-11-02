# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

"""Description of an injection: triggers and faults, independent of the hardware encoding."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Fault models -------------------------------------------------------------------------------------

BIT_SET         = "bit-set"
BIT_RESET       = "bit-reset"
BIT_FLIP        = "bit-flip"
BIT_FLIP_RANDOM = "bit-flip-random"
BIT_VALUE       = "bit-value"

# Numbering of the legacy command line (and of the v1 hardware).
LEGACY_FAULT_MODELS = {1: BIT_SET, 2: BIT_RESET, 3: BIT_FLIP, 4: BIT_FLIP_RANDOM, 5: BIT_VALUE}

def _bits(value):
    """Normalize a bit list: None/"all"/[] -> None (all bits), int/str/iterable -> list of ints."""
    if value is None or value == "all":
        return None
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        value = [v for v in value.replace(" ", "").split(",") if v != ""]
    bits = []
    for v in value:
        if isinstance(v, str) and "-" in v:
            lo, hi = v.split("-")
            bits.extend(range(int(lo), int(hi) + 1))
        else:
            bits.append(int(v))
    return bits or None

@dataclass
class Fault:
    model:  str                       # One of the fault model names (see liteinjector.software.encoder).
    signal: str
    bits:   Optional[List[int]] = None # Targeted bits (None: every bit of the signal).
    value:  Optional[str] = None       # Value pattern for bit-value ("0x3x" style).

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        model = d.pop("model")
        signal = d.pop("signal")
        bits = _bits(d.pop("bits", None))
        value = d.pop("value", None)
        if d:
            raise ValueError(f"Unknown fault field(s): {', '.join(d)}.")
        return cls(model, signal, bits, None if value is None else str(value))

    @classmethod
    def parse(cls, text):
        """Parse "MODEL:SIGNAL[:BITS]" or "bit-value:SIGNAL=VALUE" (BITS: "3", "0,2", "4-7")."""
        model, _, rest = text.partition(":")
        if not rest:
            raise ValueError(f"Invalid fault '{text}', expected MODEL:SIGNAL[:BITS] or bit-value:SIGNAL=VALUE.")
        if "=" in rest:
            signal, value = rest.split("=", 1)
            return cls(model, signal, value=value)
        signal, _, bits = rest.partition(":")
        return cls(model, signal, _bits(bits) if bits else None)

    def to_dict(self):
        d = {"model": self.model, "signal": self.signal}
        if self.bits is not None:
            d["bits"] = list(self.bits)
        if self.value is not None:
            d["value"] = self.value
        return d

@dataclass
class Trigger:
    when:     Dict[str, str] = field(default_factory=dict)                     # signal -> value pattern
    rising:   Dict[str, Optional[List[int]]] = field(default_factory=dict)     # signal -> bits
    falling:  Dict[str, Optional[List[int]]] = field(default_factory=dict)     # signal -> bits
    offset:   int = 0  # Cycles between the condition and the fault.
    duration: int = 1  # Fault duration in cycles.
    faults:   List[Fault] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        faults = d.pop("faults", [])
        if "fault" in d:
            faults = [d.pop("fault")] + list(faults)
        if isinstance(faults, dict):
            faults = [faults]
        trigger = cls(
            when     = {k: str(v) for k, v in d.pop("when", {}).items()},
            rising   = {k: _bits(v) for k, v in d.pop("rising", {}).items()},
            falling  = {k: _bits(v) for k, v in d.pop("falling", {}).items()},
            offset   = int(d.pop("offset", 0)),
            duration = int(d.pop("duration", 1)),
            faults   = [f if isinstance(f, Fault) else Fault.from_dict(f) for f in faults],
        )
        if d:
            raise ValueError(f"Unknown trigger field(s): {', '.join(d)}.")
        return trigger

    def to_dict(self):
        return {
            "when"     : dict(self.when),
            "rising"   : {k: v for k, v in self.rising.items()},
            "falling"  : {k: v for k, v in self.falling.items()},
            "offset"   : self.offset,
            "duration" : self.duration,
            "faults"   : [f.to_dict() for f in self.faults],
        }

    def describe(self):
        parts = [f"{k} == {v}" for k, v in self.when.items()]
        parts += [f"rising({k}{'' if b is None else ':' + ','.join(map(str, b))})" for k, b in self.rising.items()]
        parts += [f"falling({k}{'' if b is None else ':' + ','.join(map(str, b))})" for k, b in self.falling.items()]
        faults = []
        for f in self.faults:
            target = f"{f.signal}={f.value}" if f.value is not None else f.signal + ("" if f.bits is None else ":" + ",".join(map(str, f.bits)))
            faults.append(f"{f.model} {target}")
        return (f"when {' & '.join(parts) or '<nothing>'}, offset {self.offset}, duration {self.duration}: "
            + ("; ".join(faults) or "no fault"))
