"""
Loading and validation of LocationOutput tracking CSVs.

Each CSV holds one row per video frame for a single tracked animal/video.
This module reads the file, coerces column types, and exposes the analysis
settings that are constant across the file.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from typing import Any

import pandas as pd

# Columns we expect in a LocationOutput file. The program still runs if some
# optional ones are missing, but these are the ones the analyses rely on.
REQUIRED_COLUMNS = ["Frame", "X", "Y"]

# Columns that describe the tracking run and are identical on every row.
SETTINGS_COLUMNS = [
    "Location_Thresh",
    "Use_Window",
    "Window_Weight",
    "Window_Size",
    "Start_Frame",
]

# Boolean-ish columns that pandas may read as strings ("True"/"False").
BOOL_COLUMNS = ["center", "peripheral", "ROI_transition"]


@dataclass
class TrackingData:
    """A single loaded tracking file, ready for analysis."""

    path: str
    df: pd.DataFrame
    settings: dict[str, Any]

    @property
    def name(self) -> str:
        """Short display name (the source video if present, else the file)."""
        if "File" in self.df.columns and len(self.df):
            return str(self.df["File"].iloc[0])
        return os.path.basename(self.path)

    @property
    def n_frames(self) -> int:
        return len(self.df)


def _to_bool(series: pd.Series) -> pd.Series:
    """Coerce a 'True'/'False'/1/0 column to real booleans."""
    if series.dtype == bool:
        return series
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .map({"true": True, "false": False, "1": True, "0": False})
        .fillna(False)
    )


def load_csv(path: str) -> TrackingData:
    """Read one LocationOutput CSV into a TrackingData object.

    Raises ValueError if the file is missing required position columns.
    """
    df = pd.read_csv(path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"{os.path.basename(path)} is missing required column(s): "
            f"{', '.join(missing)}"
        )

    # Numeric position / distance columns.
    for col in ["Frame", "X", "Y", "Distance_px", "Distance_cm"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Boolean zone flags.
    for col in BOOL_COLUMNS:
        if col in df.columns:
            df[col] = _to_bool(df[col])

    # Pull the constant settings off the first row.
    settings: dict[str, Any] = {}
    for col in SETTINGS_COLUMNS:
        if col in df.columns and len(df):
            settings[col] = df[col].iloc[0]

    return TrackingData(path=path, df=df, settings=settings)


def parse_roi_coordinates(raw: str) -> dict[str, list]:
    """Parse the ROI_coordinates dict-string into {'xs': [...], 'ys': [...]}.

    The source stores a Python-literal dict as text; ast.literal_eval reads it
    safely (no code execution). Returns empty lists on any failure.
    """
    if not isinstance(raw, str) or not raw.strip():
        return {"xs": [], "ys": []}
    try:
        parsed = ast.literal_eval(raw)
        if isinstance(parsed, dict):
            return {"xs": parsed.get("xs", []), "ys": parsed.get("ys", [])}
    except (ValueError, SyntaxError):
        pass
    return {"xs": [], "ys": []}
