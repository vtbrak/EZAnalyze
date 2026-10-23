"""
Plot builders for a tracking file.

These return matplotlib Figures so the caller (GUI or script) decides whether
to embed, show, or save them. No plt.show() here.
"""

from __future__ import annotations

import numpy as np
from matplotlib.figure import Figure
from matplotlib.path import Path

from .loader import TrackingData, parse_roi_coordinates
from .regions import match_polygons

# Default figure size (inches). Embedded figures stretch to fill their tab;
# constrained layout keeps titles and axis labels inside the canvas at any size.
FIGSIZE = (5, 4.5)


def _draw_rois(ax, data: TrackingData, labels: bool = True) -> None:
    """Overlay the ROI polygon outlines (closed), each labeled with its region."""
    if "ROI_coordinates" not in data.df.columns or not len(data.df):
        return
    rois = parse_roi_coordinates(data.df["ROI_coordinates"].iloc[0])
    for xs, ys in zip(rois.get("xs", []), rois.get("ys", [])):
        if xs and ys:
            ax.plot(list(xs) + [xs[0]], list(ys) + [ys[0]],
                    color="0.6", linewidth=1.0, zorder=1)
    if not labels:
        return
    for region, (cx, cy) in _label_points(match_polygons(data)).items():
        ax.text(cx, cy, region, ha="center", va="center", fontsize=9, zorder=4,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="0.5", alpha=0.75))


def _label_points(polys: dict[str, tuple[list, list]]) -> dict[str, tuple[float, float]]:
    """Where to put each region's label: its middle, unless that middle falls
    inside another region's polygon (e.g. an open field's whole-arena
    'peripheral' contains 'center'), in which case near its top edge."""
    def area(xs, ys):  # shoelace formula
        return 0.5 * abs(np.dot(xs, np.roll(ys, 1)) - np.dot(ys, np.roll(xs, 1)))

    shapes = {r: Path(np.column_stack(p)) for r, p in polys.items()}
    areas = {r: area(np.asarray(xs, float), np.asarray(ys, float))
             for r, (xs, ys) in polys.items()}
    points = {}
    for region, (xs, ys) in polys.items():
        # Middle of the distinct vertices (some files repeat a point).
        pts = np.unique(np.column_stack([xs, ys]), axis=0)
        cx, cy = pts.mean(axis=0)
        # Only the larger, enclosing shape moves its label out of the way.
        if any(shape.contains_point((cx, cy)) and areas[other] < areas[region]
               for other, shape in shapes.items() if other != region):
            top, bottom = pts[:, 1].min(), pts[:, 1].max()
            cy = top + 0.07 * (bottom - top)  # image coords: smaller y is higher
        points[region] = (cx, cy)
    return points


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


def regions_figure(data: TrackingData, roles: dict[str, str] | None = None) -> Figure:
    """Small map of the ROI polygons, labeled by region (and role, if given),
    over a faint path — so a user can see which name is which area."""
    fig = Figure(figsize=(4, 4), dpi=100, layout="constrained")
    ax = fig.add_subplot(111)
    df = data.df
    ax.scatter(df["X"], df["Y"], s=1, color="0.8", edgecolors="none", zorder=0)
    _draw_rois(ax, data, labels=False)
    for region, (cx, cy) in _label_points(match_polygons(data)).items():
        text = region if not roles else f"{region}\n{roles.get(region) or '?'}"
        ax.text(cx, cy, text, ha="center", va="center", fontsize=8, zorder=4,
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="0.5", alpha=0.85))
    ax.set_aspect("equal", adjustable="datalim")
    ax.invert_yaxis()
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_title("Regions in this file", fontsize=10)
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
    cax.set_in_layout(True)  # so constrained layout leaves room for it
    fig.colorbar(im, cax=cax, label="Frames in cell")
    fig.get_layout_engine().set(w_pad=0.1)

    _draw_rois(ax, data)

    ax.set_title(f"Occupancy — {data.name}")
    ax.set_xlabel("X (px)")
    ax.set_ylabel("Y (px)")
    return fig
