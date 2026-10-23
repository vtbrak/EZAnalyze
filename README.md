# Behavior Tracker

Analyzes video-based locomotion tracking CSVs (`*_LocationOutput.csv`) — one row
per video frame with position, zone, ROI, and distance data — and turns them into
summary metrics, time-binned tables, path plots, and occupancy heatmaps.

## Running

Double-click **`Open Behavior Tracker.command`**. On the first run it builds a
local Python environment and installs dependencies automatically; after that it
just launches the app.

To run from a terminal instead:

```bash
./.venv/bin/python gui.py
```

## What it computes

**Summary metrics** (one row per file):
- Total distance (cm / px), duration, mean speed
- Time and percent spent in each zone (center / peripheral) and each ROI
- Number of entries into each zone, ROI transitions
- The tracking settings recorded in the file

**Time bins** (single file): the session split into fixed-length bins (default
60 s) with distance, mean speed, and time-in-zone per bin.

**Plots** (single file): path/trajectory (colored by speed) and occupancy heatmap,
both with ROI outlines overlaid.

## Modes
- **Open File…** — deep-dive one CSV: summary, time bins, and plots.
- **Open Folder…** — batch every CSV in a folder into one combined summary table.

Frame rate (default **20 fps**) and bin size are set in the toolbar; click
**Recompute** after changing them. **Export Table…** saves the active table as
CSV or Excel.

## Layout
```
BehaviorTracker/
├── core/            analysis engine (no GUI dependencies)
│   ├── loader.py    read & validate CSVs
│   ├── metrics.py   summary + time-binned metrics
│   └── plotting.py  path & heatmap figures
├── gui.py           tkinter front end
├── requirements.txt
└── Open Behavior Tracker.command   double-click launcher
```

The engine in `core/` is deliberately GUI-free so it can be scripted or, later,
bundled into a standalone app (e.g. with PyInstaller).
