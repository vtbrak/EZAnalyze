# Capture metadata file (draft spec, schema 1)

What the video capture software should write beside each video, so Track
Tamer can fill in the experiment information automatically (ROADMAP §16).
This is a **draft** for building after Track Tamer 1.0. Field names can still
change until both programs implement them.

## The file

- **One JSON file per video, beside it, with the same name:**
  `M12_day2_test.mp4` → `M12_day2_test.json`. UTF-8, plain JSON (no comments).
- **Every field is optional except `schema_version` and `video.file`.**
  Track Tamer fills in what's there and asks for (or leaves blank) the rest.
  It ignores fields it doesn't know, so the capture software can add its
  own.
- **Units are in the field names** (`_s` seconds, `_cm` centimeters, `_px`
  pixels). Dates and times use ISO 8601 with the time zone
  (`2026-06-26T14:03:15-04:00`).
- **Frames are counted in the video file, starting at 0**, the same way Track
  Tamer counts video frames. Give seconds as well when you have them.
- **Text values Track Tamer acts on must match exactly**, and are listed
  below as "one of".

## Fields

### About the file itself
| Field | What it is | Track Tamer uses it to |
|---|---|---|
| `schema_version` | `1` for this spec | read the file correctly as the spec changes |
| `capture_software` | `{"name": "...", "version": "..."}` | record it in the export |
| `created` | when the file was written (ISO 8601) | record it |

### `video`: the recording
| Field | What it is | Track Tamer uses it to |
|---|---|---|
| `file` | the video's file name (no folder) | check the JSON belongs to this video |
| `sha256` | checksum of the video file (optional) | catch a renamed or swapped video |
| `recorded_start` | when recording started (ISO 8601) | record it; time-of-day analyses |
| `fps_nominal` | frame rate the camera was set to | record it |
| `fps_measured` | actual average frame rate over the recording | **set the frame rate** (more accurate than the file's header) |
| `frame_count` | frames written | check the video is complete |
| `width_px`, `height_px` | frame size | check the calibration below fits |
| `dropped_frames` | list of frame numbers where a frame was missed or duplicated | mark them like unreadable frames, so timing stays right |
| `frame_timestamps_file` | name of a CSV beside the video with one timestamp per frame (optional) | exact timing if the frame rate varies |
| `camera` | `{"model": "...", "serial": "...", "lens": "...", "lighting": "IR"}` | record it |

### `experiment`: the study and session
| Field | What it is | Track Tamer uses it to |
|---|---|---|
| `test` | one of `"Elevated Plus Maze"`, `"Open Field"`, `"Object Recognition"` (more later, e.g. `"Acoustic Startle"`) | **set the test type** (and warn if videos in one load differ) |
| `study`, `protocol_id` | study name, IACUC/protocol number | Summary and export columns |
| `experimenter` | who ran it | Summary and export columns |
| `room`, `rig_id`, `arena_id` | where it was run | pick that rig's calibration; columns |
| `cohort`, `session_id` | grouping labels | columns |
| `day` | trial day (1, 2, ...) | **Object Recognition day**; columns |
| `phase` | one of `"Habituation"`, `"Training"`, `"Test"` | **Object Recognition phase**; columns |
| `planned_duration_s` | how long the trial is meant to be | **set the session length** |
| `notes` | free text | export |

### `animal`: the subject
| Field | What it is | Track Tamer uses it to |
|---|---|---|
| `id` | animal ID | **Summary column** (the most useful one for stats) |
| `sex` | e.g. `"F"` / `"M"` | column |
| `strain`, `genotype` | | columns |
| `date_of_birth` or `age_days` | | column (age on the test day) |
| `weight_g` | | column |
| `group` | experimental group or condition (blinded code is fine) | **column for comparing groups** |
| `treatment`, `dose`, `dose_units`, `time_since_treatment_min` | | columns |
| `cage`, `ear_tag` | | columns |

### `events`: things marked during recording
A list of `{"type": "...", "frame": 1234, "time_s": 125.4, "note": "..."}`.
Types Track Tamer acts on:
- `"animal_placed"`: **sets the trial start** (setup step 1), so nobody has
  to scrub for it.
- `"animal_removed"` / `"trial_end"`: sets the end if there's no planned
  duration.
- `"disturbance"` (noise, door, experimenter in view): listed in the Review
  tab to check.
- Anything else (`"note"`, ...) goes in the export.

### `arena`: geometry and calibration
| Field | What it is | Track Tamer uses it to |
|---|---|---|
| `size_cm` | e.g. `{"width": 40, "length": 40}` or EPM `{"arm_length": 35, "arm_width": 5}` | record it; check the scale |
| `calibration` | `{"px_per_cm": 9.25}` or `{"points_px": [[145, 240], [515, 240]], "length_cm": 40}` | **fill in the scale** (setup step 6) |
| `crop_px` | `[x0, y0, x1, y1]` around the arena | **fill in the crop** (setup step 1) |

These only make sense if the camera is fixed for a rig. Track Tamer fills them
in as a **draft for the user to check**, like "Start from previous video",
since each video is still analyzed against its own setup.

### `objects`: Object Recognition only
A list, one entry per object:
`{"name": "object 1", "identity": "glass bottle", "kind": "Novel", "position": "top left", "center_px": [220, 150], "radius_px": 30}`
- `kind`: one of `"Familiar"`, `"Novel"`, `"Moved"`. **Sets each object's
  type.**
- `identity`: what the object is (for counterbalancing records).
- `position`: a label such as `"top left"`, if pixel positions aren't known.
- `center_px` / `radius_px`: if the rig is calibrated, **draft circles** for
  setup step 5 (the user adjusts them).

### `environment` (optional)
`temperature_c`, `humidity_pct`, `light_lux`, `light_cycle_phase`
(`"light"` / `"dark"`), `zt_hours` (hours since lights on). Recorded as
columns.

### `stimuli`: future Acoustic Startle (ROADMAP §13)
A list of `{"frame": ..., "time_s": ..., "type": "pulse" | "prepulse+pulse" | "prepulse" | "none", "pulse_db": 120, "prepulse_db": 74, "interval_ms": 100}`.
This would replace separate stimulus logs. Its details get settled when ASR
is built.

## Example

```json
{
  "schema_version": 1,
  "capture_software": {"name": "Rodent Capture", "version": "0.3"},
  "created": "2026-06-26T14:13:20-04:00",
  "video": {
    "file": "1_2026-06-26_14-03-15.mp4",
    "recorded_start": "2026-06-26T14:03:15-04:00",
    "fps_nominal": 10,
    "fps_measured": 9.837,
    "frame_count": 4995,
    "width_px": 640,
    "height_px": 480,
    "dropped_frames": [],
    "camera": {"model": "ELP USB", "serial": "A1234", "lighting": "white"}
  },
  "experiment": {
    "test": "Object Recognition",
    "study": "NOR pilot",
    "experimenter": "ES",
    "rig_id": "box 1",
    "day": 2,
    "phase": "Test",
    "planned_duration_s": 600
  },
  "animal": {"id": "M12", "sex": "M", "strain": "C57BL/6J", "group": "B", "weight_g": 27.4},
  "events": [
    {"type": "animal_placed", "frame": 400, "time_s": 40.7},
    {"type": "disturbance", "frame": 2210, "time_s": 224.7, "note": "door"}
  ],
  "arena": {
    "size_cm": {"width": 40, "length": 40},
    "calibration": {"points_px": [[145, 240], [515, 240]], "length_cm": 40},
    "crop_px": [95, 25, 545, 455]
  },
  "objects": [
    {"name": "object 1", "identity": "glass bottle", "kind": "Familiar", "position": "top left",
     "center_px": [220, 150], "radius_px": 30},
    {"name": "object 2", "identity": "lego tower", "kind": "Novel", "position": "bottom right",
     "center_px": [437, 356], "radius_px": 32}
  ]
}
```

## Notes for the capture software
- Write the JSON when recording stops, and write it in one go (write to a
  temporary name, then rename), so a crash never leaves half a file.
- Keep the video file name and `video.file` in step if files are renamed
  later.
- Animal and group information is research data. These files stay off
  GitHub, like the videos.
