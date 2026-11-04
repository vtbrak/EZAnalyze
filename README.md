# Behavior Tracker

Analyzes video-based locomotion tracking CSVs (`*_LocationOutput.csv`) — one row
per video frame with position, zone, ROI, and distance data — and turns them into
summary metrics, time-binned tables, path plots, and occupancy heatmaps.

## Installing and running

For a step-by-step guide written for non-programmers, including a method
that needs no administrator password, see **[INSTALL.md](INSTALL.md)**.

### With Anaconda (recommended, Mac or Windows)
1. Install [Anaconda or Miniconda](https://www.anaconda.com/download) if the
   computer doesn't have it.
2. Get the program folder: download the zip from GitHub (or `git clone`).
   The repository is private, so others need access or a zip from you. Copy
   the folder **without** its `.venv`, if it has one.
3. Double-click **`Install Behavior Tracker.command`** (Mac) or
   **`Install Behavior Tracker.bat`** (Windows). It finds Anaconda, builds the
   program's own environment (`behavior-tracker`, from `environment.yml`,
   using the free conda-forge channel), and says Done or Failed. It only needs
   doing once; run it again after an update to bring the environment up to
   date.
4. From then on, double-click **`Open Behavior Tracker.command`** (Mac) or
   **`Open Behavior Tracker.bat`** (Windows). If the program's package list has
   changed since you installed, it says so; run the installer again.

**First time on a Mac:** macOS may block a downloaded script. Right-click the
file → **Open** → **Open**; after that, double-clicking works.
**On Windows:** if SmartScreen warns about the file, click **More info** →
**Run anyway**. A console window stays open while the app runs and shows any
error messages.

**Uninstall:** `Uninstall Behavior Tracker.command` / `.bat` removes the
environment only; the program folder and your data, results and settings
stay.

### Without Anaconda
The Open launchers fall back to a local Python environment (`.venv`), built
and filled automatically on the first run. On Windows this needs Python 3 from
[python.org](https://www.python.org/downloads/) (tick "Add python.exe to
PATH" during setup).

To run from a terminal instead:

```bash
conda activate behavior-tracker && python gui.py   # Anaconda
./.venv/bin/python gui.py                          # .venv, Mac
.venv\Scripts\python.exe gui.py                     # .venv, Windows
```

## What it computes

**Elevated Plus Maze** (when Test is EPM): open/closed-arm and center time,
% open time (of arm time), arm and center entries, % open entries, Anxiety
Index, closed/open time ratio, and latency to first open/closed/center entry.
An entry only counts once the animal stays in a region for at least **Min
entry (frames)** (default 5), which filters jitter at region boundaries.

**Open Field** (when Test is Open Field): center time and %, center entries
(a return within **Min time between center entries**, default 1 s, is the
same visit), latency to the center, time on each side, field crossings
(opposite sides, and adjoining sides when the center visit lasted at least
the adjoining minimum, default 0.5 s), and crossing speed (average and
peak, smoothed over **Speed smoothing (frames)**, default 5). Sides are judged
against the center ROI's lines exactly as drawn in the file (each edge
extended across the arena), with the top of the video as the top of the
arena.

Every analyzed row records the settings that produced it (test, entry rule,
and the Open Field thresholds), so exported tables show how they were made.

**Summary metrics** (one row per file):
- Total distance (cm / px), duration, mean speed
- Time and percent spent in each region (e.g. center / peripheral, or EPM arms) and each ROI label
- Number of entries into each zone, ROI transitions
- The tracking settings recorded in the file

**Time bins** (per file): the session split into fixed-length bins (default
60 s) with distance, mean speed, and time-in-zone per bin, plus the chosen
test's measures for each bin (EPM: arm/center time, entries, % open, Anxiety
Index, ratio; Open Field: center time and entries, side times, crossings, and
crossing speed). Entries and crossings are counted in the bin where they
start, so the bins add up to the session totals. Latency is session-only.

**Plots** (per file): path/trajectory (colored by speed or one solid color) and
occupancy heatmap, both with ROI outlines. The heatmap labels each region
outside the ROIs so the data stays visible. Cells the animal never entered are
left empty (transparent in a saved PNG) unless **Add background** fills them
with one flat color, which is easy to recolor in an image editor.

## Working with files
1. **Add File…**, **Add Folder…**, or drag files/folders onto the window. Files
   build up a list in the Summary table, each marked **Not analyzed**. Adding a
   file that's already in the list asks whether to add it again.
2. Choose the **Test** (Elevated Plus Maze / Open Field), **frame rate**
   (default 20 fps), and **bin size** in the toolbar.
3. **Analyze Selected** (the row selected in the Summary) or **Analyze All**.
   Nothing is computed until you click one. At the first Analyze, Test, frame
   rate, and bin size **lock** (greyed out), so every file in the load is
   analyzed the same way. Path and Heatmap styling never locks.
4. **Select a row** in the Summary to see that file's Time Bins, Path, and
   Heatmap.
5. **Clear** empties the list and unlocks the settings, e.g. to try one file,
   adjust the settings, then run a whole folder.

The file list resets when the app closes. Settings, plot style, Summary
columns, and region roles are remembered. **Regions…** sets what each region
in the files means (open arm, closed arm, center, periphery).

## Exporting

**Export Selected** (the row selected in the Summary) or **Export All**
(every analyzed file) writes three files **next to each source CSV**, named
after it, overwriting any earlier export:

- `<name>_analysis.xlsx`: **Summary** (the file's row), **Time Bins**, and
  **Settings** (everything used to produce the results: test, frame rate,
  entry rule, Open Field thresholds, region roles, bin size, and the Path and
  Heatmap plot settings).
- `<name>_path.png` and `<name>_heatmap.png`: drawn with the current on-screen
  plot settings at a fixed size (5 × 4.5 in, 200 dpi), whatever the window
  size, with a transparent background (heatmap cells the animal never
  entered stay transparent unless **Add background** is on).

Only analyzed files are exported. If a workbook is open in Excel, close it
before exporting again.

## Layout
```
BehaviorTracker/
├── core/            analysis engine (no GUI dependencies)
│   ├── export.py    write _analysis.xlsx and plot images
│   ├── loader.py    read & validate CSVs, detect region columns
│   ├── metrics.py   summary + time-binned metrics
│   ├── plotting.py  path, heatmap & region-map figures
│   ├── regions.py   region-role mapping and checks
│   └── config.py    saved settings (config.json)
├── gui.py           tkinter front end
├── region_dialog.py Match regions dialog
├── tooltip.py       hover tooltips
├── dialogs.py       pop-up messages (same look on Mac and Windows)
├── environment.yml  Anaconda environment (keep in step with requirements.txt)
├── requirements.txt packages for the .venv fallback
├── find_conda.sh / find_conda.bat   locate Anaconda for the launchers
├── Install Behavior Tracker.command / .bat     build or update the environment
├── Open Behavior Tracker.command / .bat        start the app
└── Uninstall Behavior Tracker.command / .bat   remove the environment
```

The engine in `core/` is deliberately GUI-free so it can be scripted or, later,
bundled into a standalone app (e.g. with PyInstaller).

## Credits and license

Video tracking is adapted from **ezTrack**
(https://github.com/denisecailab/ezTrack), by Zachary T. Pennington, Zhe Dong,
Yu Feng, Lauren M. Vetere, Lucia Page-Harley, Tristan Shuman and Denise J. Cai,
used under the GNU General Public License v3.0. Files containing adapted code
say so at the top, along with what was changed. If you use the video tracking
in published work, please cite ezTrack:

> Pennington ZT, Dong Z, Feng Y, Vetere LM, Page-Harley L, Shuman T, Cai DJ
> (2019). ezTrack: An open-source video analysis pipeline for the
> investigation of animal behavior. *Scientific Reports* 9(1): 19979.

Because it includes ezTrack's code, this program is distributed under the
**GNU General Public License v3.0** (see [LICENSE](LICENSE)). Anyone who
receives a copy, including a future standalone app, must also be able to get
its source code under the same license.
