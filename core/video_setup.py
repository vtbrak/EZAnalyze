"""One video's setup before tracking (GUI-free): trim, crop, exclusion shapes,
reference image, and (from setup step 4 on) regions and scale.

Each video has its own setup; nothing is shared between videos except by an
explicit "start from the previous video" copy, which the user then confirms
(ROADMAP §12, Stages 1 and 4).

All shapes are stored in **full-size video pixels**, and converted to the
prepared-frame pixels tracking uses (after downsampling, then cropping, as in
ezTrack) only when needed, so changing the downsampling never invalidates
anything drawn.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np

from .tracking import make_reference
from .video import Prep, VideoInfo, polygon_mask

STEPS = ("trim", "exclusions", "reference", "tracking", "regions", "scale")


def effective_dsmpl(dsmpl: float) -> float:
    """ezTrack only resizes when downsampling is below 1."""
    return dsmpl if dsmpl < 1 else 1.0


@dataclass
class VideoSetup:
    path: str
    info: VideoInfo
    start: int = 0
    end: int | None = None                   # exclusive; None = to the end
    crop: tuple[float, float, float, float] | None = None   # full-size x0, y0, x1, y1
    exclusions: list[tuple[list, list]] = field(default_factory=list)  # full-size polygons
    reference: np.ndarray | None = None
    reference_key: tuple | None = None       # what the reference was made from
    unreadable: tuple[int, int] = (0, 0)     # (unreadable, checked) at add time
    steps_done: set[str] = field(default_factory=set)

    @property
    def end_frame(self) -> int:
        return self.info.frame_count if self.end is None else min(self.end, self.info.frame_count)

    # --- coordinates -----------------------------------------------------
    def _crop_origin(self, dsmpl: float) -> tuple[int, int]:
        """Top-left of the crop in downsampled pixels, as `crop_frame` cuts it."""
        if not self.crop:
            return 0, 0
        d = effective_dsmpl(dsmpl)
        x0, y0, x1, y1 = self.crop
        return int(min(x0 * d, x1 * d)), int(min(y0 * d, y1 * d))

    def prep(self, dsmpl: float) -> Prep:
        d = effective_dsmpl(dsmpl)
        crop = tuple(v * d for v in self.crop) if self.crop else None
        return Prep(dsmpl=dsmpl, crop=crop)

    def prepared_shape(self, dsmpl: float) -> tuple[int, int]:
        """(height, width) of a prepared frame."""
        d = effective_dsmpl(dsmpl)
        w = int(self.info.width * d) if d < 1 else self.info.width
        h = int(self.info.height * d) if d < 1 else self.info.height
        if self.crop:
            x0, y0, x1, y1 = (v * d for v in self.crop)
            xmin, xmax = int(min(x0, x1)), int(max(x0, x1))
            ymin, ymax = int(min(y0, y1)), int(max(y0, y1))
            w = min(xmax, w) - max(xmin, 0)
            h = min(ymax, h) - max(ymin, 0)
        return h, w

    def to_prepared(self, xs, ys, dsmpl: float) -> tuple[list[float], list[float]]:
        """Full-size pixel coordinates -> prepared-frame coordinates."""
        d = effective_dsmpl(dsmpl)
        ox, oy = self._crop_origin(dsmpl)
        return [x * d - ox for x in xs], [y * d - oy for y in ys]

    def from_prepared(self, xs, ys, dsmpl: float) -> tuple[list[float], list[float]]:
        d = effective_dsmpl(dsmpl)
        ox, oy = self._crop_origin(dsmpl)
        return [(x + ox) / d for x in xs], [(y + oy) / d for y in ys]

    def exclusion_mask(self, dsmpl: float) -> np.ndarray | None:
        if not self.exclusions:
            return None
        polys = [self.to_prepared(xs, ys, dsmpl) for xs, ys in self.exclusions]
        return polygon_mask(self.prepared_shape(dsmpl), polys)

    # --- reference -------------------------------------------------------
    def _reference_inputs(self, dsmpl: float, frames: int) -> tuple:
        return (self.start, self.end_frame, self.crop, effective_dsmpl(dsmpl), int(frames))

    def reference_current(self, dsmpl: float, frames: int) -> bool:
        """True if the reference was made from the current trim, crop,
        downsampling, and frame count."""
        return (self.reference is not None
                and self.reference_key == self._reference_inputs(dsmpl, frames))

    def build_reference(self, dsmpl: float, frames: int) -> np.ndarray:
        self.reference = make_reference(self.path, self.prep(dsmpl), self.start,
                                        self.end_frame, num_frames=int(frames))
        self.reference_key = self._reference_inputs(dsmpl, frames)
        return self.reference

    # --- drafts from another video ---------------------------------------
    def copy_from(self, other: "VideoSetup") -> None:
        """Start from another video's crop and shapes, as a draft: the steps
        they belong to are marked not done, so the user looks at each one."""
        self.crop = copy.deepcopy(other.crop)
        self.exclusions = copy.deepcopy(other.exclusions)
        self.steps_done -= {"trim", "exclusions", "reference"}
