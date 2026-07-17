PREFIX  ?= $(HOME)/.local
BINDIR  ?= $(PREFIX)/bin
APPDIR  ?= $(PREFIX)/share/applications
ICONDIR ?= $(PREFIX)/share/icons/hicolor/scalable/apps

DESKTOP_OUT := $(APPDIR)/bpm-tapper.desktop

.PHONY: help run check install uninstall

help:
	@echo "Targets:"
	@echo "  make run        launch BPM Tapper without installing"
	@echo "  make check      syntax-check the Python source"
	@echo "  make install    copy script + desktop entry under PREFIX"
	@echo "                  (default PREFIX=$$HOME/.local; sudo PREFIX=/usr/local for system-wide)"
	@echo "  make uninstall  remove what 'install' put down"

run:
	python3 bpm_tapper.py

check:
	python3 -m py_compile bpm_tapper.py
	@if command -v desktop-file-validate >/dev/null 2>&1; then \
		tmp=$$(mktemp --suffix=.desktop); \
		sed -e 's|@BINDIR@|/tmp|g' -e 's|@ICONDIR@|/tmp|g' \
		    bpm-tapper.desktop.in > $$tmp; \
		desktop-file-validate $$tmp && echo "desktop file ok"; \
		rm -f $$tmp; \
	fi
	@echo "syntax ok"

install:
	install -d $(BINDIR) $(APPDIR) $(ICONDIR)
	install -m 0755 bpm_tapper.py $(BINDIR)/bpm_tapper.py
	install -m 0644 icon.svg      $(ICONDIR)/bpm-tapper.svg
	sed -e 's|@BINDIR@|$(BINDIR)|g' \
	    -e 's|@ICONDIR@|$(ICONDIR)|g' \
	    bpm-tapper.desktop.in > $(DESKTOP_OUT)
	chmod 0644 $(DESKTOP_OUT)
	@if command -v update-desktop-database >/dev/null 2>&1; then \
		update-desktop-database $(APPDIR) >/dev/null 2>&1 || true; \
	fi
	@if command -v gtk-update-icon-cache >/dev/null 2>&1; then \
		gtk-update-icon-cache -f -t $(PREFIX)/share/icons/hicolor >/dev/null 2>&1 || true; \
	fi
	@echo "installed to $(PREFIX)"
	@echo "  script  -> $(BINDIR)/bpm_tapper.py"
	@echo "  desktop -> $(DESKTOP_OUT)"

uninstall:
	rm -f $(BINDIR)/bpm_tapper.py
	rm -f $(ICONDIR)/bpm-tapper.svg
	rm -f $(DESKTOP_OUT)
	@if command -v update-desktop-database >/dev/null 2>&1; then \
		update-desktop-database $(APPDIR) >/dev/null 2>&1 || true; \
	fi
	@if command -v gtk-update-icon-cache >/dev/null 2>&1; then \
		gtk-update-icon-cache -f -t $(PREFIX)/share/icons/hicolor >/dev/null 2>&1 || true; \
	fi
	@echo "uninstalled from $(PREFIX)"
