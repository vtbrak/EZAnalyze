"""The video setup window: one video at a time, step by step, before tracking.

Steps (ROADMAP §12, GUI review item 6): 1 Trim and crop, 2 Exclusions,
3 Reference, 4 Tracking check, 5 Regions, 6 Scale. A switcher at the top moves
between the listed videos, and "Start from previous video" copies the
previous video's choices as a draft to check. Finished steps get a check
mark. Next never dead-ends: it moves on, or says what's missing.

Shapes are drawn on images of the video and stored in full-size video pixels
(see core/video_setup.py). Every image has a black border on all sides, so
points can be placed past the video's edge and a region reaches the edge;
shapes are clipped to the frame when used.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np
from matplotlib.path import Path
from PIL import Image, ImageDraw, ImageTk

from core.plotting import _label_points
from core.tracking import METHODS, TrackingParams, locate
from core.video import VideoReader
from core.video_setup import OUTLINE, REGION_TEMPLATES, STEPS
from dialogs import ask_yes_no, show_info, show_warning
from tooltip import Tooltip

STEP_TITLES = {
    "trim": "1  Trim and crop",
    "exclusions": "2  Exclusions",
    "reference": "3  Reference",
    "tracking": "4  Tracking check",
    "regions": "5  Regions",
    "scale": "6  Scale",
}
DOWNSAMPLE_CHOICES = ("1", "0.75", "0.5", "0.25")
# Session length choices in minutes, per test (C5b item 2); others can be typed.
LENGTH_CHOICES = {
    "Elevated Plus Maze": ("5",),
    "Open Field": ("60  (1 hour)", "90  (1.5 hours)"),
}
DEFAULT_MINUTES = {"Elevated Plus Maze": 5.0, "Open Field": 60.0}
MIN_LENGTH_S = 10    # a shorter trial is almost surely a slip: ask before using it
SCALE_GUIDE = {
    "Elevated Plus Maze": "Elevated Plus Maze: 75 cm across, from the end of one arm "
                          "to the end of the opposite arm.",
    "Open Field": "Open Field: 40 cm, from inside corner to inside corner along one wall.",
}
CLOSE_DISTANCE = 10  # screen pixels: clicking this near the first point closes a shape
GRAB_DISTANCE = 8    # screen pixels: clicking this near a point grabs it to drag
SNAP_DISTANCE = 10   # screen pixels: a region point this near another region's point or edge locks onto it
BORDER = 40          # screen pixels of black border around every image
SHAPE_COLOR = "#ff4d4d"
CROP_COLOR = "#2f9bff"
ROLE_COLORS = {"open_arm": "#ff9f1a", "closed_arm": "#2f9bff", "center": "#39d353",
               "outline": "#d36bff"}
OTHER_COLOR = "#cccccc"
SCALE_COLOR = "#ffd23f"
# Filled shapes (regions, exclusions) are 60% transparent, so the arena and
# the other regions show through them (user, 2026-11-05).
FILL_OPACITY = 0.4


def default_session_minutes(config: dict, test: str) -> float:
    """The test's remembered session length, or its standard one if the
    remembered value is too short to be a real session."""
    fallback = DEFAULT_MINUTES.get(test, 5.0)
    m = float(config["session_minutes"].get(test, fallback))
    return m if m * 60 >= MIN_LENGTH_S else fallback


def _number(text: str) -> float:
    """The first number in `text` ("60  (1 hour)" -> 60.0); ValueError if none."""
    return float(str(text).strip().split()[0])


class FrameCanvas(tk.Canvas):
    """Shows one image inside a black border, and converts between screen
    and image pixels. Callers draw overlays in image pixels with the helpers
    below; points may lie in the border (outside the image).

    Zoom: the mouse wheel (or trackpad scroll) zooms in and out at the
    pointer; right-drag, Control-drag or the arrow keys move around when
    zoomed in. `zoom_by` and `reset_view` drive the + / - / Fit buttons."""

    MAX_ZOOM = 16.0

    def __init__(self, parent, **kw):
        super().__init__(parent, background="#000000", highlightthickness=0, **kw)
        self._array = None
        self._photo = None
        self.message = "No image"
        self.scale = 1.0
        self.offset = (0, 0)
        self.zoom = 1.0
        self.center = None             # image point at the middle of the view
        self._pan_from = None
        self.redraw_overlay = lambda: None  # set by the current step
        self.on_view_change = lambda: None  # e.g. to update a zoom label
        self._base_item = None              # the canvas item showing the image
        self._fills = []                    # (screen points, color, tag) to blend in
        self._fill_photo = None
        self._fill_job = None
        self.bind("<Configure>", lambda _e: self._render())
        self.bind("<MouseWheel>", self._wheel)          # Windows and Mac
        self.bind("<Button-4>", lambda e: self.zoom_by(1.25, e.x, e.y))  # Linux
        self.bind("<Button-5>", lambda e: self.zoom_by(0.8, e.x, e.y))
        for press, drag in (("<ButtonPress-2>", "<B2-Motion>"),
                            ("<ButtonPress-3>", "<B3-Motion>"),
                            ("<Control-ButtonPress-1>", "<Control-B1-Motion>")):
            self.bind(press, self._pan_start)
            self.bind(drag, self._pan_move)
        for key, dx, dy in (("<Left>", -1, 0), ("<Right>", 1, 0),
                            ("<Up>", 0, -1), ("<Down>", 0, 1)):
            self.bind(key, lambda _e, dx=dx, dy=dy: self._pan_step(dx, dy))
        self.bind("<Enter>", lambda _e: self.focus_set())

    def show(self, array: np.ndarray | None, message: str = "No image") -> None:
        if (array is None or self._array is None
                or array.shape[:2] != self._array.shape[:2]):
            self.zoom, self.center = 1.0, None   # a different image: start fitted
        self._array = array
        self.message = message
        self._render()

    def reset_view(self) -> None:
        self.zoom, self.center = 1.0, None
        self._render()
        self.on_view_change()

    def _fit_scale(self, w: int, h: int) -> float:
        iw, ih = self.image_size()
        return min(max(w - 2 * BORDER, 20) / iw, max(h - 2 * BORDER, 20) / ih)

    def zoom_by(self, factor: float, sx: float | None = None, sy: float | None = None) -> None:
        """Zoom by `factor`, keeping the image point under (sx, sy) in place
        (the middle of the view if not given)."""
        if self._array is None:
            return
        w, h = max(self.winfo_width(), 50), max(self.winfo_height(), 50)
        sx = w / 2 if sx is None else sx
        sy = h / 2 if sy is None else sy
        ix, iy = self.to_image(sx, sy)
        new_zoom = min(max(self.zoom * factor, 1.0), self.MAX_ZOOM)
        new_scale = self._fit_scale(w, h) * new_zoom
        ox, oy = sx - ix * new_scale, sy - iy * new_scale
        self.zoom = new_zoom
        self.center = ((w / 2 - ox) / new_scale, (h / 2 - oy) / new_scale)
        self._render()
        self.on_view_change()

    def _wheel(self, e) -> None:
        if e.delta:
            self.zoom_by(1.25 if e.delta > 0 else 0.8, e.x, e.y)

    def _pan_start(self, e) -> None:
        self._pan_from = (e.x, e.y)

    def _pan_move(self, e) -> None:
        if self._pan_from is None or self.center is None:
            return
        dx, dy = e.x - self._pan_from[0], e.y - self._pan_from[1]
        self._pan_from = (e.x, e.y)
        self.center = (self.center[0] - dx / self.scale, self.center[1] - dy / self.scale)
        self._render()

    def _pan_step(self, dx: int, dy: int) -> None:
        if self.center is None or self.zoom <= 1.0:
            return
        step = max(self.winfo_width(), 50) / 6 / self.scale
        self.center = (self.center[0] + dx * step, self.center[1] + dy * step)
        self._render()

    def _render(self) -> None:
        self.delete("all")
        w, h = max(self.winfo_width(), 50), max(self.winfo_height(), 50)
        if self._array is None:
            self.create_text(w // 2, h // 2, text=self.message, fill="#bbbbbb",
                             width=max(w - 40, 100), justify=tk.CENTER)
            return
        a = self._array
        if a.dtype != np.uint8:
            a = np.clip(a, 0, 255).astype(np.uint8)
        img = Image.fromarray(a if a.ndim == 2 else cv2.cvtColor(a, cv2.COLOR_BGR2RGB))
        iw, ih = img.width, img.height
        self.scale = self._fit_scale(w, h) * self.zoom
        if self.zoom <= 1.0 or self.center is None:
            self.zoom, self.center = 1.0, (iw / 2, ih / 2)
        # Keep the view on the image (the border may show at the edges).
        cx = min(max(self.center[0], 0), iw)
        cy = min(max(self.center[1], 0), ih)
        self.center = (cx, cy)
        ox, oy = w / 2 - cx * self.scale, h / 2 - cy * self.scale
        self.offset = (ox, oy)
        # Only the visible part of the image is scaled (fast at high zoom).
        x0 = max(0, int(np.floor(-ox / self.scale)))
        y0 = max(0, int(np.floor(-oy / self.scale)))
        x1 = min(iw, int(np.ceil((w - ox) / self.scale)))
        y1 = min(ih, int(np.ceil((h - oy) / self.scale)))
        if x1 > x0 and y1 > y0:
            part = img.crop((x0, y0, x1, y1))
            size = (max(1, int(round((x1 - x0) * self.scale))),
                    max(1, int(round((y1 - y0) * self.scale))))
            resample = Image.NEAREST if self.zoom >= 4 else Image.BILINEAR
            self._photo = ImageTk.PhotoImage(part.resize(size, resample))
            self._base_item = self.create_image(ox + x0 * self.scale, oy + y0 * self.scale,
                                                image=self._photo, anchor="nw")
        # A thin line marks the video's edge inside the black border.
        self.create_rectangle(ox - 1, oy - 1, ox + iw * self.scale, oy + ih * self.scale,
                              outline="#555555")
        self.redraw_overlay()

    def to_image(self, sx: float, sy: float) -> tuple[float, float]:
        return (sx - self.offset[0]) / self.scale, (sy - self.offset[1]) / self.scale

    def to_screen(self, ix: float, iy: float) -> tuple[float, float]:
        return ix * self.scale + self.offset[0], iy * self.scale + self.offset[1]

    def image_size(self) -> tuple[int, int]:
        return (0, 0) if self._array is None else self._array.shape[1::-1]

    def delete(self, *items) -> None:
        """Canvas delete; clearing the overlay (or everything) also drops the
        see-through fills, which the next shapes drawn rebuild."""
        if any(i in ("all", "overlay") for i in items):
            self._fills = []
        super().delete(*items)

    def _schedule_fills(self) -> None:
        if self._fill_job is None:
            self._fill_job = self.after_idle(self._draw_fills)

    def _draw_fills(self) -> None:
        """Blend every filled shape into one see-through image (tkinter can't
        draw partly transparent shapes itself), just above the video image
        and below the outlines, points and labels."""
        self._fill_job = None
        super().delete("fills")
        if not self._fills or not self.winfo_exists():
            return
        w, h = max(self.winfo_width(), 1), max(self.winfo_height(), 1)
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(layer)
        alpha = int(round(255 * FILL_OPACITY))
        for pts, color, _tag in self._fills:
            r, g, b = (v // 257 for v in self.winfo_rgb(color))
            draw.polygon(list(zip(pts[0::2], pts[1::2])), fill=(r, g, b, alpha))
        self._fill_photo = ImageTk.PhotoImage(layer)
        tags = ("fills",) + tuple({t for _p, _c, t in self._fills})
        item = self.create_image(0, 0, image=self._fill_photo, anchor="nw", tags=tags)
        self.tag_lower(item)
        if self._base_item is not None and self.find_withtag(self._base_item):
            self.tag_raise(item, self._base_item)

    def polygon(self, xs, ys, color: str, closed: bool = True, tag: str = "overlay",
                label: str | None = None, label_at: tuple | None = None) -> None:
        pts = [c for x, y in zip(xs, ys) for c in self.to_screen(x, y)]
        if closed and len(xs) >= 3:
            # Outline drawn solid; the fill is blended in 60% transparent.
            self.create_polygon(*pts, outline=color, fill="", width=2, tags=tag)
            self._fills.append((pts, color, tag))
            self._schedule_fills()
        elif len(xs) >= 2:
            self.create_line(*pts, fill=color, width=2, tags=tag)
        for x, y in zip(xs, ys):
            sx, sy = self.to_screen(x, y)
            self.create_oval(sx - 3, sy - 3, sx + 3, sy + 3, outline=color, fill=color, tags=tag)
        if label and xs:
            cx, cy = self.to_screen(*(label_at or (sum(xs) / len(xs), sum(ys) / len(ys))))
            self.create_text(cx, cy, text=label, fill="white", tags=tag,
                             font=("TkDefaultFont", 11, "bold"))

    def rectangle(self, x0, y0, x1, y1, color: str, tag: str = "overlay",
                  dash=(6, 3)) -> None:
        self.create_rectangle(*self.to_screen(x0, y0), *self.to_screen(x1, y1),
                              outline=color, width=2, dash=dash, tags=tag)

    def crosshair(self, x, y, color: str = "#ff2020", tag: str = "overlay") -> None:
        sx, sy = self.to_screen(x, y)
        self.create_line(sx - 12, sy, sx + 12, sy, fill=color, width=2, tags=tag)
        self.create_line(sx, sy - 12, sx, sy + 12, fill=color, width=2, tags=tag)

    def near(self, sx, sy, ix, iy, distance: float) -> bool:
        """True if screen point (sx, sy) is within `distance` of image point (ix, iy)."""
        px, py = self.to_screen(ix, iy)
        return abs(px - sx) <= distance and abs(py - sy) <= distance


class SetupWindow(tk.Toplevel):
    """Set up the listed videos one at a time. `app` is the main window; it
    provides the shared settings (`config_data`), the test type (`test_var`),
    whether tracking settings are locked (`_tracking_locked()`), and
    `_refresh()` to update the file list."""

    def __init__(self, app, entries, index: int = 0):
        super().__init__(app)
        self.app = app
        self.entries = entries          # FileEntry objects for the videos
        self.index = index
        self.step = "trim"
        self.title("Set up videos")
        self.geometry("1040x760")
        self.minsize(860, 600)
        self.transient(app)
        self._scrub_job = None
        self._points: list[tuple[float, float]] = []   # shape being drawn (image px)
        self._drag_start = None
        self._drag = None               # (what, index) of a point being dragged
        self._press = None              # a press on a region point: drag or click?
        self._extra_names: list[str] = []   # added regions not drawn yet

        self._build()
        self._show_video()
        self.protocol("WM_DELETE_WINDOW", self._close)

    # ---------------------------------------------------------------- layout
    def _build(self) -> None:
        top = ttk.Frame(self, padding=(10, 8))
        top.pack(side=tk.TOP, fill=tk.X)
        self.prev_btn = ttk.Button(top, text="◀", width=3, command=lambda: self._move(-1))
        self.prev_btn.pack(side=tk.LEFT)
        self.video_label = ttk.Label(top, font=("TkDefaultFont", 13, "bold"))
        self.video_label.pack(side=tk.LEFT, padx=8)
        self.count_label = ttk.Label(top, foreground="gray")
        self.count_label.pack(side=tk.LEFT)
        self.next_btn = ttk.Button(top, text="▶", width=3, command=lambda: self._move(1))
        self.next_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.copy_btn = ttk.Button(top, text="Start from previous video",
                                   command=self._copy_previous)
        self.copy_btn.pack(side=tk.RIGHT)
        Tooltip(self.copy_btn, "Copy the previous video's session length, crop, "
                               "exclusion shapes, regions, and scale into this one as a "
                               "starting point. Check each step: they're marked not "
                               "done until you go through them.")

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)
        steps = ttk.Frame(body, padding=(10, 4))
        steps.pack(side=tk.LEFT, fill=tk.Y)
        self.step_buttons = {}
        for key in STEPS:
            b = ttk.Button(steps, text=STEP_TITLES[key], width=20,
                           command=lambda k=key: self._go(k))
            b.pack(fill=tk.X, pady=2)
            self.step_buttons[key] = b
        self.info_label = ttk.Label(steps, foreground="gray", wraplength=170,
                                    justify=tk.LEFT)
        self.info_label.pack(fill=tk.X, pady=(16, 0))

        right = ttk.Frame(body, padding=(4, 4, 10, 10))
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.instructions = ttk.Label(right, wraplength=760, justify=tk.LEFT)
        self.instructions.pack(fill=tk.X, pady=(0, 6))
        zoom = ttk.Frame(right)
        zoom.pack(fill=tk.X, pady=(0, 4))
        self.canvas = FrameCanvas(right)
        ttk.Label(zoom, text="Zoom:").pack(side=tk.LEFT)
        for text, cmd in (("−", lambda: self.canvas.zoom_by(0.8)),
                          ("+", lambda: self.canvas.zoom_by(1.25)),
                          ("Fit", self.canvas.reset_view)):
            ttk.Button(zoom, text=text, width=4 if text != "Fit" else 5,
                       command=cmd).pack(side=tk.LEFT, padx=(4, 0))
        self.zoom_text = ttk.Label(zoom, foreground="gray")
        self.zoom_text.pack(side=tk.LEFT, padx=(10, 0))
        self.canvas.on_view_change = self._update_zoom_text
        self._update_zoom_text()
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.controls = ttk.Frame(right)
        self.controls.pack(fill=tk.X, pady=(8, 0))
        nav = ttk.Frame(right)
        nav.pack(fill=tk.X, pady=(8, 0))
        self.back_btn = ttk.Button(nav, text="Back", command=lambda: self._step_by(-1))
        self.back_btn.pack(side=tk.LEFT)
        self.done_btn = ttk.Button(nav, text="Close", command=self._close)
        self.done_btn.pack(side=tk.RIGHT)
        Tooltip(self.done_btn, "Close the setup window. Everything set so far is kept.")
        self.next_step_btn = ttk.Button(nav, command=lambda: self._step_by(1))
        self.next_step_btn.pack(side=tk.RIGHT, padx=(0, 6))

    def _update_zoom_text(self) -> None:
        z = self.canvas.zoom
        self.zoom_text.configure(text=(
            f"{z * 100:.0f}%. Scroll to zoom at the pointer"
            + ("; right-drag, Control-drag, or the arrow keys move around." if z > 1
               else ".")))

    # --------------------------------------------------------------- helpers
    @property
    def entry(self):
        return self.entries[self.index]

    @property
    def setup(self):
        return self.entry.video

    def _test(self) -> str:
        return self.app.test_var.get()

    def _dsmpl(self) -> float:
        return float(self.app.config_data["video_downsample"])

    def _ref_frames(self) -> int:
        return int(self.app.config_data["reference_frames"])

    def _locked(self) -> bool:
        return self.app._tracking_locked()

    def _secs(self, frame: int) -> str:
        fps = self.setup.info.fps or 0
        return f"{frame / fps:.1f} s" if fps else "? s"

    def _clear_controls(self) -> None:
        if self._scrub_job is not None:
            self.after_cancel(self._scrub_job)
            self._scrub_job = None
        for child in self.controls.winfo_children():
            child.destroy()
        for seq in ("<Button-1>", "<B1-Motion>", "<ButtonRelease-1>", "<Double-Button-1>",
                    "<Motion>"):
            self.canvas.unbind(seq)
        self.canvas.redraw_overlay = lambda: None
        self._drag = None

    def _mark(self, step: str) -> None:
        self.setup.steps_done.add(step)
        self._update_step_list()
        self.app._refresh()

    def _update_step_list(self) -> None:
        for key, b in self.step_buttons.items():
            mark = "✓ " if key in self.setup.steps_done else "   "
            b.configure(text=mark + STEP_TITLES[key])
            b.state(["pressed"] if key == self.step else ["!pressed"])

    def _reference_ok(self) -> bool:
        return self.setup.reference_current(self._dsmpl(), self._ref_frames())

    def _prepared_image(self) -> np.ndarray | None:
        """What regions and scale are drawn on: the reference when it's up to
        date, else the trial's first frame prepared the same way."""
        if self._reference_ok():
            return self.setup.reference
        with VideoReader(self.setup.path, self.setup.prep(self._dsmpl())) as r:
            return r.read_at(self.setup.start)

    def _to_image(self, xs, ys):
        """Full-size pixels -> prepared-image pixels (what the canvas shows)."""
        return self.setup.to_prepared(xs, ys, self._dsmpl())

    def _to_full(self, xs, ys):
        return self.setup.from_prepared(xs, ys, self._dsmpl())

    # ------------------------------------------------------------ navigation
    def _show_video(self) -> None:
        s = self.setup
        if s.length_s is None:
            s.length_s = self._default_minutes() * 60
        self.video_label.configure(text=self.entry.label)
        self.count_label.configure(text=f"video {self.index + 1} of {len(self.entries)}")
        self.prev_btn.configure(state="normal" if self.index > 0 else "disabled")
        self.next_btn.configure(state="normal" if self.index < len(self.entries) - 1
                                else "disabled")
        self.copy_btn.configure(state="normal" if self.index > 0 else "disabled")
        info = s.info
        bad, checked = s.unreadable
        text = (f"{info.width} × {info.height} px\n{info.frame_count:,} frames\n"
                f"{info.fps:.2f} fps\n{info.frame_count / info.fps / 60:.1f} min"
                if info.fps else f"{info.width} × {info.height} px")
        if bad:
            text += f"\n\n{bad} of the first {checked} frames couldn't be read."
        self.info_label.configure(text=text)
        self._go(self.step)

    def _move(self, delta: int, step: str | None = None) -> None:
        self._points = []
        self.index = max(0, min(len(self.entries) - 1, self.index + delta))
        if step:
            self.step = step
        self._show_video()
        self.app._refresh()

    def _go(self, step: str) -> None:
        self._points = []
        self.step = step
        self._clear_controls()
        {"trim": self._step_trim, "exclusions": self._step_exclusions,
         "reference": self._step_reference, "tracking": self._step_tracking,
         "regions": self._step_regions, "scale": self._step_scale}[step]()
        k = STEPS.index(step)
        self.back_btn.configure(state="normal" if k > 0 else "disabled")
        if k < len(STEPS) - 1:
            nxt = STEP_TITLES[STEPS[k + 1]].split("  ", 1)[1]
            self.next_step_btn.configure(text=f"Next: {nxt.lower()}")
        elif self.index < len(self.entries) - 1:
            self.next_step_btn.configure(text="Next video")
        else:
            self.next_step_btn.configure(text="Finish")
        self._update_step_list()

    def _step_by(self, delta: int) -> None:
        """Back always works. Next checks the current step first: it either
        moves on or says what's missing (never a dead end)."""
        k = STEPS.index(self.step)
        if delta < 0:
            self._go(STEPS[max(0, k - 1)])
            return
        if not self._finish_step():
            return
        if k < len(STEPS) - 1:
            self._go(STEPS[k + 1])
        elif self.index < len(self.entries) - 1:
            self._move(1, step="trim")
        else:
            self._close()

    def _finish_step(self) -> bool:
        """Check and mark the current step; False (after saying why) if it
        can't be left yet."""
        s, step = self.setup, self.step
        if step == "trim":
            if not self._apply_length():
                return False
        elif step == "exclusions":
            if len(self._points) >= 3:
                self._finish_shape()
            self._points = []
        elif step == "reference":
            if not self._reference_ok():
                show_info(self, "Make the reference first",
                          "Click Make reference to build the picture of the empty arena. "
                          "Tracking compares every frame to it, so it's needed before "
                          "the next step." if s.reference is None else
                          "The trim, crop, or settings changed since the reference was "
                          "made. Click Make reference to make it again.")
                return False
        elif step == "tracking":
            if not self._reference_ok():
                show_info(self, "Make the reference first",
                          "The tracking check needs an up-to-date reference. Go back to "
                          "step 3 and click Make reference.")
                return False
            if self._read_params(save=True) is None:
                return False
        elif step == "regions":
            if len(self._points) >= 3:
                self._close_region()
            self._points = []
            missing = s.missing_regions(self._test())
            if missing and not ask_yes_no(
                    self, "Some regions aren't drawn",
                    f"Not drawn yet: {', '.join(missing)}. Without them, this video's "
                    f"{self._test()} measures can't all be worked out (distance and "
                    "plots still can). Go on anyway?"):
                return False
        elif step == "scale":
            if not self._apply_cm():
                return False
            if s.scale(self._dsmpl()) is None and not ask_yes_no(
                    self, "No scale set",
                    "Without a scale, distance and speed are in pixels only and the cm "
                    "measures are blank. Go on without a scale?"):
                return False
        self._mark(step)
        return True

    def _copy_previous(self) -> None:
        if self.index == 0:
            return
        self.setup.copy_from(self.entries[self.index - 1].video)
        self._go("trim")
        self.app._refresh()

    def _close(self) -> None:
        if self._scrub_job is not None:
            self.after_cancel(self._scrub_job)
        self.app._refresh()
        self.destroy()

    # ------------------------------------------------------ shared scrubbing
    def _make_scrub(self, parent, lo: int, hi: int, value: int, on_load) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=tk.X)
        self._on_load = on_load
        self.frame_text = ttk.Label(row, width=22, anchor="e")
        self.frame_text.pack(side=tk.RIGHT, padx=(8, 0))
        # Frame-by-frame steps (the slider alone moves many frames per pixel).
        steps = ttk.Frame(row)
        steps.pack(side=tk.RIGHT, padx=(8, 0))
        for text, delta, tip in (("◀◀", -10, "Back 10 frames"), ("◀", -1, "Back 1 frame"),
                                 ("▶", 1, "Forward 1 frame"), ("▶▶", 10, "Forward 10 frames")):
            btn = ttk.Button(steps, text=text, width=3,
                             command=lambda d=delta: self._step_frames(d))
            btn.pack(side=tk.LEFT)
            Tooltip(btn, tip + ". The , and . keys step one frame too.")
        self._scrub_range = (lo, max(lo, hi))
        self.scrub = ttk.Scale(row, from_=lo, to=max(lo, hi), orient=tk.HORIZONTAL)
        self.scrub.set(value)
        self.scrub.configure(command=lambda _v: self._on_scrub())
        self.scrub.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.bind("<comma>", lambda _e: self._step_frames(-1))
        self.bind("<period>", lambda _e: self._step_frames(1))

    def _step_frames(self, delta: int) -> None:
        """Move the scrub slider by `delta` frames and show that frame now."""
        if not getattr(self, "scrub", None) or not self.scrub.winfo_exists():
            return
        focus = self.focus_get()
        if delta in (-1, 1) and isinstance(focus, (tk.Entry, ttk.Entry)):
            return  # typing in a box (e.g. "1.5"): the key is text, not a step
        lo, hi = self._scrub_range
        self.scrub.set(min(max(self._current_frame() + delta, lo), hi))
        self._load_scrub_frame()

    def _on_scrub(self) -> None:
        if self._scrub_job is not None:
            self.after_cancel(self._scrub_job)
        self._scrub_job = self.after(80, self._load_scrub_frame)
        self._update_frame_text()

    def _current_frame(self) -> int:
        return int(round(float(self.scrub.get())))

    def _update_frame_text(self) -> None:
        f = self._current_frame()
        self.frame_text.configure(text=f"Frame {f:,} ({self._secs(f)})")

    def _load_scrub_frame(self) -> None:
        if self._scrub_job is not None:   # called directly: drop the pending load
            self.after_cancel(self._scrub_job)
        self._scrub_job = None
        self._update_frame_text()
        self._on_load()

    # --------------------------------------------------- step 1: trim + crop
    def _default_minutes(self) -> float:
        """The test's remembered session length (its standard one if the
        remembered value is too short to be a real session)."""
        return default_session_minutes(self.app.config_data, self._test())

    def _show_length(self, minutes: float) -> None:
        """Put a length in the box, remembering exactly what was shown so a
        rounded display is never read back as a new length."""
        text = f"{minutes:.2f}".rstrip("0").rstrip(".") if minutes >= 0.01 else f"{minutes:.4g}"
        self._length_shown = text
        self.length_var.set(text)

    def _step_trim(self) -> None:
        s = self.setup
        self.instructions.configure(text=(
            "Scrub to where the trial starts and click Set start here: that frame is "
            "time 0 of the analysis. The trial then runs for the session length (type "
            "another length, or scrub to the end and click Set end here). Then drag a "
            "box around the arena to crop to it: tracking ignores everything outside "
            "the box (optional)."))
        self._make_scrub(self.controls, 0, s.info.frame_count - 1, s.start,
                         self._show_trim_frame)

        row = ttk.Frame(self.controls)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(row, text="Set start here", command=self._set_start).pack(side=tk.LEFT)
        self.start_text = ttk.Label(row)
        self.start_text.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(row, text="Clear crop", command=self._clear_crop).pack(side=tk.RIGHT)
        ds = ttk.Frame(row)
        ds.pack(side=tk.RIGHT, padx=(0, 16))
        ttk.Label(ds, text="Downsample:").pack(side=tk.LEFT)
        self.ds_var = tk.StringVar(value=f"{self._dsmpl():g}")
        box = ttk.Combobox(ds, textvariable=self.ds_var, values=DOWNSAMPLE_CHOICES,
                           width=5, state="disabled" if self._locked() else "readonly")
        box.pack(side=tk.LEFT, padx=(4, 0))
        box.bind("<<ComboboxSelected>>", lambda _e: self._set_dsmpl())
        Tooltip(box, lambda: self.app.LOCKED_TRACKING_TIP if self._locked() else
                "Shrink each frame before tracking to go faster (1 = full size). "
                "Applies to every video, and locks at the first Track.")

        row2 = ttk.Frame(self.controls)
        row2.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row2, text="Session length (min):").pack(side=tk.LEFT)
        self.length_var = tk.StringVar()
        self._show_length((s.length_s or 0) / 60)
        length_box = ttk.Combobox(row2, textvariable=self.length_var, width=16,
                                  values=LENGTH_CHOICES.get(self._test(), ()))
        length_box.pack(side=tk.LEFT, padx=(4, 6))
        length_box.bind("<<ComboboxSelected>>", lambda _e: self._apply_length())
        length_box.bind("<Return>", lambda _e: self._apply_length())
        length_box.bind("<FocusOut>", lambda _e: self._apply_length(quiet=True))
        Tooltip(length_box, "How long the trial lasts, from the start. Pick a "
                            "length or type one and press Return.")
        ttk.Button(row2, text="Set end here", command=self._set_end).pack(side=tk.LEFT)
        self.end_text = ttk.Label(row2)
        self.end_text.pack(side=tk.LEFT, padx=(8, 0))

        self.canvas.bind("<Button-1>", self._crop_press)
        self.canvas.bind("<B1-Motion>", self._crop_drag)
        self.canvas.bind("<ButtonRelease-1>", self._crop_release)
        self.canvas.redraw_overlay = self._draw_crop
        self._update_trim_text()
        self._load_scrub_frame()

    def _show_trim_frame(self) -> None:
        with VideoReader(self.setup.path) as r:
            frame = r.read_at(self._current_frame(), raw=True)
        self.canvas.show(frame)

    def _update_trim_text(self) -> None:
        s = self.setup
        self.start_text.configure(text=f"Start: frame {s.start:,} ({self._secs(s.start)})")
        end = s.end_frame
        text = f"Ends at frame {end:,} ({self._secs(end)})"
        color = ""
        if s.video_shorter_than_length():
            mins = (end - s.start) / s.info.fps / 60
            text += f". The video ends first: the trial is {mins:.1f} min."
            color = "#b26a00"
        self.end_text.configure(text=text, foreground=color)

    def _apply_length(self, quiet: bool = False) -> bool:
        """Use the typed session length. False (after a warning) if invalid.
        `quiet` (leaving the box) never warns or asks; it only applies a
        sensible new length."""
        text = self.length_var.get().strip()
        if text == getattr(self, "_length_shown", None):
            return True  # unchanged: keep the exact length (it may be a scrubbed one)
        try:
            minutes = _number(text)
            if minutes <= 0:
                raise ValueError
        except (ValueError, IndexError):
            if not quiet:
                show_warning(self, "Invalid session length",
                             "The session length must be a number of minutes above 0, "
                             "such as 5 or 60.")
            return False
        if minutes * 60 < MIN_LENGTH_S:
            if quiet or not ask_yes_no(
                    self, "Very short session",
                    f"A session of {minutes * 60:.1f} s is very short. Use it anyway?"):
                return False
        s = self.setup
        s.length_s = minutes * 60
        if minutes * 60 >= MIN_LENGTH_S:  # only real session lengths are remembered
            self.app.config_data["session_minutes"][self._test()] = minutes
        self._show_length(minutes)
        self._update_trim_text()
        self.app._refresh()
        return True

    def _set_start(self) -> None:
        f = self._current_frame()
        s = self.setup
        if f >= s.info.frame_count - 1:
            show_warning(self, "Start is at the end",
                         "The start has to come before the last frame of the video.")
            return
        if s.length_s is None and f >= s.end_frame:
            show_warning(self, "Start is after the end",
                         "The start has to come before the end. Move the end first.")
            return
        s.start = f
        self._update_trim_text()
        self.app._refresh()

    def _set_end(self) -> None:
        s = self.setup
        f = self._current_frame() + 1  # the frame shown is the trial's last
        if f <= s.start:
            show_warning(self, "End is before the start",
                         "The end has to come after the start. Move the start first.")
            return
        if s.info.fps:
            length = (f - s.start) / s.info.fps
            if length < MIN_LENGTH_S and not ask_yes_no(
                    self, "Very short session",
                    f"The end would be only {length:.1f} s ({f - s.start} frames) after the "
                    "start. To set the end, scrub to where the trial ends first, then "
                    "click Set end here. Use this end anyway?"):
                return
            s.length_s = length
            self._show_length(length / 60)
        else:
            s.length_s, s.end = None, f
        self._update_trim_text()
        self.app._refresh()

    def _set_dsmpl(self) -> None:
        self.app.config_data["video_downsample"] = float(self.ds_var.get())
        self.app._refresh()

    def _draw_crop(self) -> None:
        c = self.setup.crop
        if c:
            self.canvas.rectangle(*c, color=CROP_COLOR)

    def _clamp(self, x, y):
        """Keep a crop corner inside the video (a crop can't go past the edge)."""
        w, h = self.canvas.image_size()
        return min(max(x, 0), w), min(max(y, 0), h)

    def _crop_press(self, e) -> None:
        self._drag_start = self._clamp(*self.canvas.to_image(e.x, e.y))

    def _crop_drag(self, e) -> None:
        if self._drag_start is None:
            return
        x, y = self._clamp(*self.canvas.to_image(e.x, e.y))
        self.canvas.delete("overlay")
        self.canvas.rectangle(*self._drag_start, x, y, color=CROP_COLOR)

    def _crop_release(self, e) -> None:
        if self._drag_start is None:
            return
        x0, y0 = self._drag_start
        x1, y1 = self._clamp(*self.canvas.to_image(e.x, e.y))
        self._drag_start = None
        if abs(x1 - x0) < 10 or abs(y1 - y0) < 10:
            self.canvas.delete("overlay")
            self._draw_crop()
            return  # a click, not a box
        self.setup.crop = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        self.canvas.delete("overlay")
        self._draw_crop()
        self.app._refresh()

    def _clear_crop(self) -> None:
        self.setup.crop = None
        self.canvas.delete("overlay")
        self.app._refresh()

    # --------------------------------------------------- step 2: exclusions
    def _cropped_frame(self) -> np.ndarray | None:
        """The trial's first frame, cropped, at full size (exclusions are
        drawn on it; image pixels + crop corner = full-size pixels)."""
        with VideoReader(self.setup.path) as r:
            frame = r.read_at(self.setup.start, raw=True)
        if frame is None or not self.setup.crop:
            return frame
        x0, y0, x1, y1 = (int(v) for v in self.setup.crop)
        return frame[y0:y1, x0:x1]

    def _crop_corner(self) -> tuple[float, float]:
        c = self.setup.crop
        return (int(c[0]), int(c[1])) if c else (0, 0)

    def _step_exclusions(self) -> None:
        self.instructions.configure(text=(
            "Draw a shape around anything tracking should ignore, such as a cable or "
            "an object in the arena. Click to place points; click the first point "
            "(or double-click) to close the shape. Points can go in the black border, "
            "so a shape reaches the video's edge. Draw as many as you need, or none."))
        row = ttk.Frame(self.controls)
        row.pack(fill=tk.X)
        ttk.Button(row, text="Undo point", command=self._undo_point).pack(side=tk.LEFT)
        ttk.Button(row, text="Delete last shape",
                   command=self._delete_shape).pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(row, text="Clear all", command=self._clear_shapes).pack(side=tk.LEFT,
                                                                           padx=(6, 0))
        self.shape_text = ttk.Label(row, foreground="gray")
        self.shape_text.pack(side=tk.LEFT, padx=(12, 0))
        self.canvas.bind("<Button-1>", self._shape_click)
        self.canvas.bind("<Double-Button-1>", lambda _e: self._finish_shape())
        self.canvas.redraw_overlay = self._draw_shapes
        self.canvas.show(self._cropped_frame())
        self._update_shape_text()

    def _draw_shapes(self) -> None:
        cx, cy = self._crop_corner()
        for xs, ys in self.setup.exclusions:
            self.canvas.polygon([x - cx for x in xs], [y - cy for y in ys], SHAPE_COLOR)
        if self._points:
            self.canvas.polygon([p[0] for p in self._points], [p[1] for p in self._points],
                                SHAPE_COLOR, closed=False)

    def _redraw_shapes(self) -> None:
        self.canvas.delete("overlay")
        self._draw_shapes()
        self._update_shape_text()

    def _update_shape_text(self) -> None:
        n = len(self.setup.exclusions)
        self.shape_text.configure(text=f"{n} shape{'s' if n != 1 else ''}"
                                  + (" (drawing…)" if self._points else ""))

    def _shape_click(self, e) -> None:
        x, y = self.canvas.to_image(e.x, e.y)  # may be in the border: kept as placed
        if len(self._points) >= 3 and self.canvas.near(e.x, e.y, *self._points[0],
                                                       CLOSE_DISTANCE):
            self._finish_shape()
            return
        self._points.append((x, y))
        self._redraw_shapes()

    def _finish_shape(self) -> None:
        if len(self._points) >= 3:
            cx, cy = self._crop_corner()
            self.setup.exclusions.append(([p[0] + cx for p in self._points],
                                          [p[1] + cy for p in self._points]))
            self.app._refresh()
        self._points = []
        self._redraw_shapes()

    def _undo_point(self) -> None:
        if self._points:
            self._points.pop()
            self._redraw_shapes()

    def _delete_shape(self) -> None:
        if self._points:
            self._points = []
        elif self.setup.exclusions:
            self.setup.exclusions.pop()
            self.app._refresh()
        self._redraw_shapes()

    def _clear_shapes(self) -> None:
        self._points = []
        self.setup.exclusions.clear()
        self._redraw_shapes()
        self.app._refresh()

    # ---------------------------------------------------- step 3: reference
    def _step_reference(self) -> None:
        self.instructions.configure(text=(
            "Tracking compares every frame to a picture of the empty arena, made from "
            "frames spread across the trial (the animal is somewhere different in "
            "most of them, so it drops out). Click Make reference. If a faint animal "
            "shows in it, the animal stayed still for much of the trial: try more "
            "frames or a different trim."))
        row = ttk.Frame(self.controls)
        row.pack(fill=tk.X)
        ttk.Label(row, text="Frames to use:").pack(side=tk.LEFT)
        self.ref_var = tk.StringVar(value=str(self._ref_frames()))
        spin = ttk.Spinbox(row, from_=10, to=500, increment=10, width=6,
                           textvariable=self.ref_var,
                           state="disabled" if self._locked() else "normal")
        spin.pack(side=tk.LEFT, padx=(4, 12))
        Tooltip(spin, lambda: self.app.LOCKED_TRACKING_TIP if self._locked() else
                "How many frames the reference is made from. Applies to every video, "
                "and locks at the first Track.")
        ttk.Button(row, text="Make reference", command=self._make_reference).pack(side=tk.LEFT)
        self.ref_text = ttk.Label(row, foreground="gray")
        self.ref_text.pack(side=tk.LEFT, padx=(12, 0))
        self._show_reference()

    def _show_reference(self) -> None:
        s = self.setup
        self.canvas.show(s.reference, message="No reference yet. Click Make reference.")
        n = s.end_frame - s.start
        trial = f"Trial: {n:,} frames ({self._secs(n)}). "
        if self._reference_ok():
            text = trial + "Reference is up to date."
        else:
            text = trial + ("No reference yet." if s.reference is None else
                            "The trim, crop, or settings changed since this was made. "
                            "Make it again.")
        short = n < self._ref_frames()
        if short:
            text += (" The trial is shorter than the frames used, so the reference "
                     "can't hide the animal: check the trim in step 1.")
        self.ref_text.configure(text=text, foreground="#b26a00" if short else "gray")

    def _make_reference(self) -> None:
        try:
            frames = int(float(self.ref_var.get()))
            if frames < 3:
                raise ValueError
        except ValueError:
            show_warning(self, "Invalid frame count",
                         "Frames to use must be a whole number, 3 or more.")
            return
        if not self._locked():
            self.app.config_data["reference_frames"] = frames
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.setup.build_reference(self._dsmpl(), self._ref_frames())
        except Exception as exc:  # report, keep the window usable
            show_warning(self, "Couldn't make the reference", str(exc))
            return
        finally:
            self.config(cursor="")
        self._mark("reference")
        self._show_reference()

    # ----------------------------------------------- step 4: tracking check
    def _step_tracking(self) -> None:
        s = self.setup
        self.instructions.configure(text=(
            "Check that tracking finds the animal: scrub through the trial and look for "
            "the red cross on the animal. If it's off, change the settings below and "
            "the preview updates. Differences shows what tracking sees (bright = "
            "different from the reference). These settings apply to every video and "
            "lock at the first Track."))
        cfg = self.app.config_data
        locked = self._locked()
        self._make_scrub(self.controls, s.start, s.end_frame - 1, s.start, self._preview)

        row = ttk.Frame(self.controls)
        row.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(row, text="Show:").pack(side=tk.LEFT)
        self.view_var = tk.StringVar(value="frame")
        for text, value in (("Frame", "frame"), ("Differences", "dif")):
            ttk.Radiobutton(row, text=text, value=value, variable=self.view_var,
                            command=self._preview).pack(side=tk.LEFT, padx=(4, 0))
        self.found_text = ttk.Label(row, foreground="gray")
        self.found_text.pack(side=tk.LEFT, padx=(16, 0))

        row2 = ttk.Frame(self.controls)
        row2.pack(fill=tk.X, pady=(6, 0))
        state = "disabled" if locked else "normal"
        self.method_var = tk.StringVar(value=cfg["track_method"])
        self.thresh_var = tk.StringVar(value=f"{cfg['loc_thresh']:g}")
        self.window_var = tk.BooleanVar(value=cfg["use_window"])
        self.wsize_var = tk.StringVar(value=str(cfg["window_size"]))
        self.wweight_var = tk.StringVar(value=f"{cfg['window_weight']:g}")
        ttk.Label(row2, text="Animal is:").pack(side=tk.LEFT)
        method = ttk.Combobox(row2, textvariable=self.method_var, values=METHODS, width=6,
                              state="disabled" if locked else "readonly")
        method.pack(side=tk.LEFT, padx=(4, 12))
        method.bind("<<ComboboxSelected>>", lambda _e: self._preview())
        ttk.Label(row2, text="Threshold (%):").pack(side=tk.LEFT)
        thresh = ttk.Entry(row2, textvariable=self.thresh_var, width=6, state=state)
        thresh.pack(side=tk.LEFT, padx=(4, 12))
        window = ttk.Checkbutton(row2, text="Window", variable=self.window_var,
                                 command=self._preview, state=state)
        window.pack(side=tk.LEFT)
        ttk.Label(row2, text="size (px):").pack(side=tk.LEFT, padx=(6, 0))
        wsize = ttk.Entry(row2, textvariable=self.wsize_var, width=5, state=state)
        wsize.pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(row2, text="weight:").pack(side=tk.LEFT)
        wweight = ttk.Entry(row2, textvariable=self.wweight_var, width=5, state=state)
        wweight.pack(side=tk.LEFT, padx=(4, 12))
        ttk.Button(row2, text="Update preview", command=self._preview).pack(side=tk.LEFT)
        for w in (thresh, wsize, wweight):
            w.bind("<Return>", lambda _e: self._preview())
        for widget, tip in (
            (method, "dark: the animal is darker than the floor. light: lighter. "
                     "abs: either."),
            (thresh, "Only pixels more different from the reference than this "
                     "percentage of all pixels count toward the animal (ezTrack's "
                     "default 99.5). Lower it if the cross misses a small or faint "
                     "animal; raise it if it jumps to noise."),
            (window, "Favor the area around the animal's last position, so a "
                     "shadow or reflection elsewhere can't pull the cross away."),
            (wsize, "Width of that area, in full-size video pixels. Should fit the "
                    "animal comfortably, with room to move between frames."),
            (wweight, "How strongly everything outside the area is ignored (0 = not "
                      "at all, 1 = completely). ezTrack's default 0.9."),
        ):
            Tooltip(widget, lambda t=tip: self.app.LOCKED_TRACKING_TIP if self._locked() else t)
        self.canvas.redraw_overlay = self._draw_found
        self._found = None
        self._load_scrub_frame()

    def _read_params(self, save: bool = False) -> TrackingParams | None:
        """The tracking settings from the boxes (saved to the shared settings
        unless locked); None after a warning if one is invalid."""
        cfg = self.app.config_data
        if self._locked():
            return self._params_from_config()
        try:
            thresh = float(self.thresh_var.get())
            size = int(float(self.wsize_var.get()))
            weight = float(self.wweight_var.get())
            if not (0 < thresh < 100 and size > 0 and 0 <= weight <= 1):
                raise ValueError
        except ValueError:
            show_warning(self, "Invalid tracking setting",
                         "Threshold must be between 0 and 100, window size a whole number "
                         "above 0, and window weight between 0 and 1.")
            return None
        cfg.update(loc_thresh=thresh, track_method=self.method_var.get(),
                   use_window=bool(self.window_var.get()), window_size=size,
                   window_weight=weight)
        if save:
            self.app._refresh()
        return self._params_from_config()

    def _params_from_config(self) -> TrackingParams:
        cfg = self.app.config_data
        return TrackingParams(loc_thresh=cfg["loc_thresh"], method=cfg["track_method"],
                              use_window=cfg["use_window"], window_size=cfg["window_size"],
                              window_weight=cfg["window_weight"])

    def _preview(self) -> None:
        """Find the animal in the frame shown. With the window on, the few
        frames before it are tracked first so the window has a last position,
        as in a real run."""
        s = self.setup
        self._found = None
        if not self._reference_ok():
            self.canvas.show(None, message=(
                "Make the reference first (step 3)." if s.reference is None else
                "The reference is out of date. Make it again in step 3."))
            self.found_text.configure(text="")
            return
        params = self._read_params()
        if params is None:
            return
        d = self._dsmpl()
        f = self._current_frame()
        mask = s.exclusion_mask(d)
        prior = used = None
        frame = dif = None
        y = x = np.nan
        with VideoReader(s.path, s.prep(d)) as r:
            first = max(s.start, f - 15) if params.use_window else f
            for _i, fr in r.frames(first, f + 1):
                frame = fr
                if fr is None:
                    continue
                used = prior
                y, x, dif = locate(fr, s.reference, params, mask, prior, d)
                if np.isfinite(x) and np.isfinite(y):
                    prior = (int(np.around(y)), int(np.around(x)))
        if frame is None:
            self.canvas.show(None, message=f"Frame {f:,} couldn't be read.")
            self.found_text.configure(text="")
            return
        self._found = (x, y, used if params.use_window else None, params)
        if self.view_var.get() == "dif" and dif is not None:
            dd = np.asarray(dif, dtype=float)
            dd = dd - dd.min()
            top = dd.max()
            gray = (dd / top * 255).astype(np.uint8) if top > 0 else dd.astype(np.uint8)
            self.canvas.show(cv2.applyColorMap(gray, cv2.COLORMAP_JET))
        else:
            self.canvas.show(frame)
        self.found_text.configure(text=(
            f"Animal found at x {x:.0f}, y {y:.0f}" if np.isfinite(x) else
            "No animal found in this frame."))

    def _draw_found(self) -> None:
        if not self._found:
            return
        x, y, prior, params = self._found
        if prior is not None and params.use_window:
            half = params.window_size * min(self._dsmpl(), 1.0) / 2
            py, px = prior
            self.canvas.rectangle(px - half, py - half, px + half, py + half,
                                  color="#ffd23f", dash=(4, 3))
        if np.isfinite(x) and np.isfinite(y):
            self.canvas.crosshair(x, y)

    # ---------------------------------------------------- step 5: regions
    def _region_role(self, name: str) -> str:
        for n, role in REGION_TEMPLATES.get(self._test(), []):
            if n == name:
                return role
        return "other"

    def _region_names(self) -> list[str]:
        """The test's regions in order, then any others drawn."""
        names = [n for n, _ in REGION_TEMPLATES.get(self._test(), [])]
        names += [n for n in self.setup.regions if n not in names]
        return names + [n for n in self._extra_names if n not in names]

    def _step_regions(self) -> None:
        test = self._test()
        extra = ("Draw the arena outline (inside the walls) and the center; the "
                 "periphery is the outline minus the center, so they can't overlap. "
                 if test == "Open Field" else
                 "Arms may overlap the center; those frames count as center. ")
        self.instructions.configure(text=(
            f"Draw the {test} regions on the reference. Pick a region in the list, "
            "then click points around it; click the first point (or double-click) to "
            "close it. Drag a point to move it. A point placed near another region's "
            "point or edge locks onto it (a ring shows where), so neighboring regions "
            "share their border without overlapping; locked points move together. "
            "Points can go in the black border, so a region reaches the video's edge. "
            f"{extra}Zoom in for precision. The test type is set in the main window."))
        row = ttk.Frame(self.controls)
        row.pack(fill=tk.X)
        self.region_list = ttk.Treeview(row, columns=("region", "status"), show="headings",
                                        height=5, selectmode="browse")
        self.region_list.heading("region", text="Region")
        self.region_list.heading("status", text="")
        self.region_list.column("region", width=180)
        self.region_list.column("status", width=90)
        self.region_list.pack(side=tk.LEFT)
        self.region_list.bind("<<TreeviewSelect>>", lambda _e: self._region_selected())

        side = ttk.Frame(row)
        side.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0))
        b1 = ttk.Frame(side)
        b1.pack(fill=tk.X)
        ttk.Button(b1, text="Redraw", command=self._redraw_region).pack(side=tk.LEFT)
        ttk.Button(b1, text="Undo point", command=self._undo_region_point).pack(
            side=tk.LEFT, padx=(6, 0))
        ttk.Button(b1, text="Delete", command=self._delete_region).pack(side=tk.LEFT,
                                                                        padx=(6, 0))
        b2 = ttk.Frame(side)
        b2.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(b2, text="Name:").pack(side=tk.LEFT)
        self.region_name_var = tk.StringVar()
        ttk.Entry(b2, textvariable=self.region_name_var, width=18).pack(side=tk.LEFT,
                                                                       padx=(4, 6))
        rename = ttk.Button(b2, text="Rename", command=self._rename_region)
        rename.pack(side=tk.LEFT)
        add = ttk.Button(b2, text="Add region", command=self._add_region)
        add.pack(side=tk.LEFT, padx=(6, 0))
        Tooltip(add, "Add another region with the name typed. Its role (open arm, "
                     "center, ignore, ...) is chosen with Regions… in the main window.")
        self.snap_var = tk.BooleanVar(value=True)
        snap = ttk.Checkbutton(side, text="Lock onto other regions' points and edges",
                               variable=self.snap_var)
        snap.pack(anchor="w", pady=(6, 0))
        Tooltip(snap, "On: a point placed or dragged near another region's point or "
                      "edge locks exactly onto it, so the regions meet without gaps or "
                      "overlap. Points locked together move together. Turn off to place "
                      "points freely, or to move a locked point on its own.")
        self.region_note = ttk.Label(side, foreground="#b26a00", wraplength=420,
                                     justify=tk.LEFT)
        self.region_note.pack(fill=tk.X, pady=(6, 0))

        self.canvas.bind("<Button-1>", self._region_press)
        self.canvas.bind("<B1-Motion>", self._region_drag)
        self.canvas.bind("<ButtonRelease-1>", self._region_release)
        self.canvas.bind("<Double-Button-1>", lambda _e: self._close_region())
        self.canvas.bind("<Motion>", self._region_hover)
        self.canvas.redraw_overlay = self._draw_regions
        self.canvas.show(self._prepared_image())
        self._current_region = None
        self._fill_region_list()

    def _fill_region_list(self, select: str | None = None) -> None:
        tree = self.region_list
        tree.delete(*tree.get_children())
        names = self._region_names()
        for n in names:
            tree.insert("", tk.END, iid=n, values=(n, "✓ drawn" if n in self.setup.regions
                                                   else "not drawn"))
        if select is None:
            select = self._current_region if self._current_region in names else next(
                (n for n in names if n not in self.setup.regions), names[0] if names else None)
        if select:
            tree.selection_set(select)
            tree.see(select)
        self._current_region = select
        self._check_regions()

    def _region_selected(self) -> None:
        sel = self.region_list.selection()
        if sel and sel[0] != self._current_region:
            self._points = []
            self._current_region = sel[0]
            self._redraw_regions()
        if sel:
            self.region_name_var.set(sel[0])

    def _draw_regions(self) -> None:
        shapes = {name: self._to_image(xs, ys) for name, (xs, ys) in self.setup.regions.items()
                  if len(xs) >= 3}
        # A region whose middle is covered by another (the arena outline around
        # the center) gets its label near its top edge, as on the plots.
        spots = _label_points(shapes) if shapes else {}
        for name, (xs, ys) in self.setup.regions.items():
            ix, iy = self._to_image(xs, ys)
            color = ROLE_COLORS.get(self._region_role(name), OTHER_COLOR)
            self.canvas.polygon(ix, iy, color, label=name, label_at=spots.get(name))
        if self._points:  # the region being drawn, in full-size pixels
            color = ROLE_COLORS.get(self._region_role(self._current_region or ""), OTHER_COLOR)
            ix, iy = self._to_image([p[0] for p in self._points], [p[1] for p in self._points])
            self.canvas.polygon(ix, iy, color, closed=False)

    def _redraw_regions(self) -> None:
        self.canvas.delete("overlay")
        self._draw_regions()

    def _grab(self, e, polygons: dict) -> tuple | None:
        """(key, point index) of a drawn point near the click, if any."""
        for key, (xs, ys) in polygons.items():
            ix, iy = self._to_image(xs, ys)
            for i, (x, y) in enumerate(zip(ix, iy)):
                if self.canvas.near(e.x, e.y, x, y, GRAB_DISTANCE):
                    return key, i
        return None

    def _linked(self, name: str, i: int) -> list[tuple[str, int]]:
        """Every region point at exactly the same place as point i of `name`
        (points locked together), including that point."""
        xs, ys = self.setup.regions[name]
        x, y = xs[i], ys[i]
        return [(n, j) for n, (pxs, pys) in self.setup.regions.items()
                for j, (px, py) in enumerate(zip(pxs, pys))
                if abs(px - x) < 1e-6 and abs(py - y) < 1e-6]

    def _snap(self, e, skip: set[str] = frozenset()) -> tuple[float, float, bool]:
        """Full-size position for a click at screen (e.x, e.y): exactly on
        another region's point if one is near, else on the nearest edge if
        one is near, else where clicked. Regions named in `skip` are
        ignored. Returns (x, y, snapped)."""
        fx, fy = self._to_full(*([v] for v in self.canvas.to_image(e.x, e.y)))
        here = (fx[0], fy[0], False)
        if not getattr(self, "snap_var", None) or not self.snap_var.get():
            return here
        others = {n: p for n, p in self.setup.regions.items() if n not in skip and p[0]}
        best, best_d = None, SNAP_DISTANCE
        for xs, ys in others.values():          # points first
            sx, sy = self._screen_points(xs, ys)
            for x, y, px, py in zip(xs, ys, sx, sy):
                d = np.hypot(px - e.x, py - e.y)
                if d <= best_d:
                    best, best_d = (x, y, True), d
        if best:
            return best
        for xs, ys in others.values():          # then edges
            sx, sy = self._screen_points(xs, ys)
            n = len(xs)
            for k in range(n):
                ax, ay, bx, by = sx[k], sy[k], sx[(k + 1) % n], sy[(k + 1) % n]
                vx, vy = bx - ax, by - ay
                seg = vx * vx + vy * vy
                if seg == 0:
                    continue
                t = min(max(((e.x - ax) * vx + (e.y - ay) * vy) / seg, 0.0), 1.0)
                d = np.hypot(ax + t * vx - e.x, ay + t * vy - e.y)
                if d <= best_d:
                    x0, y0 = xs[k], ys[k]
                    x1, y1 = xs[(k + 1) % n], ys[(k + 1) % n]
                    best, best_d = (x0 + t * (x1 - x0), y0 + t * (y1 - y0), True), d
        return best or here

    def _screen_points(self, xs, ys):
        ix, iy = self._to_image(xs, ys)
        pts = [self.canvas.to_screen(x, y) for x, y in zip(ix, iy)]
        return [p[0] for p in pts], [p[1] for p in pts]

    def _show_snap(self, x: float, y: float) -> None:
        self.canvas.delete("snap")
        (ix,), (iy,) = self._to_image([x], [y])
        sx, sy = self.canvas.to_screen(ix, iy)
        self.canvas.create_oval(sx - 7, sy - 7, sx + 7, sy + 7, outline="white", width=2,
                                tags=("overlay", "snap"))

    def _region_hover(self, e) -> None:
        """Show a ring where a click would lock on."""
        self.canvas.delete("snap")
        if self._drag:
            return
        x, y, snapped = self._snap(e)
        if snapped and self._current_region not in self.setup.regions:
            self._show_snap(x, y)

    def _region_press(self, e) -> None:
        """A press near a drawn point may be a drag (if the mouse moves) or a
        click that places a point locked onto it (if it doesn't)."""
        self._press = None
        if not self._points:
            hit = self._grab(e, self.setup.regions)
            if hit:  # with locking off, a point moves on its own
                group = self._linked(*hit) if self.snap_var.get() else [hit]
                self._press = (group, e.x, e.y)
                return
        self._place_region_point(e)

    def _place_region_point(self, e) -> None:
        name = self._current_region
        if not name:
            return
        if name in self.setup.regions and not self._points:
            self.region_note.configure(text=f"{name} is already drawn: drag its points, "
                                            "or click Redraw to draw it again.")
            return
        if len(self._points) >= 3:
            (fx,), (fy,) = self._to_image([self._points[0][0]], [self._points[0][1]])
            if self.canvas.near(e.x, e.y, fx, fy, CLOSE_DISTANCE):
                self._close_region()
                return
        x, y, _ = self._snap(e)
        self._points.append((x, y))
        self._redraw_regions()

    def _region_drag(self, e) -> None:
        if not self._drag and self._press:
            group, px, py = self._press
            if abs(e.x - px) + abs(e.y - py) < 4:
                return  # not moved enough to be a drag yet
            self._drag, self._press = group, None
        if not self._drag:
            return
        x, y, snapped = self._snap(e, skip={n for n, _ in self._drag})
        for name, i in self._drag:              # locked points move together
            xs, ys = self.setup.regions[name]
            xs[i], ys[i] = x, y
        self._redraw_regions()
        if snapped:
            self._show_snap(x, y)

    def _region_release(self, e) -> None:
        if self._press:  # a click on a point, not a drag: place a locked point
            _group, px, py = self._press
            self._press = None
            self._place_region_point(type("E", (), {"x": px, "y": py})())
            return
        if self._drag:
            self._drag = None
            self.canvas.delete("snap")
            self.setup.steps_done.discard("regions")
            self._update_step_list()
            self._check_regions()
            self.app._refresh()

    def _close_region(self) -> None:
        name = self._current_region
        if name and len(self._points) >= 3:
            self.setup.regions[name] = ([p[0] for p in self._points],
                                        [p[1] for p in self._points])
            self.setup.steps_done.discard("regions")
            self._points = []
            nxt = next((n for n in self._region_names() if n not in self.setup.regions), name)
            self._current_region = nxt
            self._fill_region_list(select=nxt)
            self._update_step_list()
            self.app._refresh()
        self._redraw_regions()

    def _undo_region_point(self) -> None:
        if self._points:
            self._points.pop()
            self._redraw_regions()

    def _redraw_region(self) -> None:
        name = self._current_region
        if name:
            self.setup.regions.pop(name, None)
            self._points = []
            self._fill_region_list(select=name)
            self._redraw_regions()
            self.app._refresh()

    def _delete_region(self) -> None:
        name = self._current_region
        if not name:
            return
        self.setup.regions.pop(name, None)
        if name in self._extra_names:
            self._extra_names.remove(name)
        self._points = []
        self._current_region = None
        self._fill_region_list()
        self._redraw_regions()
        self.app._refresh()

    def _rename_region(self) -> None:
        old, new = self._current_region, self.region_name_var.get().strip()
        if not old or not new or new == old:
            return
        if new in self._region_names():
            show_warning(self, "Name already used", f"There's already a region called {new}.")
            return
        if old not in self.setup.regions:
            show_info(self, "Draw it first", f"Draw {old} before renaming it.")
            return
        self.setup.regions = {(new if k == old else k): v for k, v in self.setup.regions.items()}
        self._current_region = new
        self._fill_region_list(select=new)
        self._redraw_regions()
        self.app._refresh()

    def _add_region(self) -> None:
        name = self.region_name_var.get().strip()
        if not name:
            show_info(self, "Type a name first", "Type the new region's name in the Name box.")
            return
        if name in self._region_names():
            show_warning(self, "Name already used", f"There's already a region called {name}.")
            return
        self._extra_names.append(name)   # listed now, saved once it's drawn
        self._points = []
        self._fill_region_list(select=name)
        self._redraw_regions()

    def _check_regions(self) -> None:
        """Warn right away if the Open Field center goes outside the outline."""
        note = ""
        r = self.setup.regions
        if self._test() == "Open Field" and OUTLINE in r and "center" in r:
            outline = Path(np.column_stack(r[OUTLINE]))
            if not outline.contains_points(np.column_stack(r["center"])).all():
                note = ("Part of the center is outside the arena outline. Frames there "
                        "count as center; check the lines.")
        self.region_note.configure(text=note)

    # ------------------------------------------------------ step 6: scale
    def _step_scale(self) -> None:
        s, test = self.setup, self._test()
        self.instructions.configure(text=(
            "Click two points a known distance apart, then type that distance. "
            f"{SCALE_GUIDE.get(test, '')} Drag a point to adjust it; clicking somewhere "
            "else starts again."))
        row = ttk.Frame(self.controls)
        row.pack(fill=tk.X)
        ttk.Label(row, text="Distance between the points (cm):").pack(side=tk.LEFT)
        cm = s.scale_cm if s.scale_cm else self.app.config_data["scale_cm"].get(test, 40.0)
        self.cm_var = tk.StringVar(value=f"{cm:g}")
        entry = ttk.Entry(row, textvariable=self.cm_var, width=7)
        entry.pack(side=tk.LEFT, padx=(4, 12))
        entry.bind("<Return>", lambda _e: self._apply_cm())
        entry.bind("<FocusOut>", lambda _e: self._apply_cm(quiet=True))
        ttk.Button(row, text="Clear points", command=self._clear_scale).pack(side=tk.LEFT)
        self.scale_text = ttk.Label(row, foreground="gray")
        self.scale_text.pack(side=tk.LEFT, padx=(12, 0))
        self.canvas.bind("<Button-1>", self._scale_press)
        self.canvas.bind("<B1-Motion>", self._scale_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda _e: setattr(self, "_drag", None))
        self.canvas.redraw_overlay = self._draw_scale
        self.canvas.show(self._prepared_image())
        self._apply_cm(quiet=True)

    def _apply_cm(self, quiet: bool = False) -> bool:
        try:
            cm = float(self.cm_var.get())
            if cm <= 0:
                raise ValueError
        except ValueError:
            if not quiet:
                show_warning(self, "Invalid distance",
                             "The distance must be a number of cm above 0, such as 40.")
            return False
        self.setup.scale_cm = cm
        self.app.config_data["scale_cm"][self._test()] = cm
        self._update_scale_text()
        return True

    def _update_scale_text(self) -> None:
        px = self.setup.scale_px(self._dsmpl())
        sc = self.setup.scale(self._dsmpl())
        if px is None:
            text = "Click two points."
        elif sc is None:
            text = f"{px:.1f} px apart. Type the distance."
        else:
            text = f"{px:.1f} px apart = {sc.cm:g} cm, so {sc.cm_per_px:.4f} cm per pixel."
        self.scale_text.configure(text=text)

    def _scale_points_image(self) -> list[tuple[float, float]]:
        if not self.setup.scale_points:
            return []
        xs, ys = self._to_image([p[0] for p in self.setup.scale_points],
                                [p[1] for p in self.setup.scale_points])
        return list(zip(xs, ys))

    def _draw_scale(self) -> None:
        pts = self._scale_points_image()
        if len(pts) == 2:
            self.canvas.polygon([p[0] for p in pts], [p[1] for p in pts], SCALE_COLOR,
                                closed=False)
        elif pts:
            self.canvas.polygon([pts[0][0]], [pts[0][1]], SCALE_COLOR, closed=False)

    def _scale_press(self, e) -> None:
        pts = self._scale_points_image()
        for i, (x, y) in enumerate(pts):
            if self.canvas.near(e.x, e.y, x, y, GRAB_DISTANCE):
                self._drag = ("scale", i)
                return
        fx, fy = self._to_full(*([v] for v in self.canvas.to_image(e.x, e.y)))
        if len(self.setup.scale_points) >= 2:
            self.setup.scale_points = []
        self.setup.scale_points.append((fx[0], fy[0]))
        self.setup.steps_done.discard("scale")
        self._update_step_list()
        self.canvas.delete("overlay")
        self._draw_scale()
        self._update_scale_text()

    def _scale_drag(self, e) -> None:
        if not self._drag:
            return
        fx, fy = self._to_full(*([v] for v in self.canvas.to_image(e.x, e.y)))
        self.setup.scale_points[self._drag[1]] = (fx[0], fy[0])
        self.canvas.delete("overlay")
        self._draw_scale()
        self._update_scale_text()

    def _clear_scale(self) -> None:
        self.setup.scale_points = []
        self.setup.steps_done.discard("scale")
        self._update_step_list()
        self.canvas.delete("overlay")
        self._update_scale_text()
