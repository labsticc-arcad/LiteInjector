====================
Command line client
====================

:code:`liteinjector_cli` needs :code:`litex_server` to be running and two files produced by the SoC build: the CSR map (:code:`--csr-csv`, default :code:`csr.csv`) and the LiteInjector configuration (:code:`--csv`, default :code:`injector.csv`). The connection is set with :code:`--host` and :code:`--port`.

Commands
--------

.. code-block:: console

    $ liteinjector_cli info            # core version, data width, depth, offset/duration limits, fault models
    $ liteinjector_cli list            # probed signals with their width and position
    $ liteinjector_cli run ...         # configure one injection and arm the emulator
    $ liteinjector_cli status          # done, busy, hit and fault counters, timestamp, captured data
    $ liteinjector_cli wait --timeout 5
    $ liteinjector_cli disarm          # disarm and clear the pending triggers
    $ liteinjector_cli campaign campaign.toml

Signal names can be shortened as long as they stay unambiguous (:code:`ibus_dat_r` for :code:`main_basesoc_ibus_dat_r`).

One injection
-------------

.. code-block:: console

    $ liteinjector_cli run --when ibus_adr=0x0000037A --offset 1 --fault bit-value:ibus_dat_r=0x00050C63 --wait 5

* :code:`--when SIGNAL=VALUE`: value condition, :code:`x` digits are "don't care" (:code:`0x3x`, :code:`0b1x0`).
* :code:`--rise SIGNAL[:BITS]` and :code:`--fall SIGNAL[:BITS]`: edge conditions.
* :code:`--fault MODEL:SIGNAL[:BITS]` or :code:`--fault bit-value:SIGNAL=VALUE`, BITS is a list such as :code:`3`, :code:`0,2` or :code:`4-7` (all the bits of the signal when omitted). Several :code:`--fault` can be applied by the same trigger.
* :code:`--offset N`: cycles between the condition and the fault. :code:`--duration N`: number of faulted cycles.
* :code:`--wait SECONDS`: wait for the fault and print the status. :code:`--dry-run`: print the encoded trigger without connecting.

Fault models: :code:`bit-set`, :code:`bit-reset`, :code:`bit-flip`, :code:`bit-flip-random` (new random bits for every fault, :code:`--seed` sets the LFSR seed) and :code:`bit-value`.

Chained triggers (multi-fault attacks) are described with several :code:`[[step]]` in a file: :code:`liteinjector_cli run attack.toml`.

v1 syntax
---------

The previous syntax is still accepted, the commands of the proofs of concept work unchanged:

.. code-block:: console

    $ liteinjector_cli -v main_basesoc_ibus_adr 0x0000037A 0 -bv main_basesoc_ibus_dat_r 0x00050C63 0 -o 1 0

The triggers are now chained in the order of their ID, and a trigger can combine several fault models.
