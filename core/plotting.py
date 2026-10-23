"""
Plot builders for a tracking file.

These return matplotlib Figures so the caller (GUI or script) decides whether
to embed, show, or save them. No plt.show() here.
"""

from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure

from .loader import TrackingData, parse_roi_coordinates


def _draw_rois(ax, data: TrackingData) -> None:
    """Overlay the ROI polygon outlines, if the file carries them."""
    if "ROI_coordinates" not in data.df.columns or not len(data.df):
        return
    rois = parse_roi_coordinates(data.df["ROI_coordinates"].iloc[0])
    for xs, ys in zip(rois.get("xs", []), rois.get("ys", [])):
        if xs and ys:
            ax.plot(xs, ys, color="0.6", linewidth=1.0, zorder=1)


def path_figure(data: TrackingData, color_by_speed: bool = True) -> Figure:
    """Trajectory plot of X/Y, optionally colored by frame-to-frame speed."""
    df = data.df
    fig = Figure(figsize=(6, 6), dpi=100)
    ax = fig.add_subplot(111)

    _draw_rois(ax, data)

    x = df["X"].to_numpy()
    y = df["Y"].to_numpy()

    if color_by_speed and "Distance_px" in df.columns:
        speed = df["Distance_px"].to_numpy()
        sc = ax.scatter(x, y, c=speed, cmap="viridis", s=4, zorder=2)
        fig.colorbar(sc, ax=ax, label="Speed (px/frame)", shrink=0.8)
    else:
        ax.plot(x, y, color="tab:blue", linewidth=0.6, zorder=2)

    ax.set_title(f"Path — {data.name}")
    ax.set_xlabel("X (px)")
    ax.set_ylabel("Y (px)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.invert_yaxis()  # image coordinates: origin top-left
    fig.tight_layout()
    return fig


def heatmap_figure(data: TrackingData, bins: int = 50) -> Figure:
    """Occupancy heatmap: where the animal spent the most time."""
    df = data.df
    fig = Figure(figsize=(6, 6), dpi=100)
    ax = fig.add_subplot(111)

    x = df["X"].to_numpy()
    y = df["Y"].to_numpy()

    heat, xedges, yedges = np.histogram2d(x, y, bins=bins)
    # Transpose so array orientation matches x (cols) / y (rows).
    im = ax.imshow(
        heat.T,
        origin="upper",
        extent=[xedges[0], xedges[-1], yedges[-1], yedges[0]],
        cmap="inferno",
        aspect="equal",
    )
    fig.colorbar(im, ax=ax, label="Frames in cell", shrink=0.8)

    _draw_rois(ax, data)

    ax.set_title(f"Occupancy — {data.name}")
    ax.set_xlabel("X (px)")
    ax.set_ylabel("Y (px)")
    fig.tight_layout()
    return fig
