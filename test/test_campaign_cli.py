# SPDX-License-Identifier: BSD-2-Clause

# Campaigns (sweeps, runner, results) and command line, without hardware.

import csv
import json
import shlex

import pytest

from liteinjector.software.layout import Layout
from liteinjector.software.model import Trigger, Fault
from liteinjector.software.encoder import encode
from liteinjector.software.campaign import (Campaign, CampaignRunner, Observer, ResultWriter,
    parse_sweep_values, substitute, make_observer, UartObserver, CommandObserver,
    SUCCESS, NO_EFFECT, TIMEOUT, NOT_INJECTED, INJECTED, CRASH)
from liteinjector.software.liteinjector_cli import main, legacy_parser, legacy_triggers

CAMPAIGN = {
    "campaign": {"name": "test", "repeat": 2, "seed": 100},
    "sweep":    {"bit": "0..3", "offset": [1, 2]},
    "step": [
        {"when": {"sig_a": "0x10"}, "offset": "{offset}",
         "fault": {"model": "bit-flip", "signal": "sig_b", "bits": "{bit}"}},
        {"rising": {"sig_a": [0]}, "fault": {"model": "bit-set", "signal": "sig_b", "bits": [7]}},
    ],
}

# Campaign description -----------------------------------------------------------------------------

def test_sweep_values():
    assert parse_sweep_values("0..3") == [0, 1, 2, 3]
    assert parse_sweep_values("0x10..0x18:4") == [0x10, 0x14, 0x18]
    assert parse_sweep_values([5, 9]) == [5, 9]
    assert parse_sweep_values(7) == [7]

def test_substitute():
    assert substitute({"a": "{x}", "b": ["sig={x}"]}, {"x": 3}) == {"a": 3, "b": ["sig=3"]}
    with pytest.raises(ValueError, match="placeholder"):
        substitute("{y}", {"x": 1})

def test_campaign_runs(layout):
    c = Campaign.from_dict(CAMPAIGN)
    runs = list(c.runs())
    assert len(c) == len(runs) == 4*2*2
    index, params, repetition, triggers = runs[3]
    assert (index, params, repetition) == (3, {"bit": 0, "offset": 2}, 1)
    assert triggers[0].offset == 2 and triggers[0].faults[0].bits == [0]
    assert len(triggers) == 2
    c.check(layout)

def test_campaign_check_reports_run(layout):
    d = json.loads(json.dumps(CAMPAIGN))
    d["sweep"]["bit"] = "6..8" # sig_b has 8 bits.
    with pytest.raises(ValueError, match="Run"):
        Campaign.from_dict(d).check(layout)

def test_campaign_rejects_unknown_fields():
    with pytest.raises(ValueError, match="Unknown campaign field"):
        Campaign.from_dict(dict(CAMPAIGN, sweeps={}))

def test_make_observer():
    assert isinstance(make_observer({"uart": "/dev/ttyUSB1", "send": "x\n", "success": "ok"}), UartObserver)
    assert isinstance(make_observer({"command": "true"}), CommandObserver)
    assert type(make_observer({"reset": True})) is Observer
    with pytest.raises(ValueError):
        make_observer({"uarte": "/dev/ttyUSB1"})

def test_classify():
    o = Observer(success="Access granted", failure="Access refused", crash=["panic", "trap"])
    assert o.classify("...Access granted") == SUCCESS
    assert o.classify("Access refused") == NO_EFFECT
    assert o.classify("kernel panic") == CRASH
    assert o.classify("...") is None

# Runner -------------------------------------------------------------------------------------------

class FakeClient:
    def __init__(self, layout, faults):
        self.layout = layout
        self.faults = list(faults) # fault_count returned for each run
        self.injected = []
        self.resets = 0
    def inject(self, triggers, group=0, seed=None):
        for t in triggers:
            encode(t, self.layout, group)
        self.injected.append((triggers, seed))
    def status(self):
        n = self.faults.pop(0)
        return dict(done=True, busy=False, armed=True, hit_count=n, fault_count=n, hit_timestamp=42,
            capture_before=0x0010, capture_after=0x0011)
    def disarm(self):
        pass
    def reset_target(self, delay):
        self.resets += 1

class ScriptedObserver(UartObserver):
    def __init__(self, outputs, **kwargs):
        Observer.__init__(self, **kwargs)
        self.outputs = list(outputs)
    def open(self):
        pass
    def close(self):
        pass
    def observe(self):
        out = self.outputs.pop(0)
        return self.classify(out), out

def test_runner_with_observation(layout, tmp_path):
    d = {"campaign": {"name": "t", "seed": 7}, "sweep": {"bit": "0..3"},
         "step": [{"when": {"sig_a": "1"}, "fault": {"model": "bit-flip", "signal": "sig_b", "bits": "{bit}"}}],
         "target": {"reset": True, "reset_delay": 0}}
    campaign = Campaign.from_dict(d)
    client = FakeClient(layout, faults=[1, 1, 0, 1])
    observer = ScriptedObserver(["Access granted", "Access refused", "Access refused", "garbage"],
        success="granted", failure="refused")
    out = tmp_path / "r.csv"
    summary = CampaignRunner(client, campaign, observer, ResultWriter(str(out)), log=None).run()
    assert summary == {SUCCESS: 1, NO_EFFECT: 1, NOT_INJECTED: 1, TIMEOUT: 1}
    assert client.resets == 4
    assert [seed for _, seed in client.injected] == [7, 8, 9, 10]
    rows = list(csv.DictReader(open(out)))
    assert [r["outcome"] for r in rows] == [SUCCESS, NO_EFFECT, NOT_INJECTED, TIMEOUT]
    assert json.loads(rows[0]["params"]) == {"bit": 0}
    assert rows[0]["capture_after"] == "0x0011"

def test_runner_without_observation(layout, tmp_path):
    campaign = Campaign.from_dict({"campaign": {"repeat": 2}, "step": [{"when": {"sig_a": "1"}}]})
    out = tmp_path / "r.json"
    summary = CampaignRunner(FakeClient(layout, [1, 0]), campaign, writer=ResultWriter(str(out)), log=None).run()
    assert summary == {INJECTED: 1, NOT_INJECTED: 1}
    assert [json.loads(l)["outcome"] for l in open(out)] == [INJECTED, NOT_INJECTED]

# Command line -------------------------------------------------------------------------------------

DOC_COMMANDS = [
    "-v main_count_clk_divider 0x3FFFFFF 0 -bv main_count_result 0xFFFF 0",
    "-v main_basesoc_pbus_adr 0xxxxxxxe3 0 -v main_basesoc_pbus_dat_r 0x00f71e63 0 -br main_basesoc_pbus_dat_r {12} 0",
    "-v main_basesoc_pmp_output 0x1 0 -br main_basesoc_pmp_output [] 0",
    "-v main_basesoc_ibus_adr 0x10000130 0 -bv main_basesoc_ibus_dat_r 0x00000013 0 -o 2 0",
    "-v main_basesoc_ibus_adr 0x0000037A 0 -bv main_basesoc_ibus_dat_r 0x00050C63 0 -o 1 0",
]

DOC_LAYOUT = Layout({"version": 2, "offset_depth": 500, "duration_depth": 255, "lfsr": 1}, {0: [
    ("main_count_result", 16), ("main_count_clk_divider", 26),
    ("main_basesoc_pbus_adr", 32), ("main_basesoc_pbus_dat_r", 32),
    ("main_basesoc_ibus_adr", 32), ("main_basesoc_ibus_dat_r", 32), ("main_basesoc_pmp_output", 1)]})

@pytest.mark.parametrize("command", DOC_COMMANDS)
def test_documented_v1_commands(command):
    triggers = legacy_triggers(legacy_parser().parse_args(shlex.split(command)))
    assert len(triggers) == 1
    encode(triggers[0], DOC_LAYOUT)

def test_v1_translation():
    t, = legacy_triggers(legacy_parser().parse_args(shlex.split(DOC_COMMANDS[1])))
    assert t.when == {"main_basesoc_pbus_adr": "0xxxxxxxe3", "main_basesoc_pbus_dat_r": "0x00f71e63"}
    assert t.faults == [Fault("bit-reset", "main_basesoc_pbus_dat_r", [12])]
    t, = legacy_triggers(legacy_parser().parse_args(shlex.split(DOC_COMMANDS[4])))
    assert t.offset == 1 and t.faults == [Fault("bit-value", "main_basesoc_ibus_dat_r", value="0x00050C63")]

def test_v1_trigger_order_follows_ids():
    args = legacy_parser().parse_args(shlex.split("-v sig_a 2 1 -v sig_a 1 0 -bf sig_b 0 1 -bf sig_b 1 0"))
    first, second = legacy_triggers(args)
    assert first.when == {"sig_a": "1"} and second.when == {"sig_a": "2"}

def test_cli_info_and_list(config_csv, capsys):
    csv_path = config_csv()
    assert main(["info", "--csv", csv_path, "--json"]) == 0
    info = json.loads(capsys.readouterr().out)
    assert info["version"] == 2 and "bit-flip-random" in info["fault_models"]
    assert main(["list", "--csv", csv_path]) == 0
    assert "main_sig_b" in capsys.readouterr().out
    assert main(["-l", "--csv", csv_path]) == 0
    assert capsys.readouterr().out.split() == ["main_sig_a", "main_sig_b"]

def test_cli_run_dry_run(config_csv, capsys):
    rc = main(["run", "--csv", config_csv(), "--dry-run", "--when", "sig_a=0x10", "--offset", "2",
        "--fault", "bit-flip:sig_b:0,1", "--fault", "bit-set:sig_a:7"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "fault_xor    0x0300" in out and "fault_or     0x0080" in out and "offset       2" in out

def test_cli_errors(config_csv, capsys):
    assert main(["run", "--csv", config_csv(), "--dry-run", "--fault", "bit-flip:sig_b"]) == 1
    assert "at least one condition" in capsys.readouterr().err
    assert main(["list", "--csv", "missing.csv"]) == 1

def test_cli_campaign_dry_run(config_csv, tmp_path, capsys):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(CAMPAIGN))
    assert main(["campaign", str(path), "--csv", config_csv(), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "16 run(s)" in out and out.count("--- run") == 8

# Chained triggers, repetitions, history and shell ---------------------------------------------------

from liteinjector.software import liteinjector_cli
from liteinjector.software.liteinjector_cli import (InjectorShell, parse_chain, print_history,
    print_status)

CHAIN = ["--when", "sig_a=0x10", "--offset", "2", "--fault", "bit-flip:sig_b:0",
    "--then", "--when", "sig_a=0x20", "--duration", "3", "--fault", "bit-set:sig_b:7"]

def test_parse_chain_gives_each_trigger_its_own_options():
    first, second = parse_chain(CHAIN)
    assert (first.offset, first.duration, first.when) == (2, 1, {"sig_a": "0x10"})
    assert (second.offset, second.duration, second.when) == (0, 3, {"sig_a": "0x20"})
    assert second.faults == [Fault("bit-set", "sig_b", [7])]

def test_parse_chain_rejects_empty_and_foreign_options():
    with pytest.raises(ValueError, match="Empty trigger 1"):
        parse_chain(["--when", "sig_a=1", "--then"])
    with pytest.raises(ValueError, match="unrecognized"):
        parse_chain(["--when", "sig_a=1", "--wait", "3"])
    extra = []
    triggers = parse_chain(["--when", "sig_a=1", "--then", "--when", "sig_a=2", "--wait", "3"], extra)
    assert len(triggers) == 2 and extra == ["--wait", "3"]

def test_cli_run_then_dry_run(config_csv, capsys):
    rc = main(["run", "--csv", config_csv(), "--dry-run"] + CHAIN + ["--wait", "5"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Trigger 0:" in out and "Trigger 1:" in out
    assert "fault_xor    0x0100" in out and "fault_or     0x8000" in out and "duration     3" in out

def test_cli_run_then_errors(config_csv, capsys):
    assert main(["run", "--csv", config_csv(), "--dry-run", "--when", "sig_a=1", "--then"]) == 1
    assert "Empty trigger" in capsys.readouterr().err
    # Every trigger is validated before connecting.
    assert main(["run", "--csv", config_csv(), "--dry-run", "--when", "sig_a=1", "--fault", "bit-flip:sig_b:99",
        "--then", "--when", "sig_a=2"]) == 1

def test_cli_run_several_files(config_csv, tmp_path, capsys):
    paths = []
    for i, value in enumerate(["0x10", "0x20"]):
        path = tmp_path / f"step{i}.json"
        path.write_text(json.dumps({"step": [{"when": {"sig_a": value},
            "fault": {"model": "bit-flip", "signal": "sig_b", "bits": [i]}}]}))
        paths.append(str(path))
    assert main(["run", *paths, "--csv", config_csv(), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Trigger 0:" in out and "Trigger 1:" in out and "0x0100" in out and "0x0200" in out
    assert main(["run", paths[0], "--when", "sig_a=1", "--csv", config_csv(), "--dry-run"]) == 1
    assert "not both" in capsys.readouterr().err

def test_cli_repeat_and_history_need_wait(config_csv, capsys):
    base = ["run", "--csv", config_csv(), "--dry-run", "--when", "sig_a=1", "--fault", "bit-flip:sig_b:0"]
    assert main(base + ["--repeat", "3"]) == 1
    assert "--wait" in capsys.readouterr().err
    assert main(base + ["--history"]) == 1
    assert main(base + ["--repeat", "0", "--wait", "1"]) == 1
    assert main(base + ["--repeat", "3", "--wait", "1"]) == 0
    assert "run 3 times" in capsys.readouterr().out

class FakeSequenceClient:
    """Client double that fires every loaded trigger and records the calls."""
    EVENTS = [{"index": 0, "timestamp": 100, "before": 0x5510, "after": 0x5511},
              {"index": 1, "timestamp": 130, "before": 0x5500, "after": 0x5502}]
    def __init__(self, layout, fire=True):
        self.layout, self.fire, self.calls, self.loaded = layout, fire, [], 0
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        pass
    def inject(self, triggers, group=0, seed=None):
        self.loaded = len(triggers)
        self.calls.append(("inject", len(triggers), group, seed))
    def wait(self, timeout=None):
        self.calls.append(("wait", timeout))
        return self.fire
    def clear(self):
        self.calls.append(("clear",))
    def disarm(self):
        self.calls.append(("disarm",))
    def status(self):
        n = self.loaded if self.fire else 1
        return dict(done=self.fire, busy=False, armed=True, hit_count=n, fault_count=n, hit_timestamp=130,
            capture_before=0x5500, capture_after=0x5502, loaded=self.loaded)
    def history(self):
        return self.EVENTS[:self.status()["fault_count"]]

@pytest.fixture
def fake_client(monkeypatch, layout):
    client = FakeSequenceClient(layout)
    monkeypatch.setattr(liteinjector_cli, "connect", lambda args: client)
    return client

def test_cli_run_repeat_reseeds_each_repetition(config_csv, fake_client, capsys):
    rc = main(["run", "--csv", config_csv(), "--when", "sig_a=1", "--fault", "bit-flip:sig_b:0", "--then",
        "--when", "sig_a=2", "--seed", "10", "--repeat", "3", "--wait", "1"])
    out = capsys.readouterr().out
    assert rc == 0
    assert [c[3] for c in fake_client.calls if c[0] == "inject"] == [10, 11, 12]
    assert out.count("--- Repetition") == 3 and out.count("Trigger 0:") == 1
    assert "2/2 trigger(s) fired" in out

def test_cli_run_timeout_exit_code(config_csv, fake_client, capsys):
    fake_client.fire = False
    rc = main(["run", "--csv", config_csv(), "--when", "sig_a=1", "--wait", "0.1"])
    assert rc == 2

def test_cli_run_history(config_csv, fake_client, capsys):
    main(["run", "--csv", config_csv(), "--when", "sig_a=1", "--then", "--when", "sig_a=2", "--wait", "1", "--history"])
    out = capsys.readouterr().out
    assert "Fault history (2 fault(s))" in out
    assert "cycle 100" in out and "+30" in out and "before 0x5500  after 0x5502" in out

def test_cli_history_json(config_csv, fake_client, capsys):
    fake_client.loaded = 2
    assert main(["history", "--csv", config_csv(), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [e["timestamp"] for e in data["history"]] == [100, 130] and data["loaded"] == 2

def test_cli_history_unavailable(config_csv, capsys):
    assert main(["history", "--csv", config_csv(history=0)]) == 1
    assert "without fault history" in capsys.readouterr().err

def test_status_shows_sequence_progress(capsys):
    status = dict(done=False, busy=True, fault_count=1, loaded=3)
    print_status(status, False)
    out = capsys.readouterr().out
    assert "1/3 trigger(s) fired" in out and "loaded" not in out
    print_status(dict(status, loaded=None), False)
    assert "sequence" not in capsys.readouterr().out

def test_history_reports_unrecorded_faults(capsys):
    print_history(FakeSequenceClient.EVENTS, 16, fault_count=5)
    assert "3 more fault(s) not recorded" in capsys.readouterr().out

def run_shell(layout, client, *lines):
    shell = InjectorShell(layout, client)
    for line in lines:
        shell.onecmd(line)
    return shell

def test_shell_builds_and_arms_a_sequence(layout, capsys):
    client = FakeSequenceClient(layout)
    shell = run_shell(layout, client,
        "add --when sig_a=1 --fault bit-flip:sig_b:0 --then --when sig_a=2 --offset 3 --fault bit-set:sig_b:7",
        "add --rise sig_a:0 --fault bit-reset:sig_b:1",
        "remove 2", "show", "seed 0x10", "arm", "wait 1", "history")
    out = capsys.readouterr().out
    assert len(shell.pending) == 2
    assert "Removed trigger 2" in out and "Injector armed with 2 trigger(s)" in out
    assert client.calls[0] == ("inject", 2, 0, 0x10)
    assert "2/2 trigger(s) fired" in out and "Fault history (2 fault(s))" in out

def test_shell_survives_errors(layout, capsys):
    shell = run_shell(layout, FakeSequenceClient(layout),
        "add --when nosuchsignal=1", "add --bad", "add", "remove 9", "group 7", "arm", "load")
    out = capsys.readouterr().out
    assert shell.pending == []
    assert out.count("Error:") == 7

def test_shell_offline_cannot_arm(layout, capsys):
    shell = InjectorShell(layout, None)
    shell.onecmd("add --when sig_a=1")
    shell.onecmd("arm")
    assert "offline" in capsys.readouterr().out
    assert shell.onecmd("exit") is True

def test_shell_group_and_clear(layout, capsys):
    client = FakeSequenceClient(layout)
    shell = run_shell(layout, client, "add --when sig_a=1", "group 1")
    assert "Error" in capsys.readouterr().out and shell.group == 0 # sig_a is not in group 1.
    shell.onecmd("clear")
    assert shell.pending == [] and ("clear",) in client.calls
    shell.onecmd("group 1")
    assert shell.group == 1

def test_shell_command_line_entry(config_csv, monkeypatch, capsys):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("add --when sig_a=1 --fault bit-flip:sig_b:0\nshow -v\nexit\n"))
    assert main(["shell", "--csv", config_csv(), "--offline"]) == 0
    out = capsys.readouterr().out
    assert "Trigger 0:" in out and "fault_xor    0x0100" in out
