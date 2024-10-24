// This file is Copyright (c) 2020 Florent Kermarrec <florent@enjoy-digital.fr>
// License: BSD

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <irq.h>
#include <libbase/uart.h>
#include <libbase/console.h>
#include <generated/csr.h>
#include <generated/mem.h>

#include "pmp.h"
#include "ControlRegisterStatus.h"

#define NAPOT_SIZE 128
#define PROTECTED_ARRAY_LENGTH 32

/* declaration region memory analysis in write */
volatile uint32_t protected_write[PROTECTED_ARRAY_LENGTH] __attribute__((aligned(NAPOT_SIZE)));

void test_writing (void);

/**
 * @brief Configure PMP read-Only
 * Lock and mode NAPOT
 */
struct pmp_config configR = {
	.L = PMP_LOCKED, /* LOCKED*/
	.A = PMP_NAPOT , /* Naturally-aligned power of two */
	.X = 0,
	.W = 0,
	.R = 1,
};

void test_writing (void) {

	printf("Press a key to continue...\n");

	getchar();

	/* PMP addresses are aligned on 4 bytes */
	size_t protected_addrw = ((size_t) &protected_write) >> 2;

	/* Write to the memory we are going to protect access to */
	protected_write[0] = 0xa;
	
	/* Clear the bit corresponding with alignment */
	protected_addrw &= ~(NAPOT_SIZE >> 3);

	/* Set the bits up to the alignment bit */
	protected_addrw |= ((NAPOT_SIZE >> 3) - 1);

	printf("\nTrying to write to a read-only memory area\n");

	/* Led 1 during 1 second */
	leds_out_write(1);
	busy_wait(1000);		

	/* pmp0cfg configure in read-only, addressing mode NAPOT */
	pmp_set_region(0, configR, protected_addrw);	

	__asm__ volatile ("nop");
	__asm__ volatile ("nop");
	__asm__ volatile ("nop");

	/* Attempt to write to protected_global. 
	 * This should generate a store access error exception a store access error exception. */
	protected_write[0] = 0xc;
	
	__asm__ volatile ("nop");
	__asm__ volatile ("nop");
	__asm__ volatile ("nop");


	/* check of the modified memory */
	if (protected_write[0] != 0xa){
		printf("Modified ! Incorrect PMP configuration\n");
	}
	else{
		printf("No writing, the memory area is well protected only-read\n");
	}

	__asm__ volatile ("nop");
	__asm__ volatile ("nop");
	__asm__ volatile ("nop");

	leds_out_write(3);

	printf("DONE\n");

}

/// @brief Sets the PMP zero to read-only and attempts to write to the protected memory area.
/// @param  void
/// @return int protected_global[0]
int main (void){

	#ifdef CONFIG_CPU_HAS_INTERRUPT
		irq_setmask(0);
		irq_setie(1);
	#endif

	#ifdef CSR_UART_BASE
		uart_init();
	#endif

	printf("\n");
	printf("\e[1m    ______                           __           ____  __  _______   \e[0m\n");	
	printf("\e[1m   / ____/  ______ _____ ___  ____  / /__        / __ \\/  |/  / __ \\     \e[0m\n");
	printf("\e[1m  / __/ | |/_/ __ `/ __ `__ \\/ __ \\/ / _ \\______/ /_/ / /|_/ / /_/ /     \e[0m\n");
	printf("\e[1m / /____>  </ /_/ / / / / / / /_/ / /  __/_____/ ____/ /  / / ____/       \e[0m\n");
	printf("\e[1m/_____/_/|_|\\__,_/_/ /_/ /_/ .___/_/\\___/     /_/   /_/  /_/_/              \e[0m\n");
	printf("\e[1m                          /_/                                            \e[0m\n");
	printf("\n");
	printf(" (c) Copyright 2023 Kévin.Q\n");
	printf("\n"); 

    test_writing();

	return 0;
	
}
