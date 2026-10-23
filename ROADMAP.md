# EZanalyze — Roadmap

Feature and analysis plan for the behavior-tracking analyzer. This is the design
doc; nothing here is built until we agree on it. Existing, already-working pieces
are listed first so we know the starting point.

---

## Already built (current state)
- **Core engine** (`core/`, GUI-free): loads `*_LocationOutput.csv`, validates
  columns, parses ROI polygons.
- **Summary metrics table** — one row per file: total distance (cm/px), duration,
  mean speed, time & % per zone/ROI, zone entries, ROI transitions, tracking settings.
- **Time-binned table** — session split into fixed bins (default 60 s).
- **Path plot** (speed-colored) and **occupancy heatmap**, with ROI outlines.
- **Two modes**: single-file deep dive + batch-folder summary.
- **Export** active table to CSV or Excel.
- Configurable **frame rate** (default 20 fps) and **bin size** in the toolbar.
- Double-click **`Open Behavior Tracker.command`** launcher.

---

## Design decisions (locked in)
- **Zone/region membership**: trust the file's own columns (`center`, `peripheral`,
  `ROI_location`) rather than recomputing from X/Y.
- **EPM arm identification**: real EPM files carry arm labels in `ROI_location`.
  Because exact label strings vary (the first sample even had open-field labels on
  EPM data), the app keeps a **region-role mapping**: each distinct label is
  auto-classified by keyword (`open`→open arm, `closed`→closed arm, `center`,
  `periphery`) and can be overridden. **Mapping is saved** in the program.
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
- [ ] Test-type dropdown drives which metric set is computed and shown.
- [ ] Region-role mapping panel: shows each `ROI_location` label found in the
  file, with an editable role assignment; saved.

### 4. Elevated Plus Maze (EPM) metrics
- [ ] **Open-arm vs closed-arm time** (seconds and %).
- [ ] **EPM anxiety measures** — report ALL of:
  - %open-arm time and %open-arm entries (separately)
  - Composite **Anxiety Index** = `1 − [ (open-arm time/total arm time +
    open-arm entries/total entries) / 2 ]` (higher = more anxious)
  - **Closed/open time ratio** = closed-arm time ÷ open-arm time
- [ ] **Latency to first entry** — time to first open-arm entry (and closed-arm,
  center for reference).
- [ ] **Time in center region** (the cross intersection).
- [ ] **Open- and closed-arm entry counts.**
- [ ] **Immobility detection** — immobile when speed stays below a threshold for
  at least a minimum duration. Outputs: total immobile time, % immobile, bout
  count. Threshold + min duration are **input boxes, saved**.

**Entry rule (EPM & open field):** an entry counts only when the tracked point
stays inside the region for at least **N frames** (configurable, saved). Filters
boundary jitter. (A true "all four paws" rule isn't possible — data is a single
centroid.)

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
  - Report counts per category (and a total). Sides/center come from the file's
    region labels (`ROI_location`).
- [ ] **Crossing speed** — report **both** average speed over the traversal
  (leaving one side → reaching the next) and **peak** speed during crossings.
- [ ] Immobility detection (shared with EPM).

### 6. Config / persistence
- [x] `config.json` holding fps, bin size, all thresholds, plot style, and the
  region-role mapping. Loaded on start, saved on change.

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

## Still needed
- **Sample data**: we only have one (atypical) EPM file whose labels are
  open-field-style. To build & validate §4–§5 we need (a) a representative **EPM**
  file with proper arm labels in `ROI_location`, and (b) a sample **open-field**
  file showing its region labels (center + sides). These confirm the exact label
  strings the region-role mapping and crossing logic key off.

---

## Suggested build order
1. Config/persistence layer (`config.json`) — everything else reads/writes it.
2. Plot controls + drag-and-drop (UI polish, low risk, immediately useful).
3. Test-type dropdown + region-role mapping.
4. EPM metrics (validate against a properly labeled EPM file).
5. Open-field metrics (validate against a real open-field file).
6. Shared immobility detection.
