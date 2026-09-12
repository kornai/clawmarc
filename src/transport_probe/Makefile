PYTHON ?= python3
PREFIX ?= $(HOME)/.local
BINDIR = $(PREFIX)/bin

.PHONY: test install clean

test:
	$(PYTHON) test_probe.py

install:
	$(PYTHON) -c 'import cryptography'
	install -d "$(BINDIR)"
	install -m 755 probe.py "$(BINDIR)/clawmarc-transport-probe"

clean:
	rm -rf __pycache__
