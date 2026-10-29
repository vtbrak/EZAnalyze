"""Core analysis engine for LocationOutput tracking files (GUI-independent)."""

from .loader import TrackingData, load_csv, parse_roi_coordinates
from .metrics import (
    summary_metrics,
    binned_metrics,
    batch_summary,
    summary_column_groups,
    epm_metrics,
    held_entries,
    held_states,
    of_metrics,
    side_labels,
)
from .plotting import path_figure, heatmap_figure, regions_figure
from .regions import (
    ROLE_LABELS,
    TEST_TYPES,
    auto_role,
    center_periphery_overlap,
    check_roles,
    describe_roles,
    frame_roles,
    match_polygons,
    resolve_roles,
)
from .config import DEFAULTS, load_config, save_config

__all__ = [
    "DEFAULTS",
    "load_config",
    "save_config",
    "TrackingData",
    "load_csv",
    "parse_roi_coordinates",
    "summary_metrics",
    "binned_metrics",
    "batch_summary",
    "summary_column_groups",
    "epm_metrics",
    "held_entries",
    "held_states",
    "of_metrics",
    "side_labels",
    "path_figure",
    "heatmap_figure",
    "regions_figure",
    "ROLE_LABELS",
    "TEST_TYPES",
    "auto_role",
    "center_periphery_overlap",
    "check_roles",
    "describe_roles",
    "frame_roles",
    "match_polygons",
    "resolve_roles",
]
