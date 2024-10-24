

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* convert config pmp to integer */
#define CONFIG_TO_INT(_config) (*((char *) &(_config)))

/*!
 * @brief Set of available PMP addressing modes
 * @param PMP_OFF -> Disable the PMP region
 * @param PMP_TOR -> Use Top-of-Range mode
 * @param PMP_NA4 -> Use naturally-aligned 4-byte region mode
 * @param PMP_NAPOT -> Use naturally-aligned power-of-two mode
 */
enum pmp_address_mode {
    /*! @brief Disable the PMP region */
    PMP_OFF   = 0,
    /*! @brief Use Top-of-Range mode */
    PMP_TOR   = 1,
    /*! @brief Use naturally-aligned 4-byte region mode */
    PMP_NA4   = 2,
    /*! @brief Use naturally-aligned power-of-two mode */
    PMP_NAPOT = 3
};

/*!
 * @brief Configuration for a PMP region
 * @param R -> Sets whether reads to the PMP region succeed
 * @param W -> Sets whether writes to the PMP region succeed
 * @param X -> Sets whether the PMP region is executable
 * @param PMP_UNLOCKED -> Sets whether the PMP region is unlocked
 * @param PMP_LOCKED -> Sets whether the PMP region is locked
 */
struct pmp_config {
    /*! @brief Sets whether reads to the PMP region succeed */
    unsigned int R : 1;
    /*! @brief Sets whether writes to the PMP region succeed */
    unsigned int W : 1;
    /*! @brief Sets whether the PMP region is executable */
    unsigned int X : 1;

    /*! @brief Sets the addressing mode of the PMP region */
    enum pmp_address_mode A : 2;

    int _pad : 2;

    /*! @brief Sets whether the PMP region is locked */
    enum pmp_locked {
        PMP_UNLOCKED = 0,
        PMP_LOCKED   = 1
    } L : 1;
};

/*!
 * @brief Configure a PMP region
 * @param region The PMP region to configure
 * @param config The desired configuration of the PMP region
 * @param address The desired address of the PMP region
 * @return void
 */
void pmp_set_region(   unsigned int region,
                       struct pmp_config config,
                       size_t address);

