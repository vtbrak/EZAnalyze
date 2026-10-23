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
- **Never run `pip install --upgrade pip` in the venv** — it corrupted pip before
  and required a venv rebuild. Install deps straight from `requirements.txt`.

## Current state (what's built)
- `core/` — GUI-free engine: `loader.py` (read/validate CSV, parse ROI polygons),
  `metrics.py` (summary + time-binned metrics), `plotting.py` (path & heatmap).
- `gui.py` — tkinter app: single-file + batch-folder modes, Summary / Time Bins /
  Path / Heatmap tabs, configurable fps (default 20) & bin size, CSV/Excel export.
- `Open Behavior Tracker.command` — double-click launcher (builds `.venv` on first
  run from `requirements.txt`, then launches `gui.py`).
- Verified working on the one available sample (an atypical EPM file).

## Locked design decisions
- **Trust the file's own zone columns** (`center`, `peripheral`, `ROI_location`)
  for region membership — do not recompute zones from X/Y.
- **EPM arms are labeled in `ROI_location`** in real files, but label strings vary.
  Plan: a **region-role mapping** that auto-classifies each label by keyword
  (open→open arm, closed→closed arm, center, periphery), user-overridable, **saved**.
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

## Build order (next steps)
1. Config/persistence layer (`config.json`).
2. Plot point controls (size/color/transparency) + drag-and-drop file input.
3. Test-type dropdown + region-role mapping panel.
4. EPM metrics — validate against a properly labeled EPM file.
5. Open-field metrics — validate against a real open-field file.
6. Shared immobility detection.

## Blockers
Need two sample files to build/validate steps 4–5: a **properly labeled EPM** file
and an **open-field** file (to confirm the exact `ROI_location` label strings).

## How to run
```bash
cd ~/Desktop/EZanalyze && ./.venv/bin/python gui.py
```
Or double-click `Open Behavior Tracker.command`.
