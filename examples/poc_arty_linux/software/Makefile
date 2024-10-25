CC      := riscv32-unknown-elf-gcc

# Target file name
TARGET  := poc.elf

# Source files
SRC     := main.c

# Compiler options
ARCH    := rv32i        # Set to rv32i, rv32if, rv32id, etc.
ABI     := ilp32        # Set to ilp32, ilp32f, ilp32d, etc.
CFLAGS  := -march=$(ARCH) -mabi=$(ABI) -O2 -Wall -Wextra
LDFLAGS := -march=$(ARCH) -mabi=$(ABI)

# Build rules
.PHONY: all clean

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -o $(TARGET) $(SRC) $(LDFLAGS)

clean:
	rm -f $(TARGET)
