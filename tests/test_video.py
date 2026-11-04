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

# --- core/tracking.py ---
import pandas as pd
from core import tracking

# A dark square on a light floor is found at its center.
ref = np.full((60, 80), 200.0)
frame = np.full((60, 80), 200, dtype=np.uint8); frame[20:30, 50:60] = 40
y, x, _ = tracking.locate(frame, ref, tracking.TrackingParams(use_window=False))
check("locate finds a dark animal", abs(x - 54.5) < 0.6 and abs(y - 24.5) < 0.6)
y, x, _ = tracking.locate(frame, ref, tracking.TrackingParams(method="light", use_window=False))
check("light method ignores a dark animal", not (abs(x - 54.5) < 2 and abs(y - 24.5) < 2))
mask = video.polygon_mask(ref.shape, [([45, 65, 65, 45], [15, 15, 35, 35])])
frame[40:50, 10:20] = 60
y, x, _ = tracking.locate(frame, ref, tracking.TrackingParams(use_window=False), mask)
check("exclusion shapes are ignored", abs(x - 14.5) < 0.6 and abs(y - 44.5) < 0.6)

# Region columns: blank when unreadable; periphery excludes the center;
# labels and transitions as ezTrack writes them.
pos = pd.DataFrame({"X": [5, 50, np.nan, 50, 95], "Y": [5, 50, np.nan, 50, 95]})
regions = [tracking.Region("center", [30, 70, 70, 30], [30, 30, 70, 70]),
           tracking.Region("periphery", [0, 100, 100, 0], [0, 0, 100, 100], subtract=["center"])]
cols = tracking.region_columns(pos, regions, (101, 101))
check("region columns", list(cols["center"]) == [False, True, None, True, False]
      and list(cols["periphery"]) == [True, False, None, False, True])
check("ROI_location", list(cols["ROI_location"]) == ["periphery", "center", None, "center", "periphery"])
check("ROI_transition skips the gap", list(cols["ROI_transition"]) == [False, True, False, False, True])

# Real video: matches ezTrack's EPM.csv closely (wire removal is dropped and
# the user's exact crop is estimated, so close rather than identical).
EPM_CSV = os.path.join(ROOT, "EPM.csv")
if os.path.exists(EPM_CSV):
    prep = video.Prep(crop=(165, 5, 745, 575))
    reference = tracking.make_reference(EPM_VIDEO, prep, start=460, num_frames=50)
    calls = []
    res = tracking.track_video(EPM_VIDEO, reference, tracking.TrackingParams(), prep,
                               start=460, end=760, progress=lambda d, t: calls.append((d, t)))
    b = pd.read_csv(EPM_CSV).iloc[:300]
    d = np.hypot(res.df.X - b.X, res.df.Y - b.Y)
    check(f"tracks like ezTrack (median {d.median():.1f} px)", d.median() < 3)
    check("progress reported", calls and calls[-1] == (300, 300))
    check("no unreadable frames", res.unreadable == 0 and not res.df.Frame_Unreadable.any())
    stopped = tracking.track_video(EPM_VIDEO, reference, tracking.TrackingParams(), prep,
                                   start=460, end=760, should_cancel=lambda: True)
    check("cancel", stopped.cancelled and stopped.df is None)
    out = tracking.assemble_output(EPM_VIDEO, res.df, tracking.TrackingParams(), prep, 460,
                                   regions[:1], reference.shape, tracking.Scale(100, 25), 50, 0,
                                   16.64)
    check("output starts with ezTrack's columns",
          list(out.columns[:9]) == ["File", "Location_Thresh", "Use_Window", "Window_Weight",
                                    "Window_Size", "Start_Frame", "Frame", "X", "Y"])
    check("cm distance", np.allclose(out.Distance_cm, out.Distance_px * 0.25, equal_nan=True))
else:
    print("skip EPM.csv comparison (EPM.csv not in the project folder)")

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
