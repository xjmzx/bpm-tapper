# bpm-tapper

A small Tk desktop tool to calculate beats-per-minute by tapping along.
Tap with the mouse, **Space**, or **Enter**. The window shows a live BPM
estimate from your most recent taps and signals when the tempo has
locked in.

## How "locked in" works

- **Short window**: looks at the latest 16 tap intervals and computes
  their coefficient of variation. If CV stays below `0.04` for at least
  2 seconds, the tempo is treated as steady.
- **Long window**: keeps a 20-second history of BPM samples; if the
  10–90th percentile range stays within ±0.5 BPM, it locks in even
  through occasional bad taps.

When steady, the BPM display turns green and snaps to a whole number if
within 0.2 BPM. While settling it's amber; while clearly changing it's
red/blue. After 2 seconds of silence, history clears.

## Keys

| Key | Action |
| --- | --- |
| `Space` / `Enter` | tap |
| `Esc` | reset |
| `Ctrl+C` | copy the displayed BPM to the clipboard (also: click the BPM number) |

## Install dependencies (Debian / Ubuntu)

```sh
sudo apt update
sudo apt install python3 python3-tk
```

Other distros: `pacman -S python tk`, `dnf install python3 python3-tkinter`.

## Quick start (no install)

```sh
git clone https://github.com/xjmzx/bpm-tapper.git
cd bpm-tapper
python3 bpm_tapper.py
```

## Build / install / deploy

The repo ships a `Makefile` that places the script under `PREFIX/bin`,
the icon under `PREFIX/share/icons/hicolor/scalable/apps`, and a
`.desktop` entry under `PREFIX/share/applications` (so the app appears in
GNOME / KDE / XFCE app menus).

```sh
# user-level install (no sudo) — default PREFIX is $HOME/.local
make install

# system-wide
sudo make install PREFIX=/usr/local

# remove
make uninstall                     # or: sudo make uninstall PREFIX=/usr/local
```

After `make install`, "BPM Tapper" appears in *Show Applications*. The
desktop entry is generated from `bpm-tapper.desktop.in` with the install
paths substituted in, so it works regardless of `PREFIX`.

Other targets:

```sh
make help     # list everything
make run      # launch in place
make check    # py_compile + desktop-file-validate
```
