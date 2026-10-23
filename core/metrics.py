"""
Behavioral metrics computed from a loaded tracking file.

Two families of output:
  * summary_metrics()  -> one dict of numbers for the whole session
  * binned_metrics()   -> a DataFrame with one row per time bin

Frame rate (fps) is supplied by the caller so frames can be converted to
seconds; everything time-based flows from that single number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .loader import TrackingData




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

    Groups: basics, zones (per-region time/%), entries, roi, details.
    Anything unrecognized lands in details so a new column is never silently
    lost from the on-screen table.
    """
    groups: dict[str, list[str]] = {
        "basics": [], "zones": [], "entries": [], "roi": [], "details": []
    }
    for c in columns:
        if c == "File":
            continue
        if c in _BASICS:
            groups["basics"].append(c)
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
