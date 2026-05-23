#!/usr/bin/env python3
"""BPM tapper — tap along, see the beats-per-minute, get told when it locks in."""

import time
import statistics
import tkinter as tk

WINDOW_SIZE = 16          # number of recent intervals used for BPM
RESET_AFTER = 2.0         # seconds of silence before tap history clears
STABLE_CV = 0.04          # coefficient of variation below this = "regular"
STABLE_DURATION = 2.0     # need this many seconds of low CV to declare stable
SNAP_TOLERANCE = 0.2      # once steady, snap to whole BPM if within this distance
MIN_TAPS_FOR_BPM = 2      # need at least 2 taps to show any BPM
LONG_STABLE_WINDOW = 20.0 # seconds — if BPM stays in range this long, settle
LONG_STABLE_RANGE = 1.0   # 10-90 percentile range of BPM samples must be ≤ this
                          # (trims outliers — tolerates the occasional bad tap)


class BPMTapper:
    def __init__(self, root):
        self.root = root
        self.root.title("BPM Tapper")
        self.root.geometry("420x360")
        self.root.configure(bg="#090d12")

        self.timestamps = []
        self.stable_since = None
        self.bpm_history = []  # (timestamp, bpm) for long-window stability

        self._build_ui()
        self._bind_keys()
        self._tick()

    def _build_ui(self):
        bg = "#090d12"
        fg = "#f0f6fc"
        accent = "#7af0cd"
        muted = "#6b7a8d"

        self.bpm_label = tk.Label(
            self.root, text="--", font=("Helvetica", 72, "bold"),
            fg=accent, bg=bg, cursor="hand2",
        )
        self.bpm_label.pack(pady=(30, 0))
        self.bpm_label.bind("<Button-1>", self._copy_bpm)

        tk.Label(
            self.root, text="BPM", font=("Helvetica", 14),
            fg=muted, bg=bg,
        ).pack()

        self.copy_hint = tk.Label(
            self.root, text="click number or ⌃C to copy",
            font=("Helvetica", 9), fg=muted, bg=bg, cursor="hand2",
        )
        self.copy_hint.pack(pady=(4, 0))
        self.copy_hint.bind("<Button-1>", self._copy_bpm)

        self.status_label = tk.Label(
            self.root, text="tap to begin", font=("Helvetica", 12),
            fg=muted, bg=bg,
        )
        self.status_label.pack(pady=(20, 10))

        self.tap_button = tk.Button(
            self.root, text="TAP  (or press Space)",
            font=("Helvetica", 14, "bold"),
            bg="#131d2a", fg=fg, activebackground="#1e2d3d",
            activeforeground=fg, relief="flat", bd=0,
            padx=20, pady=14, cursor="hand2",
            command=self.tap,
        )
        self.tap_button.pack(pady=10, padx=40, fill="x")

        self.reset_button = tk.Button(
            self.root, text="Reset", font=("Helvetica", 10),
            bg=bg, fg=muted, activebackground=bg,
            activeforeground=fg, relief="flat", bd=0,
            cursor="hand2", command=self.reset,
        )
        self.reset_button.pack(pady=(10, 0))

        self.count_label = tk.Label(
            self.root, text="", font=("Helvetica", 9),
            fg=muted, bg=bg,
        )
        self.count_label.pack(pady=(8, 0))

    def _bind_keys(self):
        self.root.bind("<space>", lambda e: self.tap())
        self.root.bind("<Return>", lambda e: self.tap())
        self.root.bind("<Escape>", lambda e: self.reset())
        self.root.bind("<Control-c>", self._copy_bpm)
        self.root.bind("<Control-C>", self._copy_bpm)

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
        self.bpm_label.config(text="--", fg="#7af0cd")
        self.status_label.config(text="tap to begin", fg="#6b7a8d")
        self.count_label.config(text="")

    def _copy_bpm(self, _event=None):
        text = self.bpm_label.cget("text")
        if not text or text == "--":
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        prev = self.count_label.cget("text")
        self.count_label.config(text=f"copied {text}")
        self.root.after(900, lambda: self.count_label.config(text=prev))

    def _flash(self):
        self.tap_button.config(bg="#7af0cd")
        self.root.after(80, lambda: self.tap_button.config(bg="#131d2a"))

    def _intervals(self):
        ts = self.timestamps
        return [ts[i + 1] - ts[i] for i in range(len(ts) - 1)]

    def _update_display(self):
        intervals = self._intervals()
        if len(intervals) < MIN_TAPS_FOR_BPM - 1:
            self.count_label.config(text=f"{len(self.timestamps)} tap")
            return

        mean = statistics.fmean(intervals)
        if mean <= 0:
            return
        bpm = 60.0 / mean
        self.count_label.config(text=f"{len(self.timestamps)} taps")

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
            self.status_label.config(text="● steady", fg="#4ade80")
            rounded = round(display_bpm)
            if abs(display_bpm - rounded) <= SNAP_TOLERANCE:
                self.bpm_label.config(text=f"{rounded}", fg="#4ade80")
            else:
                self.bpm_label.config(text=f"{display_bpm:.1f}", fg="#4ade80")
        elif self.stable_since is not None:
            held = now - self.stable_since
            self.status_label.config(text=f"settling… ({held:.1f}s)", fg="#fbbf24")
            self.bpm_label.config(text=f"{bpm:.1f}", fg="#fbbf24")
        elif long_span >= LONG_STABLE_WINDOW * 0.5 and long_range <= LONG_STABLE_RANGE * 2:
            self.status_label.config(
                text=f"holding ±{long_range / 2:.2f}  ({long_span:.0f}/{LONG_STABLE_WINDOW:.0f}s)",
                fg="#fbbf24",
            )
            self.bpm_label.config(text=f"{bpm:.1f}", fg="#fbbf24")
        elif len(intervals) >= 3:
            self.status_label.config(text="changing…", fg="#f87171")
            self.bpm_label.config(text=f"{bpm:.1f}", fg="#7af0cd")
        else:
            self.bpm_label.config(text=f"{bpm:.1f}", fg="#7af0cd")
            self.status_label.config(text="keep tapping…", fg="#6b7a8d")

    def _tick(self):
        # auto-clear if user stops tapping
        if self.timestamps:
            idle = time.monotonic() - self.timestamps[-1]
            if idle > RESET_AFTER:
                self.status_label.config(text="paused", fg="#6b7a8d")
                self.stable_since = None
        self.root.after(100, self._tick)


def main():
    root = tk.Tk()
    BPMTapper(root)
    root.mainloop()


if __name__ == "__main__":
    main()
