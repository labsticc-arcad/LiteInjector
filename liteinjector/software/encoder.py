# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

"""Translation of a Trigger into the words of a hardware trigger entry (pure functions)."""

from collections import namedtuple

from liteinjector.software import model

# Trigger entry flags (see liteinjector.core).
FLAG_RANDOM = 0

Entry = namedtuple("Entry", ["mask", "value", "r_edge_mask", "f_edge_mask",
    "fault_and", "fault_or", "fault_xor", "offset", "duration", "flags"])

class FaultVectors:
    """Fault applied as: output = ((data & fault_and) | fault_or) ^ fault_xor."""
    def __init__(self, data_width):
        self.all_ones  = (1 << data_width) - 1
        self.fault_and = self.all_ones
        self.fault_or  = 0
        self.fault_xor = 0
        self.flags     = 0

# Fault model registry -----------------------------------------------------------------------------

FAULT_ENCODERS = {}

def fault_model(name):
    """Register an encoder for a fault model: fn(fault, layout, group, vectors)."""
    def register(fn):
        FAULT_ENCODERS[name] = fn
        return fn
    return register

@fault_model(model.BIT_SET)
def _bit_set(fault, layout, group, v):
    v.fault_or |= layout.bits_mask(fault.signal, fault.bits, group)

@fault_model(model.BIT_RESET)
def _bit_reset(fault, layout, group, v):
    v.fault_and &= ~layout.bits_mask(fault.signal, fault.bits, group) & v.all_ones

@fault_model(model.BIT_FLIP)
def _bit_flip(fault, layout, group, v):
    v.fault_xor |= layout.bits_mask(fault.signal, fault.bits, group)

@fault_model(model.BIT_FLIP_RANDOM)
def _bit_flip_random(fault, layout, group, v):
    if not layout.with_lfsr:
        raise ValueError("bit-flip-random requires a core built with with_lfsr=True.")
    v.fault_xor |= layout.bits_mask(fault.signal, fault.bits, group)
    v.flags     |= 1 << FLAG_RANDOM

@fault_model(model.BIT_VALUE)
def _bit_value(fault, layout, group, v):
    if fault.value is None:
        raise ValueError(f"bit-value fault on {fault.signal} needs a value.")
    value, mask = layout.value_mask(fault.signal, fault.value, group)
    v.fault_and &= ~mask & v.all_ones
    v.fault_or  |= value & mask

# Encoder ------------------------------------------------------------------------------------------

def encode(trigger, layout, group=0):
    """Return the Entry to write in the trigger memory for this trigger."""
    mask = value = 0
    for name, pattern in trigger.when.items():
        v, m = layout.value_mask(name, pattern, group)
        value |= v
        mask  |= m

    r_edge_mask = 0
    for name, bits in trigger.rising.items():
        r_edge_mask |= layout.bits_mask(name, bits, group)

    f_edge_mask = 0
    for name, bits in trigger.falling.items():
        f_edge_mask |= layout.bits_mask(name, bits, group)

    if (mask | r_edge_mask | f_edge_mask) == 0:
        raise ValueError("A trigger needs at least one condition (value, rising or falling edge).")
    if not 0 <= trigger.offset <= layout.offset_depth:
        raise ValueError(f"Offset {trigger.offset} is out of range (0-{layout.offset_depth}).")
    if not 1 <= trigger.duration <= max(layout.duration_depth, 1):
        raise ValueError(f"Duration {trigger.duration} is out of range (1-{max(layout.duration_depth, 1)}).")

    vectors = FaultVectors(layout.data_width(group))
    for fault in trigger.faults:
        try:
            encoder = FAULT_ENCODERS[fault.model]
        except KeyError:
            raise ValueError(f"Unknown fault model '{fault.model}' (available: {', '.join(FAULT_ENCODERS)}).")
        encoder(fault, layout, group, vectors)

    return Entry(mask, value, r_edge_mask, f_edge_mask,
        vectors.fault_and, vectors.fault_or, vectors.fault_xor,
        trigger.offset, trigger.duration, vectors.flags)
