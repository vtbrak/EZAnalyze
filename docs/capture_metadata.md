# Creature Capture → Track Tamer (draft, for after Track Tamer 1.0)

How Track Tamer will read the trial information that **Creature Capture**
saves beside its videos, so it's filled in automatically (ROADMAP §16).
Based on Creature Capture's `_info.json` as of 2026-11-06 (app 0.1.0 plus the
changes on its `main`). Nothing here is built yet.

## Files and matching

Creature Capture writes, per arena per trial, next to the videos:
- `<date>_<time>_<arena>_info.json` (and the same as `_info.csv`)
- one MP4 per camera, named in `cameras[].video`
- one `_frames.csv` per camera, named in `cameras[].timestamps_csv`

**Matching a video to its info file:** when a video is added, Track Tamer
reads every `*_info.json` in the same folder and picks the one whose
`cameras[].video` (or `videos`) lists that video's file name exactly. This
works however the videos are named, as long as:
- names in the JSON are bare file names (no folders), exactly as on disk,
  including the extension;
- every video name is unique in the folder (two arenas recorded at the same
  second must differ, e.g. by arena name in the file name);
- videos and their JSON stay together, and aren't renamed afterward. A
  renamed video is still found if its name starts with the JSON's
  `<date>_<time>_<arena>_` prefix, with a note asking the user to confirm.

Track Tamer's own files never clash: it adds `_LocationOutput.csv`,
`_reference.png`, `_ObjectScoring.csv`, `_analysis.xlsx`, `_path.png`,
`_heatmap.png` and `_tracked.mp4` to the video's name. When a folder is
added, it skips `_frames.csv`, `_info.csv` and `_ObjectScoring.csv` (they
aren't tracking files).

## What Track Tamer would import

| Creature Capture field | Track Tamer uses it to |
|---|---|
| `assay` | **set the test type**, through a fixed list of names (see "Asks" below) |
| `arena` | Summary column; remember that arena's crop, scale and regions as a draft for its next video |
| `date`, `start_time`, `start_wall_clock` | Summary columns (recording start) |
| `experimenter`, `cohort`, `animal_id`, `sex`, `strain`, `dob`, `treatment`, `notes` | **Summary and export columns**, so the table is ready for stats by animal and group; age on the test day from `dob` |
| `trial_day` | Summary column; **Object Recognition day** |
| `duration_set_min` | **set the session length** |
| `duration_actual_s`, `stopped_early` | warn when the recording is shorter than the session length, and use what's there |
| `cameras[].frames`, `verified_frames_in_file` | check the video is complete (warn if they differ, or if `error` isn't empty) |
| `cameras[].repeated_frame_indices` | mark repeated frames: they're kept, so timing stays right, but they're counted in the Summary and left out of speed peaks |
| `cameras[]._frames.csv` (`video_time_s`) | **the real frame rate** (and per-frame times if the rate wasn't steady) |
| `cameras[].label`, `slot`, `camera_settings` | recorded in the export's Settings sheet (exposure, gain and so on, for reproducibility) |
| `encoder`, `app_version` | recorded in the Settings sheet |

The info is copied into the tracking file when a video is tracked, so a
`_LocationOutput.csv` still carries it if the JSON is moved away.

## Asks for Creature Capture

**Needed for matching and reading reliably**
1. **`schema_version`** (e.g. `1`), raised whenever a field is renamed,
   removed or changes meaning, so Track Tamer can read old and new files.
2. **A time zone on `start_wall_clock`** (`2026-11-05T16:56:42.906-05:00`).
3. **Confirm frame numbering:** are `repeated_frame_indices` and the
   `_frames.csv` `frame` column counted from 0, the same as the frames in the
   MP4? (Track Tamer counts from 0.) And does `frames` include the repeated
   frames?
4. **Types:** numbers as numbers (`trial_day: 2`, `duration_set_min: 5`),
   `stopped_early` as `true`/`false`, empty fields as `null` or left out
   rather than `""`.

**Fills in setup automatically**
5. **Frame rate per camera:** `fps_set` (what was asked for) and
   `fps_measured` (frames ÷ recorded time). Track Tamer can work it out from
   `_frames.csv`, but having it in the JSON is simpler and gets checked.
6. **Frame size per camera:** `width_px`, `height_px`.
7. **A fixed list of `assay` names** that both programs agree on:
   `Elevated Plus Maze`, `Open Field`, `Object Recognition` (later, e.g.
   `Acoustic Startle`). Today's `Elevated Plus` would need a translation
   table.

**Object Recognition**
8. **`phase`**: one of `Habituation`, `Training`, `Test`.
9. **`objects`**: one entry per object with `name` (`object 1`), `identity`
    (what it is, e.g. `glass bottle`), `kind` (`Familiar`, `Novel` or
    `Moved`) and `position` (e.g. `top left`). The experimenter knows this
    when placing the objects. Track Tamer would fill in each object's type,
    and the user just draws the circles.

**Worth recording while you're there (optional)**
10. `weight_g`; `dose`, `dose_units`, `time_since_treatment_min`;
    `cage`, `ear_tag`.
11. `room` or `rig`; `arena_size_cm` (e.g. `{"width": 40, "length": 40}`),
    which Track Tamer could suggest as the scale length.
12. Environment: `temperature_c`, `humidity_pct`, `light_lux`,
    `light_phase` (`light`/`dark`), `zt_hours` (hours since lights on).
13. Later, for startle (ROADMAP §13): stimulus times and levels in the
    same file, instead of separate stimulus logs.

## Notes
- **No "animal placed" keypress** (user, 2026-11-06): marking events during
  recording isn't realistic in the lab, so the trial start stays a setup
  step in Track Tamer.
- **Two fields say similar things:** top-level `frames` and `repeated_frames`
  repeat the per-camera numbers as text. Track Tamer will use the per-camera
  ones in `cameras[]`.
- **Write the JSON in one go** when recording stops (write to a temporary
  name, then rename), so a crash never leaves half a file.
- **Keep these files off GitHub:** they hold animal information, so they're
  research data, like the videos.
