"""Persistent settings (config.json) for the Behavior Tracker.

Everything the user can tune lives here so it carries over between sessions.
Loading is forgiving: a missing, unreadable, or partly-invalid file falls back
to defaults key by key, so a bad config can never stop the app from starting.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"
)

DEFAULTS: dict = {
    "fps": 20.0,
    "bin_seconds": 60.0,
    "test_type": "Elevated Plus Maze",  # or "Open Field"
    # Entry rule: point must stay in a region this many frames to count.
    "min_entry_frames": 5,
    # Immobility: speed below threshold for at least min duration.
    "immobility_speed_cm_s": 2.0,
    "immobility_min_seconds": 1.0,
    # Open field.
    "min_seconds_between_entries": 1.0,
    "min_center_seconds_adjoining": 0.5,
    # Plot style.
    "plot": {
        "point_size": 4.0,  # float so sizes like 2.5 survive a reload
        "point_color": "#1f77b4",
        "alpha": 0.8,
        "color_by_speed": True,
        "heatmap_bins": 50,
        "heatmap_cmap": "inferno",
        # Fill cells the animal never entered with one flat color (off = those
        # cells are transparent in a saved PNG).
        "heatmap_background": False,
        "heatmap_bg_color": "#cccccc",
    },
    # Which Summary-table column groups are shown on screen (export has all).
    "summary_groups": {
        "basics": True,
        "zones": False,
        "entries": False,
        "roi": False,
        "details": False,
    },
    # ROI_location label -> role (open_arm, closed_arm, center, periphery).
    "region_roles": {},
}


def _merge(defaults: dict, loaded: dict) -> dict:
    """Overlay `loaded` on `defaults`, keeping only values of a matching type."""
    out = copy.deepcopy(defaults)
    for key, default in defaults.items():
        if key not in loaded:
            continue
        value = loaded[key]
        if isinstance(default, dict):
            if isinstance(value, dict):
                # region_roles starts empty, so its user-defined keys are kept as-is.
                out[key] = _merge(default, value) if default else dict(value)
        elif isinstance(default, bool):
            if isinstance(value, bool):
                out[key] = value
        elif isinstance(default, (int, float)):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                out[key] = type(default)(value)
        elif isinstance(value, type(default)):
            out[key] = value
    return out


def load_config(path: str = CONFIG_PATH) -> dict:
    """Return settings from `path`, filling anything missing with defaults."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
    except (OSError, ValueError):
        return copy.deepcopy(DEFAULTS)
    if not isinstance(loaded, dict):
        return copy.deepcopy(DEFAULTS)
    return _merge(DEFAULTS, loaded)


def save_config(config: dict, path: str = CONFIG_PATH) -> None:
    """Write settings atomically so a crash mid-save can't corrupt the file."""
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".config-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
