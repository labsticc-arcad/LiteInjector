============
Introduction
============

What is fault emulation ?
-------------------------

Fault emulation, or deliberate fault injection, is a technique used in computer science and electronics to simulate errors or failures in a system or component. The two main purposes of this method are to test the reliability of a system in the face of abnormal conditions or failures and to test the resistance of a component or system to a fault injection attack.

Using specific techniques, such as electromagnetic noise injection, signal alteration or data modification, fault emulation creates situations where errors occur in a controlled manner. This allows developers and engineers to understand how a system behaves in the event of a failure and to take steps to improve its robustness.

In short, fault emulation is a technique for emulating controlled errors or failures in a system or component in order to assess its reliability and resistance to such situations.

Emulation or Simulation ?
-------------------------

In our case, when we talk about emulation, we're talking about deliberate fault injection on a hardware platform. Whereas with simulation, we test the design on a computer, the software simulates the behaviour of signals, components, etc. This means you can change the signal values at any time and see how the design behaves. Simulation gives you control over the component and allows you to inject faults anywhere, but it requires a lot of resources and can take a long time to run. Having an emulation platform means that we can run our tests directly on the hardware and speed up the injection campaign enormously. However, you need to define points of interest in advance to know where you want to inject faults. Once the points of interest have been identified, we instrument the design to be tested by adding injection points.

What is LiteX ?
---------------

LiteX is an open-source framework that facilitates the development of custom System-on-Chip (SoC) devices by offering a flexible and modular approach. It allows developers to design and create custom SoCs using predefined hardware and software components, providing a solid foundation for embedded system design.

LiteX uses the Python-based hardware description tool, Migen. This enables high-level languages to be used for hardware design. It supports several popular FPGA platforms, such as Xilinx, Intel, Lattice, and can be adapted to other custom hardware architectures. The framework also provides tools for configuring, generating and programming LiteX SoCs.

In short, LiteX is a powerful framework for developing custom systems-on-a-chip. Its modularity, flexibility, direct access to hardware components and integrated simulation make it an attractive choice for fault emulation in embedded systems. It offers developers a flexible and controllable environment for testing the resilience of their systems to errors and failures, which is essential for ensuring their reliability and safety.

Why LiteInjector ?
------------------

The LiteInjector project has been created to replace long or even impossible simulation campaigns. To test components implementing countermeasures, whether hardware or software, it is necessary to test their resistance to fault injection attacks. To test these components, we can either use simulation tools, but this becomes very time-consuming when it comes to testing large components or if we want to simulate a complete SoC to test the software part. That's why we use emulation, which runs directly on the hardware to speed up injection campaigns. The LiteInjector project was created with this in mind. LiteInjector is an emulator that enables faults to be injected precisely into any signal in the design to be tested, just like in a simulation. We chose to use LiteX so that we could easily create our SoCs and deploy a complete emulation environment very quickly. Finally, LiteInjector is based on the LiteScope tool developed by Enjoy Digital, which has saved us development time and allows the emulator to be integrated very easily into a LiteX design, as the LiteScope tool does.