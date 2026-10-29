"""
Behavioral metrics computed from a loaded tracking file.

Families of output:
  * summary_metrics()  -> one dict of numbers for the whole session
  * epm_metrics()      -> Elevated Plus Maze measures (added to the summary)
  * of_metrics()       -> Open Field measures (added to the summary)
  * binned_metrics()   -> a DataFrame with one row per time bin

Frame rate (fps) is supplied by the caller so frames can be converted to
seconds; everything time-based flows from that single number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .loader import TrackingData
from .regions import frame_roles, match_polygons


def held_states(labels: np.ndarray, min_frames: int) -> list[tuple[str, int]]:
    """Where the animal is, under the entry rule: [(label, first frame), ...],
    starting with the place it starts in.

    The current place only changes once the animal has stayed somewhere new
    for at least `min_frames` consecutive frames; shorter visits (boundary
    jitter) are ignored and don't break up a stay.
    """
    n = len(labels)
    if n == 0:
        return []
    # Run-length encode: start index and label of each run of equal labels.
    change = np.flatnonzero(labels[1:] != labels[:-1]) + 1
    starts = np.concatenate([[0], change])
    lengths = np.diff(np.concatenate([starts, [n]]))
    states = []
    for start, length in zip(starts, lengths):
        label = str(labels[start])
        if length < max(1, min_frames) or (states and label == states[-1][0]):
            continue
        states.append((label, int(start)))
    return states


def held_entries(roles: np.ndarray, min_frames: int) -> list[tuple[str, int]]:
    """Entries under the entry rule: [(role, first frame of the entry), ...].

    Same as held_states, minus the starting place: the animal was put there,
    so it isn't counted as an entry (its time still counts toward the
    region's total). Being in no region ("" role) counts as a place too, so
    returning from it is a new entry.
    """
    return held_states(roles, min_frames)[1:]


def epm_metrics(
    data: TrackingData, roles: dict[str, str], fps: float = 20.0, min_entry_frames: int = 5
) -> dict:
    """Elevated Plus Maze measures for one file, as EPM_* summary columns.

    Times come straight from the per-frame roles (arm + center overlap counts
    as center). Entries and latencies use the entry rule (`held_entries`).
    Values that can't be computed (e.g. a ratio with no open-arm time, or a
    latency to an arm never entered) are left blank.
    """
    per_frame = frame_roles(data, roles)
    n = len(per_frame)
    nan = float("nan")

    def secs(frames):
        return round(frames / fps, 2) if fps else nan

    frames = {k: int(np.sum(per_frame == k)) for k in ("open_arm", "closed_arm", "center")}
    entries = held_entries(per_frame, min_entry_frames)
    counts = {k: sum(1 for r, _ in entries if r == k) for k in frames}
    first = {k: next((f for r, f in entries if r == k), None) for k in frames}

    arm_frames = frames["open_arm"] + frames["closed_arm"]
    arm_entries = counts["open_arm"] + counts["closed_arm"]
    open_time_frac = frames["open_arm"] / arm_frames if arm_frames else nan
    open_entry_frac = counts["open_arm"] / arm_entries if arm_entries else nan

    out = {
        "EPM_OpenArm_s": secs(frames["open_arm"]),
        "EPM_ClosedArm_s": secs(frames["closed_arm"]),
        "EPM_Center_s": secs(frames["center"]),
        # % of time on the arms that was spent on the open arms.
        "EPM_PctOpenTime": round(100 * open_time_frac, 1),
        "EPM_OpenEntries": counts["open_arm"],
        "EPM_ClosedEntries": counts["closed_arm"],
        "EPM_CenterEntries": counts["center"],
        # % of arm entries that were into the open arms.
        "EPM_PctOpenEntries": round(100 * open_entry_frac, 1),
        # 1 - mean(open time fraction, open entry fraction); higher = more anxious.
        "EPM_AnxietyIndex": round(1 - (open_time_frac + open_entry_frac) / 2, 3),
        "EPM_ClosedOpenRatio": (
            round(frames["closed_arm"] / frames["open_arm"], 3)
            if frames["open_arm"] else nan
        ),
        "EPM_Latency_Open_s": secs(first["open_arm"]) if first["open_arm"] is not None else nan,
        "EPM_Latency_Closed_s": (
            secs(first["closed_arm"]) if first["closed_arm"] is not None else nan
        ),
        "EPM_Latency_Center_s": secs(first["center"]) if first["center"] is not None else nan,
        "EPM_PctSession_Open": round(100 * frames["open_arm"] / n, 1) if n else nan,
        "EPM_PctSession_Closed": round(100 * frames["closed_arm"] / n, 1) if n else nan,
        "EPM_PctSession_Center": round(100 * frames["center"] / n, 1) if n else nan,
    }
    return out



def summary_metrics(data: TrackingData, fps: float = 20.0) -> dict:
    """Compute whole-session summary metrics for one file.

    Returns a flat dict suitable for a one-row-per-file results table.
    """
    df = data.df
    n = len(df)
    duration_s = n / fps if fps else float("nan")

    dist_cm = float(df["Distance_cm"].sum()) if "Distance_cm" in df else float("nan")
    dist_px = float(df["Distance_px"].sum()) if "Distance_px" in df else float("nan")

    out: dict = {
        "File": data.name,
        "Frames": n,
        "FPS": fps,
        "Duration_s": round(duration_s, 2),
        "Duration_min": round(duration_s / 60.0, 3),
        "TotalDistance_cm": round(dist_cm, 2),
        "TotalDistance_px": round(dist_px, 1),
    }

    # Mean speed over the whole session.
    if duration_s and not np.isnan(dist_cm):
        out["MeanSpeed_cm_s"] = round(dist_cm / duration_s, 3)

    # Time spent in each boolean zone (seconds and percent of session).
    for zone in data.regions:
        frames_in = int(df[zone].sum())
        out[f"Time_{zone}_s"] = round(frames_in / fps, 2) if fps else float("nan")
        out[f"Percent_{zone}"] = round(100.0 * frames_in / n, 1) if n else 0.0

    # Time spent in each ROI_location category.
    if "ROI_location" in df.columns:
        counts = df["ROI_location"].value_counts()
        for label, frames_in in counts.items():
            safe = str(label)
            out[f"Time_ROI_{safe}_s"] = round(frames_in / fps, 2) if fps else float("nan")
            out[f"Percent_ROI_{safe}"] = round(100.0 * frames_in / n, 1) if n else 0.0

    # Zone entries: count rising edges (False -> True) per zone.
    for zone in data.regions:
        entries = int(((~df[zone].shift(1, fill_value=False)) & df[zone]).sum())
        out[f"Entries_{zone}"] = entries

    # ROI transitions flagged in the data.
    if "ROI_transition" in df.columns:
        out["ROI_transitions"] = int(df["ROI_transition"].sum())

    # Carry the tracking settings through so they appear in the results table.
    for key, val in data.settings.items():
        out[key] = val

    return out


SIDES = ("left", "right", "top", "bottom")


def _polygon_edges(xs, ys) -> list[tuple[np.ndarray, np.ndarray, str]]:
    """The polygon's edges as (start point, outward unit normal, side), with
    repeated points dropped. Each edge's side comes from which way it faces:
    an edge facing -x is the "left" edge, facing up (smaller y) is "top", etc.
    """
    pts = np.column_stack([xs, ys]).astype(float)
    keep = [pts[0]]
    for p in pts[1:]:
        if np.hypot(*(p - keep[-1])) > 1e-9:
            keep.append(p)
    if len(keep) > 1 and np.hypot(*(keep[-1] - keep[0])) < 1e-9:
        keep.pop()  # closing point repeats the first
    pts = np.array(keep)
    # Shoelace sign: > 0 means counter-clockwise in these (x, y) coordinates.
    area2 = np.dot(pts[:, 0], np.roll(pts[:, 1], -1)) - np.dot(pts[:, 1], np.roll(pts[:, 0], -1))
    edges = []
    for a, b in zip(pts, np.roll(pts, -1, axis=0)):
        dx, dy = b - a
        length = np.hypot(dx, dy)
        if length < 1e-9:
            continue
        # Right-hand normal points outward for a counter-clockwise polygon.
        normal = np.array([dy, -dx]) / length
        if area2 < 0:
            normal = -normal
        if abs(normal[0]) >= abs(normal[1]):
            side = "left" if normal[0] < 0 else "right"
        else:
            side = "top" if normal[1] < 0 else "bottom"  # image coords: smaller y is up
        edges.append((a, normal, side))
    return edges


def side_labels(x: np.ndarray, y: np.ndarray, center_xs, center_ys) -> np.ndarray:
    """Which side of the arena each point is on, judged against the center
    ROI's own drawn edges (as drawn in the file, tilt and all; nothing is
    straightened or redrawn).

    Each edge line is extended across the arena. A point belongs to the side
    whose line it's furthest beyond: left of the drawn left edge = "left",
    above the drawn top edge = "top", and so on. In a corner area (beyond two
    lines) the larger distance wins, which splits the corner along its
    diagonal. Image coordinates: the top of the video is the top of the arena.

    A point inside the polygon gets the side of its nearest edge. That only
    matters for points the file's region columns say aren't in the center.
    """
    edges = _polygon_edges(center_xs, center_ys)
    pts = np.column_stack([x, y])
    # Signed distance past each edge line (positive = outside that edge).
    dist = np.stack([(pts - a) @ n for a, n, _ in edges])
    names = np.array([side for _, _, side in edges])
    return names[np.argmax(dist, axis=0)]


def of_metrics(
    data: TrackingData,
    roles: dict[str, str],
    fps: float = 20.0,
    min_entry_frames: int = 5,
    min_between_entries_s: float = 1.0,
    min_center_adjoining_s: float = 0.5,
    speed_smoothing_frames: int = 5,
) -> dict:
    """Open Field measures for one file, as OF_* summary columns.

    Center membership comes from the file's region columns (center+periphery
    overlap counts as center). Sides come from X/Y relative to the center
    ROI's bounding box (`side_labels`). Entries use the entry rule; a return
    to the center within `min_between_entries_s` of leaving it is the same
    visit. A crossing is side A -> center -> side B (B != A): opposite sides
    always count; adjoining sides only if the center visit lasted at least
    `min_center_adjoining_s`. Crossing speeds use speed smoothed with a
    centered rolling mean over `speed_smoothing_frames` frames.
    """
    nan = float("nan")
    per_frame = frame_roles(data, roles)
    n = len(per_frame)
    in_center = per_frame == "center"

    def secs(frames):
        return round(frames / fps, 2) if fps else nan

    out = {
        "OF_Center_s": secs(int(in_center.sum())),
        "OF_PctCenter": round(100 * in_center.mean(), 1) if n else nan,
        "OF_Periphery_s": secs(int(np.sum(per_frame == "periphery"))),
        "OF_PctPeriphery": round(100 * np.mean(per_frame == "periphery"), 1) if n else nan,
    }

    # Center entries, with the debounce: re-entering within the minimum gap
    # after leaving continues the same visit.
    states = held_states(np.where(in_center, "center", "out"), min_entry_frames)
    min_gap = min_between_entries_s * fps
    entries, first_entry, last_exit = 0, None, None
    for k, (label, start) in enumerate(states):
        if label == "out":
            if k > 0:
                last_exit = start
            continue
        if k == 0:
            continue  # started in the center: time counts, not an entry
        if last_exit is not None and start - last_exit < min_gap:
            continue  # came back too soon: same visit
        entries += 1
        if first_entry is None:
            first_entry = start
    out["OF_CenterEntries"] = entries
    out["OF_Latency_Center_s"] = secs(first_entry) if first_entry is not None else nan

    # Sides from X/Y around the center ROI.
    centers = [r for r, k in roles.items() if k == "center"]
    polys = match_polygons(data)
    center_polys = [polys[r] for r in centers if r in polys]
    crossing_cols = ["OF_Left_s", "OF_Right_s", "OF_Top_s", "OF_Bottom_s",
                     "OF_Crossings_Total", "OF_Crossings_Opposite",
                     "OF_Crossings_LeftRight", "OF_Crossings_TopBottom",
                     "OF_Crossings_Adjoining", "OF_CrossingSpeed_Mean_cm_s",
                     "OF_CrossingSpeed_Peak_cm_s"]
    if not center_polys:
        out.update({c: nan for c in crossing_cols})  # no center ROI to measure from
        return out

    def poly_area(p):
        xs, ys = np.asarray(p[0], float), np.asarray(p[1], float)
        return abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))

    cxs, cys = max(center_polys, key=poly_area)  # the main center ROI if several
    x = data.df["X"].to_numpy(dtype=float)
    y = data.df["Y"].to_numpy(dtype=float)
    sides = side_labels(x, y, cxs, cys)
    # Center frames are "center"; others take their side ("" if untracked).
    place = np.where(in_center, "center", np.where(np.isnan(x) | np.isnan(y), "", sides))
    for side in SIDES:
        out[f"OF_{side.capitalize()}_s"] = secs(int(np.sum(place == side)))

    # Crossings: side A -> center -> side B, using held places.
    states = held_states(place, min_entry_frames)
    speed = None
    if "Distance_cm" in data.df.columns:
        # Per-frame speed, smoothed so a one-frame tracking jump can't set the peak.
        speed = (data.df["Distance_cm"].astype(float) * fps).rolling(
            max(1, int(speed_smoothing_frames)), center=True, min_periods=1
        ).mean().to_numpy()
    opposite = {frozenset(("left", "right")), frozenset(("top", "bottom"))}
    lr = tb = adjoining = 0
    avg_speeds, peaks = [], []
    for (a, a_start), (c, c_start), (b, b_start) in zip(states, states[1:], states[2:]):
        if c != "center" or a not in SIDES or b not in SIDES or a == b:
            continue
        pair = frozenset((a, b))
        if pair in opposite:
            if pair == frozenset(("left", "right")):
                lr += 1
            else:
                tb += 1
        elif (b_start - c_start) >= min_center_adjoining_s * fps:
            adjoining += 1
        else:
            continue  # adjoining sides, but cut through the center too briefly
        if speed is not None:
            # The traversal: from leaving side A to reaching side B.
            seg = speed[c_start:b_start + 1]
            seg = seg[~np.isnan(seg)]
            if len(seg):
                avg_speeds.append(float(seg.mean()))
                peaks.append(float(seg.max()))
    out["OF_Crossings_Total"] = lr + tb + adjoining
    out["OF_Crossings_Opposite"] = lr + tb
    out["OF_Crossings_LeftRight"] = lr
    out["OF_Crossings_TopBottom"] = tb
    out["OF_Crossings_Adjoining"] = adjoining
    out["OF_CrossingSpeed_Mean_cm_s"] = round(float(np.mean(avg_speeds)), 3) if avg_speeds else nan
    out["OF_CrossingSpeed_Peak_cm_s"] = round(max(peaks), 3) if peaks else nan
    return out


def binned_metrics(
    data: TrackingData, fps: float = 20.0, bin_seconds: float = 60.0
) -> pd.DataFrame:
    """Break the session into fixed time bins and summarize each bin.

    One row per bin: distance, mean speed, and time/percent in each zone.
    """
    df = data.df.copy()
    n = len(df)
    if n == 0 or not fps or not bin_seconds:
        return pd.DataFrame()

    frames_per_bin = max(1, int(round(bin_seconds * fps)))
    df["_bin"] = (np.arange(n) // frames_per_bin).astype(int)

    zones = data.regions
    rows = []
    for bin_idx, g in df.groupby("_bin"):
        gframes = len(g)
        dist_cm = float(g["Distance_cm"].sum()) if "Distance_cm" in g else float("nan")
        bin_dur_s = gframes / fps
        row = {
            "Bin": int(bin_idx) + 1,
            "Start_s": round(bin_idx * bin_seconds, 2),
            "End_s": round(bin_idx * bin_seconds + bin_dur_s, 2),
            "Frames": gframes,
            "Distance_cm": round(dist_cm, 2),
            "MeanSpeed_cm_s": round(dist_cm / bin_dur_s, 3) if bin_dur_s else float("nan"),
        }
        for zone in zones:
            frames_in = int(g[zone].sum())
            row[f"Time_{zone}_s"] = round(frames_in / fps, 2)
            row[f"Percent_{zone}"] = round(100.0 * frames_in / gframes, 1) if gframes else 0.0
        rows.append(row)

    return pd.DataFrame(rows)


_BASICS = ("Duration_min", "TotalDistance_cm", "MeanSpeed_cm_s")
_DETAILS = ("Frames", "FPS", "Duration_s", "TotalDistance_px")


def summary_column_groups(columns) -> dict[str, list[str]]:
    """Sort summary-table columns into display groups (File is not grouped).

    Groups: basics, test (EPM_/OF_ measures), zones (per-region time/%),
    entries, roi, details.
    Anything unrecognized lands in details so a new column is never silently
    lost from the on-screen table.
    """
    groups: dict[str, list[str]] = {
        "basics": [], "test": [], "zones": [], "entries": [], "roi": [], "details": []
    }
    for c in columns:
        if c == "File":
            continue
        if c in _BASICS:
            groups["basics"].append(c)
        elif c.startswith(("EPM_", "OF_")):
            groups["test"].append(c)  # the chosen test's own measures
        elif c.startswith(("Time_ROI_", "Percent_ROI_")):
            groups["roi"].append(c)
        elif c.startswith("Entries_") or c == "ROI_transitions":
            groups["entries"].append(c)
        elif (c.startswith("Time_") and c.endswith("_s")) or c.startswith("Percent_"):
            groups["zones"].append(c)  # per-region columns: center, ol, mid, ...
        else:
            groups["details"].append(c)  # _DETAILS + tracking settings + unknown
    return groups


def batch_summary(datasets: list[TrackingData], fps: float = 20.0) -> pd.DataFrame:
    """Summary metrics for many files, one row each, aligned into a table."""
    return pd.DataFrame([summary_metrics(d, fps=fps) for d in datasets])
