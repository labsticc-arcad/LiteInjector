=====================
Software Controller
=====================

The software controller drives the emulator from the host machine through :code:`litex_server`. It is organized in layers, from the hardware registers to the injection campaigns, so that each part can be used and tested on its own:

* :code:`layout` reads the configuration CSV written by LiteInjector during the SoC build (signals, groups, capabilities of the core).
* :code:`model` describes an injection: :code:`Trigger` (conditions, offset, duration) and :code:`Fault` (fault model, signal, bits or value).
* :code:`encoder` translates a trigger into the words of a hardware trigger entry. Every fault model is a small function registered in a table, a new fault model does not need any change of the hardware.
* :code:`driver` is the only module that accesses the CSRs of the core.
* :code:`client` is the Python API (connection, injection, status).
* :code:`campaign` runs campaigns: parameter sweeps, repetitions, observation of the target and results.

.. toctree::
   :maxdepth: 2
   :caption: Contents :

   cli.rst
   campaign.rst
   api.rst
