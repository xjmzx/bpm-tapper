PREFIX  ?= $(HOME)/.local
BINDIR  ?= $(PREFIX)/bin
APPDIR  ?= $(PREFIX)/share/applications
ICONDIR ?= $(PREFIX)/share/icons/hicolor/scalable/apps

# Package version. Bumped with every release alongside VERSION in
# bpm_tapper.py -- two places, both set to the same string as the v* tag.
VERSION ?= 0.1.1
MAINTAINER ?= xjmzx <admin@jmzx.uk>
DIST_DIR := dist
PKG_NAME := bpm-tapper_$(VERSION)_all
PKG_DIR  := build/$(PKG_NAME)

# Linux icons crop the grid margin. The masters carry the art in an 824 square
# on a 1024 canvas (Apple's grid, ICONS.md), which fills 80.5% of the tile --
# visibly smaller in the dock than Yaru's own icons, which fill 89%. Cropping to
# this viewBox gets the same 89% out of the master with no re-export. The .icns
# and the .ico keep the full canvas.
LINUX_VIEWBOX ?= 49 49 926 926

DESKTOP_OUT := $(APPDIR)/bpm-tapper.desktop

.PHONY: help run check install uninstall deb clean-deb version

help:
	@echo "Targets:"
	@echo "  make run        launch BPM Tapper without installing"
	@echo "  make check      syntax-check the Python source"
	@echo "  make install    copy script + desktop entry under PREFIX"
	@echo "                  (default PREFIX=$$HOME/.local; sudo PREFIX=/usr/local for system-wide)"
	@echo "  make uninstall  remove what 'install' put down"
	@echo "  make deb        build dist/bpm-tapper_$(VERSION)_all.deb"
	@echo "  make version V=x.y.z  set the version in both places"

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
	install -d $(DESTDIR)$(BINDIR) $(DESTDIR)$(APPDIR) $(DESTDIR)$(ICONDIR)
	install -m 0755 bpm_tapper.py $(DESTDIR)$(BINDIR)/bpm_tapper.py
	@# Linux fill: crop the grid margin on the way in (see LINUX_VIEWBOX).
	sed '1s|viewBox="[^"]*"|viewBox="$(LINUX_VIEWBOX)"|' icon.svg > $(DESTDIR)$(ICONDIR)/bpm-tapper.svg
	chmod 0644 $(DESTDIR)$(ICONDIR)/bpm-tapper.svg
	@# The .desktop records the FINAL paths, not the staged ones, so a
	@# DESTDIR build still points at $(PREFIX) once dpkg unpacks it.
	sed -e 's|@BINDIR@|$(BINDIR)|g' \
	    -e 's|@ICONDIR@|$(ICONDIR)|g' \
	    bpm-tapper.desktop.in > $(DESTDIR)$(DESKTOP_OUT)
	chmod 0644 $(DESTDIR)$(DESKTOP_OUT)
	@# Refresh the caches on a real user install only -- skip when staging
	@# into DESTDIR (make deb), where dpkg triggers own them.
	@if [ -z "$(DESTDIR)" ] && command -v update-desktop-database >/dev/null 2>&1; then \
		update-desktop-database $(APPDIR) >/dev/null 2>&1 || true; \
	fi
	@if [ -z "$(DESTDIR)" ] && command -v gtk-update-icon-cache >/dev/null 2>&1; then \
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

# Package the same files `install` lays down into a .deb, by staging them
# under DESTDIR and writing a control file over the top -- the pattern pong
# uses. Architecture is `all`: this is a Python script, not a compiled binary.
deb:
	rm -rf $(PKG_DIR)
	mkdir -p $(PKG_DIR)/DEBIAN $(DIST_DIR)
	$(MAKE) install DESTDIR=$(CURDIR)/$(PKG_DIR) PREFIX=/usr
	@printf '%s\n' \
	  "Package: bpm-tapper" \
	  "Version: $(VERSION)" \
	  "Section: sound" \
	  "Priority: optional" \
	  "Architecture: all" \
	  "Depends: python3 (>= 3.8), python3-tk" \
	  "Maintainer: $(MAINTAINER)" \
	  "Homepage: https://github.com/xjmzx/bpm-tapper" \
	  "Description: Tap-along beats-per-minute calculator" \
	  " Tap a key in time with the music and read the tempo back. Averages" \
	  " the intervals between taps, so the reading settles as you keep time." \
	  " ." \
	  " A small Tk utility, used alongside nsmpl when tagging samples." \
	  > $(PKG_DIR)/DEBIAN/control
	dpkg-deb --root-owner-group --build $(PKG_DIR) $(DIST_DIR)/$(PKG_NAME).deb
	@echo ""
	@echo "Built: $(DIST_DIR)/$(PKG_NAME).deb"
	@echo "Install with: sudo apt install ./$(DIST_DIR)/$(PKG_NAME).deb"

clean-deb:
	rm -rf build $(DIST_DIR)

# Keep the two version strings in step: the Makefile's VERSION (which names
# the .deb) and the one the app shows in its own about line.
version:
	@test -n "$(V)" || { echo "usage: make version V=0.1.1" >&2; exit 2; }
	@sed -i.bak -E 's/^VERSION \?= .*/VERSION ?= $(V)/' Makefile && rm -f Makefile.bak
	@sed -i.bak -E 's/^VERSION = ".*"/VERSION = "$(V)"/' bpm_tapper.py && rm -f bpm_tapper.py.bak
	@echo "version set to $(V) in both places:"
	@git diff --stat -- Makefile bpm_tapper.py
