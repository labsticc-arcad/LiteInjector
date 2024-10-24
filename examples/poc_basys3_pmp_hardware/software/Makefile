BUILD_DIR?= ../build/digilent_basys3_platform

include $(BUILD_DIR)/software/include/generated/variables.mak
include common.mak

OBJECTS_Vex   = start_Vexriscv.o trap_handler.o pmp.o main.o
OBJECTS_CVA6   = start_CVA6.o trap_handler.o pmp.o main.o

# To change by ROM or RAM
LINKER = linker.ld

CVA6: PMPTestWrite_CVA6.bin
Vex: PMPTestWrite_VexRiscv.bin

%.bin: %.elf
	$(OBJCOPY) -O binary $< $@
ifneq ($(OS),Windows_NT)
	chmod -x $@
endif

vpath %.a $(PACKAGES:%=../%)

PMPTestWrite_CVA6.elf: $(OBJECTS_CVA6)
	$(CC) $(LDFLAGS) -T $(LINKER) -N -o $@ \
		$(OBJECTS_CVA6) \
		$(PACKAGES:%=-L$(BUILD_DIR)/software/%) \
		-Wl,--whole-archive \
		-Wl,--gc-sections \
		-Wl,-Map,$@.map \
		$(LIBS:lib%=-l%)

PMPTestWrite_VexRiscv.elf: $(OBJECTS_Vex)
	$(CC) $(LDFLAGS) -T $(LINKER) -N -o $@ \
		$(OBJECTS_Vex) \
		$(PACKAGES:%=-L$(BUILD_DIR)/software/%) \
		-Wl,--whole-archive \
		-Wl,--gc-sections \
		-Wl,-Map,$@.map \
		$(LIBS:lib%=-l%)

ifneq ($(OS),Windows_NT)
	chmod -x $@
endif

# pull in dependency info for *existing* .o files
-include $(OBJECTS_CVA6:.o=.d)
-include $(OBJECTS_Vex:.o=.d)


#donut.o: CFLAGS   += -w

VPATH = $(BIOS_DIRECTORY):$(BIOS_DIRECTORY)/cmds:$(CPU_DIRECTORY)


%.o: %.cpp
	$(compilexx)

%.o: %.c
	$(compile)

%.o: %.S
	$(assemble)

clean:
	$(RM) $(OBJECTS_CVA6) $(OBJECTS_Vex) PMPTestWrite_CVA6.elf PMPTestWrite_VexRiscv.elf PMPTestWrite_CVA6.bin PMPTestWrite_VexRiscv.bin .*~ *~

.PHONY: all clean
