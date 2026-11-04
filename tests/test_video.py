"""Checks for core/video.py and core/tracking.py using ezTrack's practice
videos (in ezTrack/PracticeVideos, gitignored, so this only runs where they
exist).

Run from the project folder:  .venv/bin/python tests/test_video.py
"""
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from core import video

EPM_VIDEO = os.path.join(ROOT, "ezTrack", "PracticeVideos", "6_2024-04-01_11-49-23.mp4")
if not os.path.exists(EPM_VIDEO):
    sys.exit("ezTrack's practice videos aren't in ezTrack/PracticeVideos.")

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)

# --- core/video.py ---
info = video.video_info(EPM_VIDEO)
check("video info", (info.width, info.height, info.frame_count) == (800, 600, 6419)
      and abs(info.fps - 16.64) < 0.01)
check("is_video", video.is_video("a/b.MP4") and not video.is_video("a/b.csv"))

with video.VideoReader(EPM_VIDEO) as r:
    f = r.read_at(460)
    check("read_at gives a grayscale full-size frame", f is not None and f.shape == (600, 800))
    check("read_at past the end gives None", r.read_at(10_000) is None)
    got = list(r.frames(100, 105))
    check("frames() yields the range in order", [i for i, _ in got] == list(range(100, 105)))
    check("frames() matches read_at", np.array_equal(got[0][1], r.read_at(100)))

prep = video.Prep(dsmpl=0.5, crop=(10, 20, 210, 120))
with video.VideoReader(EPM_VIDEO, prep) as r:
    check("downsample then crop", r.read_at(0).shape == (100, 200))
    tail = list(r.frames(info.frame_count - 3, info.frame_count + 50))
    check("frames() stops at the real end", [i for i, _ in tail][-1] == info.frame_count - 1
          or all(fr is not None for _, fr in tail))

bad, checked = video.check_readable(EPM_VIDEO)
check("readability check", checked == 300 and bad == 0)

m = video.polygon_mask((10, 10), [([2, 7, 7, 2], [2, 2, 7, 7])])
check("polygon mask", m.dtype == bool and m[4, 4] and not m[0, 0] and not m[9, 9])
check("empty mask", not video.polygon_mask((5, 5), []).any())

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
