"""The playback window: a tracked file's video with its tracked position drawn
on, to check the tracking (ROADMAP §12, Stage 6, items 7-8).

Play/pause, a scrub slider, frame steps and a speed choice; a red marker on the
tracked position, an optional short trail and region outlines; frame, time
and current region shown, and unreadable frames marked. "Save as video…"
writes `<name>_tracked.mp4` beside the video in the background.
"""

from __future__ import annotations

import os
import threading
import time
import tkinter as tk
import traceback
from tkinter import ttk

from core.playback import FrameSource, Playback, tracked_video_path, write_tracked_video
from dialogs import show_info, show_warning
from setup_window import FrameCanvas
from tooltip import Tooltip

SPEEDS = ("0.25x", "0.5x", "1x", "2x", "4x", "8x")
TRAIL_SECONDS = 1.0
MARKER_COLOR = "#ff2828"
TRAIL_COLOR = "#ffc828"
ROI_COLOR = "#5adc5a"


class PlaybackWindow(tk.Toplevel):
    def __init__(self, parent, pb: Playback, label: str):
        super().__init__(parent)
        self.pb = pb
        self.title(f"Playback: {label}")
        self.geometry("900x720")
        self.minsize(600, 480)
        self.source = FrameSource(pb)
        self.row = 0
        self.playing = False
        self._job = None
        self._clock = None          # (wall time, row) when play started
        self._frame = None
        self._save = None           # (thread, cancel event, progress list) while saving
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<space>", lambda _e: self.toggle())
        self.show(0)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.canvas = FrameCanvas(self)
        self.canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.canvas.redraw_overlay = self._overlay
        self.info = ttk.Label(self, anchor=tk.W, padding=(8, 4))
        self.info.pack(side=tk.TOP, fill=tk.X)

        self.slider = ttk.Scale(self, from_=0, to=max(self.pb.n_frames - 1, 0),
                                orient=tk.HORIZONTAL, command=self._on_slider)
        self.slider.pack(side=tk.TOP, fill=tk.X, padx=8)

        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(side=tk.TOP, fill=tk.X)
        ttk.Button(bar, text="◀", width=3, command=lambda: self.step(-1)).pack(side=tk.LEFT)
        self.play_btn = ttk.Button(bar, text="Play", width=7, command=self.toggle)
        self.play_btn.pack(side=tk.LEFT, padx=4)
        Tooltip(self.play_btn, "Play or pause (space bar).")
        ttk.Button(bar, text="▶", width=3, command=lambda: self.step(1)).pack(side=tk.LEFT)
        ttk.Label(bar, text="Speed:").pack(side=tk.LEFT, padx=(12, 4))
        self.speed_var = tk.StringVar(value="1x")
        speed = ttk.Combobox(bar, textvariable=self.speed_var, values=SPEEDS,
                             state="readonly", width=6)
        speed.pack(side=tk.LEFT)
        speed.bind("<<ComboboxSelected>>", lambda _e: self._restart_clock())
        self.trail_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Trail", variable=self.trail_var,
                        command=self._redraw).pack(side=tk.LEFT, padx=(12, 0))
        self.roi_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Regions", variable=self.roi_var,
                        command=self._redraw).pack(side=tk.LEFT, padx=(8, 0))

        self.save_btn = ttk.Button(bar, text="Save as video…", command=self.save_video)
        self.save_btn.pack(side=tk.RIGHT)
        Tooltip(self.save_btn, f"Write {os.path.basename(tracked_video_path(self.pb.video))} "
                               "next to the video: the session with the marker (and the "
                               "trail and regions, if shown) drawn on, at the video's own "
                               "frame rate. Replaces an earlier one.")
        self.save_text = ttk.Label(bar, foreground="gray")
        self.save_text.pack(side=tk.RIGHT, padx=8)

    # ------------------------------------------------------------- showing
    def _trail_frames(self) -> int:
        return int(round(TRAIL_SECONDS * (self.pb.fps or 20))) if self.trail_var.get() else 0

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
            self._frame = frame
            self.canvas.show(frame)
        else:
            self._redraw()  # keep the last image; the info line says why
        self._set_slider(self.row)
        self._update_info(frame is None)

    def _redraw(self) -> None:
        self.canvas._render()

    def _overlay(self) -> None:
        c, pb, row = self.canvas, self.pb, self.row
        if self.roi_var.get():
            for name, (xs, ys) in pb.regions().items():
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
            r = 6
            c.create_oval(sx - r, sy - r, sx + r, sy + r, fill=MARKER_COLOR,
                          outline="white", width=1)

    def _update_info(self, unread_video: bool = False) -> None:
        pb, row = self.pb, self.row
        parts = [f"Frame {row + 1:,} of {pb.n_frames:,}", pb.time_text(row),
                 f"video frame {pb.video_frame(row):,}"]
        if pb.unreadable(row):
            parts.append("unreadable frame (no position)")
        elif pb.position(row) is None:
            parts.append("no position found")
        elif pb.region(row):
            parts.append(f"region: {pb.region(row)}")
        if unread_video:
            parts.append("the video frame couldn't be read")
        self.info.configure(text="   ·   ".join(parts))

    def _set_slider(self, row: int) -> None:
        self._setting = True
        self.slider.set(row)
        self._setting = False

    def _on_slider(self, value) -> None:
        if getattr(self, "_setting", False):
            return
        row = int(float(value))
        if row != self.row:
            self.show(row)
            self._restart_clock()

    def step(self, delta: int) -> None:
        self.pause()
        self.show(self.row + delta)

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
        if not self.playing or not self.winfo_exists():
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
        if self._save is not None:
            self._save[1].set()  # the button reads Cancel while saving
            return
        cancel = threading.Event()
        state = {"done": 0, "total": self.pb.n_frames, "result": None, "error": None}
        trail, rois = self._trail_frames(), bool(self.roi_var.get())

        def work():
            try:
                state["result"] = write_tracked_video(
                    self.pb, trail_frames=trail, show_regions=rois,
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
