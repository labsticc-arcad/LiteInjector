
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define read_csr(reg) ({ unsigned long __tmp; \
	__asm__ volatile ("csrr %0, " #reg : "=r"(__tmp)); \
	__tmp; })

#define write_csr(reg, val) ({ \
	__asm__ volatile ("csrw " #reg ", %0" :: "r"(val)); \
})

#define set_csr(csr, rs) ({ \
	unsigned long rd; \
	__asm__ volatile ("csrrs %0, " #csr ", %1" : "=r"(rd) : "r"(rs)); \
	rd; \
})

#define clear_csr(csr, rs) ({ \
	unsigned long rd; \
	__asm__ volatile ("csrrc %0, " #csr ", %1" : "=r"(rd) : "r"(rs)); \
	rd; \
})

