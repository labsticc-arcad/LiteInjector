#!/usr/bin/env python3

# Copyright (c) 2020 Antmicro <www.antmicro.com>
# Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
# Copyright (c) 2023 Adam Henault <contact@adamhlt.com>
# SPDX-License-Identifier: BSD-2-Clause

"""LiteInjector command line client.

    liteinjector_cli info                              # core capabilities
    liteinjector_cli list                              # probed signals
    liteinjector_cli run --when ibus_adr=0x37A --offset 1 --fault bit-value:ibus_dat_r=0x00050C63
    liteinjector_cli run --when a=1 --fault bit-flip:b:0 --then --when a=2 --fault bit-set:b:7   # chained faults
    liteinjector_cli run attack1.toml attack2.toml --repeat 10 --wait 5 --history
    liteinjector_cli status | wait | disarm | history
    liteinjector_cli shell                             # interactive session, keeps the connection open
    liteinjector_cli campaign campaign.toml            # sweeps, repetitions, observation, report

The v1 syntax (liteinjector_cli -v SIGNAL VALUE ID -bv SIGNAL VALUE ID ...) is still accepted.
"""

import os
import cmd
import ast
import sys
import json
import shlex
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
        if k in ("loaded", "history"):
            continue
        print(f"{k:15s} {hex(v) if k.startswith('capture') else v}")
    if status.get("loaded") is not None: # Progress of a chained sequence.
        print(f"{'sequence':15s} {status['fault_count']}/{status['loaded']} trigger(s) fired")

def print_history(events, width, fault_count=None):
    """Faults of the sequence, one line each (cycle since arming, data before/after the fault)."""
    digits = (width + 3)//4
    print(f"Fault history ({len(events)} fault(s)):")
    previous = None
    for event in events:
        delta = "" if previous is None else f"+{event['timestamp'] - previous}"
        previous = event["timestamp"]
        print(f"  #{event['index']:<3d} cycle {event['timestamp']:<10d} {delta:<8s}"
            f" before 0x{event['before']:0{digits}x}  after 0x{event['after']:0{digits}x}")
    if fault_count is not None and fault_count > len(events):
        print(f"  ({fault_count - len(events)} more fault(s) not recorded, the history holds one fault per queue slot)")

def report(client, group, as_json, with_history):
    """Print the status of a finished (or running) sequence, and optionally its fault history."""
    status  = client.status()
    history = client.history() if with_history else None
    if as_json:
        print(json.dumps(status if history is None else dict(status, history=history)))
        return
    print_status(status, False)
    if history is not None:
        print_history(history, client.layout.data_width(group), status["fault_count"])

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

# Trigger options ----------------------------------------------------------------------------------

THEN = "--then" # Separates the triggers of a chained injection on the command line.

class TriggerParser(argparse.ArgumentParser):
    """Parser of one trigger. Errors are raised, so that a shell session survives a typo."""
    def error(self, message):
        raise ValueError(f"{message} (a trigger accepts --when, --rise, --fall, --fault, --offset, --duration)")

def add_trigger_args(parser):
    parser.add_argument("--when",     action="append", metavar="SIGNAL=VALUE", help="Value condition (0x3x patterns allowed).")
    parser.add_argument("--rise",     action="append", metavar="SIGNAL[:BITS]", help="Rising edge condition.")
    parser.add_argument("--fall",     action="append", metavar="SIGNAL[:BITS]", help="Falling edge condition.")
    parser.add_argument("--fault",    action="append", metavar="SPEC",
        help="MODEL:SIGNAL[:BITS] or bit-value:SIGNAL=VALUE, models: " + ", ".join(sorted(FAULT_ENCODERS)) + ".")
    parser.add_argument("--offset",   default=0, type=int, help="Cycles between the condition and the fault.")
    parser.add_argument("--duration", default=1, type=int, help="Fault duration in cycles.")

def trigger_from_namespace(args):
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
    return Trigger(when=when, rising=edges(args.rise), falling=edges(args.fall),
        offset=args.offset, duration=args.duration, faults=[Fault.parse(f) for f in args.fault or []])

def parse_chain(tokens, extra=None):
    """Triggers described by `tokens`, separated by --then: [Trigger, ...].

    Tokens that are not trigger options are an error, unless `extra` is a list: they are then
    appended to it (options of the whole injection, such as --wait, written after the last trigger).
    """
    segments = [[]]
    for token in tokens:
        if token == THEN:
            segments.append([])
        else:
            segments[-1].append(token)
    triggers = []
    for i, segment in enumerate(segments):
        if not segment:
            raise ValueError(f"Empty trigger {i} (check the position of {THEN}).")
        parser = TriggerParser(prog=f"trigger {i}", add_help=False, allow_abbrev=False)
        add_trigger_args(parser)
        if extra is None:
            namespace = parser.parse_args(segment)
        else:
            namespace, rest = parser.parse_known_args(segment)
            extra.extend(rest)
        triggers.append(trigger_from_namespace(namespace))
    return triggers

def triggers_from_file(path):
    campaign = Campaign.from_dict(load_file(path))
    if campaign.sweep or campaign.repeat != 1:
        raise ValueError("'run' executes a single injection, use 'campaign' for sweeps and repetitions.")
    return list(next(campaign.runs())[3])

def triggers_from_args(args):
    chained = list(getattr(args, "then", None) or [])
    if args.files:
        if args.when or args.rise or args.fall or args.fault or chained:
            raise ValueError("Give either campaign file(s) or trigger options, not both.")
        triggers = []
        for path in args.files: # Several files form one longer sequence, in the order given.
            triggers.extend(triggers_from_file(path))
        return triggers
    return [trigger_from_namespace(args)] + chained

# Injection ----------------------------------------------------------------------------------------

def inject(args, triggers):
    layout  = load_layout(args)
    repeat  = getattr(args, "repeat", 1)
    history = getattr(args, "history", False)
    for trigger in triggers: # Validate everything before touching the hardware.
        encode(trigger, layout, args.group)
    if repeat < 1:
        raise ValueError("--repeat must be at least 1.")
    if (repeat > 1 or history) and args.wait is None:
        raise ValueError("--repeat and --history need --wait SECONDS, to know when the sequence is over.")
    if history and not layout.with_history:
        raise ValueError("This core was built without fault history (with_history=False).")
    if args.dry_run:
        print_entries(triggers, layout, args.group)
        if repeat > 1:
            print(f"The sequence would be run {repeat} times.")
        return EXIT_OK
    with connect(args) as client:
        code = EXIT_OK
        for i in range(repeat):
            seed = None if args.seed is None else args.seed + i # A new random sequence at each repetition.
            client.inject(triggers, group=args.group, seed=seed)
            if repeat > 1:
                print(f"--- Repetition {i + 1}/{repeat}")
            if i == 0:
                for n, trigger in enumerate(triggers):
                    print(f"Trigger {n}: {trigger.describe()}")
            print("Injector armed.")
            if args.wait is None:
                return EXIT_OK
            if not client.wait(args.wait):
                code = EXIT_TIMEOUT
            report(client, args.group, args.json, history)
        return code

def cmd_run(args):
    return inject(args, triggers_from_args(args))

def cmd_history(args):
    layout = load_layout(args)
    if not layout.with_history:
        raise ValueError("This core was built without fault history (with_history=False).")
    with connect(args) as client:
        report(client, args.group, args.json, True)
    return EXIT_OK

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

# Interactive shell --------------------------------------------------------------------------------

class InjectorShell(cmd.Cmd):
    """Build a sequence of triggers step by step, arm it and look at the result.

    The connection stays open between the commands. Without a client (--offline) triggers can be
    written and checked but not armed.
    """
    intro  = "LiteInjector shell. Type 'help' for the commands, 'exit' to leave."
    prompt = "liteinjector> "

    def __init__(self, layout, client=None, group=0, seed=None):
        super().__init__()
        self.layout  = layout
        self.client  = client
        self.group   = group
        self.seed    = seed
        self.pending = [] # Triggers of the sequence being built, sent to the core by 'arm'.

    def onecmd(self, line):
        try:
            return super().onecmd(line)
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            print(f"Error: {e}")
        except KeyboardInterrupt:
            print("Interrupted.")
        return False

    def emptyline(self):
        pass # Do not repeat the previous command.

    def _client(self):
        if self.client is None:
            raise RuntimeError("Not connected (offline shell), restart without --offline.")
        return self.client

    # Sequence -------------------------------------------------------------------------------------

    def do_add(self, arg):
        """add TRIGGER [--then TRIGGER ...]   Append triggers to the sequence.
TRIGGER: --when SIGNAL=VALUE, --rise SIGNAL[:BITS], --fall SIGNAL[:BITS], --fault SPEC,
--offset N, --duration N. Example: add --when ibus_adr=0x37A --offset 1 --fault bit-flip:ibus_dat_r:3"""
        triggers = parse_chain(shlex.split(arg))
        for trigger in triggers:
            encode(trigger, self.layout, self.group) # Check before keeping any of them.
        first = len(self.pending)
        self.pending.extend(triggers)
        for i, trigger in enumerate(triggers):
            print(f"Trigger {first + i}: {trigger.describe()}")

    def do_load(self, arg):
        """load FILE...   Append the steps of campaign file(s) (without sweep) to the sequence."""
        paths = shlex.split(arg)
        if not paths:
            raise ValueError("Usage: load FILE...")
        triggers = []
        for path in paths:
            triggers.extend(triggers_from_file(path))
        for trigger in triggers:
            encode(trigger, self.layout, self.group)
        self.pending.extend(triggers)
        print(f"{len(triggers)} trigger(s) loaded, {len(self.pending)} in the sequence.")

    def do_show(self, arg):
        """show [-v]   Show the sequence (-v: encoded hardware entries)."""
        if not self.pending:
            print("The sequence is empty.")
        elif arg.strip() == "-v":
            print_entries(self.pending, self.layout, self.group)
        else:
            for i, trigger in enumerate(self.pending):
                print(f"Trigger {i}: {trigger.describe()}")

    def do_remove(self, arg):
        """remove N   Remove trigger N from the sequence."""
        try:
            index   = int(arg)
            trigger = self.pending.pop(index)
        except (ValueError, IndexError):
            raise ValueError(f"Usage: remove N, with N between 0 and {len(self.pending) - 1}.")
        print(f"Removed trigger {index}: {trigger.describe()}")

    def do_clear(self, arg):
        """clear   Empty the sequence, and the queue of the core when connected."""
        self.pending.clear()
        if self.client is not None:
            self.client.clear()
        print("Sequence cleared.")

    # Core -----------------------------------------------------------------------------------------

    def do_arm(self, arg):
        """arm   Load the sequence in the core and arm it."""
        if not self.pending:
            raise ValueError("The sequence is empty, use 'add' first.")
        self._client().inject(self.pending, group=self.group, seed=self.seed)
        print(f"Injector armed with {len(self.pending)} trigger(s).")

    def do_disarm(self, arg):
        """disarm   Disarm the core and clear its queue (the sequence is kept)."""
        self._client().clear()
        print("Injector disarmed, pending triggers cleared.")

    def do_wait(self, arg):
        """wait [SECONDS]   Wait until every trigger has fired, then show the status."""
        client = self._client()
        done = client.wait(float(arg) if arg.strip() else None)
        report(client, self.group, False, False)
        if not done:
            print("Timeout: some triggers did not fire.")

    def do_status(self, arg):
        """status   Show the status of the core."""
        report(self._client(), self.group, False, False)

    def do_history(self, arg):
        """history   Show the cycle and data of every fault of the sequence."""
        if not self.layout.with_history:
            raise ValueError("This core was built without fault history (with_history=False).")
        client = self._client()
        print_history(client.history(), self.layout.data_width(self.group), client.status()["fault_count"])

    # Settings -------------------------------------------------------------------------------------

    def do_group(self, arg):
        """group [N]   Show or select the probed signal group."""
        if arg.strip():
            group = int(arg)
            if group not in self.layout.groups:
                raise ValueError(f"Group {group} does not exist (groups: {sorted(self.layout.groups)}).")
            for trigger in self.pending:
                encode(trigger, self.layout, group)
            self.group = group
        print(f"Group {self.group} ({self.layout.data_width(self.group)} bits).")

    def do_seed(self, arg):
        """seed [N]   Show or set the seed of the random bit flip generator."""
        if arg.strip():
            self.seed = int(arg, 0)
        print(f"Seed: {self.seed if self.seed is not None else 'default'}.")

    def do_signals(self, arg):
        """signals   List the probed signals of the current group."""
        for name, width in self.layout.signals(self.group):
            print(f"{name:40s} {width:3d} bits")

    def do_exit(self, arg):
        """exit   Leave the shell."""
        return True

    do_quit = do_exit
    do_EOF  = do_exit

def cmd_shell(args):
    layout = load_layout(args)
    if args.group not in layout.groups:
        raise ValueError(f"Group {args.group} does not exist (groups: {sorted(layout.groups)}).")
    try:
        if args.offline:
            InjectorShell(layout, None, args.group, args.seed).cmdloop()
        else:
            with connect(args) as client:
                InjectorShell(layout, client, args.group, args.seed).cmdloop()
    except KeyboardInterrupt:
        print()
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
    args.repeat, args.history = 1, False
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
    p.add_argument("files", nargs="*", metavar="FILE",
        help="Campaign file(s) whose steps form the injection (no sweep), chained in the order given.")
    add_trigger_args(p)
    p.add_argument("--group",    default=0, type=int)
    p.add_argument("--seed",     default=None, type=lambda x: int(x, 0), help="LFSR seed for bit-flip-random.")
    p.add_argument("--wait",     default=None, type=float, metavar="SECONDS", help="Wait for the fault and print the status.")
    p.add_argument("--repeat",   default=1, type=int, metavar="N", help="Run the sequence N times (needs --wait).")
    p.add_argument("--history",  action="store_true", help="Print the cycle and data of every fault (needs --wait).")
    p.add_argument("--dry-run",  action="store_true", help="Print the encoded triggers without connecting.")
    p.add_argument("--json",     action="store_true")
    p.set_defaults(then=[])
    p.epilog = f"Chain triggers with {THEN}: run --when a=1 --fault bit-flip:b:0 {THEN} --when a=2 --fault bit-set:b:7"

    p = command("status", cmd_status, "Show the injector status.")
    p.add_argument("--json", action="store_true")

    p = command("wait", cmd_wait, "Wait until every trigger has fired.")
    p.add_argument("--timeout", default=None, type=float)
    p.add_argument("--json", action="store_true")

    command("disarm", cmd_disarm, "Disarm the injector and clear the pending triggers.")

    p = command("history", cmd_history, "Show the cycle and data of every fault of the last sequence.")
    p.add_argument("--group", default=0, type=int)
    p.add_argument("--json", action="store_true")

    p = command("shell", cmd_shell, "Interactive session: build, arm and inspect a sequence of faults.")
    p.add_argument("--group",   default=0, type=int)
    p.add_argument("--seed",    default=None, type=lambda x: int(x, 0), help="LFSR seed for bit-flip-random.")
    p.add_argument("--offline", action="store_true", help="Do not connect, only write and check triggers.")

    p = command("campaign", cmd_campaign, "Run an injection campaign described in a TOML/JSON file.")
    p.add_argument("file")
    p.add_argument("--output",  default=None, help="Results file (.csv or .json), overrides the campaign file.")
    p.add_argument("--send",    default=None, help="Override the stimulus sent to the target (\\n escapes allowed).")
    p.add_argument("--dry-run", action="store_true", help="Check and print every run without connecting.")
    return parser

COMMANDS = {"info", "list", "run", "status", "wait", "disarm", "history", "shell", "campaign"}

def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv and argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
            return legacy_main(argv)
        chained = []
        if argv and argv[0] == "run" and THEN in argv: # argparse cannot split on a repeated separator.
            i, extra = argv.index(THEN), []
            chained = parse_chain(argv[i + 1:], extra)
            argv = argv[:i] + extra # Options of the whole injection may follow the last trigger.
        args = build_parser().parse_args(argv)
        if chained:
            args.then = chained
        return args.func(args)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return EXIT_ERROR

if __name__ == "__main__":
    sys.exit(main())
