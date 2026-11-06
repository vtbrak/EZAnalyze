# Track Tamer video metadata standard

**Schema 1 (draft, 2026-11-06).** The trial information that any app
recording videos for Track Tamer saves beside its videos, so Track Tamer can
fill it in automatically (ROADMAP §16). **Track Tamer owns this standard**:
apps that generate video follow it, and changes are made here first, then in
the apps. Reading it in Track Tamer is planned for after Track Tamer 1.0.

Apps covered so far: **Creature Capture** (see "Apps" at the end). Others
will be added as their analyses come into Track Tamer.

---

## 1. Files and names

For each trial, per arena, an app writes beside the videos:

| File | What it is |
|---|---|
| `<date>_<time>_<arena>_info.json` | the trial information (this standard) |
| one video per camera | named in `cameras[].video` |
| one `_frames.csv` per camera (optional) | per-frame times, named in `cameras[].timestamps_csv` |
| `<date>_<time>_<arena>_info.csv` (optional) | the same trial fields as a spreadsheet row |

**Name parts:** `<date>` is `YYYY-MM-DD`; `<time>` is the start time as
`HH-MM-SS` (24-hour, dashes because `:` isn't allowed in Windows file
names); `<arena>` is the arena name, using letters, digits and `-` only (no
spaces or `_`, so names can be split reliably). Example:
`2026-11-05_16-56-42_EPM1_info.json`.

**Videos** should be named `<date>_<time>_<arena>_<camera label>.mp4`
(e.g. `2026-11-05_16-56-42_EPM1_Overhead.mp4`). Every video name must be
unique within its folder.

**How Track Tamer matches a video to its info file:** it reads every
`*_info.json` in the video's folder and picks the one whose `cameras[].video`
lists the video's exact file name. If a video was renamed, a name starting
with the info file's `<date>_<time>_<arena>_` still matches, after the user
confirms. So: write bare file names (no folders), exactly as on disk, and
keep videos and their info file together.

**Reserved endings.** Track Tamer adds these to a video's name for its own
files, so apps must not use them: `_LocationOutput.csv`, `_reference.png`,
`_ObjectScoring.csv`, `_analysis.xlsx`, `_path.png`, `_heatmap.png`,
`_tracked.mp4`. Track Tamer skips `_frames.csv` and `_info.csv` when a
folder is added.

---

## 2. Assay names

`assay` must be **exactly** one of these names. Track Tamer uses it to set
the test type. Matching ignores upper/lower case and spaces at the ends, but
apps should write the name as shown.

| `assay` | Track Tamer | Variants (`assay_variant`, optional) |
|---|---|---|
| `Elevated Plus Maze` | built | |
| `Open Field` | built | |
| `Object Recognition` | built | `Novel Object`, `Object Location` |
| `Acoustic Startle Response` | planned (ROADMAP §13) | `Prepulse Inhibition`, `Habituation` |
| `Conditioned Place Preference` | planned | `Pretest`, `Conditioning`, `Test` |
| `Fear Conditioning` | planned (freezing, ROADMAP §12) | `Training`, `Context Test`, `Cue Test` |

New assays are added to this table when Track Tamer starts analyzing them.
An app may record something not listed (e.g. a pilot); Track Tamer then asks
the user to choose the test.

---

## 3. Fields every app writes

JSON, UTF-8. **Required:** `schema_version`, `assay`, `animal_id`,
`cameras` (with each `video`). Everything else is optional but used when
present. Leave a field out (or `null`) when it's unknown; don't write `""`.
Numbers are JSON numbers; yes/no values are `true`/`false`. Frames are
counted from **0**, the same as the frames in the video file.

### Trial and animal
| Field | Type | What it is | Track Tamer uses it to |
|---|---|---|---|
| `schema_version` | number | `1` | read the file correctly |
| `app_name`, `app_version` | text | the app that wrote it | Settings sheet |
| `date` | `YYYY-MM-DD` | trial date | Summary column |
| `start_time` | `HH:MM:SS` | start time | Summary column |
| `start_wall_clock` | ISO 8601 with time zone | start to the millisecond, e.g. `2026-11-05T16:56:42.906-05:00` | Summary column |
| `assay` | text | from section 2 | **set the test type** |
| `assay_variant` | text | from section 2 | Summary column |
| `arena` | text | arena name (as in the file name) | Summary column; draft crop, scale and regions from that arena's last video |
| `room` | text | room or rig | Summary column |
| `experimenter` | text | who ran it | Summary column |
| `cohort` | text | cohort or litter | Summary column |
| `animal_id` | text | animal ID | **Summary column** |
| `sex` | text | `F` or `M` | Summary column |
| `strain` | text | strain or genotype | Summary column |
| `dob` | `YYYY-MM-DD` | date of birth | age on the test day |
| `treatment` | text | treatment or group (a blinded code is fine) | **Summary column for comparing groups** |
| `dose`, `dose_units`, `time_since_treatment_min` | number, text, number | | Summary columns |
| `weight_g` | number | | Summary column |
| `cage`, `ear_tag` | text | | Summary columns |
| `trial_day` | number | trial or day (1, 2, …) | Summary column; Object Recognition day |
| `notes` | text | | export |
| `duration_set_min` | number | length chosen | **set the session length** |
| `duration_actual_s` | number | length actually recorded | warn if shorter than the session length |
| `stopped_early` | true/false | | warn |
| `arena_size_cm` | object | e.g. `{"width": 40, "length": 40}` | suggest the scale length |
| `environment` | object | `temperature_c`, `humidity_pct`, `light_lux`, `light_phase` (`light`/`dark`), `zt_hours` | Summary columns |

### `cameras`: one entry per camera in this arena
| Field | Type | What it is | Track Tamer uses it to |
|---|---|---|---|
| `label` | text | camera label (as in the video name) | Settings sheet |
| `video` | text | the video's file name | **match the video** |
| `timestamps_csv` | text | its `_frames.csv` file name | exact frame times |
| `fps_set` | number | frame rate asked for | Settings sheet |
| `fps_measured` | number | frames ÷ recorded seconds | **set the frame rate** |
| `width_px`, `height_px` | number | frame size | check |
| `frames` | number | frames written (including repeats) | check the video is complete |
| `verified_frames_in_file` | number | frames counted in the finished file | check (should equal `frames`) |
| `repeated_frames` | number | frames repeated to keep timing | Summary column |
| `repeated_frame_indices` | list of numbers | which frames, from 0 | kept for timing, left out of speed peaks |
| `error` | text | error message, empty if none | warn |
| `slot`, `camera_settings` | text, object | camera position and the controls used | Settings sheet |

### `_frames.csv` (optional)
One row per video frame: `frame` (from 0), `video_time_s`, and any of the
app's own timing columns (e.g. `tick_time_s`, `camera_frame_time_s`,
`camera_frame_seq`), plus `repeated` (`true`/`false`).

---

## 4. Fields for one assay

Written only for that assay.

### Object Recognition
| Field | Type | What it is |
|---|---|---|
| `phase` | text | one of `Habituation`, `Training`, `Test` |
| `objects` | list | one entry per object: `name` (`object 1`, `object 2`, …), `identity` (what it is, e.g. `glass bottle`), `kind` (`Familiar`, `Novel` or `Moved`), `position` (e.g. `top left`) |

Track Tamer sets the phase and each object's type; the user draws the
circles.

### Acoustic Startle Response (planned)
`stimuli`: one entry per trial with `frame`, `video_time_s`, `type`
(`pulse`, `prepulse+pulse`, `prepulse`, `none`), `pulse_db`, `prepulse_db`,
`interval_ms`. Settled when Track Tamer's startle analysis is built.

### Fear Conditioning (planned)
To be added when freezing analysis is built (e.g. tone and shock times).

### Conditioned Place Preference (planned)
To be added when its analysis is built (e.g. which chamber was paired with
the drug, `conditioning_session` number, and the chamber the animal was
confined to in a conditioning session).

---

## 5. An app's own fields

An app may add fields this standard doesn't have. Put them in an object
named after the app, e.g. `"creature_capture": {...}`, so they can't clash
with future standard fields. Track Tamer records them in the export and
otherwise ignores them. A field several apps need is moved into the
standard.

---

## 6. Changing the standard

- Track Tamer owns this file. Changes are agreed here, then made in the apps.
- **Adding** an optional field doesn't change `schema_version`.
- **Renaming, removing, or changing the meaning** of a field raises
  `schema_version` by 1. Track Tamer keeps reading every earlier version.
- Write the JSON in one go when recording stops (write to a temporary name,
  then rename), so a crash never leaves half a file.
- These files hold animal information: they're research data and stay off
  GitHub, like the videos.

### Changes
- **Schema 1 (2026-11-06):** first version, built from Creature Capture's
  `_info.json` (app 0.1.0 plus its `main`). Assay names reserved for
  planned analyses: `Acoustic Startle Response`, `Fear Conditioning`,
  `Conditioned Place Preference`.

---

## Apps

### Creature Capture
Writes `<date>_<time>_<arena>_info.json` (and `_info.csv`) per arena per
trial, one MP4 and one `_frames.csv` per camera. Most of section 3 already
matches its fields; the standard kept its names. **To change to match the
standard:**
1. Add `schema_version: 1` and `app_name: "Creature Capture"`.
2. Write `assay` from section 2's list (today's `Elevated Plus` becomes
   `Elevated Plus Maze`). A dropdown with exactly those names is easiest.
3. Add the time zone to `start_wall_clock`.
4. Numbers as numbers (`trial_day`, `duration_set_min`, …), `stopped_early`
   as `true`/`false`, unknown fields left out instead of `""`.
5. Arena names without spaces or `_`, and videos named
   `<date>_<time>_<arena>_<camera label>.mp4`.
6. Per camera: add `fps_set`, `fps_measured`, `width_px`, `height_px`, and
   write `repeated_frames` as a number.
7. Top-level `frames`, `repeated_frames` and `videos` repeat the per-camera
   values as text. They may stay, but Track Tamer reads `cameras[]`.
8. Object Recognition: add `phase` and `objects` (section 4).
9. Confirm that `repeated_frame_indices` and the `_frames.csv` `frame`
   column count from 0, the same as the MP4's frames.
10. Optional extras from section 3 when convenient: `weight_g`, `dose`,
    `room`, `arena_size_cm`, `environment`, …
11. App-only settings (`encoder`, …) can stay at the top level for now, or
    move into `"creature_capture": {...}` (section 5).

<!-- Add a section here for each new app as it's brought in. -->
