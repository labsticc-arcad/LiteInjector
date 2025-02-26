================
Proof of Concept
================

In this section we will detail the 4 proofs of concept we have created. You can reproduce the PoCs using the files provided in the :code:`examples` folder in the package. For each proof of concept we will describe the SoC used and how the attack works. On these 4 PoCs we will attack the Wishbone data bus of the SoC, we will also see how to instrument Verilog code to attack external IPs and finally we will see an attack on an SoC using a Linux operating system.

.. toctree::
   :maxdepth: 2
   :caption: Contents :

   vexriscv_sw.rst
   pmp_sw.rst
   pmp_hw.rst
   linux.rst