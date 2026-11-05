"""The Review tab and the playback window (user, 2026-11-05).

The Review tab lists the moments to check: every stretch where the tracked
point was outside all the drawn regions. Brief ones are jumps at the wall or
head dips, and they count for the region they belong to. A long one may mean
the tracker got stuck on a dark spot or a reflection, so stretches at least
as long as the cutoff are flagged. "Open playback window", or clicking a row,
opens the video in its own resizable window at that exact frame. (The video
was first built into the tab; it was too cramped there. A separate window
will also suit manual scoring, e.g. object recognition, later.)

The playback window: play/pause (space bar on the video), one-frame and
10-second steps, a scrub slider and a speed choice. It draws a red marker on
the tracked position, an optional short trail, and region outlines. The info
line shows the session frame and time, the video's own frame and time
(tracking files record the video frame of their first row), and the region
each frame counted for. "Save as video…" writes `<name>_tracked.mp4` beside
the video in the background.

Adapted from ezTrack's `PlayVideo` via core/playback.py (GPL-3.0, see LICENSE).
"""

from __future__ import annotations

import os
import threading
import time
import tkinter as tk
import traceback
from tkinter import ttk

from core.metrics import _outside_mask, outside_events, region_labels
from core.playback import FrameSource, open_playback, tracked_video_path, write_tracked_video
from dialogs import show_info, show_warning
from setup_window import FrameCanvas
from tooltip import Tooltip

SPEEDS = ("0.25x", "0.5x", "1x", "2x", "4x", "8x")
TRAIL_SECONDS = 1.0
SKIP_SECONDS = 10
MARKER_COLOR = "#ff2828"
TRAIL_COLOR = "#ffc828"
ROI_COLOR = "#5adc5a"
EVENT_COLUMNS = (("#", 34), ("Frame", 64), ("Session time", 84), ("Video frame", 78),
                 ("Video time", 78), ("Length (s)", 66), ("Counted as", 96),
                 ("Px outside", 70), ("Check", 70))


def clock(seconds: float) -> str:
    """m:ss.ss"""
    return f"{int(seconds // 60)}:{seconds % 60:05.2f}"


class PlaybackWindow(tk.Toplevel):
    """A tracked file's video with its tracking drawn on, in its own window."""

    def __init__(self, parent, pb, labels, outside, title: str):
        super().__init__(parent)
        self.pb = pb
        self.source = FrameSource(pb)
        self._labels, self._outside = labels, outside
        self.title(f"Playback: {title}")
        self.geometry("960x760")
        self.minsize(600, 480)
        self.row = 0
        self.playing = False
        self._job = None
        self._clock = None
        self._save = None
        self._setting = False
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.show(0)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        # Controls are packed first, from the bottom, so a small window
        # shrinks the video instead of hiding them; two short rows fit narrow.
        bar2 = ttk.Frame(self, padding=(8, 0, 8, 8))
        bar2.pack(side=tk.BOTTOM, fill=tk.X)
        bar = ttk.Frame(self, padding=(8, 6, 8, 4))
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.slider = ttk.Scale(self, from_=0, to=max(self.pb.n_frames - 1, 0),
                                orient=tk.HORIZONTAL, command=self._on_slider)
        self.slider.pack(side=tk.BOTTOM, fill=tk.X, padx=8)
        self.info = ttk.Label(self, anchor=tk.W, padding=(8, 4), justify=tk.LEFT)
        self.info.pack(side=tk.BOTTOM, fill=tk.X)
        self.info.bind("<Configure>",
                       lambda e: self.info.configure(wraplength=max(200, e.width - 16)))
        self.canvas = FrameCanvas(self)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.canvas.redraw_overlay = self._overlay
        self.canvas.bind("<space>", lambda _e: self.toggle())
        for text, cmd, tip in (
                ("◀◀", lambda: self.skip(-SKIP_SECONDS), "Back 10 seconds"),
                ("◀", lambda: self.step(-1), "Back 1 frame")):
            b = ttk.Button(bar, text=text, width=3, command=cmd)
            b.pack(side=tk.LEFT)
            Tooltip(b, tip)
        self.play_btn = ttk.Button(bar, text="Play", width=7, command=self.toggle)
        self.play_btn.pack(side=tk.LEFT, padx=4)
        Tooltip(self.play_btn, "Play or pause (space bar with the pointer on the video).")
        for text, cmd, tip in (
                ("▶", lambda: self.step(1), "Forward 1 frame"),
                ("▶▶", lambda: self.skip(SKIP_SECONDS), "Forward 10 seconds")):
            b = ttk.Button(bar, text=text, width=3, command=cmd)
            b.pack(side=tk.LEFT)
            Tooltip(b, tip)
        ttk.Label(bar, text="Speed:").pack(side=tk.LEFT, padx=(12, 4))
        self.speed_var = tk.StringVar(value="1x")
        speed = ttk.Combobox(bar, textvariable=self.speed_var, values=SPEEDS,
                             state="readonly", width=6)
        speed.pack(side=tk.LEFT)
        speed.bind("<<ComboboxSelected>>", lambda _e: self._restart_clock())
        self.trail_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar2, text="Trail", variable=self.trail_var,
                        command=self._redraw).pack(side=tk.LEFT)
        self.roi_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar2, text="Regions", variable=self.roi_var,
                        command=self._redraw).pack(side=tk.LEFT, padx=(8, 0))
        self.save_btn = ttk.Button(bar2, text="Save as video…", command=self.save_video)
        self.save_btn.pack(side=tk.RIGHT)
        Tooltip(self.save_btn, f"Write {os.path.basename(tracked_video_path(self.pb.video))} "
                               "next to the video: the session with the marker (and the "
                               "trail and regions, if shown) drawn on, at the video's own "
                               "frame rate. Replaces an earlier one.")
        self.save_text = ttk.Label(bar2, foreground="gray")
        self.save_text.pack(side=tk.RIGHT, padx=8)

    # ------------------------------------------------------------- showing
    def _trail_frames(self) -> int:
        if not self.trail_var.get():
            return 0
        return int(round(TRAIL_SECONDS * (self.pb.fps or 20)))

    def show(self, row: int) -> None:
        if not self.winfo_exists():
            return
        self.row = max(0, min(self.pb.n_frames - 1, row))
        try:
            frame = self.source.frame(self.row)
        except Exception:
            traceback.print_exc()
            frame = None
        if frame is not None:
            self.canvas.show(frame)
        else:
            self._redraw()  # keep the last image; the info line says why
        self._set_slider(self.row)
        self._update_info(frame is None)

    def _redraw(self) -> None:
        self.canvas._render()

    def _overlay(self) -> None:
        if self.pb is None:
            return
        c, pb, row = self.canvas, self.pb, self.row
        if self.roi_var.get():
            for _name, (xs, ys) in pb.regions().items():
                pts = [v for x, y in zip(xs, ys) for v in c.to_screen(x, y)]
                if len(pts) >= 6:
                    c.create_polygon(*pts, outline=ROI_COLOR, fill="", width=1)
        trail = self._trail_frames()
        if trail:
            pts = pb.trail(row, trail)
            for a, b in zip(pts, pts[1:]):
                if a and b:
                    c.create_line(*c.to_screen(*a), *c.to_screen(*b), fill=TRAIL_COLOR,
                                  width=2)
        pos = pb.position(row)
        if pos:
            sx, sy = c.to_screen(*pos)
            c.create_oval(sx - 6, sy - 6, sx + 6, sy + 6, fill=MARKER_COLOR,
                          outline="white", width=1)

    def _update_info(self, unread_video: bool = False) -> None:
        pb, row = self.pb, self.row
        vf = pb.video_frame(row)
        parts = [f"Frame {row + 1:,} of {pb.n_frames:,}", f"session {clock(row / pb.fps)}",
                 f"video frame {vf:,}", f"video time {clock(vf / pb.fps)}"]
        if pb.unreadable(row):
            parts.append("unreadable frame (no position)")
        elif pb.position(row) is None:
            parts.append("no position found")
        else:
            region = self._labels[row] if row < len(self._labels) else ""
            text = f"region: {region}" if region else "in no region"
            if row < len(self._outside) and self._outside[row]:
                text += " (outside the drawn regions)"
            parts.append(text)
        if unread_video:
            parts.append("the video frame couldn't be read")
        self.info.configure(text="   ·   ".join(parts))

    def _set_slider(self, row: int) -> None:
        self._setting = True
        self.slider.set(row)
        self._setting = False

    def _on_slider(self, value) -> None:
        if self._setting or self.pb is None:
            return
        row = int(float(value))
        if row != self.row:
            self.show(row)
            self._restart_clock()

    def step(self, delta: int) -> None:
        self.pause()
        self.show(self.row + delta)

    def skip(self, seconds: float) -> None:
        if self.pb is None:
            return
        self.show(self.row + int(round(seconds * (self.pb.fps or 20))))
        self._restart_clock()

    # ------------------------------------------------------------- playing
    def _speed(self) -> float:
        try:
            return float(self.speed_var.get().rstrip("x"))
        except ValueError:
            return 1.0

    def _restart_clock(self) -> None:
        self._clock = (time.perf_counter(), self.row)

    def toggle(self) -> None:
        self.pause() if self.playing else self.play()

    def play(self) -> None:
        if self.pb is None:
            return
        if self.row >= self.pb.n_frames - 1:
            self.show(0)
        self.playing = True
        self.play_btn.configure(text="Pause")
        self._restart_clock()
        self._tick()

    def pause(self) -> None:
        self.playing = False
        self.play_btn.configure(text="Play")
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None

    def _tick(self) -> None:
        """Show the frame the clock is at; frames are skipped if drawing can't
        keep up, so playback runs at the chosen speed."""
        self._job = None
        if not self.playing or self.pb is None or not self.winfo_exists():
            return
        t0, r0 = self._clock
        rate = (self.pb.fps or 20) * self._speed()
        target = r0 + int((time.perf_counter() - t0) * rate)
        if target >= self.pb.n_frames - 1:
            self.show(self.pb.n_frames - 1)
            self.pause()
            return
        if target != self.row:
            self.show(target)
        self._job = self.after(max(1, int(1000 / rate)), self._tick)

    # -------------------------------------------------------------- saving
    def save_video(self) -> None:
        if self.pb is None:
            return
        if self._save is not None:
            self._save[1].set()  # the button reads Cancel saving while saving
            return
        cancel = threading.Event()
        state = {"done": 0, "total": self.pb.n_frames, "result": None, "error": None}
        trail, rois, pb = self._trail_frames(), bool(self.roi_var.get()), self.pb

        def work():
            try:
                state["result"] = write_tracked_video(
                    pb, trail_frames=trail, show_regions=rois,
                    progress=lambda d, t: state.update(done=d, total=t),
                    should_cancel=cancel.is_set)
            except Exception as exc:
                traceback.print_exc()
                state["error"] = str(exc) or type(exc).__name__

        thread = threading.Thread(target=work, daemon=True)
        self._save = (thread, cancel, state)
        self.save_btn.configure(text="Cancel saving")
        thread.start()
        self.after(200, self._poll_save)

    def _poll_save(self) -> None:
        if self._save is None or not self.winfo_exists():
            return
        thread, cancel, state = self._save
        if thread.is_alive():
            pct = int(100 * state["done"] / state["total"]) if state["total"] else 0
            self.save_text.configure(text="Stopping…" if cancel.is_set()
                                     else f"Saving video {pct}%")
            self.after(200, self._poll_save)
            return
        self._save = None
        self.save_btn.configure(text="Save as video…")
        self.save_text.configure(text="")
        if state["error"]:
            show_warning(self, "The video couldn't be saved",
                         f"The video couldn't be saved.\n\n{state['error']}")
        elif state["result"]:
            show_info(self, "Video saved",
                      f"Saved {os.path.basename(state['result'])} next to the video.")

    # --------------------------------------------------------------- close
    def close(self) -> None:
        self.pause()
        if self._save is not None:
            self._save[1].set()
            self._save[0].join(timeout=10)
            self._save = None
        self.source.close()
        self.destroy()


class ReviewPanel(ttk.Frame):
    """The Review tab: the points to review and the button that opens the
    playback window."""

    def __init__(self, parent, on_cutoff=None):
        super().__init__(parent)
        self.on_cutoff = on_cutoff or (lambda value: None)
        self.pb = None
        self._data = None
        self._title = ""
        self.window: PlaybackWindow | None = None
        self.events: list[dict] = []
        self._build()
        self.show_message("Select a tracked file in the file list to review its video.")

    def _build(self) -> None:
        self.message = ttk.Label(self, padding=20, wraplength=520, justify=tk.LEFT)
        self.body = ttk.Frame(self, padding=(8, 8, 8, 4))
        head = ttk.Frame(self.body)
        head.pack(side=tk.TOP, fill=tk.X)
        self.open_btn = ttk.Button(head, text="Open playback window",
                                   command=lambda: self.open_window())
        self.open_btn.pack(side=tk.LEFT)
        Tooltip(self.open_btn, "Play the selected file's video with its tracked position "
                               "drawn on, in its own window. Clicking a row below opens "
                               "it at that moment.")
        self.cutoff_var = tk.StringVar()
        cutoff = ttk.Entry(head, textvariable=self.cutoff_var, width=5)
        cutoff.pack(side=tk.RIGHT)
        cutoff.bind("<Return>", lambda _e: self._apply_cutoff())
        cutoff.bind("<FocusOut>", lambda _e: self._apply_cutoff())
        ttk.Label(head, text="Flag stretches at least (s):").pack(side=tk.RIGHT, padx=(0, 4))
        Tooltip(cutoff, "A stretch outside the regions this long or longer may mean the "
                        "tracker lost the animal (stuck on a dark spot or a reflection), "
                        "so it's flagged for review. Brief ones are usually jumps or head "
                        "dips. Saved per test.")
        ttk.Label(self.body, text="Points to review", font=("TkDefaultFont", 0, "bold")).pack(
            side=tk.TOP, anchor="w", pady=(10, 0))
        self.summary = ttk.Label(self.body, foreground="gray", anchor=tk.W, justify=tk.LEFT)
        self.summary.pack(side=tk.TOP, fill=tk.X, pady=(2, 6))
        self.summary.bind("<Configure>",
                          lambda e: self.summary.configure(wraplength=max(200, e.width - 8)))
        wrap = ttk.Frame(self.body)
        wrap.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(wrap, columns=[c for c, _ in EVENT_COLUMNS],
                                 show="headings", selectmode="browse")
        for col, width in EVENT_COLUMNS:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=width, minwidth=width, anchor=tk.CENTER,
                             stretch=col == "Check")
        self.tree.tag_configure("flag", foreground="#c62828")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._on_event)

    def show_message(self, text: str) -> None:
        """Show a note instead of the list (no file, not tracked, no video)."""
        self.unload()
        self.body.pack_forget()
        self.message.configure(text=text)
        self.message.pack(side=tk.TOP, anchor="nw")

    def load(self, data, video_hint, roles: dict, cutoff: float, title: str = "") -> None:
        """List this tracking file's points to review (the video opens on
        request). Says why instead if the video can't be matched to it."""
        self.cutoff_var.set(f"{cutoff:g}")
        if data is self._data and self.pb is not None:
            self._fill_events()   # same file: just re-flag with the cutoff
            return
        self.unload()
        try:
            pb = open_playback(data, video_hint)
        except ValueError as exc:
            self.show_message(f"This file's video can't be shown.\n\n{exc}")
            return
        self.pb, self._data, self._title = pb, data, title or os.path.basename(pb.video)
        self.events = outside_events(data, roles, pb.fps)
        # The region each frame counted for (outside frames included) and
        # which frames were outside the drawn regions, for the info line.
        self._labels = region_labels(data, roles)[0]
        self._outside = _outside_mask(data)
        self.message.pack_forget()
        self.body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self._fill_events()

    def open_window(self, row: int | None = None) -> PlaybackWindow | None:
        """Open the playback window (or bring it forward), at `row` if given."""
        if self.pb is None:
            return None
        if self.window is None or not self.window.winfo_exists():
            try:
                self.window = PlaybackWindow(self.winfo_toplevel(), self.pb, self._labels,
                                             self._outside, self._title)
            except Exception as exc:
                traceback.print_exc()
                show_warning(self, "The video couldn't be opened",
                             f"The video couldn't be opened.\n\n{exc}")
                return None
        else:
            self.window.lift()
        if row is not None:
            self.window.pause()
            self.window.show(row)
        return self.window

    def pause(self) -> None:
        if self.window is not None and self.window.winfo_exists():
            self.window.pause()

    def unload(self) -> None:
        if self.window is not None and self.window.winfo_exists():
            self.window.close()
        self.window = None
        self.pb = self._data = None
        self.events = []

    def _cutoff(self) -> float:
        try:
            v = float(self.cutoff_var.get())
            return v if v > 0 else 1.0
        except ValueError:
            return 1.0

    def _apply_cutoff(self) -> None:
        value = self._cutoff()
        self.cutoff_var.set(f"{value:g}")
        self.on_cutoff(value)
        self._fill_events()

    def _fill_events(self) -> None:
        self.tree.delete(*self.tree.get_children())
        if self.pb is None:
            return
        pb, cutoff = self.pb, self._cutoff()
        flagged = 0
        for n, e in enumerate(self.events):
            long = e["seconds"] >= cutoff
            flagged += long
            vf = pb.video_frame(e["row"])
            self.tree.insert("", tk.END, iid=str(n), tags=("flag",) if long else (), values=(
                n + 1, f"{e['row'] + 1:,}", clock(e["row"] / pb.fps), f"{vf:,}",
                clock(vf / pb.fps), f"{e['seconds']:g}", e["region"] or "none",
                f"{e['px_outside']:g}", "⚠ check" if long else "brief"))
        total = sum(e["seconds"] for e in self.events)
        if not self.events:
            self.summary.configure(text="The tracked point never left the drawn regions.")
        else:
            longest = max(e["seconds"] for e in self.events)
            self.summary.configure(text=(
                f"Outside the drawn regions {len(self.events)} times, {total:.2f} s in all "
                f"(average {total / len(self.events):.3f} s, longest {longest:g} s). "
                f"{flagged} at or over {cutoff:g} s. Each counts for the region shown; "
                "click a row to see it."))

    def _on_event(self, _e=None) -> None:
        sel = self.tree.selection()
        if sel and self.pb is not None:
            self.open_window(self.events[int(sel[0])]["row"])

