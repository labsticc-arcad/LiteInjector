#!/usr/bin/env python3

# Copyright (c) 2020 Antmicro <www.antmicro.com>
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

"""LiteInjector command line client.

    liteinjector_cli info                              # core capabilities
    liteinjector_cli list                              # probed signals
    liteinjector_cli run --when ibus_adr=0x37A --offset 1 --fault bit-value:ibus_dat_r=0x00050C63
    liteinjector_cli status | wait | disarm
    liteinjector_cli campaign campaign.toml            # sweeps, repetitions, observation, report

The v1 syntax (liteinjector_cli -v SIGNAL VALUE ID -bv SIGNAL VALUE ID ...) is still accepted.
"""

import os
import ast
import sys
import json
import argparse

from liteinjector.software.layout import Layout
from liteinjector.software.model import Trigger, Fault, LEGACY_FAULT_MODELS, _bits
from liteinjector.software.encoder import encode, FAULT_ENCODERS
from liteinjector.software.campaign import Campaign, CampaignRunner, ResultWriter, load_file

EXIT_OK      = 0
EXIT_ERROR   = 1
EXIT_TIMEOUT = 2

# Helpers ------------------------------------------------------------------------------------------

def load_layout(args):
    if not os.path.exists(args.csv):
        raise FileNotFoundError(f"{args.csv} not found. It is written by LiteInjector during the SoC build "
            "(csr_csv argument of LiteInjector), set it with --csv.")
    return Layout.from_csv(args.csv)

def connect(args):
    from liteinjector.software.client import LiteInjectorClient
    return LiteInjectorClient(host=args.host, port=args.port, csr_csv=args.csr_csv, config_csv=args.csv,
        debug=args.debug).open()

def print_entries(triggers, layout, group):
    width = (layout.data_width(group) + 3)//4
    for i, trigger in enumerate(triggers):
        entry = encode(trigger, layout, group)
        print(f"Trigger {i}: {trigger.describe()}")
        for name, value in entry._asdict().items():
            print(f"  {name:12s} 0x{value:0{width}x}" if name not in ("offset", "duration", "flags") else f"  {name:12s} {value}")

def print_status(status, as_json):
    if as_json:
        print(json.dumps(status))
        return
    for k, v in status.items():
        print(f"{k:15s} {hex(v) if k.startswith('capture') else v}")

def unescape(text):
    return text.encode().decode("unicode_escape") if text else text

# Commands -----------------------------------------------------------------------------------------

def cmd_info(args):
    layout = load_layout(args)
    info = dict(layout.config)
    info["groups"] = {g: layout.data_width(g) for g in sorted(layout.groups)}
    info["fault_models"] = sorted(FAULT_ENCODERS) if layout.with_lfsr else sorted(m for m in FAULT_ENCODERS if m != "bit-flip-random")
    if args.json:
        print(json.dumps(info))
    else:
        for k, v in info.items():
            print(f"{k:15s} {v}")
    return EXIT_OK

def cmd_list(args):
    layout = load_layout(args)
    for name, width in layout.signals(args.group):
        start, _ = layout.fields[(args.group, name)]
        print(name if args.names_only else f"{name:40s} {width:3d} bits  [{start + width - 1}:{start}]")
    return EXIT_OK

def triggers_from_args(args):
    if args.file:
        d = load_file(args.file)
        campaign = Campaign.from_dict(d)
        if campaign.sweep or campaign.repeat != 1:
            raise ValueError("'run' executes a single injection, use 'campaign' for sweeps and repetitions.")
        return list(next(campaign.runs())[3])
    when = {}
    for spec in args.when or []:
        if "=" not in spec:
            raise ValueError(f"Invalid --when '{spec}', expected SIGNAL=VALUE.")
        k, v = spec.split("=", 1)
        when[k] = v
    def edges(specs):
        out = {}
        for spec in specs or []:
            name, _, bits = spec.partition(":")
            out[name] = _bits(bits) if bits else None
        return out
    trigger = Trigger(when=when, rising=edges(args.rise), falling=edges(args.fall),
        offset=args.offset, duration=args.duration, faults=[Fault.parse(f) for f in args.fault or []])
    return [trigger]

def inject(args, triggers):
    layout = load_layout(args)
    for trigger in triggers: # Validate everything before touching the hardware.
        encode(trigger, layout, args.group)
    if args.dry_run:
        print_entries(triggers, layout, args.group)
        return EXIT_OK
    with connect(args) as client:
        client.inject(triggers, group=args.group, seed=args.seed)
        for i, trigger in enumerate(triggers):
            print(f"Trigger {i}: {trigger.describe()}")
        print("Injector armed.")
        if args.wait is None:
            return EXIT_OK
        done = client.wait(args.wait)
        print_status(client.status(), args.json)
        return EXIT_OK if done else EXIT_TIMEOUT

def cmd_run(args):
    return inject(args, triggers_from_args(args))

def cmd_status(args):
    with connect(args) as client:
        print_status(client.status(), args.json)
    return EXIT_OK

def cmd_wait(args):
    with connect(args) as client:
        done = client.wait(args.timeout)
        print_status(client.status(), args.json)
    return EXIT_OK if done else EXIT_TIMEOUT

def cmd_disarm(args):
    with connect(args) as client:
        client.clear()
    print("Injector disarmed, pending triggers cleared.")
    return EXIT_OK

def cmd_campaign(args):
    campaign = Campaign.from_file(args.file)
    if args.send is not None:
        campaign.target["send"] = unescape(args.send)
    for key in ["host", "port", "csr_csv", "csv"]:
        value = campaign.connection.get("config_csv" if key == "csv" else key)
        if value is not None and getattr(args, key) == DEFAULTS[key]:
            setattr(args, key, value)
    layout = load_layout(args)
    campaign.check(layout)
    print(f"Campaign '{campaign.name}': {len(campaign)} run(s).")
    if args.dry_run:
        for index, params, repetition, triggers in campaign.runs():
            if repetition == 0:
                print(f"--- run {index} {params}")
                print_entries(triggers, layout, campaign.group)
        return EXIT_OK
    output = args.output or campaign.output or f"{campaign.name}_results.csv"
    with connect(args) as client:
        runner = CampaignRunner(client, campaign, writer=ResultWriter(output))
        summary = runner.run()
    print(f"Results written to {output}")
    for outcome, count in sorted(summary.items()):
        print(f"  {outcome:13s} {count}")
    return EXIT_OK

# Legacy (v1) command line -------------------------------------------------------------------------

def parse_legacy_bits(text):
    text = text.strip()
    if text.startswith(("[", "{", "(")):
        value = ast.literal_eval(text)
        return sorted(int(b) for b in value) or None
    return _bits(text)

def legacy_triggers(args):
    steps = {}
    def step(i):
        return steps.setdefault(int(i), Trigger())
    for signal, value, i in args.value_trigger or []:
        step(i).when[signal] = value
    for signal, location, i in args.rising_edge or []:
        bits = step(i).rising.get(signal) or []
        step(i).rising[signal] = bits + (parse_legacy_bits(location) or [])
    for signal, location, i in args.falling_edge or []:
        bits = step(i).falling.get(signal) or []
        step(i).falling[signal] = bits + (parse_legacy_bits(location) or [])
    for value, i in args.offset or []:
        step(i).offset = int(value, 0)
    for number, option in [(1, "bit_set"), (2, "bit_reset"), (3, "bit_flip"), (4, "bit_flip_random"), (5, "bit_value")]:
        for signal, arg, i in getattr(args, option) or []:
            model = LEGACY_FAULT_MODELS[number]
            if model == "bit-value":
                step(i).faults.append(Fault(model, signal, value=arg))
            else:
                step(i).faults.append(Fault(model, signal, parse_legacy_bits(arg)))
    return [steps[i] for i in sorted(steps)]

def legacy_parser():
    parser = argparse.ArgumentParser(prog="liteinjector_cli", description="LiteInjector client (v1 syntax).")
    parser.add_argument("-r",   "--rising-edge",     action="append", nargs=3, metavar=("SIGNAL", "LOCATION", "ID"))
    parser.add_argument("-f",   "--falling-edge",    action="append", nargs=3, metavar=("SIGNAL", "LOCATION", "ID"))
    parser.add_argument("-v",   "--value-trigger",   action="append", nargs=3, metavar=("SIGNAL", "VALUE", "ID"))
    parser.add_argument("-o",   "--offset",          action="append", nargs=2, metavar=("VALUE", "ID"))
    parser.add_argument("-bs",  "--bit-set",         action="append", nargs=3, metavar=("SIGNAL", "LOCATION", "ID"))
    parser.add_argument("-br",  "--bit-reset",       action="append", nargs=3, metavar=("SIGNAL", "LOCATION", "ID"))
    parser.add_argument("-bf",  "--bit-flip",        action="append", nargs=3, metavar=("SIGNAL", "LOCATION", "ID"))
    parser.add_argument("-bfr", "--bit-flip-random", action="append", nargs=3, metavar=("SIGNAL", "LOCATION", "ID"))
    parser.add_argument("-bv",  "--bit-value",       action="append", nargs=3, metavar=("SIGNAL", "VALUE", "ID"))
    parser.add_argument("-l",   "--list",            action="store_true")
    add_connection_args(parser)
    parser.add_argument("--group", default=0, type=int)
    return parser

def legacy_main(argv):
    args = legacy_parser().parse_args(argv)
    args.dry_run, args.wait, args.seed, args.json = False, None, None, False
    if args.list:
        args.names_only = True
        return cmd_list(args)
    triggers = legacy_triggers(args)
    if not triggers:
        raise ValueError("You have not added any triggers!")
    return inject(args, triggers)

# Main ---------------------------------------------------------------------------------------------

DEFAULTS = {"host": "localhost", "port": 1234, "csr_csv": "csr.csv", "csv": "injector.csv"}

def add_connection_args(parser):
    parser.add_argument("--host",    default=DEFAULTS["host"],    help="litex_server host.")
    parser.add_argument("--port",    default=DEFAULTS["port"],    type=int, help="litex_server port.")
    parser.add_argument("--csr-csv", default=DEFAULTS["csr_csv"], help="SoC CSR map (--csr-csv of the SoC build).")
    parser.add_argument("--csv",     default=DEFAULTS["csv"],     help="LiteInjector configuration CSV.")
    parser.add_argument("--debug",   action="store_true",         help="Print the triggers written to the core.")

def build_parser():
    parser = argparse.ArgumentParser(prog="liteinjector_cli", description="LiteInjector client.",
        epilog="The v1 syntax (-v/-r/-f/-o/-bs/-br/-bf/-bfr/-bv) is still accepted.")
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name, func, help):
        p = sub.add_parser(name, help=help)
        add_connection_args(p)
        p.set_defaults(func=func)
        return p

    p = command("info", cmd_info, "Show the core capabilities.")
    p.add_argument("--json", action="store_true")

    p = command("list", cmd_list, "List the probed signals.")
    p.add_argument("--group", default=0, type=int)
    p.add_argument("--names-only", action="store_true")

    p = command("run", cmd_run, "Configure one injection (one or several chained triggers) and arm.")
    p.add_argument("file", nargs="?", help="Campaign file whose steps form the injection (no sweep).")
    p.add_argument("--when",     action="append", metavar="SIGNAL=VALUE", help="Value condition (0x3x patterns allowed).")
    p.add_argument("--rise",     action="append", metavar="SIGNAL[:BITS]", help="Rising edge condition.")
    p.add_argument("--fall",     action="append", metavar="SIGNAL[:BITS]", help="Falling edge condition.")
    p.add_argument("--fault",    action="append", metavar="SPEC",
        help="MODEL:SIGNAL[:BITS] or bit-value:SIGNAL=VALUE, models: " + ", ".join(sorted(FAULT_ENCODERS)) + ".")
    p.add_argument("--offset",   default=0, type=int, help="Cycles between the condition and the fault.")
    p.add_argument("--duration", default=1, type=int, help="Fault duration in cycles.")
    p.add_argument("--group",    default=0, type=int)
    p.add_argument("--seed",     default=None, type=lambda x: int(x, 0), help="LFSR seed for bit-flip-random.")
    p.add_argument("--wait",     default=None, type=float, metavar="SECONDS", help="Wait for the fault and print the status.")
    p.add_argument("--dry-run",  action="store_true", help="Print the encoded triggers without connecting.")
    p.add_argument("--json",     action="store_true")

    p = command("status", cmd_status, "Show the injector status.")
    p.add_argument("--json", action="store_true")

    p = command("wait", cmd_wait, "Wait until every trigger has fired.")
    p.add_argument("--timeout", default=None, type=float)
    p.add_argument("--json", action="store_true")

    command("disarm", cmd_disarm, "Disarm the injector and clear the pending triggers.")

    p = command("campaign", cmd_campaign, "Run an injection campaign described in a TOML/JSON file.")
    p.add_argument("file")
    p.add_argument("--output",  default=None, help="Results file (.csv or .json), overrides the campaign file.")
    p.add_argument("--send",    default=None, help="Override the stimulus sent to the target (\\n escapes allowed).")
    p.add_argument("--dry-run", action="store_true", help="Check and print every run without connecting.")
    return parser

COMMANDS = {"info", "list", "run", "status", "wait", "disarm", "campaign"}

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv and argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
            return legacy_main(argv)
        args = build_parser().parse_args(argv)
        return args.func(args)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR

if __name__ == "__main__":
    sys.exit(main())
