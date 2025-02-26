=============================================
LiteInjector : A fault emulator for LiteX SoC
=============================================

The goal of the LiteInjector project is to create a modular, open source fault emulator for Systems on Chip made with LiteX. LiteInjector is written in Migen (like LiteX) and is heavily parameterizable. It allows to inject fault in any Migen design, the emulateur support the multi fault, it has a advenced trigger system, compatible with most FPGA boards and integrate a software controller that allow to create custom script. This project was developed within the ARCAD team at the Lab-STICC research laboratory in Lorient, France.

Organization of this Document
-----------------------------

This documentation is split into multiple parts.

The :doc:`LiteInjector Overview <presentation/index>` section provides a detailed introduction to the LiteInjector emulator. This document is intended for users who want to understand why we created LiteInjector and why it is innovative.

The :doc:`LiteInjector Installation Guide <install/index>` is a detailed installation guide. We start with installing LiteX through to adding Liteinjector to the SoCs generated. We will also detail the use of the software controller and how to connect the emulator to the host machine. Finally, we provide a test on an example SoC to help you understand how to use LiteInjector.

The :doc:`LiteInjector Proof of Concept <poc/index>` section presents the various proofs of concept we have developed to test the emulator's capabilities. The proofs of concept try to approximate real-world cases. We also present a proof of concept that injects faults into a component that is not described in Migen. For each of the demonstrations we provide the files and instructions for doing them yourself.

The :doc:`LiteInjector Functional Testing <poc/index>` section is dedicated to the presentation of various tests carried out to validate the operation of the emulator's various components, principally the trigger system and the fault injector.

.. toctree::
   :maxdepth: 2
   :hidden:

   presentation/index.rst
   install/index.rst
   poc/index.rst