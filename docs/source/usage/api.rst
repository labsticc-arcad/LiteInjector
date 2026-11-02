===========
Python API
===========

The same layers as the command line can be used from Python scripts:

.. code-block:: python

    from liteinjector.software import LiteInjectorClient, Trigger, Fault

    with LiteInjectorClient(csr_csv="csr.csv", config_csv="injector.csv") as inj:
        inj.inject([Trigger(when={"ibus_adr": "0x0000037A"}, offset=1,
                            faults=[Fault("bit-value", "ibus_dat_r", value="0x00050C63")])])
        inj.wait(timeout=5)
        print(inj.status())

A new fault model only needs an encoder function. The fault is applied by the hardware as :code:`((data & fault_and) | fault_or) ^ fault_xor`:

.. code-block:: python

    from liteinjector.software import fault_model

    @fault_model("stuck-at-0")
    def stuck_at_0(fault, layout, group, v):
        v.fault_and &= ~layout.bits_mask(fault.signal, fault.bits, group) & v.all_ones

Reference
---------

.. automodule:: liteinjector.software.model
   :members: Trigger, Fault

.. automodule:: liteinjector.software.client
   :members: LiteInjectorClient

.. automodule:: liteinjector.software.encoder
   :members: encode, fault_model

.. automodule:: liteinjector.software.campaign
   :members: Campaign, CampaignRunner

.. automodule:: liteinjector.software.driver.injector
   :members: LiteInjectorDriver
