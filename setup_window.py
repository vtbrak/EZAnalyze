"""The video setup window: one video at a time, step by step, before tracking.

Steps (ROADMAP §12, GUI review item 6): 1 Trim and crop, 2 Exclusions,
3 Reference, 4 Tracking check, 5 Regions, 6 Scale. A switcher at the top moves
between the listed videos, and "Start from previous video" copies the
previous video's crop and shapes as a draft to check. Finished steps get a
check mark.

Shapes are drawn on images of the video and stored in full-size video pixels
(see core/video_setup.py).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

from core.video import VideoReader
from core.video_setup import STEPS, effective_dsmpl
from dialogs import show_info, show_warning
from tooltip import Tooltip

STEP_TITLES = {
    "trim": "1  Trim and crop",
    "exclusions": "2  Exclusions",
    "reference": "3  Reference",
    "tracking": "4  Tracking check",
    "regions": "5  Regions",
    "scale": "6  Scale",
}
BUILT_STEPS = ("trim", "exclusions", "reference")  # steps 4-6 arrive in build chunk C6
DOWNSAMPLE_CHOICES = ("1", "0.75", "0.5", "0.25")
CLOSE_DISTANCE = 10  # screen pixels: clicking this near the first point closes a shape
SHAPE_COLOR = "#ff4d4d"
CROP_COLOR = "#2f9bff"


class FrameCanvas(tk.Canvas):
    """Shows one image, scaled to fit, and converts between screen and image
    pixels. Callers draw overlays in image pixels with the helpers below."""

    def __init__(self, parent, **kw):
        super().__init__(parent, background="#202020", highlightthickness=0, **kw)
        self._array = None
        self._photo = None
        self.scale = 1.0
        self.offset = (0, 0)
        self.redraw_overlay = lambda: None  # set by the current step
        self.bind("<Configure>", lambda _e: self._render())

    def show(self, array: np.ndarray | None) -> None:
        self._array = array
        self._render()

    def _render(self) -> None:
        self.delete("all")
        w, h = max(self.winfo_width(), 50), max(self.winfo_height(), 50)
        if self._array is None:
            self.create_text(w // 2, h // 2, text="No image", fill="#bbbbbb")
            return
        a = self._array
        if a.dtype != np.uint8:
            a = np.clip(a, 0, 255).astype(np.uint8)
        img = Image.fromarray(a if a.ndim == 2 else cv2.cvtColor(a, cv2.COLOR_BGR2RGB))
        self.scale = min(w / img.width, h / img.height)
        size = (max(1, int(img.width * self.scale)), max(1, int(img.height * self.scale)))
        self.offset = ((w - size[0]) // 2, (h - size[1]) // 2)
        self._photo = ImageTk.PhotoImage(img.resize(size))
        self.create_image(*self.offset, image=self._photo, anchor="nw")
        self.redraw_overlay()

    def to_image(self, sx: float, sy: float) -> tuple[float, float]:
        return (sx - self.offset[0]) / self.scale, (sy - self.offset[1]) / self.scale

    def to_screen(self, ix: float, iy: float) -> tuple[float, float]:
        return ix * self.scale + self.offset[0], iy * self.scale + self.offset[1]

    def image_size(self) -> tuple[int, int]:
        return (0, 0) if self._array is None else self._array.shape[1::-1]

    def polygon(self, xs, ys, color: str, closed: bool = True, tag: str = "overlay") -> None:
        pts = [c for x, y in zip(xs, ys) for c in self.to_screen(x, y)]
        if closed and len(xs) >= 3:
            self.create_polygon(*pts, outline=color, fill=color, stipple="gray25",
                                width=2, tags=tag)
        elif len(xs) >= 2:
            self.create_line(*pts, fill=color, width=2, tags=tag)
        for x, y in zip(xs, ys):
            sx, sy = self.to_screen(x, y)
            self.create_oval(sx - 3, sy - 3, sx + 3, sy + 3, outline=color, fill=color, tags=tag)

    def rectangle(self, x0, y0, x1, y1, color: str, tag: str = "overlay") -> None:
        self.create_rectangle(*self.to_screen(x0, y0), *self.to_screen(x1, y1),
                              outline=color, width=2, dash=(6, 3), tags=tag)


class SetupWindow(tk.Toplevel):
    """Set up the listed videos one at a time. `app` is the main window; it
    provides the shared settings (`config_data`), whether they're locked
    (`_tracking_locked()`), and `_refresh()` to update the file list."""

    def __init__(self, app, entries, index: int = 0):
        super().__init__(app)
        self.app = app
        self.entries = entries          # FileEntry objects for the videos
        self.index = index
        self.step = "trim"
        self.title("Set up videos")
        self.geometry("1000x700")
        self.minsize(820, 560)
        self.transient(app)
        self._scrub_job = None
        self._points: list[tuple[float, float]] = []   # shape being drawn
        self._drag_start = None

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
        Tooltip(self.copy_btn, "Copy the previous video's crop and exclusion shapes "
                               "into this one as a starting point. Check each step: "
                               "they're marked not done until you go through them.")

        body = ttk.Frame(self)
        body.pack(fill=tk.BOTH, expand=True)
        steps = ttk.Frame(body, padding=(10, 4))
        steps.pack(side=tk.LEFT, fill=tk.Y)
        self.step_buttons = {}
        for key in STEPS:
            b = ttk.Button(steps, text=STEP_TITLES[key], width=20,
                           command=lambda k=key: self._go(k))
            b.pack(fill=tk.X, pady=2)
            if key not in BUILT_STEPS:
                b.configure(state="disabled")
            self.step_buttons[key] = b
        self.info_label = ttk.Label(steps, foreground="gray", wraplength=170,
                                    justify=tk.LEFT)
        self.info_label.pack(fill=tk.X, pady=(16, 0))

        right = ttk.Frame(body, padding=(4, 4, 10, 10))
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.instructions = ttk.Label(right, wraplength=700, justify=tk.LEFT)
        self.instructions.pack(fill=tk.X, pady=(0, 6))
        self.canvas = FrameCanvas(right)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.controls = ttk.Frame(right)
        self.controls.pack(fill=tk.X, pady=(8, 0))
        nav = ttk.Frame(right)
        nav.pack(fill=tk.X, pady=(8, 0))
        self.back_btn = ttk.Button(nav, text="Back", command=lambda: self._step_by(-1))
        self.back_btn.pack(side=tk.LEFT)
        self.done_btn = ttk.Button(nav, text="Done", command=self._close)
        self.done_btn.pack(side=tk.RIGHT)
        self.next_step_btn = ttk.Button(nav, command=lambda: self._step_by(1))
        self.next_step_btn.pack(side=tk.RIGHT, padx=(0, 6))

    # --------------------------------------------------------------- helpers
    @property
    def entry(self):
        return self.entries[self.index]

    @property
    def setup(self):
        return self.entry.video

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
        for child in self.controls.winfo_children():
            child.destroy()
        self.canvas.unbind("<Button-1>")
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<ButtonRelease-1>")
        self.canvas.unbind("<Double-Button-1>")
        self.canvas.redraw_overlay = lambda: None

    def _mark(self, step: str) -> None:
        self.setup.steps_done.add(step)
        self._update_step_list()

    def _update_step_list(self) -> None:
        for key, b in self.step_buttons.items():
            done = key in self.setup.steps_done
            mark = "✓ " if done else "   "
            b.configure(text=mark + STEP_TITLES[key])
        for key, b in self.step_buttons.items():
            b.state(["pressed"] if key == self.step else ["!pressed"])

    # ------------------------------------------------------------ navigation
    def _show_video(self) -> None:
        s = self.setup
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

    def _move(self, delta: int) -> None:
        self._points = []
        self.index = max(0, min(len(self.entries) - 1, self.index + delta))
        self._show_video()
        self.app._refresh()

    def _go(self, step: str) -> None:
        self._points = []
        self.step = step
        self._clear_controls()
        {"trim": self._step_trim, "exclusions": self._step_exclusions,
         "reference": self._step_reference}[step]()
        built = list(BUILT_STEPS)
        k = built.index(step)
        self.back_btn.configure(state="normal" if k > 0 else "disabled")
        if k < len(built) - 1:
            nxt = STEP_TITLES[built[k + 1]].split("  ", 1)[1]
            self.next_step_btn.configure(text=f"Next: {nxt.lower()}", state="normal")
        else:
            self.next_step_btn.configure(text="Next", state="disabled")
        self._update_step_list()

    def _step_by(self, delta: int) -> None:
        built = list(BUILT_STEPS)
        k = built.index(self.step)
        if delta > 0 and self.step in ("trim", "exclusions"):
            self._mark(self.step)  # these steps have nothing that must be done
        if delta > 0 and self.step == "exclusions" and self._points:
            self._finish_shape()
        self._go(built[max(0, min(len(built) - 1, k + delta))])

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

    # --------------------------------------------------- step 1: trim + crop
    def _step_trim(self) -> None:
        s = self.setup
        self.instructions.configure(text=(
            "Scrub to where the trial starts and click Set start, then to where it "
            "ends and click Set end. Then drag a box around the arena to crop to it: "
            "tracking ignores everything outside the box (optional)."))
        row = ttk.Frame(self.controls)
        row.pack(fill=tk.X)
        self.frame_var = tk.IntVar(value=s.start)
        self.scrub = ttk.Scale(row, from_=0, to=max(0, s.info.frame_count - 1),
                               orient=tk.HORIZONTAL, command=lambda _v: self._on_scrub())
        self.scrub.set(s.start)
        self.scrub.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.frame_text = ttk.Label(row, width=22, anchor="e")
        self.frame_text.pack(side=tk.LEFT, padx=(8, 0))

        row2 = ttk.Frame(self.controls)
        row2.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(row2, text="Set start here", command=self._set_start).pack(side=tk.LEFT)
        ttk.Button(row2, text="Set end here", command=self._set_end).pack(side=tk.LEFT,
                                                                           padx=(6, 0))
        self.trim_text = ttk.Label(row2)
        self.trim_text.pack(side=tk.LEFT, padx=(12, 0))
        ttk.Button(row2, text="Clear crop", command=self._clear_crop).pack(side=tk.RIGHT)
        ds = ttk.Frame(row2)
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

        self.canvas.bind("<Button-1>", self._crop_press)
        self.canvas.bind("<B1-Motion>", self._crop_drag)
        self.canvas.bind("<ButtonRelease-1>", self._crop_release)
        self.canvas.redraw_overlay = self._draw_crop
        self._update_trim_text()
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
        self._scrub_job = None
        self._update_frame_text()
        with VideoReader(self.setup.path) as r:
            frame = r.read_at(self._current_frame(), raw=True)
        self.canvas.show(frame)

    def _update_trim_text(self) -> None:
        s = self.setup
        self.trim_text.configure(text=(
            f"Start {s.start:,} ({self._secs(s.start)})   "
            f"End {s.end_frame:,} ({self._secs(s.end_frame)})"))

    def _set_start(self) -> None:
        f = self._current_frame()
        if f >= self.setup.end_frame:
            show_warning(self, "Start is after the end",
                         "The start has to come before the end. Move the end first.")
            return
        self.setup.start = f
        self._update_trim_text()
        self.app._refresh()

    def _set_end(self) -> None:
        f = self._current_frame() + 1  # the end frame is included in the trial
        if f <= self.setup.start:
            show_warning(self, "End is before the start",
                         "The end has to come after the start. Move the start first.")
            return
        self.setup.end = f
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
            "(or double-click) to close the shape. Draw as many as you need, or none."))
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
        x, y = self._clamp(*self.canvas.to_image(e.x, e.y))
        if len(self._points) >= 3:
            fx, fy = self.canvas.to_screen(*self._points[0])
            if abs(fx - e.x) <= CLOSE_DISTANCE and abs(fy - e.y) <= CLOSE_DISTANCE:
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
        if s.reference_current(self._dsmpl(), self._ref_frames()):
            self.canvas.show(s.reference)
            self.ref_text.configure(text="Reference is up to date.")
        else:
            self.canvas.show(s.reference)  # an old one (or none) until remade
            self.ref_text.configure(text=(
                "No reference yet." if s.reference is None else
                "The trim, crop, or settings changed since this was made. Make it again."))

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
        self.app._refresh()
