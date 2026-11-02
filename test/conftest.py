# SPDX-License-Identifier: BSD-2-Clause

import pytest

CONFIG = """\
config,None,version,{version}
config,None,data_width,16
config,None,depth,16
config,None,offset_depth,500
config,None,duration_depth,255
config,None,lfsr,{lfsr}
signal,0,main_sig_a,8
signal,0,main_sig_b,8
signal,1,main_other,16
"""

CSRS = ["mux_value", "trigger_enable", "trigger_clear", "trigger_seed", "trigger_mem_write",
    "trigger_mem_mask", "trigger_mem_value", "trigger_mem_r_edge_mask", "trigger_mem_f_edge_mask",
    "trigger_mem_fault_and", "trigger_mem_fault_or", "trigger_mem_fault_xor", "trigger_mem_offset",
    "trigger_mem_duration", "trigger_mem_flags", "trigger_mem_full", "trigger_done", "trigger_busy",
    "trigger_hit_count", "trigger_fault_count", "trigger_hit_timestamp", "capture_before", "capture_after"]

class FakeReg:
    def __init__(self, log, name):
        self.value = 0
        self.log   = log
        self.name  = name
    def write(self, value):
        self.value = value
        self.log.append((self.name, value))
    def read(self):
        return self.value

class FakeRegs:
    """Stand-in for litex RemoteClient.regs, records every write."""
    def __init__(self, prefix="injector"):
        self.log = []
        self.d = {f"{prefix}_{name}": FakeReg(self.log, name) for name in CSRS}
    def __getitem__(self, name):
        return self.d["injector_" + name].value

@pytest.fixture
def config_csv(tmp_path):
    def make(version=2, lfsr=1):
        path = tmp_path / "injector.csv"
        path.write_text(CONFIG.format(version=version, lfsr=lfsr))
        return str(path)
    return make

@pytest.fixture
def layout(config_csv):
    from liteinjector.software.layout import Layout
    return Layout.from_csv(config_csv())
