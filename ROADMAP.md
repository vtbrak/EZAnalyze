# EZanalyze — Roadmap

Feature and analysis plan for the behavior-tracking analyzer. This is the design
doc: what's built, what was decided (and why), and what's next. Nothing new is
built until it's agreed here.

---

## Already built (current state, as of 2026-10-30)
- **Core engine** (`core/`, GUI-free): loads tracking CSVs, validates columns,
  detects **region columns** automatically (any True/False column, e.g. EPM
  `ol/or/ct/cb/mid`, open field `center/peripheral`), parses ROI polygons.
- **File list** (§7): Add File… / Add Folder… / drag-and-drop add files to a
  list in the Summary, each marked *Not analyzed* until **Analyze Selected** or
  **Analyze All**. **Clear** empties the list. Test type, fps, bin size, the
  entry rule, and the Open Field thresholds lock at the first Analyze and
  unlock at Clear. The selected Summary row drives Time Bins, Path, and
  Heatmap.
- **Test-type dropdown** (EPM / Open Field) and **region-role mapping**
  (auto-classified, user-overridable via the Match regions dialog, saved).
  Each file's regions are checked against the test at Analyze.
- **EPM measures** (§4) and **Open Field measures** (§5) in the Summary
  ("Test measures" group) and **per time bin** (§5b). Includes the entry rule,
  Open Field sides judged against each file's own drawn center lines,
  crossings, and smoothed crossing speed.
- **Summary table**: one row per file. File and Status are always shown; the
  other columns come in checkbox groups (Session basics and Test measures on
  by default; Zone time & %, Entries & transitions, ROI label time & %,
  Details). Choices are saved. Each analyzed row records the settings that
  produced it.
- **Time Bins table**: fixed bins (default 60 s) with distance, speed, region
  time, and the test's measures per bin.
- **Path plot** (color-by-speed or solid color; size, transparency) and
  **occupancy heatmap** (bins, colormap, region labels outside the ROIs, empty
  cells transparent, optional flat-color background). Each tab has its own
  controls, which never lock.
- **Center/periphery overlap warning** at Analyze.
- **Export Selected / Export All** (§9): per file, `_analysis.xlsx` (Summary,
  Time Bins, Settings) plus `_path.png` and `_heatmap.png` next to the source
  CSV.
- **Settings saved** to `config.json` (test type, fps, bin size, entry rule,
  Open Field thresholds, plot style, Summary columns, region roles).
- **Cross-platform groundwork** (§10): shared pop-up dialogs (`dialogs.py`),
  hover tooltips (`tooltip.py`), and launchers for Mac
  (`Open Behavior Tracker.command`) and Windows (`Open Behavior Tracker.bat`).
- **Regression test**: `tests/regress_gui.py` drives the app through the whole
  workflow on the sample files.
- Code is on GitHub (`vtbrak/EZAnalyze`, private). Data CSVs and export
  outputs are gitignored.

---

## Design decisions (locked in)
- **Zone/region membership**: trust the file's own **region columns** (one
  True/False column per region) rather than recomputing from X/Y. The one
  exception is open-field sides, which the file doesn't have, so they're
  judged against **that file's own drawn center-ROI lines** (§5).
- **Each file has its own ROI lines and is analyzed against its own.** ROI
  geometry is never shared or reused between files; only the region
  name → role mapping is shared.
- **Region identification**: region names vary between files (EPM uses short
  codes like `ol`, `ct`, `mid`; open field uses `center`, `peripheral`), and
  their order varies too. So the app keeps a **region-role mapping**: each
  region is auto-classified by keyword or code and can be overridden.
  Unrecognized names prompt the user with a dropdown. **Mapping is saved.**
- **Overlaps**: a frame in more than one region counts as **center**. Center
  and periphery must never overlap; if they do, the file is in error and the
  user is warned.
- **Test type**: a **dropdown** (Elevated Plus Maze / Open Field) selects which
  metric set runs. No auto-detection for now.
- **Thresholds** (entry rule, Open Field gap / adjoining time / speed
  smoothing): **input boxes** in the UI, **values persisted** to `config.json`,
  locked at Analyze, and **recorded with the results** (Summary row and the
  export's Settings sheet).

---

## Planned features

### 1. File input
- [x] **Drag-and-drop** files/folders onto the window, in addition to the
  Add File… / Add Folder… buttons.
- [x] Graceful fallback: if drag-and-drop can't initialize, buttons still work.

### 2. Plot controls (path & heatmap)
- [x] Adjustable **point size**.
- [x] Adjustable **point color** (used when not coloring by speed).
- [x] Adjustable **transparency (alpha)**.
- [x] Toggle: color-by-speed vs solid color; heatmap bin count.
- [x] Settings persisted in `config.json`.
- Later additions: controls moved into their own tabs (Path: size,
  transparency, speed coloring, point color; Heatmap: bins, colormap, Add
  background + color), and they never lock (§7, §8).

### 3. Test-type framework
- [x] Test-type dropdown (saved). It chooses which measures are computed
  (EPM §4 or Open Field §5) and what the region check expects.
- [x] Region-role mapping ("Match regions" dialog, also via **Regions…**):
  each region column is auto-classified (keywords + EPM codes like ol/ct/mid),
  user-overridable, saved. Opens automatically when names can't be matched or
  don't fit the chosen test.
- [x] ROI polygons are paired with regions by data agreement, not file order,
  and labeled on the plots (Path: on the region; Heatmap: outside it, §8).

### 4. Elevated Plus Maze (EPM) metrics (✅ built 2026-10-29; immobility deferred)
- [x] **Open-arm vs closed-arm time** (seconds and %).
- [x] **EPM anxiety measures** — report ALL of:
  - %open-arm time and %open-arm entries (separately)
  - Composite **Anxiety Index** = `1 − [ (open-arm time/total arm time +
    open-arm entries/total entries) / 2 ]` (higher = more anxious)
  - **Closed/open time ratio** = closed-arm time ÷ open-arm time
- [x] **Latency to first entry** — time to first open-arm entry (and closed-arm,
  center for reference).
- [x] **Time in center region** (the cross intersection). Arm+center
  overlap frames count as center (`core.regions.frame_roles`).
- [x] **Open- and closed-arm entry counts.**
- ⏸ **Immobility detection: deferred to a future item** (user, 2026-10-29: not
  calculated for this type of data for now). See §11.

**Entry rule (EPM & open field):** an entry counts only when the tracked point
stays inside the region for at least **N frames** (configurable, saved). Filters
boundary jitter. (A true "all four paws" rule isn't possible — data is a single
centroid.)
- ✅ Built as `core.metrics.held_entries`. The current region only changes
  after N consecutive frames somewhere new, so brief visits don't count and
  jitter doesn't split one stay into two entries. **Default N = 5 frames**
  (0.25 s at 20 fps), set in the toolbar's "Min entry (frames)" box, saved,
  and locked at Analyze with fps and bin size.
- ✅ **Starting region (decided 2026-10-29):** time spent in the region the
  animal starts in **counts toward that region's total time**, but **not
  toward latency**. Latency is the first time it *enters* the region after
  leaving. The starting stay also isn't counted as an entry. Example:
  `EPM.csv` starts on an open arm for 6.80 s; that time is included in open-arm
  time (23.65 s), while open latency is 75.5 s.
- **The rule is recorded with the results**: every analyzed Summary row
  carries `Test` and `MinEntryFrames` columns (Details group), and the §9
  export's Settings sheet lists it ("Min entry (frames)").
- Sample `EPM.csv` (20 fps): open entries are 22 with no rule, 6 at 5 frames,
  and 6 at 10 frames. So 5 frames filters boundary flicker without losing
  real visits.

**EPM columns** (Summary "Test measures" group, on by default):
`EPM_OpenArm_s`, `EPM_ClosedArm_s`, `EPM_Center_s`, `EPM_PctOpenTime` (% of
arm time), `EPM_OpenEntries`, `EPM_ClosedEntries`, `EPM_CenterEntries`,
`EPM_PctOpenEntries` (% of arm entries), `EPM_AnxietyIndex`,
`EPM_ClosedOpenRatio`, `EPM_Latency_Open_s` / `_Closed_s` / `_Center_s`, and
`EPM_PctSession_Open` / `_Closed` / `_Center`. Blank = can't be computed
(e.g. no open-arm time, or an arm never entered).

### 5. Open Field metrics (✅ built 2026-10-29; immobility deferred)
- [x] **Center-region entries** — count entries into the center, using the
  shared entry rule (min frames inside) plus a **minimum time-between-entries
  threshold** (debounce). Both configurable, saved.
- [x] **Time & % in center**, latency to first center entry.
- [x] **Field crossings** — a crossing is a traversal **across the center** that
  connects two sides. Counts in three categories:
  - **Opposite sides**: left↔right and top↔bottom.
  - **Adjoining sides**: e.g. left→top — counted **only if the path spends at
    least a minimum time in the center region** between the two sides
    (configurable, saved), so corner-cuts near an edge don't count.
  - Report counts per category (and a total). Center comes from the file's
    region column. **Sides come from X/Y** relative to the center ROI, with
    the top of the video as the top of the arena (the files have no side
    regions).
- [x] **Crossing speed** — report **both** average speed over the traversal
  (leaving one side → reaching the next) and **peak** speed during crossings.

**✅ Open Field definitions (decided 2026-10-29)**
- **Defaults:** min time between center entries **1 s**; min center time for an
  adjoining-side crossing **0.5 s**; speed smoothing **5 frames**. All three are
  input boxes on a third toolbar row that only shows when the test is Open
  Field. They're saved and lock at Analyze.
- **Center entries:** the entry rule (min frames) applies. Re-entering the
  center less than the minimum gap after leaving it continues the same visit.
  The starting region counts toward time, not entries or latency (as for EPM).
- **Sides follow the center ROI's drawn lines as they are in the file**
  (user, 2026-10-29: "Follow the lines of the ROIs from the file, not what
  would be assumed to be straight." The program doesn't draw ROI lines; it
  reports which side of the drawn line the point is on.) Each edge of the
  drawn center polygon is extended across the arena, and a point belongs to
  the side whose line it's furthest beyond: left of the drawn left edge =
  left, above the drawn top edge = top, and so on. **Corners split along the
  diagonal** between the two lines. An edge's side comes from the way it
  faces. Top of the video = top of the arena. A point inside the polygon but
  not in the center by the file's columns takes its nearest edge's side, so
  every frame is center or exactly one side. Built as
  `core.metrics.side_labels`.
- **Every file has its own ROI lines, and each file is analyzed against its
  own** (user, 2026-10-29). Center membership comes from that file's region
  columns; sides, crossings, and plot outlines/labels come from that file's
  own `ROI_coordinates`. Nothing geometric is shared or reused between files.
  Only the region *name → role* mapping is shared, since names mean the same
  thing across files. Verified with two files that have the same path but
  different center squares: each gets its own sides and crossings.
- **Crossings:** side A → center → side B with B ≠ A, using the entry rule's
  held places. Opposite sides (left↔right, top↔bottom) always count. Adjoining
  sides count only if the center visit lasted ≥ the minimum. Going around the
  edge without the center, or returning to the same side, isn't a crossing.
- **Crossing speed:** speed is **smoothed** first (user, 2026-10-29): a
  centered rolling mean over **Speed smoothing (frames)**, default **5**
  (0.25 s at 20 fps), saved, locked at Analyze, 1 = none. The average is the
  mean of each counted crossing's average speed from leaving side A to
  reaching side B. The peak is the fastest smoothed frame during any counted
  crossing.
- **Recorded with the results:** Open Field rows carry
  `MinBetweenCenterEntries_s`, `MinCenterAdjoiningCrossing_s`, and
  `SpeedSmoothing_frames` (plus `Test` and `MinEntryFrames`) in the Details
  group and every export.
- **Columns** (Summary "Test measures"): `OF_Center_s`, `OF_PctCenter`,
  `OF_Periphery_s`, `OF_PctPeriphery`, `OF_CenterEntries`,
  `OF_Latency_Center_s`, `OF_Left_s` / `_Right_s` / `_Top_s` / `_Bottom_s`,
  `OF_Crossings_Total`, `_Opposite`, `_LeftRight`, `_TopBottom`, `_Adjoining`,
  `OF_CrossingSpeed_Mean_cm_s`, `OF_CrossingSpeed_Peak_cm_s`.
- **Sample `Open Field.csv`:** center 21.5% (793 s), 227 center entries (250
  with no gap, 202 with 3 s), 197 crossings (66 opposite: 27 L↔R and 39 T↔B;
  131 adjoining), crossing speed 10.2 cm/s average and 36.1 cm/s peak with
  5-frame smoothing (42.8 unsmoothed). Center + sides = the full 3686.3 s
  session.
- ⏸ Immobility detection: deferred (see §11).

### 5b. Test measures per time bin (✅ built 2026-10-30)
- [x] The **EPM and Open Field measures are added to the Time Bins** table
  (on screen and in the exported Time Bins sheet), after the general bin
  columns (requested 2026-10-30).
- **EPM per bin:** open/closed/center time, % open time, open/closed/center
  entries, % open entries, Anxiety Index, closed/open ratio, and
  `EPM_PctBin_Open` / `_Closed` / `_Center` (% of the bin).
- **Open Field per bin:** center and periphery time and %, center entries,
  time per side, crossings (total, opposite, L↔R, T↔B, adjoining), and
  crossing speed (average and peak) for the crossings in that bin.
- **How bins are counted:** entries and crossings are found **once over the
  whole session**, then each is counted in the **bin where it starts** (a
  crossing starts when the animal leaves side A for the center). So bin
  values add up to the session totals, a visit or crossing that spans a bin
  edge isn't split or double-counted, and a bin's start isn't treated as a
  starting position. Verified on both samples at 60 s and 30 s bins: every
  entry and crossing count sums exactly to the session, and times match.
- **Latency is session-only** (time to the first entry), so it isn't in the
  bins.
- Built as `epm_binned` / `of_binned` in `core/metrics.py`, sharing one
  span calculation (`_epm_block` / `_of_block`) with the session summary.

### 6. Config / persistence
- [x] `config.json` holding fps, bin size, all thresholds, plot style, and the
  region-role mapping. Loaded on start, saved on change.

### 7. File-input workflow (requested 2026-10-23 — ✅ built 2026-10-23)
The larger concern: how the program handles files loaded one after another,
and multiple files from a folder.

**Problems before §7 was built**
- Loading a file **replaces** the previous one and **immediately computes**
  using whatever settings (test type etc.) are already selected.
- There's no chance to choose the test type and parameters for a file
  *before* it's analyzed — so loading an open-field file while EPM is selected
  triggers the "doesn't fit the test" warning before the user can say which
  test it is.
- After loading a **folder**, there's no way to pick one file from it and view
  its Time Bins, Path, or Heatmap (batch mode only shows the Summary table).

**Notes from building**
- Each file's regions are checked against the test **on its own** at Analyze
  time. Files that still don't fit after the Match regions dialog are skipped
  and named, while the rest are analyzed.
- Repeated files get "(2)", "(3)", ... after the name so their rows can be
  told apart.
- Export later became per file (§9), replacing the single-table export.

**Wanted**
- [x] A load step that lets the user **pick the test type and parameters for a
  file before computing**, without the EPM/open-field warning firing first.
- [x] A defined behavior for **loading files one after another** (rather than
  silently replacing and recomputing).
- [x] In folder/batch mode, a way to **select a single file** and view its Time
  Bins, Path, and Heatmap.

**✅ Decided 2026-10-23**
- [x] **New files are added to a list.** Loading (Add File…, Add Folder…,
  drag-and-drop) appends to the list instead of replacing what's there.
- [x] **Clear button** empties the list.
- [x] **The list resets when the app closes.** It isn't saved between
  sessions.
- [x] **Settings are chosen once per load session.** They stay editable after
  files are added, and **lock at the first Analyze**. They then apply to every
  file added afterward. **Clear** resets this, so settings can be chosen again
  for the next batch. (Changed 2026-10-23: originally locked at the first
  load, but the user wants to load a file *then* choose settings.)
  - A **tooltip** explains this, e.g. on Clear: "Clears the file list and
    lets you choose settings again."
- [x] **Analysis starts with an Analyze button**, not automatically on load.
  So the EPM/open-field warning can't fire before the test is chosen.
- [x] **Two ways to analyze:** **Analyze all** files in the list, or
  **Analyze selected**, the file selected in the Summary table.
- [x] **The file selected in the Summary table drives the Path and
  Heatmap** tabs. Clicking a row shows that file's plots. This is also how a
  single file is viewed in folder mode.

**✅ Details decided 2026-10-23**
- [x] **Locked for the whole load session** (until Clear): **test type**,
  **fps**, and **time-bin size** (later also the entry rule and the Open
  Field thresholds). Bin size stays consistent across every file
  in the load, and **is remembered when the app closes**, like fps.
- [x] **Plot style stays adjustable at any time** (point size, colors,
  transparency, colormap, heatmap bins, background), and whatever is selected
  **is remembered** (already saved in `config.json`).
- [x] **"Not analyzed" status in the Summary**, in a column **immediately
  after the file name**. It changes once the file is analyzed.
- [x] **Repeated file: ask the user** whether to ignore it or add it again.
- [x] **Always wait for Analyze.** Files added later are never analyzed
  automatically, even when settings are already chosen.
- [x] Files can be added **one at a time or via a folder**, mixed freely.

**Use case to support:** analyze **one file**, look at the results, adjust
the settings, then run a **larger set** of files. In practice: load one file
→ Analyze → **Clear** (resets the list and unlocks the settings) → choose new
settings → load a folder → Analyze all. The Clear tooltip should make this
clear.

- [x] **Time Bins, Path, and Heatmap all follow the file selected in the
  Summary table.**
- [x] **Locked settings live in the toolbar** (no separate dialog). Test
  type, fps, and bin size can be set before or after adding files. Once
  **Analyze** is clicked, they're **greyed out** with a tooltip explaining
  they're locked until Clear.
- [x] **Path and Heatmap controls never lock**, so plots can be restyled
  after a file is analyzed.

All §7 decisions are made (2026-10-23).

### 8. Layout / display changes (requested 2026-10-23 — ✅ built 2026-10-23)
- [x] **Heatmap: no region labels drawn on the plot** (both EPM and open field).
  The name boxes added in step 3 sit on top of the data and block the view.
  Keep the ROI outlines. (Path plot labels are not part of this request.)
  - ✅ Decided: **labels sit outside the bounds of the regions.** Each label
    goes just past the outermost ROI edge, in its region's direction (EPM
    arms: past the arm end; a central region: along a free diagonal), with a
    thin line that **stops at the region's edge** so it doesn't cross data
    inside the region.
- [x] **Heatmap: no background by default** (EPM and open field). Today
  every empty cell is drawn in the colormap's lowest color (black for
  inferno), so the whole rectangle around the maze is filled. Instead, cells
  with no occupancy should show nothing.
- [x] **"Add background" button** on the Heatmap tab (EPM and open field).
  ✅ Decided 2026-10-23:
  - **Background = any pixel the mouse never occupied.** In practice that's
    every heatmap cell with zero frames, so it follows the heatmap's bin size.
  - **Format: transparent PNG**, so the background can be recolored or
    replaced in Photoshop. With the button off, those cells are transparent;
    with it on, they're filled with a background color.
  - **The button's on/off state is saved** in `config.json` like the other
    plot settings.
  - ✅ Built as an "Add background" toggle plus a **Background color…** picker
    (default light gray `#cccccc`), both saved. The toolbar's save keeps
    transparency (`savefig.transparent`), verified by checking the PNG's
    pixels: empty cells have alpha 0, or a flat color when the background is on.
  - **Heatmap grid now covers the whole arena** (all ROIs plus wherever the
    animal went), with **square cells**: `bins` cells along the longer side.
    So "background" fills every arena cell the animal never entered, not just
    gaps within the area it covered. Side effect: for a narrow path like the
    EPM sample, cells are coarser than before at the same bin count. Raise
    Bins for finer detail.

- [x] **Dialog box text: only the first sentence in bold**, the rest in
  regular type, for every pop-up (warnings, errors, info, questions).
  ✅ Built 2026-10-23 as `dialogs.py`, a tkinter-drawn dialog, because native
  message boxes style text differently (macOS bolds the whole message;
  Windows bolds nothing). It looks the same on both (§10).

### 9. Exporting results (requested 2026-10-23 — ✅ built 2026-10-29)
- [x] Proper **export for a single file** and for **multiple files**
  (folder/batch).

**Built as:** **Export Selected** / **Export All** buttons (replacing Export
Table…), with `core/export.py` doing the writing. Notes:
- Only analyzed files are exported. Export All reports how many weren't
  analyzed; Export Selected on an unanalyzed file says to analyze first.
- A file added to the list twice is exported once (same output names).
- The **Settings sheet** has Section / Setting / Value rows: Source (file path,
  video name, export time), Analysis (test, fps, min entry frames, and for
  Open Field the entry gap, adjoining center time, and speed smoothing),
  Region roles, Time Bins (bin size), Path, Heatmap, and the file's own
  tracking settings. On/off values read Yes/No.
- Images are drawn by the same builders as the on-screen plots, using the
  plot settings at the moment of export, transparent, and cropped to their
  content so no label is clipped.
- **Exported plots are a fixed size: 5 × 4.5 in at 200 dpi** (about 1000 ×
  900 px before cropping), independent of the window. Matching the on-screen
  size was tried and **reverted** (user, 2026-10-29: the image must not resize
  with the window). Because the on-screen plot stretches to fill its tab,
  points can look denser in the export than on screen at the same point size.
- A file open in another program (e.g. the workbook in Excel, which locks
  files on Windows) is reported by name; the other files still export.
- Output files (`*_analysis.xlsx`, `*_path.png`, `*_heatmap.png`) are
  gitignored like the CSVs.

**What existed before**
- **Export Table…** saves whichever table tab is active (Summary or Time
  Bins) as CSV or Excel. It's one table at a time, and the Summary always
  includes every column.
- In batch mode, only the combined Summary can be exported. There are no
  per-file Time Bins.
- Plots can only be saved one at a time, through the matplotlib toolbar under
  each plot.

**✅ Decided 2026-10-23: export everything, per loaded file**
For each loaded file (one file, or every file in a folder), named after the
**loaded file's own name** (e.g. `EPM.csv` → `EPM_...`):
- [x] `<name>_analysis.xlsx`: one Excel workbook with **everything, each
  table on its own sheet**: Summary and Time Bins (both including the test's
  measures) plus Settings.
- [x] `<name>_path.png`: the Path plot image.
- [x] `<name>_heatmap.png`: the Heatmap image, keeping the transparent
  background (§8).

**✅ Details decided 2026-10-23**
- [x] **Saved next to each source CSV** (same folder as the file it came
  from).
- [x] **Existing output files are overwritten** without asking.
- [x] Each `_analysis.xlsx` **includes that file's Summary row** (its own
  sheet).
- [x] Each `_analysis.xlsx` includes a **settings sheet** recording every
  setting used to generate its results:
  - analysis: fps, test type, region roles, thresholds, **entry rule (min
    entry frames)**, and for Open Field the **min time between center entries**,
    **min center time for adjoining crossings**, and **speed smoothing**
  - **Time Bins**: bin size
  - **Path**: point size, transparency, color-by-speed, point color
  - **Heatmap**: bins, colormap, background on/off
- [x] Plot images use the **on-screen plot settings** (point size, colors,
  transparency, colormap, bins, background on/off).
- **No separate summary file.** The Summary row lives only in
  `_analysis.xlsx`, and there's no combined file either. (Decided 2026-10-23,
  replacing the earlier separate-CSV plan.)

### 10. Runs on both Mac and PC (requested 2026-10-23 — requirement)
- [ ] The program must **work on Windows PCs as well as macOS**. Groundwork
  built 2026-10-23 (shared dialogs + Windows launcher). **Awaiting the first PC
  test** (user not ready yet as of 2026-10-30). This applies to everything
  built from now on.

**PC test checklist** (for when the user tests): clone the repo, run
`Open Behavior Tracker.bat` (first run installs packages); add a file, change
the test/fps, Analyze, and check the settings grey out; hover a locked setting
for its tooltip; add the same file twice (bold first line, Add Again /
Ignore); drag a CSV or folder onto the window; analyze the Open Field file
(overlap warning); restyle Path and Heatmap; open Regions… (✓/⚠ line); Export
and open the workbook and images; check every toolbar row fits; close and
reopen (settings remembered).

**Known Mac-only or at-risk pieces**
- ✅ **Launcher:** `Open Behavior Tracker.bat` added alongside the Mac
  `.command`. It builds `.venv` from `requirements.txt` (via `py -3`, falling
  back to `python`) and runs `.venv\Scripts\python.exe gui.py` in a console so
  errors stay visible. CRLF line endings are enforced by `.gitattributes`.
  Untested on Windows.
- ✅ **Dialog styling:** `dialogs.py` draws every pop-up with tkinter itself
  (bold first sentence, colored edge by kind, no icons/emoji), so it looks the
  same on both. Native file pickers and the color picker stay native, which is
  fine on both.
- **Drag-and-drop:** `tkinterdnd2` ships Windows builds, but this is
  untested on a PC.
- **Fonts and sizes:** fonts and widget sizes differ between macOS and
  Windows, so layouts (toolbar width, dialog wrapping) need checking on both.
  On the Mac the widest toolbar row is ~900 px, so the minimum window width is
  940 px. Windows fonts may run wider.
- **File paths:** keep using `os.path` and never hard-code `/` separators.
  Exports go "next to the source CSV" (§9), which also works on Windows paths.
- **Unicode symbols** in labels (⚠, ✓, —) should be checked on Windows
  fonts.

**Testing**
- ✅ **The user has a Windows PC to test on** (2026-10-23). After
  cross-platform work, hand over a short checklist of what to try on the PC.
- **Avoid Mac-specific features entirely**, even where a Mac-only option
  would look nicer. Prefer one portable approach used on both systems.
- Not part of this item: compiling/bundling (still on hold per CLAUDE.md).

### 11. Future items (deferred, not scheduled)
- ⏸ **Immobility detection** (EPM and open field). Deferred 2026-10-29: the
  user chose not to calculate immobility for this type of data for now.
  - **Superseded 2026-10-30:** freezing will come from **ezTrack's Freeze
    Analysis** (§12), using its thresholds instead of the speed-based plan
    below. It measures pixel change in the video, not the tracked point's
    speed, so tracking jitter doesn't affect it. It needs the video; data
    available only as a CSV still gets no freezing measure.
  - Original spec: immobile when speed stays below a threshold for at least a
    minimum duration (seeded at < 2 cm/s for ≥ 1 s, both input boxes, saved).
    Outputs: total immobile time, % immobile, bout count.
  - **Why it needs care — jitter measured in the samples:** while the animal
    is still, the tracked point wanders only ~0.07 cm (radius) and moves
    ~0.04–0.05 cm per frame (median; 95th pct ~0.13–0.15 cm). But at 20 fps
    that's an *apparent* speed of ~1 cm/s (95th pct 2.7–3.1 cm/s), so 10–14%
    of still frames read over 2 cm/s raw, and 8–9% with 5-frame smoothing.
    Larger windows (10–20 frames) were no better, because they blend in real
    movement. A single blip would break a bout, so bouts would be undercounted.
    (The tracking software's own smoothing is on in both files:
    `Use_Window = True`, weight 0.9, window 100. With one centroid, jitter
    can't be fully separated from small real movements like sniffing.)
  - Proposed when it's picked up: keep 2 cm/s / 1 s, share the 5-frame speed
    smoothing, and let a bout continue through a blip shorter than the entry
    rule. Each of these needs the user's OK.

### 12. Video analysis from ezTrack (branch `video-tracking`, started 2026-10-30)
Add video analysis to the app by adapting **ezTrack** (the open-source program
that produced these CSVs), so one tool goes video → tracking → analysis →
export. Development happens on the **`video-tracking` branch**; `main` stays
stable until it's merged.

**Source:** https://github.com/denisecailab/ezTrack (local reference copy in
`ezTrack/`, gitignored, including practice videos).

**License and credit (required; the user asked that they be kept):**
- ezTrack is **GPL-3.0**, so once its code is adapted in, the combined app is
  GPL-3.0. Add the GPL-3.0 license text to the repo; mark every file with
  adapted code ("adapted from ezTrack", authors, GPL-3.0, what was changed);
  credit and cite ezTrack in the README and an in-app About/credits screen.
  A distributed standalone app must also be GPL-3.0, with source available.
- **Citation:** Pennington ZT, Dong Z, Feng Y, Vetere LM, Page-Harley L,
  Shuman T, Cai DJ (2019). ezTrack: An open-source video analysis pipeline for
  the investigation of animal behavior. *Scientific Reports* 9(1): 19979.
- The ezTrack logo art is by Kathleen Wang; credit her if it's ever used.

**What ezTrack is:** two modules of Python functions driven by Jupyter
notebooks with HoloViews interactive tools (crop box, ROI drawing,
distance points). The notebook/HoloViews interface would be rebuilt as
tkinter windows; the processing uses OpenCV (works on Mac and PC, adds a
large dependency).

**✅ Decided 2026-10-30:**
- **Keep both modules:** Location Tracking *and* Freeze Analysis.
- **Freezing uses ezTrack's freeze thresholds**, replacing the planned
  speed-based immobility (§11). ezTrack's defaults: motion cutoff
  `mt_cutoff` = 10 (brightness change for a pixel to count as changed, after
  a light blur, `SIGMA` = 1); `FreezeThresh` = 200 (a frame is still if fewer
  pixels than this changed); `MinDuration` = 15 frames (0.75 s at 20 fps).
  Calibration from an empty-chamber video recommends `mt_cutoff` = 2 × the
  99.99th percentile of pixel change.

**Function catalog** (to go through with the user: keep / drop / rebuild):
- *Location Tracking:* `LoadAndCrop`, `cropframe`, `check_p_frames`,
  `Mask_select` (load/crop/exclude areas); `Reference` (empty-arena
  background); `Locate`, `TrackLocation`, `LocationThresh_View` (tracking and
  preview); `ROI_plot`, `ROI_Location`, `ROI_linearize`, `ROI_transitions`
  (draw ROIs and produce the region columns); `DistanceTool`, `setScale`,
  `ScaleDistance` (pixel → cm); `Summarize_Location`, `showtrace`, `Heatmap`,
  `PlayVideo` / `PlayVideo_ext` / `display_image` (summaries, figures,
  playback); `Batch_LoadFiles`, `Batch_Process` (folders).
- *Freeze Analysis:* `LoadAndCrop` / `cropframe` / `check_p_frames`;
  `Calibrate`; `Measure_Motion`; `Measure_Freezing`; `PlayVideo` /
  `PlayVideo_ext` / `display_image`; `SaveData`; `Summarize`;
  `Batch_LoadFiles` / `Batch`.
- Overlap with what this app already has: `Summarize_Location`, `Heatmap`,
  and `showtrace` (path) are already covered, in more detail.

**Useful for validation:** `ezTrack/PracticeVideos/6_2024-04-01_11-49-23.mp4`
is the video behind `EPM.csv`, so the adapted tracker can be checked against
an existing output.

**✅ Walkthrough, Stage 1 — Load and prepare the video (decided 2026-10-30;
not built).** Functions: `LoadAndCrop`, `cropframe`, `check_p_frames`,
`Mask_select`. Freeze Analysis has near-copies of the first three, so these
decisions apply to both modules. The user accepted all recommendations:
1. **Open videos and report their info** (frame count, frame rate, size):
   keep. **Fill the fps setting from the video's own frame rate
   automatically**, with an option to override it.
2. **Start/end trimming** (`start` / `end`): keep, set by **scrubbing through
   the video** to the trial's start and end frames, shown in seconds as well
   as frames (not only by typing frame numbers). Context: the user's ezTrack
   notebook tracked the EPM practice video from frame 460 to 6460, matching
   `Start_Frame = 460` in `EPM.csv`.
3. **Downsampling** (`dsmpl`): keep as an optional speed setting, **default
   full size (1.0)**.
4. **Display zoom** (`stretch`): **drop**. The app's window handles sizing.
5. **Crop rectangle**: keep as the main way to select the arena (tracking
   ignores everything outside it). `cropframe` stays as its helper.
6. **Crop for a folder of videos:** ezTrack applies one crop (drawn on the
   first video) to every video in a batch. Instead, **each new video starts
   from the previous video's crop, and can be adjusted per video**. This fits
   the rule that each file has its own geometry, and handles a camera that
   moved between sessions.
7. **Compatibility check** (`check_p_frames`: >1% of the first 300 frames
   unreadable): keep, but as a **warning naming the video, with an option to
   continue**, instead of ezTrack's hard stop.
8. **Exclusion shapes** (`Mask_select`, any number of drawn areas to ignore,
   e.g. cables or objects): keep for Location Tracking, and **optionally offer
   it in Freeze Analysis too** (ezTrack's freeze module only has the crop).

**✅ How videos fit the app (decided 2026-10-30; not built):** videos go into
the **same file list as CSVs**, with a **"Not tracked"** status. Tracking
(stages 1–5) produces the same per-frame data a CSV provides; from then on,
everything that already exists works unchanged: Analyze, Summary, Time Bins,
plots, and export.

**✅ Walkthrough, Stage 2 — Reference image (decided 2026-10-30; not built).**
Function: `Reference` (Location Tracking only; Freeze Analysis compares each
frame to the previous one and needs no reference). Tracking compares every
frame to a picture of the empty arena; this stage makes that picture.
1. **Only Option 1 is kept: build the reference from the video itself**, as
   the median of frames spread evenly across the trimmed trial (the animal is
   in a different place in most frames, so it drops out).
   - **Dropped:** Option 2 (a separate empty-box video) and Option 3 (a
     hand-picked list of frames).
   - Frame count: ezTrack's code defaults to 100; its notebook and batch mode
     use 50. Default and whether it's a setting are to confirm when building
     (recommendation was 50, changeable, saved).
   - Known limitation to keep in mind: if the animal stays in one spot for
     about half the trial or more, a "ghost" of it remains in the reference
     and tracking suffers there.
2. **Each video gets its own reference image** (as ezTrack's batch mode
   already does), never shared between videos.
3. **Unreadable frames** are replaced by another frame, as in ezTrack.
4. **The reference image is saved with the results**: kept with the tracked
   file and exported as `<name>_reference.png`, next to the other outputs.
5. **Reference as a plot background:** the **Path and Heatmap** plots (on
   screen and exported) get an **option to use the video's reference image as
   the background**. Details to settle in Stage 6, including:
   - how it combines with the Heatmap's current background choices (empty
     cells transparent, or "Add background" flat color), likely as a third
     choice;
   - alignment: X/Y and the reference must share the same crop and
     downsampling so the path sits exactly on the arena;
   - files loaded as CSVs have no reference image, so the option is
     unavailable for them.
- **Open question:** whether to show the reference for a check before
  tracking. Without Options 2 and 3, the remedies for a ghost would be
  changing the frame count or trim.

**✅ Walkthrough, Stage 3 — Tracking the animal (decided 2026-10-30; not
built).** Functions: `Locate` (finds the animal in one frame), `TrackLocation`
(runs it on every frame and builds the per-frame table) and
`LocationThresh_View` (preview on sample frames).
1. **Tracking math is kept as ezTrack does it**: grayscale → downsample →
   crop → difference from the reference (`dark` / `light` / `abs`) → zero the
   exclusion shapes → optional window around the previous position → keep the
   top `loc_thresh` percentile → position = center of mass. The only change is
   item 2.
2. **Wire removal is dropped** (`rmv_wire` / `wire_krn`, and with it ezTrack's
   per-frame wire warning). Note: the user's notebook had it on, so the
   practice video won't reproduce `EPM.csv` exactly; validation against it
   should expect close, not identical, positions.
3. **Settings are input boxes, saved to `config.json` and locked at Track**
   like the other settings, defaulting to the user's notebook values:
   `loc_thresh` 99.5; `method` dark; window on, `window_size` 100 px,
   `window_weight` 0.9.
4. **`window_size` scales automatically with downsampling**, so "100 px"
   always means the same area of the arena (in full-size video pixels).
5. **Preview, improved:** ezTrack's sample frames (red crosshair at the found
   position plus a color view of the differences), plus **scrub to any frame**
   and **re-preview after changing a setting**, before the full track.
6. **Progress bar with Cancel** while a video tracks (ezTrack only prints a
   text bar).
7. **Unreadable frames don't stop tracking** (ezTrack stops at the first one,
   silently dropping the rest of the video). The frame **stays in the data as
   a row** with a blank position, tracking continues (the window uses the last
   good position), and the user is told how many were unreadable.
   - **New column `Frame_Unreadable`** (True/False) in the tracking output
     marks these rows. ezTrack CSVs don't have it, so a file without the
     column is treated as all frames readable.
   - The loader must list it with the other non-region True/False columns
     (`ROI_transition`, `Use_Window`) so it's never taken for a region.
   - **Analysis adjusted for it** (details to confirm when building; these
     are the recommendations): the Summary reports the count (and %) of
     unreadable frames; those frames add no time to any region and no
     distance (no step is drawn across the gap); the entry rule treats them as
     a continuation of the place before, so a gap doesn't create or break an
     entry; Time Bins report unreadable frames per bin; plots skip them.
8. **Every setting used is recorded**: besides what ezTrack already writes
   (threshold, window on/size/weight, start frame), also method, crop,
   downsampling, reference frame count and whether exclusion shapes were
   used, in the tracking output and in the export's Settings sheet.
9. **A tracking CSV is saved**: `<name>_LocationOutput.csv` next to the
   video, in ezTrack's format (plus the new column and settings), so a video
   only needs tracking once and can be reloaded later like any CSV.

**✅ Walkthrough, Stage 4 — Regions of interest (decided 2026-11-03; not
built).** Functions: `ROI_plot` (draw named polygons on the reference),
`ROI_Location` (per-frame True/False column per region, plus
`ROI_coordinates`), `ROI_linearize` (`ROI_location` text label per frame) and
`ROI_transitions` (`ROI_transition`, where that label changes).
1. **Drawing tool rebuilt in tkinter** on the video's own reference image:
   click to place points and close the polygon, drag points to adjust,
   delete or redraw a region.
2. **Test type first, then the tool offers that test's regions to draw**, so
   each region knows its role as it's drawn (no "Match regions" step for
   videos). EPM: open arm 1, open arm 2, closed arm 1, closed arm 2, center.
   Names stay editable; extra regions can be added (role "ignore" or a chosen
   role).
3. **Open Field: draw the arena outline and the center**; periphery = inside
   the outline and not in the center, so the two can't overlap by
   construction. **Rule: a point in both center and periphery counts as
   center** (applies anywhere they could coincide, e.g. a shared edge or a
   center drawn partly outside the outline). The CSV side already resolves
   overlaps to center (`frame_roles` checks center first) while still warning
   that the file is in error.
4. **Each video gets its own ROIs, including in batch** (ezTrack's batch mode
   draws once and shares them; that's dropped). A new video can **start from
   the previous video's ROIs as a draft** that must be looked at and adjusted
   or confirmed; once confirmed, the lines belong to that video only.
5. **Checks while drawing:** warn right away if Open Field center and
   periphery would overlap; EPM arm/center overlaps stay allowed (count as
   center); warn before Track if a required region hasn't been drawn.
6. **Region test kept as ezTrack's** (pixel mask of each polygon, X/Y looked
   up in it), so video results match ezTrack CSVs. Unreadable frames get
   **blank** region values and a blank `ROI_location`.
   - ezTrack does **not** fill in a missing position from the frames around
     it (it stops tracking at the first unreadable frame).
   - **Decided:** the raw `_LocationOutput.csv` keeps unreadable frames
     blank. A **gap-filling option on the analysis side, off by default**,
     fills short gaps with a straight line between the positions just before
     and after (max gap length a saved setting, e.g. 5 frames); longer gaps
     stay blank. Filled rows stay marked by `Frame_Unreadable`, the saved
     data is never altered, and the option and max gap are recorded in the
     export's Settings sheet. Region values for filled frames come from the
     filled position against that file's own ROIs.
7. **Output format kept exactly as ezTrack's**: one True/False column per
   region, `ROI_coordinates`, `ROI_location`, `ROI_transition`, so the
   existing loader and analysis read video results unchanged.
8. **ROIs use the same coordinates as X/Y** (after crop and downsampling), so
   the path and reference background line up; crop and downsampling are
   recorded (Stage 3).
9. **Videos without regions are allowed** (distance and plots only), with a
   warning at Analyze since EPM and Open Field measures need regions.

**✅ Walkthrough, Stage 5 — Scale, pixels to cm (decided 2026-11-03; not
built).** Functions: `DistanceTool` (click two points on the reference, shows
the pixel length), `setScale` (real length and unit) and `ScaleDistance`
(cm per pixel = real ÷ pixel length; `Distance_cm` = `Distance_px` × factor).
Only distance is converted; X/Y and ROI coordinates stay in pixels.
1. **Measuring tool rebuilt in tkinter** on the video's reference image:
   click two points, drag to adjust, live pixel length, then type the real
   length.
   - **Guidance text above the drawing area** giving the arena sizes:
     **Open Field: 40 cm, inside corner to inside corner along one wall.
     EPM: 75 cm across** (end to end of opposite arms).
2. **Unit fixed to cm** (no free-text unit; ezTrack names the column after
   whatever is typed, which our analysis wouldn't find), so the output is
   always `Distance_cm`.
3. **Each video gets its own scale, including in batch** (ezTrack's batch
   mode measures once and shares it; dropped). A new video starts from the
   previous video's points and length as a draft to confirm or adjust.
4. **The real length is remembered** in `config.json` (per test type,
   starting at 40 cm for Open Field and 75 cm for EPM), so usually only the
   two points need clicking.
5. **The scale is recorded**: pixel length, real length and cm-per-pixel
   factor go in the tracking output and the export's Settings sheet.
6. **Missing scale: warn before Track**, with the option to go ahead; cm
   measures are then blank, as for a CSV without `Distance_cm`.
7. **Measured on the image tracking uses** (after crop and downsampling), so
   the factor always matches X/Y.
8. **One line, as in ezTrack.** A second (perpendicular) line could be added
   later if the camera angle makes horizontal and vertical lengths differ.

**✅ Walkthrough, Stage 6 — Summaries, plots and playback (decided
2026-11-03; not built).** Functions: `Summarize_Location`, `showtrace`,
`Heatmap`, `PlayVideo`, `PlayVideo_ext`, `display_image`.
1. **`Summarize_Location` dropped**: our Summary and Time Bins replace it.
2. **`showtrace` and `Heatmap` dropped**: our Path and Heatmap stay (the
   heatmap stays our square-cell grid, not ezTrack's blurred image). The
   one thing taken from them is the reference image as a background
   (Stage 2).
3. **Background choices**, saved in `config.json`: **Path** — *None* or
   *Reference image*; **Heatmap** — *None* (empty cells transparent), *Flat
   color* (the current "Add background") or *Reference image*.
4. **How the reference background looks:** grayscale; heatmap cells stay
   fully colored on top, so the reference shows only where the animal never
   went; with the reference on, the plot shows the whole reference image
   (the cropped arena) instead of fitting to the ROIs and data; the exported
   PNG is then not transparent.
5. **Alignment:** the reference sits in the same pixel coordinates as X/Y
   and the ROIs, top of the video at the top (guaranteed by Stage 4 item 8).
6. **Files without a reference** (loaded CSVs): *Reference image* is greyed
   out with a tooltip saying why; they fall back to *None*.
7. **Playback kept, rebuilt as a tkinter window** for the selected file:
   play/pause, scrub slider, speed choice; colored marker on the tracked
   position plus an optional short trail; optional ROI outlines; frame
   number, time and current region shown; unreadable frames marked (no
   marker) instead of crashing (ezTrack's playback crashes on a blank
   position). This is the main way to check the tracking.
8. **Saving the playback as a video: optional button, off by default**,
   writing `<name>_tracked.avi` next to the video at the video's **real**
   frame rate (ezTrack always writes 20 fps), with marker and ROIs drawn
   on, in a format that plays on Mac and Windows without extra software;
   overwrites like the other exports (ezTrack always writes
   `video_output.avi`, overwriting across videos).

**✅ Walkthrough, Stage 7 — Batch processing (decided 2026-11-03; not
built).** Functions: `Batch_LoadFiles` (videos of one type in one folder),
`Batch_Process` (per video: unreadable-frame check, own reference, track,
save `_LocationOutput.csv`, add to `BatchSummary.csv`; crop, exclusions,
ROIs and scale set once on the first video and reused) and `check_p_frames`
(refuses a video if >1% of its first 300 frames are unreadable).
1. **Adding videos:** Add File, Add Folder and drag-and-drop accept videos
   (`.mp4`, `.avi`, `.mov`, `.wmv`, `.mpg`, `.mkv`) as well as CSVs; mixed
   folders are fine; new videos show **"Not tracked"**.
2. **Already tracked:** if a video has a `_LocationOutput.csv` beside it,
   ask once for the batch: **Use existing tracking** (default) or **Track
   again**.
3. **"Set up each, then track all":** the interactive steps (trim, crop,
   exclusions, ROIs, scale) are done per video up front, each starting from
   the previous video's choices as a draft; then **Track All** runs every
   set-up video unattended. Videos not fully set up are skipped and named
   afterward. (ezTrack's shared first-video setup is dropped.)
4. **Running:** one video at a time in the background (window stays
   responsive); overall progress ("video 3 of 12") plus the current video's;
   **Cancel** stops after the current frame, keeps finished videos, leaves
   the rest "Not tracked"; a failure in one video doesn't stop the others and
   is reported at the end.
5. **After tracking:** each video becomes **"Not analyzed"**, like a loaded
   CSV, and the existing Analyze Selected/All step runs as now ("always wait
   for analyze"). Its `_LocationOutput.csv` and `_reference.png` are already
   saved.
6. **Tracking settings** (threshold, method, window, reference frame count,
   downsampling) **lock at the first Track** for the whole load and unlock at
   Clear, like test type, fps and bin size.
7. **Frame rate:** read from each video; warn before Track if it differs from
   the fps setting or from other videos in the load (option to continue);
   the rate used is recorded in the outputs.
8. **Unreadable-frame check kept as a warning, not a refusal**, when a video
   is added; the file list shows the % found, and the warning keeps ezTrack's
   suggestion to convert the video.
9. **`BatchSummary.csv` and the combined plot layout dropped** (no summary
   file, per the user; plots follow the selected file).

**⏸ Walkthrough — Freeze Analysis (recorded 2026-11-03; EXCLUDED from the
current build).** The user asked for these to be logged but **not built for
now**: the first video build is Location Tracking only. Nothing below goes
into the build order until the user brings it back. Any freezing hooks
mentioned elsewhere (e.g. FREEZING/ACTIVE in playback) are part of this
deferral.

ezTrack's module measures how much of the picture changes frame to frame (no
reference image). Functions: `LoadAndCrop` (same as Stage 1), `Measure_Motion`
(grayscale → downsample → crop → blur `SIGMA` → count pixels whose change >
`mt_cutoff` = the frame's Motion), `Measure_Freezing` (freezing = Motion below
`FreezeThresh` for ≥ `MinDuration` frames, back-filled to the bout start;
0/100 per frame), `SaveData` (`_FreezingOutput.csv`), `Summarize`,
`PlayVideo`/`PlayVideo_ext` (FREEZING/ACTIVE overlay), `Calibrate` (empty-arena
video; `mt_cutoff` = 2 × the 99.99th percentile of pixel change), and the
batch functions.

Problems found in ezTrack's code: stops at the first unreadable frame (and
drops a good one); the first frame can never be freezing; no exclusion shapes;
`FreezeThresh` is a pixel count (depends on resolution/downsampling/crop);
`MinDuration` is in frames (depends on fps); `Calibrate` ignores the crop.

Decisions (as recommended):
1. **Method kept as ezTrack's**, defaults `mt_cutoff` 10, `FreezeThresh` 200,
   `MinDuration` 15 frames, `SIGMA` 1; saved boxes that lock at Track. Only
   change to the math: fix the first-frame quirk.
2. **"Measure freezing" checkbox** (saved): measured in the **same pass
   through the video as tracking**; works for EPM and Open Field videos. New
   test type **"Freezing only"** (e.g. fear conditioning) skips tracking and
   regions.
3. **`<name>_FreezingOutput.csv` kept separate, in ezTrack's format**, plus a
   `Frame_Unreadable` column and all settings used; the loader joins it with
   `_LocationOutput.csv` by frame; reloadable without the video.
4. **Unreadable frames:** keep going, Motion blank, frame marked; a blank
   frame **breaks** a bout and is left out of the % freezing denominator.
5. **Stage 1 exclusion shapes also apply to motion** (addition to ezTrack).
6. **Units kept as ezTrack's** (pixels, frames) so thresholds match the
   published ones; each box shows its equivalent for the current video (e.g.
   "15 frames = 0.75 s"); warn if downsampling/crop changed since the
   thresholds were last used; all recorded in the export.
7. **Measures:** % time and total time freezing, bout count, mean and
   longest bout, latency to first freeze, mean Motion; in the Summary (new
   "Freezing" column group) and per time bin (bouts counted in the bin where
   they start).
8. **Freezing by region role** when both tracking and freezing ran (EPM open/
   closed/center; Open Field center/periphery).
9. **Freezing tab**: Motion over time, freezing shaded, threshold line;
   exported as `<name>_freezing.png`.
10. **Playback** (Stage 6 window): FREEZING/ACTIVE and current Motion, also in
    the optional saved video.
11. **`Calibrate` kept as an optional tool**: empty-arena video or a stretch
    with no animal; uses the crop; shows the histogram; suggested `mt_cutoff`
    to accept or ignore.
12. **Batch follows Stage 7** (one pass); `Summarize` dropped (our Summary and
    Time Bins replace it); `SaveData`'s file kept (item 3).

**Still to decide:** the details of the video windows (in the GUI review below).

**Last step of the planning, before building:** once every walkthrough stage
is decided, **review the GUI as a whole**: how the new video steps (load,
crop, reference, track, ROIs, scale, freeze, and ASR from §13) fit with the existing CSV
workflow, how windows, tabs, toolbars and settings are organized, and what
should be regrouped or simplified. Record the agreed layout here, then build.

**✅ GUI review (decided 2026-11-03; not built).** Problems found in the
current layout: the toolbar grows a row with each group of settings (three
rows already; tracking would add more, and the window's 940 px minimum width
comes from this); the file list is the Summary tab, so it's hidden on Time
Bins / Path / Heatmap; files can't be removed one at a time (only Clear);
greyed-out locked settings don't say why; there's nowhere for the GPL credits
and license ezTrack requires.
1. **Settings move to a left-hand panel** in sections: **Session** (Test,
   frame rate, bin size), **Entries and regions** (min entry, Regions…),
   **Open Field** (only for Open Field), **Tracking** (only when videos are
   listed). Each section shows a lock icon and "Locked. Clear to change."
   The toolbar becomes one row of buttons.
2. **File list always visible above the tabs**: File, Type (CSV / Video),
   Status, with a draggable divider between list and tabs. The **Summary
   tab** keeps the full table of measures.
3. **Status steps per file** with color tags: *Needs setup → Ready to track →
   Tracking 45% → Not analyzed → Analyzed*, plus *Failed* (with the reason).
   CSVs start at *Not analyzed*.
4. **Toolbar in working order:** Add files / Add folder / **Remove** / Clear |
   **Set up videos…** | **Select all** / **Track** / **Analyze** / **Export** |
   **About**. Set up videos… and Track show only when videos are listed.
   (Decided 2026-11-03 after mocking alternatives: separate Selected/All
   buttons, a shared "Apply to" dropdown, and per-button dropdowns were all
   considered; the user found "Apply to" unclear and chose this.)
   - **Track, Analyze and Export always act on the selected files**, and each
     button shows how many, e.g. **Analyze (1)**.
   - **Select all** selects every file in the list; once everything is
     selected it reads **Select none**. Ctrl+A (Windows) / Cmd+A (Mac) does
     the same.
   - With nothing selected, the buttons say "Select a file first" instead of
     doing nothing.
   - The first file added is selected automatically, so running one file at a
     time (the usual case for students) needs no extra clicks.
5. **Multi-select in the file list** (Shift-click, Ctrl/Cmd-click), so the
   buttons can act on a few chosen files.
6. **One video setup window** with a step list on the left (1 Trim and crop,
   2 Exclusions, 3 Reference, 4 Tracking check, 5 Regions, 6 Scale), each
   step's instructions above the image, Back / Next, a **video 2 of 3**
   switcher with arrows, **Start from previous video**, and a check mark on
   finished steps.
7. **Tracking settings are adjusted in step 4 (Tracking check)**, where their
   effect is visible, and shown in the main window's Tracking section. They
   are shared by every video in the load and lock at the first Track; step 4
   says they apply to all videos.
8. **Tracking progress in a bar at the bottom of the main window** with
   Cancel, not a pop-up, so the window stays usable.
9. **Path and Heatmap tabs** get the **Background** choice (Stage 6) and a
   **Play video…** button for the selected video. No new tabs for now.
10. **About button:** version, ezTrack credit and citation, and the GPL-3.0
    license text, as the license requires.
11. **Right-click menu on file rows** (Analyze, Export, Set up, Play video,
    Remove) as a shortcut, buttons kept; right-click or Control-click on
    Mac. Optional, low priority.
12. **Room for later:** freezing and ASR plug in as their own settings
    sections and tabs, shown by test type, without redoing this layout.

**Planning for the video build is complete.** Build started 2026-11-04.

**🔨 Video build progress (Location Tracking only; freezing and ASR excluded).**
Built in small chunks; **each chunk is committed and pushed when done** so the
work survives interruption (e.g. the laptop closing). A new session resumes at
the first unchecked chunk. Run `tests/regress_gui.py` (and the chunk's own
test) before each commit.
- [x] **C0. Groundwork:** OpenCV (`opencv-python-headless`), SciPy and Pillow
  in `requirements.txt` and `environment.yml`; GPL-3.0 `LICENSE`; ezTrack
  credit and citation in the README; this checklist.
- [x] **C1. Video reading (`core/video.py`):** open a video, report frame
  count / fps / size, read frame N as grayscale with downsampling and crop
  (ezTrack `LoadAndCrop` / `cropframe`), unreadable-frame check as a warning
  (`check_p_frames`), exclusion-shape mask from polygons (`Mask_select`).
  Built 2026-11-04, tested by `tests/test_video.py`. Notes: ezTrack's resize
  call actually uses bilinear interpolation (it passes `INTER_NEAREST` in the
  `dst` slot), kept for matching results; a run of unreadable frames at the
  very end of a video is dropped (files often report a few frames more than
  they hold), while unreadable frames before the end are kept as blank rows.
- [x] **C2. Tracking engine (`core/tracking.py`):** reference image
  (`Reference`, median of N evenly spaced frames, unreadable frames
  replaced), `locate` (`Locate` minus wire removal; window size scaled by
  downsampling), `track_video` generator (progress, cancel, unreadable frames
  kept as blank rows with `Frame_Unreadable`), region columns from polygons
  (`ROI_Location` etc., blank for unreadable frames; Open Field periphery =
  outline minus center), scale (`Distance_cm`), write
  `<name>_LocationOutput.csv` + `<name>_reference.png`. Validate on the
  practice video against `EPM.csv` (close, not identical: wire removal
  dropped).
  Built 2026-11-04, tested by `tests/test_video.py`. **Validation:** `EPM.csv`
  was tracked on a cropped frame (ezTrack coordinates start at the crop
  corner); the best-matching crop is (165, 5)–(745, 575). With it and the
  notebook settings, over the whole session: median position difference
  2.0 px (95th percentile 6 px); region membership agrees on 97.2–99.6% of
  frames per region; open-arm time 0.7% vs 1.4% (ol) and 5.9% vs 7.4% (or),
  closed and center within 0.7 points. The remaining difference fits the
  dropped wire removal and the unrecorded exclusion shapes and random
  reference frames. We keep one more row than ezTrack (it drops the last
  frame). Tracking speed: ~6,000 frames in 30–45 s on this Mac.
- [x] **C3. Analysis for unreadable frames:** loader treats `Frame_Unreadable`
  as a non-region column; unreadable frames add no time, distance or entries
  (entry rule carries the previous place through a gap); Summary and Time Bins
  report unreadable counts; plots skip them; optional gap filling (off by
  default, max gap saved, recorded in Settings).
  Built 2026-11-04, tested by `tests/test_unreadable.py` (gaps injected into
  both sample files: entries and crossings unchanged, time and distance
  reduced only by the gap). Gap filling lives in `core/gaps.py` (config
  `fill_gaps`, `fill_gaps_max_frames`; works on a copy, filled rows marked
  `Frame_Filled`); its on-screen control comes with the C4 settings panel.
  Summary gains `UnreadableFrames` (and `FilledFrames` when filling), in the
  Details group; Time Bins gain `UnreadableFrames`.
- [x] **C4. Main window re-layout (GUI review items 1–5, 10):** settings panel,
  file list above the tabs with Type and Status, Remove, Select all,
  Track/Analyze/Export on the selection with counts, multi-select, About
  (credits + GPL). CSV workflow unchanged; regression test updated.
  Built 2026-11-04 (`about.py` for the About window). The "Unreadable video
  frames" section (gap filling) appears only when a listed file has a
  `Frame_Unreadable` column. Set up videos… and Track buttons are added in
  C5/C7. Not yet checked by eye: screen capture isn't available to the
  assistant, so the user should look over the new layout.
- [x] **C5. Video setup window, steps 1–3:** trim (scrub), crop, exclusions,
  reference; video switcher; start from previous video; fps from the video.
  Built 2026-11-04: `setup_window.py` (window + drawing canvas),
  `core/video_setup.py` (each video's setup). Shapes are stored in full-size
  video pixels and converted at tracking time, so changing downsampling never
  invalidates them. Downsampling and reference frame count are shared
  settings (config `video_downsample`, `reference_frames`) that lock at the
  first Track. Videos join the file list as Video / "Needs setup"; adding a
  video with >1% unreadable frames asks "Add anyway / Skip". "Start from
  previous video" copies crop and exclusions as a draft (steps un-ticked).
  **Moved to C7:** filling the fps setting from the video and the fps
  mismatch warning (they belong with Track).
- [ ] **C6. Setup steps 4–6:** tracking check (preview, scrub, settings),
  regions (draw/edit; EPM five regions, Open Field outline + center), scale
  (two points, guidance text, remembered length).
- [ ] **C7. Tracking runs:** Track on the selection in a background thread,
  bottom progress bar with Cancel, status steps, existing-tracking prompt,
  settings lock at first Track, fps mismatch warning, results loaded as
  "Not analyzed".
- [ ] **C8. Plots and playback:** reference-image background for Path and
  Heatmap; playback window; optional `<name>_tracked.avi`.
- [ ] **C9. Finish:** exported Settings sheet gains tracking/scale/crop
  settings; README and INSTALL updates; PC test checklist.

### 13. Acoustic startle response (ASR) from video (requested 2026-11-03 — planned, not built)

Measure the startle response from video with a **motion index**, following a
method described in a paper the user supplied. **The user cites papers
outside the app**, so no citation is added in the app or exports for this.

**⏰ Reminder when ASR work starts:** remind the user to put a **sample ASR
video and its stimulus logs** into the project folder (gitignored like the
CSVs) before building.

**The method as described:**
- Videos are recorded at **30 fps**.
- For each pair of successive frames, subtract the later image from the
  earlier one; every pixel whose intensity changed is a candidate, from tiny
  changes (0 → 1) to large ones (0 → 255 and back).
- A **pixel intensity threshold** separates noise from movement: changes
  below it are noise, changes above it are the animal's movement. The paper
  chose **15** by manual inspection and trials.
- **Motion index** for a frame = above-threshold pixels ÷ total pixels in
  the frame, as a **percentage**.
- Sensitive to slight movements (a small head lift, minor limb movement), not
  to ultra-fine ones like breathing; suited to gross startle movements.
- **The ASR value is the maximum motion index** within the response period
  (the paper's wording, "computed between two frames", is read as the peak
  between the start and end frames of the response window; accepted by the
  user 2026-11-03).

**Plan:**
1. **Motion index engine** (`core/asr.py`, GUI-free): read each frame, convert
   to grayscale, absolute difference from the previous frame, count pixels
   whose change is above the threshold, divide by the pixels analyzed, ×100.
   Per frame, record the motion index (%), the above-threshold pixel count
   and the total pixel count. The first frame has no predecessor and is left
   blank.
   - This is the same frame-differencing idea as ezTrack's freezing
     `Measure_Motion` (§12, deferred). Share the reading/differencing code if
     freezing is built later, but ASR follows the paper: no blur by default,
     output as a percentage of pixels, threshold 15.
2. **Adjustable intensity threshold (required):**
   - A **threshold scale (slider) from 0 to 255 paired with an input box**,
     default **15**, saved to `config.json`, locked at Analyze like other
     settings, recorded in the export.
   - **Live preview**: pick any frame (scrub slider) and see that frame
     pair's difference image with **above-threshold pixels highlighted** in
     color over the frame, plus the resulting motion index, updating as the
     slider moves. A second view can show a histogram of pixel changes with
     the threshold marked, to see where noise ends.
   - Optional **noise check**: on a stretch where the animal is still, show
     what share of pixels exceed the threshold (should be near 0%).
3. **Area analyzed:** whole frame by default (as in the paper). Optional crop
   to the animal's enclosure and exclusion shapes (reuse §12 Stage 1 tools)
   so lights, timestamps or the chamber edge don't count; the percentage is
   then out of the **analyzed** pixels. The choice and pixel count are
   recorded, since they change the scale of the index.
4. **Frame rate:** read from the video; warn if it isn't 30 fps (the method
   and threshold were set at 30 fps). Note: at 30 fps one frame is 33 ms, so
   startle latency (onset often within ~10–20 ms in rodents) can only be
   resolved to the nearest frame.
5. **Trials and the response window:** ASR is measured per startle stimulus,
   so the app needs each stimulus's time. **Open question** (how stimulus
   times are known):
   - typed in or loaded from a file (e.g. the startle system's trial log:
     onset time, trial type);
   - a fixed schedule (first onset + interval);
   - or detected from the video (e.g. a cue light) or its audio track.
   For each trial: a **response window** after onset (start and length,
   saved settings) and an optional **baseline window** before onset.
6. **Per-trial measures:** **peak (maximum) motion index** in the response
   window (the ASR value), frame/latency of the peak, mean motion index in the
   window, baseline motion index, and peak minus baseline. Flag trials where
   the animal was already moving at baseline (above a saved level), and
   trials with unreadable frames in the window.
7. **Session measures (decided 2026-11-03: measure both PPI and
   habituation):**
   - mean and median ASR across trials, per trial type;
   - **Prepulse inhibition (PPI):** %PPI = 100 × (1 − mean prepulse+pulse ASR
     ÷ mean pulse-alone ASR), per prepulse level and overall;
   - **Habituation:** ASR across the session by trial number and by block
     (block size a saved setting), e.g. first block vs last block and %
     habituation = 100 × (1 − last-block ASR ÷ first-block ASR), plus the
     trial-by-trial trend;
   - trial types (pulse alone, prepulse + pulse at each level, no-stimulus)
     come from the stimulus log; details settled once the sample logs are in
     the folder.
8. **Unreadable frames:** same rule as §12 — keep going, leave the motion
   index blank, mark the frame (`Frame_Unreadable`), report the count.
9. **Outputs** (next to the video, overwriting, like other exports):
   - `<name>_MotionIndex.csv`: one row per frame (Frame, Time_s,
     MotionIndex_pct, AboveThreshold_px, Total_px, Frame_Unreadable, and the
     settings), so a video only needs processing once and can be reloaded;
   - `<name>_ASR_analysis.xlsx`: Trials, Summary and Settings sheets;
   - `<name>_ASR.png`: motion index over time with stimulus onsets and
     response windows marked, plus a plot of all trials' traces aligned to
     onset.
10. **GUI:** a new test type **"Acoustic startle (ASR)"**, with its own
    settings row (threshold scale, response window, baseline window, trial
    source) and tabs (motion trace, trials table, threshold preview). Video
    files are added and batched like §12 Stage 7. Exact placement is part of
    the GUI review.
11. **Validation:** check against a video the user has already scored by
    hand or with the paper's method; confirm the threshold-15 result and the
    peak values match.

**Still open (to settle from the sample video and logs):**
- How stimulus onset times and trial types are read from the logs (item 5),
  and the default response/baseline window lengths.
- PPI and habituation details that depend on the log format (prepulse
  levels, block structure).

### 14. Anaconda install (requested 2026-11-03 — ✅ built 2026-11-03 on `main`, merged into `video-tracking`)

Goal: anyone with **Anaconda or Miniconda** on a Mac or Windows PC gets the
project folder, double-clicks **one install file** to build the program's
environment, then double-clicks the **Open** file from then on. Build it on
`main` and merge into `video-tracking`, so the installer is usable now and
later packages (OpenCV, SciPy for video) are one line each.

1. **`environment.yml`** (Anaconda's own format):
   - **conda-forge channel only** (not Anaconda's default channel, whose
     commercial terms can apply to larger institutions; conda-forge is free).
   - One fixed Python version; pandas, numpy, matplotlib, openpyxl; OpenCV and
     SciPy added when the video build needs them; `tkinterdnd2` through the
     file's `pip:` section (may not be on conda-forge).
   - One named environment, e.g. `behavior-tracker`, separate from anything
     else on the computer.
2. **Conda-finding helpers, one per system**, shared by the Install, Open and
   Uninstall files so the search lives in one place:
   - **`find_conda.sh` (Mac):** use `conda` if it already works or
     `CONDA_EXE` is set; otherwise look in the usual install folders
     (`anaconda3` / `miniconda3` in the home folder, `~/opt`, `/opt`,
     `/opt/homebrew`, …); then load `etc/profile.d/conda.sh` so
     `conda activate` works inside the script.
   - **`find_conda.bat` (Windows):** same idea in Windows terms (`where
     conda`, `%CONDA_EXE%`, `anaconda3` / `miniconda3` under
     `%USERPROFILE%`, `%ProgramData%` and `%LOCALAPPDATA%`, …); activate
     through `condabin\conda.bat`.
   - If nothing is found: a plain message saying Anaconda needs installing,
     then stop.
   - If the user copies the `find_conda.sh` from their other program into the
     folder, reuse what worked there (e.g. extra folders it checked).
   - Also searched: Miniforge/Mambaforge and Homebrew cask folders (Mac), and
     the older `%LOCALAPPDATA%\Continuum` location (Windows).
3. **Install files:** `Install Behavior Tracker.command` (Mac) and
   `Install Behavior Tracker.bat` (Windows). First run creates the
   environment from `environment.yml`; running again **updates** it to match
   (how new packages arrive later). **Never upgrades pip.** Ends with a clear
   Done/Failed message and keeps the window open.
4. **Open files** (the existing `Open Behavior Tracker` launchers): use the
   conda environment if it exists (on Windows, activate it properly first, or
   numpy can fail to load); **fall back to the current `.venv` setup** on
   computers without Anaconda; if the environment is missing, say "run the
   installer first" instead of crashing; if `environment.yml` changed since
   install (stored stamp), suggest re-running the installer.
5. **Optional Uninstall file:** `conda env remove` for the environment; the
   user's files are untouched.
6. **Keep `requirements.txt` (venv fallback) and `environment.yml` in sync**;
   the regression test fails if they list different packages.
7. **README:** install Anaconda; get the folder (zip from GitHub or clone; the
   repo is private, so others need access or a zip); double-click Install,
   then Open; Mac first time: right-click → Open (macOS blocks downloaded
   scripts); what to do if Windows SmartScreen warns.
8. **PC test checklist:** installer finds Anaconda installed "just me" and
   "all users"; works from a folder with spaces; re-running updates; Open
   uses the conda environment; drag-and-drop still works.

**Built as planned.** Notes: `tkinterdnd2` isn't on conda-forge, so it comes
through `environment.yml`'s `pip:` section; Python is pinned to 3.12; the
"changed since install" check compares `environment.yml` with a copy the
installer leaves inside the environment; with Anaconda present but the
environment not installed, Open still uses an existing `.venv` (so current
setups keep working) and otherwise says to run the installer.

New requests are added to this list as they come in.

---

## Open questions — RESOLVED (2026-10-09)
1. **EPM anxiety index** — ✅ report all three: %open time & %open entries, the
   composite Anxiety Index, and the closed/open time ratio. (See §4.)
2. **What counts as an "entry"** — ✅ minimum frames inside (configurable, saved).
3. **Open-field crossing** — ✅ traversal across center; opposite sides
   (left↔right, top↔bottom) and adjoining sides (e.g. left→top). (See §5.)
4. **Adjoining-side time filter** — ✅ require a minimum time in the center
   region between the two sides (configurable, saved).
5. **Crossing speed** — ✅ report both average (over traversal) and peak.
6. **Immobility defaults** — ✅ seed at <2 cm/s for ≥1 s; both configurable, saved.
   (Immobility itself was later deferred, §11.)

## Sample data findings (2026-10-23)
- **EPM** (`EPM.csv`): region columns `ol`, `or` (open left/right), `ct`, `cb`
  (closed top/bottom), `mid`. `ROI_location` also has overlap labels where the
  point is in two polygons at once (`or_mid`, `ol_mid`, `ct_mid`, `cb_mid`,
  `or_ct_mid`; ~1.3% of frames).
- **Open field** (`Open Field.csv`): region columns `center`, `peripheral`.
  `peripheral` is the *whole arena* (center frames read `center_peripheral`);
  `non_roi` = outside both. **There are no side regions** (left/right/top/
  bottom) — see decisions below.
- Both files are gitignored (`*.csv`) — research data stays off GitHub.

## Decisions from sample data — RESOLVED (2026-10-23)
1. **EPM overlap frames count as center.** A frame in an arm *and* the middle
   (or_mid, ct_mid, or_ct_mid, ...) is center; so is open+closed at once.
   Implemented in `core.regions.frame_roles` — §4 metrics must use it.
2. **Open-field sides come from X/Y**: the top of the video is the top of the
   arena (image coords: smaller Y = top). §5 crossings derive left/right/top/
   bottom from position relative to the file's own drawn center-ROI lines.
3. **Center and periphery must never overlap.** Any frame marked as both is a
   file/ROI error: the app warns the user when the file is analyzed (per file,
   frames + %), and counts those frames as center. `Open Field.csv` has this error (21.5% of
   frames — its periphery ROI covers the whole arena).

---

## Build order
Done:
1. ✅ Config/persistence layer (`config.json`) — §6.
2. ✅ Plot controls + drag-and-drop — §1, §2.
3. ✅ Test-type dropdown + region-role mapping — §3.
4. ✅ **File-input workflow (§7).**
5. ✅ **Mac + PC groundwork (§10):** shared pop-up dialog and Windows
   launcher.
6. ✅ **Display fixes (§8).**
7. ✅ **EPM metrics (§4)**, validated against `EPM.csv`.
8. ✅ **Open-field metrics (§5)**, validated against `Open Field.csv`.
9. ⏸ ~~Shared immobility detection~~: deferred to future items (§11).
10. ✅ **Export (§9).**
11. ✅ **Test measures per time bin (§5b).**

**Everything planned so far is built** (as of 2026-10-30). Still open:
- ✅ **Anaconda install (§14)**: built 2026-11-03 on `main`, merged into
  `video-tracking`. Tested on Mac (fresh install, clean environment, app
  launch, regression test inside the conda env); **PC test pending**.
- **Video analysis from ezTrack** (§12), on the `video-tracking` branch:
  Location Tracking walkthrough decided; Freeze Analysis logged but excluded
  from the current build; GUI review next, then build.
- **Acoustic startle (ASR) from video** (§13): planned, including PPI and
  habituation; not built. **When starting it, remind the user to add a sample
  video and stimulus logs to the folder.**
- **First PC test** (§10), whenever the user is ready.
- **Future items** (§11): immobility, now to be covered by §12's freezing.
- **Standalone app** (bundling): on hold until the user says so.
- New requests from the user.

Throughout: keep everything working on both Mac and PC (§10), with a PC test
checklist after cross-platform changes.
