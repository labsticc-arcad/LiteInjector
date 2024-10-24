[> Example PMP configure
----------------------

This firmware tests the configuration of a read-only PMP.

[> Build and Load over LiteX-Term
---------------------------------

To build a LiteX SoC for the Arty board (available in LiteX-Boards) and build the demo app for it, execute the following commands:

Since our app is small and for simplicity we'll just load it over serial here:
 `$ litex_term /dev/ttyUSBX --kernel=enter-the-path/exampe-pmp.bin`

You should see the minimal demo app running and should be able to interact with it:

    --============== Boot ==================--
    Booting from serial...
    Press Q or ESC to abort boot completely.
    sL5DdSMmkekro
    [LITEX-TERM] Received firmware download request from the device.
    [LITEX-TERM] Uploading litex/litex/soc/software/example-pmp/example-pmp.bin to 0x40000000 (5980 bytes)...
    [LITEX-TERM] Upload calibration... (inter-frame: 10.00us, length: 64)
    [LITEX-TERM] Upload complete (9.8KB/s).
    [LITEX-TERM] Booting the device.
    [LITEX-TERM] Done.
    Executing booted program at 0x40000000

    --============= Liftoff! ===============--

        ______                           __           ____  __  _______   
      / ____/  ______ _____ ___  ____  / /__        / __ \/  |/  / __ \     
      / __/ | |/_/ __ `/ __ `__ \/ __ \/ / _ \______/ /_/ / /|_/ / /_/ /     
    / /____>  </ /_/ / / / / / / /_/ / /  __/_____/ ____/ /  / / ____/       
    /_____/_/|_|\__,_/_/ /_/ /_/ .___/_/\___/     /_/   /_/  /_/_/              
                              /_/                                            

    (c) Copyright 2023 Kévin.Q

    --============== Status =================--

    Trying to write to a read-only memory area
    No writing, the memory area is well protected
    DONE