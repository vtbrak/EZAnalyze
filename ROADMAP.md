# EZanalyze — Roadmap

Feature and analysis plan for the behavior-tracking analyzer. This is the design
doc; nothing here is built until we agree on it. Existing, already-working pieces
are listed first so we know the starting point.

---

## Already built (current state, as of 2026-10-23)
- **Core engine** (`core/`, GUI-free): loads tracking CSVs, validates columns,
  detects **region columns** automatically (any True/False column, e.g. EPM
  `ol/or/ct/cb/mid`, open field `center/peripheral`), parses ROI polygons.
- **Summary table**: one row per file. File name is always shown, and the
  other columns come in checkbox groups (Session basics on by default; Zone
  time & %, Entries & transitions, ROI label time & %, Details). Choices are
  saved.
- **Time-binned table**: session split into fixed bins (default 60 s).
- **Path plot** (color-by-speed or solid color, with adjustable size and
  transparency) and **occupancy heatmap** (adjustable bins and colormap).
  Each tab has its own controls. ROI outlines are labeled with region names.
- **Test-type dropdown** (EPM / Open Field) and **region-role mapping**
  (auto-classified, user-overridable via the Match regions dialog, saved).
  ROI polygons are paired with regions by data agreement.
- **Center/periphery overlap warning** on load.
- **File list** (§7): add files/folders/drops to a list, Clear, Analyze
  Selected / Analyze All. Test type, fps, and bin size lock at the first
  Analyze,
  and the selected Summary row drives Time Bins, Path, and Heatmap.
- **Settings saved** to `config.json` (fps, bin size, plot style, summary
  columns, test type, region roles).
- **Export** the active table to CSV or Excel (to be replaced by §9).
- Double-click **`Open Behavior Tracker.command`** launcher (Mac).
- Code is on GitHub (`vtbrak/EZAnalyze`, private). Data CSVs are gitignored.

---

## Design decisions (locked in)
- **Zone/region membership**: trust the file's own **region columns** (one
  True/False column per region) rather than recomputing from X/Y. The one
  exception is open-field sides, which the file doesn't have (see decisions).
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
- **Thresholds** (immobility etc.): **input boxes** in the UI, **values persisted**
  to a `config.json` so they carry over between sessions.

---

## Planned features

### 1. File input
- [x] **Drag-and-drop** files/folders onto the window, in addition to the existing
  Open File / Open Folder buttons.
- [x] Graceful fallback: if drag-and-drop can't initialize, buttons still work.

### 2. Plot controls (path & heatmap)
- [x] Adjustable **point size**.
- [x] Adjustable **point color** (used when not coloring by speed).
- [x] Adjustable **transparency (alpha)**.
- [x] Toggle: color-by-speed vs solid color; heatmap bin count.
- [x] Settings persisted in `config.json`.

### 3. Test-type framework
- [x] Test-type dropdown (saved). It will drive which metric set runs once
  §4–§5 exist; for now it drives the region check below.
- [x] Region-role mapping ("Match regions" dialog, also via **Regions…**):
  each region column is auto-classified (keywords + EPM codes like ol/ct/mid),
  user-overridable, saved. Opens automatically when names can't be matched or
  don't fit the chosen test.
- [x] ROI polygons are paired with regions by data agreement, not file order,
  and labeled on the plots.

### 4. Elevated Plus Maze (EPM) metrics (✅ built 2026-10-29, except immobility)
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
- [ ] **Immobility detection** — immobile when speed stays below a threshold for
  at least a minimum duration. Outputs: total immobile time, % immobile, bout
  count. Threshold + min duration are **input boxes, saved**.

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
  carries `Test` and `MinEntryFrames` columns (Details group), so today's
  Export Table shows it. The §9 settings sheet must list it too.
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

### 5. Open Field metrics
- [ ] **Center-region entries** — count entries into the center, using the
  shared entry rule (min frames inside) plus a **minimum time-between-entries
  threshold** (debounce). Both configurable, saved.
- [ ] **Time & % in center**, latency to first center entry.
- [ ] **Field crossings** — a crossing is a traversal **across the center** that
  connects two sides. Counts in three categories:
  - **Opposite sides**: left↔right and top↔bottom.
  - **Adjoining sides**: e.g. left→top — counted **only if the path spends at
    least a minimum time in the center region** between the two sides
    (configurable, saved), so corner-cuts near an edge don't count.
  - Report counts per category (and a total). Center comes from the file's
    region column. **Sides come from X/Y** relative to the center ROI, with
    the top of the video as the top of the arena (the files have no side
    regions).
- [ ] **Crossing speed** — report **both** average speed over the traversal
  (leaving one side → reaching the next) and **peak** speed during crossings.
- [ ] Immobility detection (shared with EPM).

### 6. Config / persistence
- [x] `config.json` holding fps, bin size, all thresholds, plot style, and the
  region-role mapping. Loaded on start, saved on change.

### 7. File-input workflow (requested 2026-10-23 — ✅ built 2026-10-23)
The larger concern: how the program handles files loaded one after another,
and multiple files from a folder.

**Problems today**
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
- The Summary export includes every file in the list, with its Status.

**Wanted**
- [x] A load step that lets the user **pick the test type and parameters for a
  file before computing**, without the EPM/open-field warning firing first.
- [x] A defined behavior for **loading files one after another** (rather than
  silently replacing and recomputing).
- [x] In folder/batch mode, a way to **select a single file** and view its Time
  Bins, Path, and Heatmap.

**✅ Decided 2026-10-23**
- [x] **New files are added to a list.** Loading (Open File, Open Folder,
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
  **fps**, and **time-bin size**. Bin size stays consistent across every file
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
  regular type. ✅ Built 2026-10-23 as `dialogs.py`, used for every pop-up. Today pop-ups such as the center/periphery overlap warning
  show all of their text in bold.
  - Applies to every pop-up message (warnings, errors, info).
  - Implementation note: on macOS, tkinter's `messagebox` shows the `message`
    text in bold and the optional `detail` text in regular type. **Windows
    doesn't do this.** Its message boxes have no bold line, so the same split
    wouldn't give the required look on a PC. To match on both, build one small
    custom dialog (a tkinter `Toplevel` with a bold first line and regular
    text) and use it for every pop-up. See §10.

### 9. Exporting results (requested 2026-10-23 — not built yet)
- [ ] Proper **export for a single file** and for **multiple files**
  (folder/batch).

**What exists today**
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
- [ ] `<name>_analysis.xlsx`: one Excel workbook with **everything, each
  table on its own sheet** (Summary, Time Bins, and later the EPM/open-field
  metrics).
- [ ] `<name>_path.png`: the Path plot image.
- [ ] `<name>_heatmap.png`: the Heatmap image, keeping the transparent
  background (§8).

**✅ Details decided 2026-10-23**
- [ ] **Saved next to each source CSV** (same folder as the file it came
  from).
- [ ] **Existing output files are overwritten** without asking.
- [ ] Each `_analysis.xlsx` **includes that file's Summary row** (its own
  sheet).
- [ ] Each `_analysis.xlsx` includes a **settings sheet** recording every
  setting used to generate its results:
  - analysis: fps, test type, region roles, thresholds, **entry rule (min
    entry frames)**
  - **Time Bins**: bin size
  - **Path**: point size, transparency, color-by-speed, point color
  - **Heatmap**: bins, colormap, background on/off
- [ ] Plot images use the **on-screen plot settings** (point size, colors,
  transparency, colormap, bins, background on/off).
- **No separate summary file.** The Summary row lives only in
  `_analysis.xlsx`, and there's no combined file either. (Decided 2026-10-23,
  replacing the earlier separate-CSV plan.)

### 10. Runs on both Mac and PC (requested 2026-10-23 — requirement)
- [ ] The program must **work on Windows PCs as well as macOS**. Groundwork
  built 2026-10-23 (shared dialogs + Windows launcher). Awaiting the first PC
  test. This applies
  to everything built from now on, and the existing code needs checking.

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

More layout/function items to come in later messages.

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
   bottom from position relative to the center ROI.
3. **Center and periphery must never overlap.** Any frame marked as both is a
   file/ROI error: the app warns the user on load (per file, frames + %), and
   counts those frames as center. `Open Field.csv` has this error (21.5% of
   frames — its periphery ROI covers the whole arena).

---

## Build order
Done:
1. ✅ Config/persistence layer (`config.json`) — §6.
2. ✅ Plot controls + drag-and-drop — §1, §2.
3. ✅ Test-type dropdown + region-role mapping — §3.

Next (updated 2026-10-23):
4. ✅ **File-input workflow (§7).**
5. ✅ **Mac + PC groundwork (§10):** shared pop-up dialog and Windows
   launcher. Next: the user's first PC test.
6. ✅ **Display fixes (§8).**
7. ✅ **EPM metrics (§4)**, validated against `EPM.csv`. Immobility is still
   to come (step 9).
8. **Open-field metrics (§5)**, validated against `Open Field.csv`.
9. **Shared immobility detection** (§4/§5).
10. **Export (§9)** comes last, since it bundles every table and plot built
    above.

Throughout: keep everything working on both Mac and PC (§10), with a PC test
checklist after cross-platform changes.
