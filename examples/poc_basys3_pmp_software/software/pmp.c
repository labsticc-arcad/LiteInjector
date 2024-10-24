
#include "pmp.h"

/*!
 * @brief Configure a PMP region
 * @param region The PMP region to configure
 * @param config The desired configuration of the PMP region
 * @param address The desired address of the PMP region
 * @return void
 */
void pmp_set_region(   unsigned int region,
                       struct pmp_config config,
                       size_t address)
{
	switch(region) {
        case 0:
            __asm__("csrw pmpaddr0, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 1:
            __asm__("csrw pmpaddr1, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 2:
            __asm__("csrw pmpaddr2, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 3:
            __asm__("csrw pmpaddr3, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 4:
            __asm__("csrw pmpaddr4, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 5:
            __asm__("csrw pmpaddr5, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 6:
            __asm__("csrw pmpaddr6, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 7:
            __asm__("csrw pmpaddr7, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 8:
            __asm__("csrw pmpaddr8, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 9:
            __asm__("csrw pmpaddr9, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 10:
            __asm__("csrw pmpaddr10, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 11:
            __asm__("csrw pmpaddr11, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 12:
            __asm__("csrw pmpaddr12, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 13:
            __asm__("csrw pmpaddr13, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 14:
            __asm__("csrw pmpaddr14, %[addr]"
                    :: [addr] "r" (address) :);
            break;
        case 15:
            __asm__("csrw pmpaddr15, %[addr]"
                    :: [addr] "r" (address) :);
            break;
    }

        /* Mask to clear old pmpcfg */
       	size_t cfgmask = (0xFF << (8 * (region % 4)) );
    	size_t pmpcfg = (CONFIG_TO_INT(config) << (8 * (region % 4)) );
        
        switch(region / 4) {
        case 0:
            __asm__("csrc pmpcfg0, %[mask]"
                    :: [mask] "r" (cfgmask) :);

            __asm__("csrs pmpcfg0, %[cfg]"
                    :: [cfg] "r" (pmpcfg) :);
            break;
        case 1:
            __asm__("csrc pmpcfg1, %[mask]"
                    :: [mask] "r" (cfgmask) :);

            __asm__("csrs pmpcfg1, %[cfg]"
                    :: [cfg] "r" (pmpcfg) :);
            break;
        case 2:
            __asm__("csrc pmpcfg2, %[mask]"
                    :: [mask] "r" (cfgmask) :);

            __asm__("csrs pmpcfg2, %[cfg]"
                    :: [cfg] "r" (pmpcfg) :);
            break;
        case 3:
            __asm__("csrc pmpcfg3, %[mask]"
                    :: [mask] "r" (cfgmask) :);

            __asm__("csrs pmpcfg3, %[cfg]"
                    :: [cfg] "r" (pmpcfg) :);
            break;
        }
}