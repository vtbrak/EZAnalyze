"""
Plot builders for a tracking file.

These return matplotlib Figures so the caller (GUI or script) decides whether
to embed, show, or save them. No plt.show() here.
"""

from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure

from .loader import TrackingData, parse_roi_coordinates

# Default figure size (inches). Embedded figures stretch to fill their tab;
# constrained layout keeps titles and axis labels inside the canvas at any size.
FIGSIZE = (5, 4.5)


def _draw_rois(ax, data: TrackingData) -> None:
    """Overlay the ROI polygon outlines, if the file carries them."""
    if "ROI_coordinates" not in data.df.columns or not len(data.df):
        return
    rois = parse_roi_coordinates(data.df["ROI_coordinates"].iloc[0])
    for xs, ys in zip(rois.get("xs", []), rois.get("ys", [])):
        if xs and ys:
            ax.plot(xs, ys, color="0.6", linewidth=1.0, zorder=1)


def path_figure(
    data: TrackingData,
    color_by_speed: bool = True,
    point_size: float = 4,
    point_color: str = "#1f77b4",
    alpha: float = 0.8,
) -> Figure:
    """Trajectory plot of X/Y points, colored by speed or a single solid color."""
    df = data.df
    fig = Figure(figsize=FIGSIZE, dpi=100, layout="constrained")
    ax = fig.add_subplot(111)

    _draw_rois(ax, data)

    x = df["X"].to_numpy()
    y = df["Y"].to_numpy()

    if color_by_speed and "Distance_px" in df.columns:
        speed = df["Distance_px"].to_numpy()
        sc = ax.scatter(
            x, y, c=speed, cmap="viridis", s=point_size, alpha=alpha,
            edgecolors="none", zorder=2,
        )
        fig.colorbar(sc, ax=ax, label="Speed (px/frame)", shrink=0.8)
    else:
        ax.scatter(
            x, y, color=point_color, s=point_size, alpha=alpha,
            edgecolors="none", zorder=2,
        )

    ax.set_title(f"Path — {data.name}")
    ax.set_xlabel("X (px)")
    ax.set_ylabel("Y (px)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.invert_yaxis()  # image coordinates: origin top-left
    return fig


def heatmap_figure(data: TrackingData, bins: int = 50, cmap: str = "inferno") -> Figure:
    """Occupancy heatmap: where the animal spent the most time."""
    df = data.df
    fig = Figure(figsize=FIGSIZE, dpi=100, layout="constrained")
    ax = fig.add_subplot(111)

    x = df["X"].to_numpy()
    y = df["Y"].to_numpy()

    # Untracked frames come through as NaN; histogram2d can't bin them.
    ok = ~(np.isnan(x) | np.isnan(y))
    heat, xedges, yedges = np.histogram2d(x[ok], y[ok], bins=bins)
    # Transpose so array orientation matches x (cols) / y (rows).
    im = ax.imshow(
        heat.T,
        origin="upper",
        extent=[xedges[0], xedges[-1], yedges[-1], yedges[0]],
        cmap=cmap,
        aspect="equal",
    )
    # Colorbar is attached to the axes (not the figure edge) so the square plot
    # and its bar stay together, centered, however wide the tab is.
    cax = ax.inset_axes([1.04, 0.1, 0.04, 0.8])
    fig.colorbar(im, cax=cax, label="Frames in cell")

    _draw_rois(ax, data)

    ax.set_title(f"Occupancy — {data.name}")
    ax.set_xlabel("X (px)")
    ax.set_ylabel("Y (px)")
    return fig
