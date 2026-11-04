"""Reading video frames (GUI-free).

Adapted from ezTrack (https://github.com/denisecailab/ezTrack),
LocationTracking_Functions.py: `LoadAndCrop`, `cropframe`, `check_p_frames`
and `Mask_select`. Copyright (C) Zachary T. Pennington, Zhe Dong, Yu Feng,
Lauren M. Vetere, Lucia Page-Harley, Tristan Shuman, Denise J. Cai.
Licensed under the GNU General Public License v3.0 (see LICENSE).

Changes from ezTrack: no notebook/HoloViews tools (the GUI draws crops and
shapes and passes plain coordinates here); the unreadable-frame check returns
counts for a warning instead of raising an error; sequential reading keeps
going past an unreadable frame (reported as None) instead of stopping.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import cv2
import numpy as np

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".wmv", ".mpg", ".mpeg", ".mkv", ".m4v")


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


@dataclass
class VideoInfo:
    path: str
    frame_count: int  # as the file reports it; may overcount by a few frames
    fps: float
    width: int
    height: int


def video_info(path: str) -> VideoInfo:
    cap = cv2.VideoCapture(path)
    try:
        if not cap.isOpened():
            raise ValueError(f"Couldn't open the video {os.path.basename(path)}.")
        return VideoInfo(
            path=path,
            frame_count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
            fps=float(cap.get(cv2.CAP_PROP_FPS)),
            width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
        )
    finally:
        cap.release()


@dataclass
class Prep:
    """How each frame is prepared before tracking, as in ezTrack: grayscale,
    then downsample, then crop.

    dsmpl: scale factor (1.0 = full size; ezTrack only resizes when < 1).
    crop: (x0, y0, x1, y1) in downsampled pixels, or None for the whole frame.
    """
    dsmpl: float = 1.0
    crop: tuple[float, float, float, float] | None = None


def prepare(frame_bgr: np.ndarray, prep: Prep) -> np.ndarray:
    frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    if prep.dsmpl < 1:
        # ezTrack passes cv2.INTER_NEAREST positionally, where cv2.resize
        # expects `dst`, so its frames are actually resized with the default
        # (bilinear) interpolation. Kept that way so results match ezTrack.
        frame = cv2.resize(
            frame, (int(frame.shape[1] * prep.dsmpl), int(frame.shape[0] * prep.dsmpl))
        )
    return crop_frame(frame, prep.crop)


def crop_frame(frame: np.ndarray, crop) -> np.ndarray:
    if not crop:
        return frame
    x0, y0, x1, y1 = crop
    xmin, xmax = int(min(x0, x1)), int(max(x0, x1))
    ymin, ymax = int(min(y0, y1)), int(max(y0, y1))
    return frame[ymin:ymax, xmin:xmax]


class VideoReader:
    """Frames from one video, prepared (grayscale, downsampled, cropped).

    Use as a context manager. `read_at` jumps to any frame (for previews and
    the reference image); `frames` reads a range in order (for tracking).
    """

    def __init__(self, path: str, prep: Prep | None = None):
        self.path = path
        self.prep = prep or Prep()
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise ValueError(f"Couldn't open the video {os.path.basename(path)}.")
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self) -> None:
        self.cap.release()

    def read_at(self, index: int, raw: bool = False) -> np.ndarray | None:
        """Frame `index` (0-based), or None if it can't be read. `raw` returns
        the original color frame without preparation (for display)."""
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ret, frame = self.cap.read()
        if not ret:
            return None
        return frame if raw else prepare(frame, self.prep)

    def frames(self, start: int = 0, end: int | None = None):
        """Yield (index, frame) for start <= index < end, in order. An
        unreadable frame is yielded as None and reading continues after it.
        A run of unreadable frames at the very end is dropped: files often
        report a few more frames than they hold (ezTrack stops there too)."""
        end = self.frame_count if end is None else min(end, self.frame_count)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, start)
        pending = []  # unreadable indices not yet yielded
        for index in range(start, end):
            ret, frame = self.cap.read()
            if not ret:
                pending.append(index)
                # Step past the bad frame so the next read is the next frame.
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, index + 1)
                continue
            for bad in pending:
                yield bad, None
            pending = []
            yield index, prepare(frame, self.prep)


def check_readable(path: str, frames_checked: int = 300) -> tuple[int, int]:
    """(unreadable, checked) over the first `frames_checked` frames, read in
    order, as ezTrack's `check_p_frames` does. ezTrack refuses a video with
    more than 1% unreadable; the app warns instead (see UNREADABLE_WARN)."""
    cap = cv2.VideoCapture(path)
    try:
        checked = min(frames_checked, int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
        bad = sum(not cap.read()[0] for _ in range(checked))
        return bad, checked
    finally:
        cap.release()


UNREADABLE_WARN = 0.01  # ezTrack's limit: warn above 1% unreadable


def polygon_mask(shape: tuple[int, int], polygons) -> np.ndarray:
    """Boolean mask (True inside any polygon) for an image of `shape` (h, w).
    `polygons` is a list of (xs, ys) vertex lists, in the same pixels as the
    prepared frames. Filled as ezTrack does (cv2.fillPoly on truncated
    coordinates)."""
    mask = np.zeros(shape, dtype=np.uint8)
    for xs, ys in polygons:
        if len(xs) < 3:
            continue
        pts = np.column_stack((np.asarray(xs), np.asarray(ys))).astype(np.int32)
        cv2.fillPoly(mask, pts=[pts], color=1)
    return mask.astype(bool)
