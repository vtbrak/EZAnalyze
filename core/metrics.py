"""
Behavioral metrics computed from a loaded tracking file.

Families of output:
  * summary_metrics()  -> one dict of numbers for the whole session
  * epm_metrics()      -> Elevated Plus Maze measures (added to the summary)
  * binned_metrics()   -> a DataFrame with one row per time bin

Frame rate (fps) is supplied by the caller so frames can be converted to
seconds; everything time-based flows from that single number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .loader import TrackingData
from .regions import frame_roles


def held_entries(roles: np.ndarray, min_frames: int) -> list[tuple[str, int]]:
    """Entries under the entry rule: [(role, first frame of the entry), ...].

    The animal's current region only changes once it has stayed in a new one
    for at least `min_frames` consecutive frames; shorter visits (boundary
    jitter) are ignored and don't break up a stay. The region it starts in is
    where it was placed, so it isn't counted as an entry. Leaving every region
    ("" role) counts as a place too, so returning from it is a new entry.
    """
    n = len(roles)
    if n == 0:
        return []
    # Run-length encode: start index and label of each run of equal roles.
    change = np.flatnonzero(roles[1:] != roles[:-1]) + 1
    starts = np.concatenate([[0], change])
    lengths = np.diff(np.concatenate([starts, [n]]))
    current = None
    entries = []
    for start, length in zip(starts, lengths):
        role = roles[start]
        if length < max(1, min_frames) or role == current:
            continue
        if current is not None:
            entries.append((str(role), int(start)))
        current = role
    return entries


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
