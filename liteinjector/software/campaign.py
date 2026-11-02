# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

"""Injection campaigns: sweep parameters, repeat, observe the target and record the results.

A campaign file (TOML or JSON) looks like::

    [campaign]
    name   = "bios-unlock"
    repeat = 1
    output = "results.csv"

    [sweep]
    bit = "0..31"

    [[step]]
    when  = { ibus_adr = "0x0000037A" }
    fault = { model = "bit-flip", signal = "ibus_dat_r", bits = "{bit}" }

    [target]
    uart    = "/dev/ttyUSB1"
    send    = "unlock aaaa\\n"
    success = "Access granted"
    failure = "Access refused"
    timeout = 2.0
"""

import os
import re
import csv
import json
import time
import shlex
import itertools
import subprocess

from liteinjector.software.model import Trigger
from liteinjector.software.encoder import encode

# Loading ------------------------------------------------------------------------------------------

def _load_toml(path):
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            raise RuntimeError("Reading TOML campaigns needs Python 3.11+ or the 'tomli' package "
                "(or use a .json campaign file).")
    with open(path, "rb") as f:
        return tomllib.load(f)

def load_file(path):
    if path.endswith(".json"):
        with open(path) as f:
            return json.load(f)
    return _load_toml(path)

def parse_sweep_values(spec):
    """"0..31" (inclusive), "0..31:2" (step), a list, or a single value."""
    if isinstance(spec, list):
        return spec
    if isinstance(spec, str):
        m = re.fullmatch(r"\s*(-?\w+)\s*\.\.\s*(-?\w+)\s*(?::\s*(\w+))?\s*", spec)
        if m:
            lo, hi = int(m.group(1), 0), int(m.group(2), 0)
            step = int(m.group(3), 0) if m.group(3) else 1
            return list(range(lo, hi + 1, step))
    return [spec]

def substitute(obj, params):
    """Replace "{name}" placeholders in every string of obj (keeps the type for a lone placeholder)."""
    if isinstance(obj, dict):
        return {k: substitute(v, params) for k, v in obj.items()}
    if isinstance(obj, list):
        return [substitute(v, params) for v in obj]
    if isinstance(obj, str):
        m = re.fullmatch(r"\{(\w+)\}", obj)
        if m and m.group(1) in params:
            return params[m.group(1)]
        try:
            return obj.format(**params)
        except (KeyError, IndexError):
            raise ValueError(f"Unknown placeholder in '{obj}' (sweep parameters: {', '.join(params) or 'none'}).")
    return obj

class Campaign:
    def __init__(self, steps, sweep=None, repeat=1, group=0, seed=None, name="campaign",
        output=None, target=None, connection=None):
        self.steps      = steps            # List of trigger dicts, may contain {placeholders}.
        self.sweep      = sweep or {}      # {name: [values]}
        self.repeat     = repeat
        self.group      = group
        self.seed       = seed
        self.name       = name
        self.output     = output
        self.target     = target or {}
        self.connection = connection or {}

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        meta = dict(d.pop("campaign", {}))
        steps = d.pop("step", d.pop("steps", []))
        if isinstance(steps, dict):
            steps = [steps]
        if not steps:
            raise ValueError("A campaign needs at least one [[step]].")
        campaign = cls(
            steps      = steps,
            sweep      = {k: parse_sweep_values(v) for k, v in d.pop("sweep", {}).items()},
            repeat     = int(meta.pop("repeat", 1)),
            group      = int(meta.pop("group", 0)),
            seed       = meta.pop("seed", None),
            name       = meta.pop("name", "campaign"),
            output     = meta.pop("output", None),
            target     = d.pop("target", {}),
            connection = d.pop("connection", {}),
        )
        if meta or d:
            raise ValueError(f"Unknown campaign field(s): {', '.join(list(meta) + list(d))}.")
        return campaign

    @classmethod
    def from_file(cls, path):
        return cls.from_dict(load_file(path))

    def combinations(self):
        names = list(self.sweep)
        for values in itertools.product(*(self.sweep[n] for n in names)):
            yield dict(zip(names, values))

    def runs(self):
        """Yield (index, params, repetition, [Trigger]) for every run of the campaign."""
        index = 0
        for params in self.combinations():
            triggers = [Trigger.from_dict(substitute(step, params)) for step in self.steps]
            for repetition in range(self.repeat):
                yield index, params, repetition, triggers
                index += 1

    def __len__(self):
        n = self.repeat
        for values in self.sweep.values():
            n *= len(values)
        return n

    def check(self, layout):
        """Encode every run without hardware, raise on the first invalid trigger."""
        for index, params, _, triggers in self.runs():
            for trigger in triggers:
                try:
                    encode(trigger, layout, self.group)
                except ValueError as e:
                    raise ValueError(f"Run {index} {params}: {e}")

# Observation --------------------------------------------------------------------------------------

NO_EFFECT   = "no-effect"   # The target behaved normally ("failure" pattern seen).
SUCCESS     = "success"     # The attack goal was reached ("success" pattern seen).
CRASH       = "crash"       # A crash pattern was seen.
TIMEOUT     = "timeout"     # Nothing recognized before the timeout (hang or silent crash).
INJECTED    = "injected"    # No observation configured, the fault was injected.
NOT_INJECTED = "not-injected"

class Observer:
    """Stimulate the target after arming and classify its behaviour."""
    def __init__(self, success=None, failure=None, crash=None, timeout=2.0):
        def patterns(p):
            if p is None:
                return []
            return [re.compile(x) for x in ([p] if isinstance(p, str) else p)]
        self.success = patterns(success)
        self.failure = patterns(failure)
        self.crash   = patterns(crash)
        self.timeout = timeout

    def open(self):
        pass

    def close(self):
        pass

    def classify(self, output):
        for outcome, patterns in [(SUCCESS, self.success), (CRASH, self.crash), (NO_EFFECT, self.failure)]:
            if any(p.search(output) for p in patterns):
                return outcome
        return None

    def observe(self):
        """Return (outcome or None, output text)."""
        return None, ""

class UartObserver(Observer):
    """Send a stimulus on the target console (not the UARTBone port) and read its answer."""
    def __init__(self, port, baudrate=115200, send=None, **kwargs):
        super().__init__(**kwargs)
        self.port     = port
        self.baudrate = baudrate
        self.send     = send
        self.serial   = None

    def open(self):
        import serial
        self.serial = serial.Serial(self.port, self.baudrate, timeout=0.05)

    def close(self):
        if self.serial is not None:
            self.serial.close()

    def observe(self):
        self.serial.reset_input_buffer()
        if self.send:
            self.serial.write(self.send.encode())
        output = ""
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            output += self.serial.read(256).decode(errors="replace")
            outcome = self.classify(output)
            if outcome is not None:
                return outcome, output
        return None, output

class CommandObserver(Observer):
    """Run a command (e.g. over ssh on a Linux target) and classify its output."""
    def __init__(self, command, **kwargs):
        super().__init__(**kwargs)
        self.command = command

    def observe(self):
        try:
            r = subprocess.run(shlex.split(self.command), capture_output=True, text=True, timeout=self.timeout)
            output = r.stdout + r.stderr
        except subprocess.TimeoutExpired as e:
            output = e.stdout or ""
            if isinstance(output, bytes):
                output = output.decode(errors="replace")
            return None, output
        return self.classify(output), output

def make_observer(target):
    target = dict(target)
    for key in ["reset", "reset_delay", "settle"]:
        target.pop(key, None)
    common = {k: target.pop(k) for k in ["success", "failure", "crash", "timeout"] if k in target}
    if "uart" in target:
        observer = UartObserver(target.pop("uart"), target.pop("baudrate", 115200), target.pop("send", None), **common)
    elif "command" in target:
        observer = CommandObserver(target.pop("command"), **common)
    else:
        observer = Observer(**common)
    if target:
        raise ValueError(f"Unknown target field(s): {', '.join(target)}.")
    return observer

# Results ------------------------------------------------------------------------------------------

FIELDS = ["run", "repetition", "params", "outcome", "injected", "hit_count", "fault_count",
    "hit_timestamp", "capture_before", "capture_after", "duration_s", "output"]

class ResultWriter:
    """Write one row per run, flushed immediately (CSV or JSON lines, from the file extension)."""
    def __init__(self, path):
        self.path = path
        self.f    = open(path, "w", newline="")
        self.json = path.endswith(".json") or path.endswith(".jsonl")
        if not self.json:
            self.csv = csv.DictWriter(self.f, FIELDS)
            self.csv.writeheader()

    def write(self, row):
        if self.json:
            self.f.write(json.dumps(row) + "\n")
        else:
            row = dict(row, params=json.dumps(row["params"]), output=row["output"].replace("\r", "").replace("\n", "\\n"))
            self.csv.writerow(row)
        self.f.flush()

    def close(self):
        self.f.close()

# Runner -------------------------------------------------------------------------------------------

class CampaignRunner:
    def __init__(self, client, campaign, observer=None, writer=None, log=print):
        self.client   = client
        self.campaign = campaign
        self.observer = observer or make_observer(campaign.target)
        self.writer   = writer
        self.log      = log
        self.summary  = {}

    def run_one(self, index, params, repetition, triggers):
        target = self.campaign.target
        start  = time.time()
        if target.get("reset", False):
            self.client.reset_target(target.get("reset_delay", 0.5))
        seed = None if self.campaign.seed is None else int(self.campaign.seed) + index
        self.client.inject(triggers, group=self.campaign.group, seed=seed)
        if target.get("settle"):
            time.sleep(target["settle"])
        outcome, output = self.observer.observe()
        status = self.client.status()
        self.client.disarm()

        injected = status["fault_count"] > 0
        if outcome is None:
            if isinstance(self.observer, (UartObserver, CommandObserver)):
                outcome = TIMEOUT
            else:
                outcome = INJECTED if injected else NOT_INJECTED
        elif outcome == NO_EFFECT and not injected:
            outcome = NOT_INJECTED

        width = (self.client.layout.data_width(self.campaign.group) + 3)//4
        return {
            "run"            : index,
            "repetition"     : repetition,
            "params"         : params,
            "outcome"        : outcome,
            "injected"       : injected,
            "hit_count"      : status["hit_count"],
            "fault_count"    : status["fault_count"],
            "hit_timestamp"  : status["hit_timestamp"],
            "capture_before" : f"0x{status['capture_before']:0{width}x}",
            "capture_after"  : f"0x{status['capture_after']:0{width}x}",
            "duration_s"     : round(time.time() - start, 4),
            "output"         : output[-500:],
        }

    def run(self):
        total = len(self.campaign)
        self.observer.open()
        try:
            for index, params, repetition, triggers in self.campaign.runs():
                row = self.run_one(index, params, repetition, triggers)
                self.summary[row["outcome"]] = self.summary.get(row["outcome"], 0) + 1
                if self.writer is not None:
                    self.writer.write(row)
                if self.log:
                    self.log(f"[{index + 1}/{total}] {params or ''} -> {row['outcome']}"
                        + ("" if row["injected"] else " (no fault injected)"))
        finally:
            self.observer.close()
            if self.writer is not None:
                self.writer.close()
        return self.summary
