==========
Campaigns
==========

A campaign repeats an injection over a set of parameters, observes the behaviour of the target after every fault and writes one line of results per run. It is described in a TOML (Python 3.11+ or the :code:`tomli` package) or JSON file:

.. code-block:: toml

    [campaign]
    name   = "bios-unlock"
    repeat = 1                 # Runs for every combination of the sweep.
    seed   = 1                 # Optional LFSR seed (seed + run index), for bit-flip-random.
    output = "results.csv"     # .csv, or .json for JSON lines.

    [sweep]                    # Every combination is run, values replace {name} in the steps.
    bit    = "0..31"           # Inclusive range, "0..31:2" for a step, or a list.

    [[step]]                   # One trigger, several [[step]] are chained (multi-fault).
    when     = { ibus_adr = "0x0000037A" }
    offset   = 1
    duration = 1
    fault    = { model = "bit-flip", signal = "ibus_dat_r", bits = "{bit}" }

    [target]                   # Optional observation of the target.
    uart     = "/dev/ttyUSB1"  # Console of the target (not the UARTBone port).
    send     = "unlock aaaa\n" # Sent after arming the emulator.
    success  = "Access granted"
    failure  = "Access refused"
    crash    = ["panic", "trap"]
    timeout  = 2.0
    reset    = false           # Reset the SoC (ctrl_reset) before every run.

A :code:`command` (for instance a program started over :code:`ssh` on a Linux target) can replace :code:`uart`/:code:`send`. The optional :code:`[connection]` table sets :code:`host`, :code:`port`, :code:`csr_csv` and :code:`config_csv`.

.. code-block:: console

    $ liteinjector_cli campaign campaign.toml --dry-run   # check and print every run without hardware
    $ liteinjector_cli campaign campaign.toml

Every run is classified as :code:`success`, :code:`no-effect`, :code:`crash` or :code:`timeout` from the target output, or :code:`injected`/:code:`not-injected` without observation. A run where the emulator did not inject any fault is reported as :code:`not-injected`. Each line of results also holds the sweep parameters, the hit and fault counters, the cycle of the fault since arming, the faulted data before and after injection and the end of the target output.
