============
Introduction
============

.. note::
    * OS : Ubuntu 20.04
    * FPGA Toolchain : Vivado 2019.1
    * LiteX Version : 2022.08
    * FPGA Board : Digilent Basys3 or Arty-A7 100T
    * Python 3.6 or higher

For the various proofs of concept we created and for the tests carried out on the emulator, we used several setups. We used 2 different FPGA boards:

* Digilient Basys3
* Digilent Arty-A7 100T

All the FPGA boards supported by LiteX are compatible with the emulator. We have chosen the Digilent Basys3 board as it is an inexpensive board and is often used in education. For the Digilent Arty-A7 board we used it to be able to run a Linux operating system. In order to run the operating system, a minimum amount of RAM is required, which is not available on the Basys3 card. Otherwise, it would have been possible to carry out all the proofs of concept with the Basys3 board.

For the connection between the FPGA board and the control software we used 2 methods: 

* UART
* Ethernet

All our proofs of concept use the UART protocol to control the emulator. The UART only requires 2 GPIOs, which means it can be integrated into any FPGA board, providing a simple but not very fast way of controlling the emulator. We also carried out tests using the Ethernet protocol to control the emulator. To do this, we used an Arty-A7 board that natively integrates an Ethernet port. However, you should be aware that there are other ways of controlling the emulator using other protocols.