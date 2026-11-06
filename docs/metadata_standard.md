# Track Tamer video metadata standard

**Schema 1 (draft, 2026-11-06).** The trial information that any app
recording videos for Track Tamer saves beside its videos, so Track Tamer can
fill it in automatically (ROADMAP §16). **Track Tamer owns this standard**:
apps that generate video follow it, and changes are made here first, then in
the apps. It stays a draft until the user says otherwise; while it's a draft,
changes don't raise `schema_version`. Reading it in Track Tamer is planned
for after Track Tamer 1.0.

Apps covered so far: **Creature Capture** (see "Apps" at the end). Others
will be added as their analyses come into Track Tamer.

---

## 1. Files and names

For each trial, per arena, an app writes beside the videos:

| File | What it is |
|---|---|
| `<date>_<time>_<arena>_info.json` | the trial information (this standard). **The only file Track Tamer reads for trial information.** |
| one video per camera | named in `cameras[].video` |
| one `_frames.csv` per camera | the measured time of every frame, named in `cameras[].timestamps_csv` |
| `<date>_<time>_<arena>_info.csv` (optional) | for people (e.g. a spreadsheet log); Track Tamer doesn't read it |

**Name parts:**
- `<date>` is `YYYY-MM-DD`.
- `<time>` is the start time as `HH-MM-SS` (24-hour; dashes because `:`
  isn't allowed in Windows file names).
- `<arena>` and `<camera label>` use letters, digits and `-` only: **no
  spaces and no `_`**, so names can be split reliably.

Example: `2026-11-05_16-56-42_EPM1_info.json`.

**Videos** are named `<date>_<time>_<arena>_<camera label>.mp4`
(e.g. `2026-11-05_16-56-42_EPM1_Overhead.mp4`). Every video name must be
unique within its folder.

**How Track Tamer matches a video to its info file:** it reads every
`*_info.json` in the video's folder and picks the one whose `cameras[].video`
lists the video's exact file name. If a video was renamed, a name starting
with the info file's `<date>_<time>_<arena>_` still matches, after the user
confirms. So: write bare file names (no folders), exactly as on disk, and
keep videos and their info file together.

**Reserved endings.**
- For the apps: `_info.json`, `_info.csv`, `_frames.csv`.
- For Track Tamer's own files (added to a video's name, so apps must not use
  them): `_LocationOutput.csv`, `_reference.png`, `_ObjectScoring.csv`,
  `_analysis.xlsx`, `_path.png`, `_heatmap.png`, `_tracked.mp4`.

Track Tamer skips `_frames.csv` and `_info.csv` when a folder is added.

---

## 2. How an info file is organized

Every info file has up to three kinds of fields:

| Kind | Where it goes | Who writes it |
|---|---|---|
| **Standard fields** (section 4) | top level, and in each `cameras` entry | every app, using only the ones it has (the required ones are a must) |
| **Assay fields** (section 5) | top level | only for that assay (e.g. `objects` only for the object assays) |
| **App fields** | inside one object named after the app, in lowercase with `_` (`creature_capture`, `startle_box`, …) | only that app |

An app writes **only the standard fields it has**: anything it doesn't know
is left out, never filled with blanks. Anything the standard doesn't cover
goes in the app's own object, never at the top level, so it can't clash
with a standard field added later or with another app's field of the same
name. Per-camera app fields go in an object of the same name inside that
camera's entry.

Track Tamer reads the standard and assay fields, copies the app objects
into the export's Settings sheet as they are, and otherwise ignores them. If
a field in an app object turns out to be useful to Track Tamer or needed by
several apps, it's added to the standard (section 7) and apps move it to
the top level.

Example, from a Creature Capture Open Field trial:

```json
{
  "schema_version": 1,
  "app_name": "Creature Capture",
  "app_version": "0.2.0",
  "date": "2026-11-05",
  "start_time": "16:56:42",
  "assay": "Open Field",
  "arena": "OF2",
  "animal_id": "M7",
  "treatment": "saline",
  "trial_number": 1,
  "duration_set_min": 60,
  "cameras": [
    {
      "label": "Overhead",
      "camera_position": "Camera5",
      "video": "2026-11-05_16-56-42_OF2_Overhead.mp4",
      "timestamps_csv": "2026-11-05_16-56-42_OF2_Overhead_frames.csv",
      "fps_measured": 9.84,
      "camera_settings": {"encoder": "libx264", "exposure": {"apply": true, "value": -5}}
    }
  ],
  "creature_capture": {"experiment": "Open Field 60 min", "gpu": false}
}
```

Here `assay`, `animal_id` and the rest are standard fields. There are no
assay fields, since Open Field has none. `experiment` and `gpu` are Creature
Capture's own fields, so they sit in its object.

---

## 3. Assay names

`assay` must be **exactly** one of these names. Track Tamer uses it to set
the test type. Matching ignores upper/lower case and spaces at the ends, but
apps should write the name as shown. Each task is its own assay, even when
two share Track Tamer's analysis.

| `assay` | Track Tamer analysis | `phase` (one of) |
|---|---|---|
| `Elevated Plus Maze` | Elevated Plus Maze (built) | |
| `Open Field` | Open Field (built) | |
| `Novel Object Location` | Object Recognition (built) | `Habituation`, `Training`, `Test` |
| `Spatial Object Location` | Object Recognition (built) | `Habituation`, `Training`, `Test` |
| `Acoustic Startle Response` | planned (ROADMAP §13) | |
| `Prepulse Inhibition` | planned (ROADMAP §13) | |
| `Startle Habituation` | planned (ROADMAP §13) | |
| `Conditioned Place Preference` | planned | `Pretest`, `Conditioning`, `Test` |
| `Fear Conditioning` | planned (freezing, ROADMAP §12) | `Training`, `Context Test`, `Cue Test` |

New assays are added to this table when Track Tamer starts analyzing them.
An app may record something not listed (e.g. a pilot); Track Tamer then asks
the user to choose the test.

---

## 4. Standard fields

JSON, UTF-8. **Required:** `schema_version`, `assay`, `animal_id`, and
`cameras`, with each camera's `video`, `camera_position` and
`camera_settings`. Everything else is optional but used when present.
Leave a field out when it's unknown or empty; don't write `""` or `null`.
Numbers are JSON numbers; yes/no values are `true`/`false`. Frames are
counted from **0**, the same as the frames in the video file.

### Trial and animal
| Field | Type | What it is | Track Tamer uses it to |
|---|---|---|---|
| `schema_version` | number | `1` | read the file correctly |
| `app_name`, `app_version` | text | the app that wrote it | Settings sheet |
| `date` | `YYYY-MM-DD` | trial date, from the recording computer's clock | Summary column |
| `start_time` | `HH:MM:SS` | start time, from the recording computer's clock | Summary column |
| `assay` | text | from section 3 | **set the test type** |
| `phase` | text | from section 3's list for that assay | Summary column; Object Recognition phase |
| `arena` | text | arena name (as in the file name) | Summary column; draft crop, scale and regions from that arena's last video |
| `room` | text | room or rig | Summary column |
| `experimenter` | text | who ran it | Summary column |
| `cohort` | text | **Cohort / litter** (label it that way on screen; the field name stays `cohort`) | Summary column |
| `animal_id` | text | animal ID | **Summary column** |
| `sex` | text | `F`, `M`, or `U` (unknown or not recorded) | Summary column |
| `strain` | text | strain or genotype | Summary column |
| `dob` | `YYYY-MM-DD` | date of birth | age on the test day |
| `treatment` | text | treatment or group (a blinded code is fine) | **Summary column for comparing groups** |
| `trial_number` | number | which trial this is for the animal (1, 2, …) | Summary column |
| `notes` | text | | export |
| `duration_set_min` | number | length chosen, in minutes | **set the session length** |
| `duration_actual_s` | number | length actually recorded, in seconds | warn if shorter than the session length |
| `stopped_early` | true/false | | warn |

### `cameras`: one entry per camera in this arena
| Field | Type | What it is | Track Tamer uses it to |
|---|---|---|---|
| `label` | text | camera label (as in the video name) | Settings sheet |
| `camera_position` | text | where the camera is (the app's camera position or slot, e.g. `Camera5`) | Settings sheet |
| `camera_settings` | object | **every** setting used, whether changed or not, including the video `encoder` (e.g. `{"encoder": "libx264", "exposure": {"apply": true, "value": -5}, …}`) | Settings sheet |
| `video` | text | the video's file name | **match the video** |
| `timestamps_csv` | text | its `_frames.csv` file name | **the frame times (the record of timing)** |
| `fps_set` | number | frame rate asked for | Settings sheet |
| `fps_measured` | number | frames ÷ recorded seconds, from the frame times | check |
| `width_px`, `height_px` | number | frame size | check |
| `frames` | number | frames written (including repeats) | check the video is complete |
| `verified_frames_in_file` | number | frames counted in the finished file | check (should equal `frames`) |
| `repeated_frames` | number | frames repeated to keep timing | Summary column |
| `repeated_frame_indices` | list of numbers | which frames, from 0 | kept for timing, left out of speed peaks |
| `error` | text | error message (left out if none) | warn |

### `_frames.csv`
One row per video frame: `frame` (from 0), `video_time_s`, `repeated`
(`true`/`false`), and any of the app's own timing columns (e.g.
`tick_time_s`, `camera_frame_time_s`, `camera_frame_seq`).

**These measured times are the record of timing.** Track Tamer takes each
frame's time from `video_time_s`, and uses `fps_measured` and the video
file's own frame rate only as checks (or when there's no `_frames.csv`).

---

## 5. Assay fields

Written only for those assays.

### Novel Object Location and Spatial Object Location
| Field | Type | What it is |
|---|---|---|
| `objects` | list | one entry per object: `name`, `identity` (what it is, e.g. `glass bottle`), `kind` (`Familiar`, `Novel` or `Moved`), `position` (e.g. `top left`) |

`name` must be `object 1`, `object 2`, … in order: those are the names
Track Tamer gives the objects, so each object's type can be matched. Track
Tamer sets each object's type; the user draws the circles.

### Acoustic Startle Response, Prepulse Inhibition, Startle Habituation (planned)
`stimuli`: one entry per trial with `frame`, `video_time_s`, `type`
(`pulse`, `prepulse+pulse`, `prepulse`, `none`), `pulse_db`, `prepulse_db`,
`interval_ms`. Settled when Track Tamer's startle analysis is built.

### Fear Conditioning (planned)
To be added when freezing analysis is built (e.g. tone and shock times).

### Conditioned Place Preference (planned)
To be added when its analysis is built (e.g. which chamber was paired with
the drug, the conditioning session number, and the chamber the animal was
confined to in a conditioning session).

---

## 6. General rules

- Write the JSON in one go when recording stops (write to a temporary name,
  then rename), so a crash never leaves half a file.
- These files hold animal information: they're research data and stay off
  GitHub, like the videos. (This standard itself is fine to share.)

---

## 7. Changing the standard

- Track Tamer owns this file. Changes are agreed here, then made in the apps.
- While the standard is a draft, changes don't raise `schema_version`.
- After that: **adding** an optional field doesn't change `schema_version`;
  **renaming, removing, or changing the meaning** of a field raises it by 1,
  and Track Tamer keeps reading every earlier version.

### Changes
- **Schema 1 (draft, 2026-11-06):** first version, built from Creature
  Capture's `_info.json`. Revised the same day: `assay_variant` removed
  (each task is its own assay: `Novel Object Location` and `Spatial Object
  Location` replace `Object Recognition`; `Prepulse Inhibition` and `Startle
  Habituation` are their own assays); `phase` made a standard field with a
  list per assay; `start_wall_clock` removed (date and start time come from
  the recording computer's clock); `trial_number` added; `sex` may be `U`;
  `slot` renamed `camera_position`, and it and `camera_settings` (now
  including `encoder`) became required standard camera fields; the frame
  times in `_frames.csv` are the record of timing; Track Tamer reads only
  the JSON. Then removed (not recorded in the lab): `trial_day`,
  `weight_g`, `cage`, `ear_tag`, dose fields, `arena_size_cm`,
  `environment`; `cohort` is labeled "Cohort / litter".

---

## Apps

### Creature Capture
Writes `<date>_<time>_<arena>_info.json` (and `_info.csv`) per arena per
trial, one MP4 and one `_frames.csv` per camera.

**Already matches** (done in Creature Capture after the first draft):
`schema_version` and `app_name`; assay names from a dropdown; numbers and
`true`/`false` types, blank fields left out; arena names without spaces or
`_`, and videos named `<date>_<time>_<arena>_<camera label>.mp4`; per-camera
`fps_set`, `fps_measured`, `width_px`, `height_px`, numeric
`repeated_frames`; `phase` and `objects` for object trials; frames counted
from 0 in `repeated_frame_indices` and `_frames.csv` (confirmed); the JSON
written in one go.

**To change for this revision:**
1. **Assay names:** replace `Object Recognition` + `assay_variant` with the
   separate assays `Novel Object Location` and `Spatial Object Location`.
   Stop writing `assay_variant`.
2. **Phase for every assay that has one** (section 3): `Conditioned Place
   Preference` and `Fear Conditioning` too, from their own lists.
3. **Remove `start_wall_clock`**; `date` and `start_time` from the recording
   computer's clock are the start.
4. **Add `trial_number`** (which trial that day).
5. **Sex:** write `U` when it's unknown or not recorded, instead of leaving
   it out.
6. **Cameras:** rename `slot` to `camera_position`, and move it and
   `camera_settings` out of `creature_capture` into each camera's entry
   (standard fields). Every camera writes both, even when nothing was
   changed. Put `encoder` inside `camera_settings`.
7. **Camera labels** use letters, digits and `-` only.
8. **`error`:** leave it out when there's no error (no `""`).
9. **Fields removed from the standard:** `trial_day`, `weight_g`, `cage`,
   `ear_tag`, dose fields, `arena_size_cm`, `environment`. Stop writing
   `trial_day` (use `trial_number`), and don't add the others.
10. **Cohort:** label the box "Cohort / litter" (the field stays `cohort`).

<!-- Add a section here for each new app as it's brought in. -->
