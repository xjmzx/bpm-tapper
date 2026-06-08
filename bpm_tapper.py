#!/usr/bin/env python3
"""BPM tapper — tap along, see the beats-per-minute, get told when it locks in."""

import time
import statistics
import tkinter as tk
import tkinter.font as tkfont

# --- Tunables ---
WINDOW_SIZE = 16          # number of recent intervals used for BPM
RESET_AFTER = 2.0         # seconds of silence before tap history clears
STABLE_CV = 0.04          # coefficient of variation below this = "regular"
STABLE_DURATION = 2.0     # need this many seconds of low CV to declare stable
MIN_TAPS_FOR_BPM = 2      # need at least 2 taps to show any BPM

# --- Identity ---
APP_NAME = "BPM tap"
VERSION = "0.1"
LONG_STABLE_WINDOW = 20.0 # seconds — if BPM stays in range this long, settle
LONG_STABLE_RANGE = 1.0   # 10-90 percentile range of BPM samples must be ≤ this
                          # (trims outliers — tolerates the occasional bad tap)

# --- Design tokens ---
# Mirrors the ndisc-suite fizx palette
# (see ~/code_gh/xjmzx/ndisc.smpl/src/index.css :root). Keep these in
# sync if the canonical palette shifts.
BG            = "#090d12"  # near-black navy field
PANEL         = "#131d2a"  # tap button surface
SURFACE_HOVER = "#1e2d3d"  # tap button active state
FG            = "#f0f6fc"  # cool white
MUTED         = "#6b7a8d"  # cool grey-blue — secondary chrome
MUTED_ACCENT  = "#6f989d"  # MUTED warmed 25% toward ACCENT — idle status chrome
ACCENT        = "#7af0cd"  # mint — focal BPM, default tone
OK            = "#4ade80"  # green — locked / steady
WARN          = "#fbbf24"  # amber — settling / holding
ALERT         = "#f87171"  # red — changing

# Two-tier typography. The focal BPM digits ride the mono-bold "data is
# mono" pattern shared with pong's clock; everything else is the same
# Ubuntu-first sans at one of two sizes.
BPM_FONT_SIZE  = 72       # focal BPM digits, mono bold
UI_FONT_SIZE   = 14       # primary chrome (labels, status, tap button)
UI_SMALL_SIZE  = 11       # secondary chrome (hint, count, reset)

# Preferred font families; resolved at startup against tkfont.families().
# Tkinter takes a single family string per font spec, so we pick the
# first installed match instead of passing a stack like pygame does.
MONO_FAMILIES = ["Liberation Mono", "DejaVu Sans Mono", "Ubuntu Mono",
                 "Courier New", "Courier"]
UI_FAMILIES = ["Ubuntu", "Helvetica", "Arial", "Liberation Sans",
               "DejaVu Sans"]


def _resolve_family(root, preferences):
    """Pick the first preferred family that's installed; fall back to
    the last entry (Tk will substitute its own default if absent)."""
    available = {f.lower(): f for f in tkfont.families(root)}
    for fam in preferences:
        if fam.lower() in available:
            return available[fam.lower()]
    return preferences[-1]


class BPMTapper:
    def __init__(self, root):
        self.root = root
        self.root.title("BPM Tapper")
        self.root.geometry("420x480")
        self.root.minsize(420, 480)  # don't let resize crop the chrome
        self.root.configure(bg=BG)

        # Resolve fonts now that we have a Tk root in scope.
        self.mono = _resolve_family(root, MONO_FAMILIES)
        self.ui = _resolve_family(root, UI_FAMILIES)

        self.timestamps = []
        self.stable_since = None
        self.bpm_history = []  # (timestamp, bpm) for long-window stability

        self._build_ui()
        self._bind_keys()
        self._tick()

    def _build_ui(self):
        # Info button — app name + version, top-right, opens an About panel.
        self.about_label = tk.Label(
            self.root, text=f"{APP_NAME} v{VERSION}",
            font=(self.ui, UI_SMALL_SIZE),
            fg=MUTED, bg=BG, cursor="hand2",
        )
        self.about_label.place(relx=1.0, x=-12, y=10, anchor="ne")
        self.about_label.bind("<Button-1>", self._show_about)

        self.bpm_label = tk.Label(
            self.root, text="--",
            font=(self.mono, BPM_FONT_SIZE, "bold"),
            fg=ACCENT, bg=BG, cursor="hand2",
        )
        self.bpm_label.pack(pady=(30, 0))
        self.bpm_label.bind("<Button-1>", self._copy_bpm)

        self.status_label = tk.Label(
            self.root, text="tap to begin",
            font=(self.ui, UI_FONT_SIZE),
            fg=MUTED_ACCENT, bg=BG,
        )
        self.status_label.pack(pady=(20, 4))

        # Stability progress: fills left-to-right toward STABLE_DURATION
        # while a steady tempo is settling. Empty otherwise. Width grows
        # with the window since we pack with fill="x".
        self.stability_canvas = tk.Canvas(
            self.root, height=3, bg=BG, highlightthickness=0,
        )
        self.stability_canvas.pack(fill="x", padx=40, pady=(0, 8))
        self.stability_bar = self.stability_canvas.create_rectangle(
            0, 0, 0, 3, fill=WARN, outline="",
        )

        # Beat pad — passive rounded rectangle drawn on a Canvas, no text,
        # no border, no hover state. The whole window is the tap target
        # (see _root_click); this just gives the rhythm somewhere to land.
        # On each tap the fill lifts one tone (PANEL → SURFACE_HOVER) for
        # ~150ms — quiet pulse, not a strobe.
        self.beat_pad_canvas = tk.Canvas(
            self.root, height=72, bg=BG, highlightthickness=0,
        )
        self.beat_pad_canvas.pack(fill="x", padx=60, pady=10)
        self.beat_pad = None
        self.beat_pad_canvas.bind("<Configure>", self._redraw_pad)

        self.reset_button = tk.Button(
            self.root, text="Reset",
            font=(self.ui, UI_SMALL_SIZE),
            bg=BG, fg=MUTED_ACCENT, activebackground=BG,
            activeforeground=FG, relief="flat", bd=0,
            cursor="hand2", command=self.reset,
        )
        self.reset_button.pack(pady=(10, 0))

        self.count_label = tk.Label(
            self.root, text="",
            font=(self.ui, UI_SMALL_SIZE),
            fg=MUTED_ACCENT, bg=BG,
        )
        self.count_label.pack(pady=(8, 0))

    def _bind_keys(self):
        self.root.bind("<space>", lambda e: self.tap())
        self.root.bind("<Return>", lambda e: self.tap())
        self.root.bind("<Escape>", lambda e: self.reset())
        self.root.bind("<Control-c>", self._copy_bpm)
        self.root.bind("<Control-C>", self._copy_bpm)
        # Whole-window tap: click anywhere → tap, except widgets that
        # own their own click (BPM digit copies, Reset button resets).
        self.root.bind("<Button-1>", self._root_click)

    def _root_click(self, event):
        if event.widget in (self.bpm_label, self.reset_button,
                            self.about_label):
            return
        self.tap()


    def _show_about(self, _event=None):
        win = tk.Toplevel(self.root)
        win.title(f"About {APP_NAME}")
        win.configure(bg=BG)
        win.geometry("320x240")
        win.resizable(False, False)
        win.transient(self.root)  # stays above main window
        tk.Label(win, text=APP_NAME,
                 font=(self.ui, 20, "bold"),
                 fg=ACCENT, bg=BG).pack(pady=(28, 0))
        tk.Label(win, text=f"version {VERSION}",
                 font=(self.mono, UI_FONT_SIZE),
                 fg=MUTED, bg=BG).pack(pady=(2, 0))
        tk.Label(win,
                 text="Tap along — the BPM locks in when steady.",
                 font=(self.ui, UI_SMALL_SIZE),
                 fg=FG, bg=BG, wraplength=280).pack(pady=(14, 0))
        tk.Label(win, text="Python 3 · Tkinter",
                 font=(self.ui, UI_SMALL_SIZE),
                 fg=MUTED, bg=BG).pack(pady=(14, 0))
        tk.Label(win, text="github.com/xjmzx/bpm-tapper",
                 font=(self.mono, UI_SMALL_SIZE),
                 fg=MUTED, bg=BG).pack(pady=(2, 0))
        tk.Button(win, text="close",
                  font=(self.ui, UI_SMALL_SIZE),
                  bg=PANEL, fg=FG, activebackground=SURFACE_HOVER,
                  activeforeground=FG, relief="flat", bd=0,
                  padx=14, pady=6, cursor="hand2",
                  command=win.destroy).pack(pady=(18, 0))
        # Esc closes the About window too.
        win.bind("<Escape>", lambda e: win.destroy())

    def _set_stability(self, fraction):
        canvas_w = self.stability_canvas.winfo_width()
        self.stability_canvas.coords(
            self.stability_bar, 0, 0, int(canvas_w * fraction), 3,
        )

    def tap(self):
        now = time.monotonic()
        if self.timestamps and now - self.timestamps[-1] > RESET_AFTER:
            self.timestamps = []
            self.stable_since = None
            self.bpm_history = []
        self.timestamps.append(now)
        if len(self.timestamps) > WINDOW_SIZE + 1:
            self.timestamps = self.timestamps[-(WINDOW_SIZE + 1):]
        self._flash()
        self._update_display()

    def reset(self):
        self.timestamps = []
        self.stable_since = None
        self.bpm_history = []
        self.bpm_label.config(text="--", fg=ACCENT)
        self.status_label.config(text="tap to begin", fg=MUTED_ACCENT)
        self.count_label.config(text="")
        self._set_stability(0)

    def _copy_bpm(self, _event=None):
        text = self.bpm_label.cget("text")
        if not text or text == "--":
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        prev = self.count_label.cget("text")
        self.count_label.config(text=f"copied {text}")
        self.root.after(900, lambda: self.count_label.config(text=prev))

    def _redraw_pad(self, _event=None):
        """(Re)draw the beat pad — rounded rectangle via smoothed polygon.
        Called on resize and initial layout (via the <Configure> bind)."""
        self.beat_pad_canvas.delete("pad")
        w = self.beat_pad_canvas.winfo_width()
        h = self.beat_pad_canvas.winfo_height()
        if w <= 0 or h <= 0:
            return
        r = 14
        pts = [
            r, 0, w - r, 0, w, 0,
            w, r, w, h - r, w, h,
            w - r, h, r, h, 0, h,
            0, h - r, 0, r, 0, 0,
        ]
        self.beat_pad = self.beat_pad_canvas.create_polygon(
            pts, smooth=True, fill=PANEL, outline="", tags="pad",
        )

    def _flash(self):
        # Quiet tone-lift, not a strobe — fill goes one notch lighter
        # then settles back.
        if self.beat_pad is None:
            return
        self.beat_pad_canvas.itemconfig(self.beat_pad, fill=SURFACE_HOVER)
        self.root.after(
            150,
            lambda: self.beat_pad_canvas.itemconfig(
                self.beat_pad, fill=PANEL),
        )

    def _intervals(self):
        ts = self.timestamps
        return [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]

    def _update_display(self):
        intervals = self._intervals()
        if len(intervals) < MIN_TAPS_FOR_BPM - 1:
            self.count_label.config(text=f"{len(self.timestamps)} tap")
            self._set_stability(0)
            return

        mean = statistics.fmean(intervals)
        if mean <= 0:
            return
        bpm = 60.0 / mean
        self.count_label.config(text=f"{len(self.timestamps)} taps")
        # Clear the bar by default; settling branch repopulates below.
        self._set_stability(0)

        now = time.monotonic()
        self.bpm_history.append((now, bpm))
        cutoff = now - LONG_STABLE_WINDOW
        while self.bpm_history and self.bpm_history[0][0] < cutoff:
            self.bpm_history.pop(0)

        long_stable = False
        long_bpm = bpm
        long_span = 0.0
        long_range = float("inf")
        if len(self.bpm_history) >= 5:
            long_span = self.bpm_history[-1][0] - self.bpm_history[0][0]
            bpms_sorted = sorted(b for _, b in self.bpm_history)
            n = len(bpms_sorted)
            # 10-90 percentile range trims occasional bad taps
            lo = bpms_sorted[max(0, n // 10)]
            hi = bpms_sorted[min(n - 1, n - n // 10 - 1)]
            long_range = hi - lo
            if long_span >= LONG_STABLE_WINDOW * 0.95 and long_range <= LONG_STABLE_RANGE:
                long_stable = True
                long_bpm = statistics.median(bpms_sorted)

        short_stable = False
        if len(intervals) >= 3:
            stdev = statistics.pstdev(intervals)
            cv = stdev / mean
            if cv < STABLE_CV:
                if self.stable_since is None:
                    self.stable_since = now
                if now - self.stable_since >= STABLE_DURATION:
                    short_stable = True
            else:
                self.stable_since = None

        if short_stable or long_stable:
            display_bpm = long_bpm if long_stable else bpm
            self.status_label.config(text="● steady", fg=OK)
            self.bpm_label.config(text=f"{round(display_bpm)}", fg=OK)
        elif self.stable_since is not None:
            # Bar + amber BPM convey settling; no word needed.
            held = now - self.stable_since
            self._set_stability(min(1.0, held / STABLE_DURATION))
            self.status_label.config(text="", fg=WARN)
            self.bpm_label.config(text=f"{round(bpm)}", fg=WARN)
        elif long_span >= LONG_STABLE_WINDOW * 0.5 and long_range <= LONG_STABLE_RANGE * 2:
            self.status_label.config(
                text=f"holding ±{long_range / 2:.2f}  ({long_span:.0f}/{LONG_STABLE_WINDOW:.0f}s)",
                fg=WARN,
            )
            self.bpm_label.config(text=f"{round(bpm)}", fg=WARN)
        elif len(intervals) >= 3:
            # Red BPM digit carries the "changing" signal; no word needed.
            self.status_label.config(text="", fg=ALERT)
            self.bpm_label.config(text=f"{round(bpm)}", fg=ALERT)
        else:
            self.bpm_label.config(text=f"{round(bpm)}", fg=ACCENT)
            self.status_label.config(text="~~..", fg=MUTED_ACCENT)

    def _tick(self):
        # auto-clear if user stops tapping
        if self.timestamps:
            idle = time.monotonic() - self.timestamps[-1]
            if idle > RESET_AFTER:
                self.status_label.config(text="[||]", fg=MUTED_ACCENT)
                self.stable_since = None
                self._set_stability(0)
        self.root.after(100, self._tick)


def main():
    root = tk.Tk()
    BPMTapper(root)
    root.mainloop()


if __name__ == "__main__":
    main()
