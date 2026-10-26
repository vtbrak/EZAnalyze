# EZanalyze — Project Context

This file is auto-loaded when a Claude Code session starts in this folder. It is
the handoff brief so a fresh session continues the work with full context. The
detailed plan lives in [ROADMAP.md](ROADMAP.md) — read it before building.

## What this is
A desktop app ("Behavior Tracker") that analyzes video-based rodent locomotion
tracking CSVs (`*_LocationOutput.csv`, one row per video frame) and produces
summary metrics, time-binned tables, path plots, and heatmaps. Supports two
assays: **Elevated Plus Maze (EPM)** and **Open Field**.

## Hard constraints (from the user)
- **Do NOT compile/bundle the app (PyInstaller etc.) until explicitly told.**
  End goal is a standalone app, but we build & run from source for now.
- Keep the **`.command` launcher** that opens the GUI working.
- **Must run on both macOS and Windows PCs.** Avoid Mac-specific features
  entirely, using one portable approach on both. The user tests on a real PC, so
  give them a PC test checklist after cross-platform changes. See ROADMAP §10
  for at-risk pieces (launcher, dialog styling, DnD, fonts).
- **Never run `pip install --upgrade pip` in the venv** — it corrupted pip before
  and required a venv rebuild. Install deps straight from `requirements.txt`.

## Current state (what's built)
- `core/`: GUI-free engine. `loader.py` (read CSV, detect region columns),
  `metrics.py` (summary + time bins + summary column groups), `plotting.py`
  (path, heatmap, region map), `regions.py` (role mapping, per-frame roles,
  polygon matching, overlap check), `config.py` (`config.json`).
- `gui.py`: tkinter app. File list (Add File/Folder/drop, Clear, Analyze
  Selected/All). Test type, fps, and bin size lock at the first Analyze, and
  unlock at Clear. Path/Heatmap controls never lock. Summary
  (File, Status, checkbox column groups); the selected row drives the Time
  Bins / Path / Heatmap tabs (per-tab plot controls). Center/periphery overlap
  warning at Analyze.
- `tooltip.py`: portable hover tooltips.
- `dialogs.py`: **use this for every pop-up** (show_info/show_warning/
  show_error/ask_yes_no), never `tkinter.messagebox`. It renders the first
  sentence bold on both Mac and Windows, so write messages whose first
  sentence says what happened.
- `Open Behavior Tracker.bat`: Windows launcher (CRLF via `.gitattributes`).
- `region_dialog.py`: the Match regions dialog.
- `Open Behavior Tracker.command`: Mac double-click launcher (builds `.venv`
  on first run from `requirements.txt`).
- Git repo pushed to GitHub `vtbrak/EZAnalyze` (private). `*.csv` and
  `config.json` are gitignored.

## Locked design decisions
- **Trust the file's own region columns** (one True/False column per region)
  rather than recomputing zones from X/Y. The exception is open-field sides,
  which files don't have, so they come from X/Y.
- **Region names and order vary between files**, so there's a **region-role
  mapping**: auto-classified by keyword or code (EPM `ol/or`→open, `ct/cb`→
  closed, `mid`→center), user-overridable, **saved**. Unrecognized names
  prompt the user with a dropdown.
- **Overlaps count as center** (EPM arm+mid). **Center/periphery must never
  overlap**: that's a file error, so warn the user.
- **Test type** chosen via a **dropdown** (EPM / Open Field); no auto-detect.
- **All thresholds** are **input boxes in the UI, persisted to `config.json`**.

## Resolved analysis specs (see ROADMAP §4–§5 for full detail)
- **Entry rule**: counts only after the point stays inside a region ≥ N frames (saved).
- **EPM**: open vs closed arm time; report %open time, %open entries, composite
  Anxiety Index, AND closed/open time ratio; latency to first entry; time in
  center; arm entry counts; immobility.
- **Immobility**: immobile when speed < threshold for ≥ min duration; seed
  <2 cm/s for ≥1 s; both configurable/saved; outputs total time, %, bout count.
- **Open field**: center entries (min-frames + min time-between-entries); time/% in
  center; latency; **crossings** across center — opposite sides (L↔R, T↔B) and
  adjoining sides (counted only if ≥ min time in center between sides); **crossing
  speed** reported as both average and peak.

## Build order and progress
Steps 1–3, ROADMAP §7 (file-input workflow), and the §10 groundwork (shared
dialogs + Windows launcher), and §8 display fixes are done. Next: the user's first PC
test (when they're ready), EPM metrics,
open-field metrics, immobility, and §9 export last. **ROADMAP "Build order" is
the source of truth.**
Sample files `EPM.csv` and `Open Field.csv` are in the project folder
(gitignored). See ROADMAP "Sample data findings" and "Decisions from sample
data".

## How to run
```bash
cd ~/Desktop/EZanalyze && ./.venv/bin/python gui.py
```
Or double-click `Open Behavior Tracker.command`.
