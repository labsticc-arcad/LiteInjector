BUILD_DIR?= ../build/digilent_basys3_platform

include $(BUILD_DIR)/software/include/generated/variables.mak
include common.mak

OBJECTS_Vex = start_Vexriscv.o trap_handler.o pmp.o main.o

# To change by ROM or RAM
LINKER = linker.ld

default: Vex

Vex: poc.bin

%.bin: %.elf
	$(OBJCOPY) -O binary $< $@
ifneq ($(OS),Windows_NT)
	chmod -x $@
endif

vpath %.a $(PACKAGES:%=../%)

poc.elf: $(OBJECTS_Vex)
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
-include $(OBJECTS_Vex:.o=.d)


VPATH = $(BIOS_DIRECTORY):$(BIOS_DIRECTORY)/cmds:$(CPU_DIRECTORY)


%.o: %.cpp
	$(compilexx)

%.o: %.c
	$(compile)

%.o: %.S
	$(assemble)

clean:
	$(RM) $(OBJECTS_CVA6) $(OBJECTS_Vex) poc.elf poc.bin .*~ *~

.PHONY: all clean
