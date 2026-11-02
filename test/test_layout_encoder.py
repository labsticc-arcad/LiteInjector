# SPDX-License-Identifier: BSD-2-Clause

# Signal layout, trigger model and encoder (pure software, no hardware).

import pytest

from liteinjector.software.layout import Layout, parse_value
from liteinjector.software.model import Trigger, Fault
from liteinjector.software.encoder import encode, fault_model, FAULT_ENCODERS, FLAG_RANDOM

ALL = 0xffff

# Layout -------------------------------------------------------------------------------------------

def test_parse_value():
    assert parse_value("0x3x", 8) == (0x30, 0xf0)
    assert parse_value("0b1x0", 3) == (0b100, 0b101)
    assert parse_value("12", 8) == (12, 0xff)
    assert parse_value("0x00_ff", 16) == (0xff, 0xffff)

def test_layout_config(layout):
    assert layout.version == 2
    assert layout.data_width(0) == 16 and layout.data_width(1) == 16
    assert layout.with_lfsr and layout.offset_depth == 500

def test_resolve(layout):
    assert layout.resolve("main_sig_a") == "main_sig_a"
    assert layout.resolve("sig_b") == "main_sig_b"
    assert layout.resolve("other", group=1) == "main_other"
    with pytest.raises(ValueError, match="ambiguous"):
        layout.resolve("sig")
    with pytest.raises(ValueError, match="No signal"):
        layout.resolve("missing")

def test_masks(layout):
    assert layout.bits_mask("sig_b", [0, 7]) == 0x8100
    assert layout.bits_mask("sig_b") == 0xff00
    assert layout.value_mask("sig_b", "0xAx") == (0xa000, 0xf000)
    with pytest.raises(ValueError):
        layout.bits_mask("sig_a", [8])
    with pytest.raises(ValueError):
        layout.value_mask("sig_a", "0x100")

def test_version_check(config_csv):
    with pytest.raises(RuntimeError, match="Rebuild"):
        Layout.from_csv(config_csv(version=1)).check_version()

# Model --------------------------------------------------------------------------------------------

def test_fault_parse():
    assert Fault.parse("bit-flip:sig_a:0,3") == Fault("bit-flip", "sig_a", [0, 3])
    assert Fault.parse("bit-set:sig_a:4-6") == Fault("bit-set", "sig_a", [4, 5, 6])
    assert Fault.parse("bit-reset:sig_a") == Fault("bit-reset", "sig_a", None)
    assert Fault.parse("bit-value:sig_a=0x1x") == Fault("bit-value", "sig_a", value="0x1x")
    with pytest.raises(ValueError):
        Fault.parse("bit-flip")

def test_trigger_from_dict():
    t = Trigger.from_dict({"when": {"sig_a": 16}, "rising": {"sig_b": [1]}, "offset": 2,
        "fault": {"model": "bit-flip", "signal": "sig_b", "bits": "0-1"},
        "faults": [{"model": "bit-set", "signal": "sig_a", "bits": 7}]})
    assert t.when == {"sig_a": "16"} and t.rising == {"sig_b": [1]} and t.offset == 2
    assert t.faults == [Fault("bit-flip", "sig_b", [0, 1]), Fault("bit-set", "sig_a", [7])]
    with pytest.raises(ValueError, match="Unknown trigger field"):
        Trigger.from_dict({"when": {"sig_a": "1"}, "ofset": 2})

# Encoder ------------------------------------------------------------------------------------------

def test_condition_and_edges(layout):
    e = encode(Trigger(when={"sig_a": "0x1x"}, rising={"sig_b": [0, 7]}, falling={"sig_a": [1]}), layout)
    assert (e.value, e.mask, e.r_edge_mask, e.f_edge_mask) == (0x0010, 0x00f0, 0x8100, 0x0002)
    assert (e.fault_and, e.fault_or, e.fault_xor, e.duration) == (ALL, 0, 0, 1)

@pytest.mark.parametrize("fault, vectors", [
    (Fault("bit-set",   "sig_b", [0, 3]),    (ALL, 0x0900, 0)),
    (Fault("bit-reset", "sig_b", [1]),       (ALL & ~0x0200, 0, 0)),
    (Fault("bit-flip",  "sig_b"),            (ALL, 0, 0xff00)),
    (Fault("bit-value", "sig_b", value="0xAx"), (0x0fff, 0xa000, 0)), # "x" digits are kept.
])
def test_fault_models(layout, fault, vectors):
    e = encode(Trigger(when={"sig_a": "1"}, faults=[fault]), layout)
    assert (e.fault_and, e.fault_or, e.fault_xor) == vectors

def test_bit_reset_on_two_signals(layout):
    e = encode(Trigger(when={"sig_a": "1"}, faults=[Fault("bit-reset", "sig_a", [0]), Fault("bit-reset", "sig_b", [1])]), layout)
    assert e.fault_and == ALL & ~0x0201

def test_several_models_in_one_trigger(layout):
    e = encode(Trigger(when={"sig_a": "1"}, faults=[Fault("bit-set", "sig_a", [0]), Fault("bit-flip", "sig_b")]), layout)
    assert (e.fault_or, e.fault_xor) == (0x0001, 0xff00)

def test_random_flip(layout, config_csv):
    t = Trigger(when={"sig_a": "1"}, faults=[Fault("bit-flip-random", "sig_b")])
    e = encode(t, layout)
    assert e.fault_xor == 0xff00 and e.flags == 1 << FLAG_RANDOM
    with pytest.raises(ValueError, match="with_lfsr"):
        encode(t, Layout.from_csv(config_csv(lfsr=0)))

def test_group(layout):
    e = encode(Trigger(when={"other": "0x1234"}, faults=[Fault("bit-flip", "other", [15])]), layout, group=1)
    assert (e.value, e.fault_xor) == (0x1234, 0x8000)

@pytest.mark.parametrize("trigger, error", [
    (Trigger(faults=[Fault("bit-flip", "sig_a")]), "at least one condition"),
    (Trigger(when={"sig_a": "1"}, offset=501), "Offset"),
    (Trigger(when={"sig_a": "1"}, duration=0), "Duration"),
    (Trigger(when={"sig_a": "1"}, faults=[Fault("glitch", "sig_a")]), "Unknown fault model"),
    (Trigger(when={"sig_a": "1"}, faults=[Fault("bit-value", "sig_a")]), "needs a value"),
])
def test_invalid_triggers(layout, trigger, error):
    with pytest.raises(ValueError, match=error):
        encode(trigger, layout)

def test_custom_fault_model(layout):
    @fault_model("stuck-at-0")
    def stuck_at_0(fault, layout, group, v):
        v.fault_and &= ~layout.bits_mask(fault.signal, fault.bits, group) & v.all_ones
    try:
        e = encode(Trigger(when={"sig_a": "1"}, faults=[Fault("stuck-at-0", "sig_a", [2])]), layout)
        assert e.fault_and == ALL & ~0x0004
    finally:
        del FAULT_ENCODERS["stuck-at-0"]
