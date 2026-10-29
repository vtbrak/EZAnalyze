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
- `core/export.py`: writes each analyzed file's `_analysis.xlsx` (Summary,
  Time Bins, Settings sheets), `_path.png`, and `_heatmap.png` next to its CSV.
- `region_dialog.py`: the Match regions dialog.
- `tests/regress_gui.py`: workflow regression test. Run it after GUI changes
  (`.venv/bin/python tests/regress_gui.py`); it needs the sample CSVs.
- `Open Behavior Tracker.command`: Mac double-click launcher (builds `.venv`
  on first run from `requirements.txt`).
- Git repo pushed to GitHub `vtbrak/EZAnalyze` (private). `*.csv`,
  `config.json`, and export outputs (`*_analysis.xlsx`, `*_path.png`,
  `*_heatmap.png`) are gitignored.

## Locked design decisions
- **Trust the file's own region columns** (one True/False column per region)
  rather than recomputing zones from X/Y. The exception is open-field sides,
  which files don't have, so they come from X/Y judged against **that file's
  own drawn center-ROI lines** (as drawn, tilt and all; never straightened).
- **Each file has its own ROI lines; always analyze a file against its own.**
  Never share or cache ROI geometry between files. Only the region-name → role
  mapping is shared.
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
  center; arm entry counts.
- **Immobility: deferred** (user, 2026-10-29: don't calculate it for this data
  for now). Spec and jitter findings are kept in ROADMAP §11 for later.
- **Open field**: center entries (min-frames + min time-between-entries); time/% in
  center; latency; **crossings** across center — opposite sides (L↔R, T↔B) and
  adjoining sides (counted only if ≥ min time in center between sides); **crossing
  speed** reported as both average and peak.

## Build order and progress
Steps 1–3, ROADMAP §7 (file-input workflow), and the §10 groundwork (shared
dialogs + Windows launcher), §8 display fixes, and EPM and open-field metrics (§4–§5)
and §9 export are done. Immobility is deferred (ROADMAP §11). Everything in
the current build order is built; next steps come from the user (and the
first PC test when they're ready). **ROADMAP "Build order" is
the source of truth.**
Sample files `EPM.csv` and `Open Field.csv` are in the project folder
(gitignored). See ROADMAP "Sample data findings" and "Decisions from sample
data".

## How to run
```bash
cd ~/Desktop/EZanalyze && ./.venv/bin/python gui.py
```
Or double-click `Open Behavior Tracker.command`.
