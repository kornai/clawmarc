CC ?= cc
CFLAGS ?= -O2 -std=c99 -Wall -Wextra
LDFLAGS ?=
HOST_ARCH := $(shell uname -m)
ifneq ($(filter arm64 aarch64,$(HOST_ARCH)),)
CFLAGS += -mgeneral-regs-only
endif
ifeq ($(STATIC),1)
LDFLAGS += -static
endif
TOOLS = build/cxcc-verify build/cxcc-inspect build/cxcc-mint-text
REPO_ROOT ?= ../..
all: $(TOOLS)
build:
	mkdir -p build
build/cxcc-core: cxcc.c sha256.c tweetnacl.c sha256.h tweetnacl.h | build
	$(CC) $(CFLAGS) cxcc.c sha256.c tweetnacl.c $(LDFLAGS) -o $@
build/cxcc-verify: build/cxcc-core
	cp $< $@
build/cxcc-inspect: build/cxcc-core
	cp $< $@
build/cxcc-mint-text: build/cxcc-core
	cp $< $@
test: all
	@for card in $(REPO_ROOT)/cards/reference_dropofwater.cxcc $(REPO_ROOT)/cards/reference_geminiexit.cxcc $(REPO_ROOT)/src/model_resources/cards/*.cxcc; do build/cxcc-verify $$card || exit 1; done
clean:
	rm -f build/cxcc-core $(TOOLS)
.PHONY: all test clean
