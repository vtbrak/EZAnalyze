"""Workflow regression test for the Behavior Tracker GUI.

Drives the real app (window hidden behind fakes for pop-ups) through the file
list, locking, Analyze, repeats, Clear, region checks, and saved settings,
using the sample files EPM.csv and "Open Field.csv" in the project folder
(gitignored, so this only runs where they exist). Settings go to a temporary
config, never the real config.json.

Run from the project folder:  .venv/bin/python tests/regress_gui.py
(Windows: .venv\\Scripts\\python.exe tests\\regress_gui.py)
"""
import json
import os
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
cfg = os.path.join(tempfile.mkdtemp(), "config.json")
import gui, core
gui.load_config = lambda: core.load_config(cfg)
gui.save_config = lambda c: core.save_config(c, cfg)
log, yesno, dialogs = [], [], []
gui.show_warning = lambda p, t, m, **k: log.append(t)
gui.show_info = lambda p, t, m, **k: log.append(t)
gui.show_error = lambda p, t, m, **k: log.append(t)
gui.ask_yes_no = lambda p, t, m, **k: (log.append(t), yesno.pop(0))[1]
class FakeDialog:
    def __init__(self, parent, test, overview, roles, preview=None, reason=""):
        dialogs.append([n for n, _ in overview]); self.result = None
gui.RegionDialog = FakeDialog
gui.BehaviorTrackerApp.wait_window = lambda self, w=None: None
E = os.path.join(ROOT, "EPM.csv"); O = os.path.join(ROOT, "Open Field.csv")
if not (os.path.exists(E) and os.path.exists(O)):
    sys.exit("Sample files EPM.csv and 'Open Field.csv' aren't in the project folder.")
app = gui.BehaviorTrackerApp(); app.update()
fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)
lockw = lambda: tuple(str(w.cget("state")) for w in (app.test_box, app.fps_entry, app.bin_entry,
                                                     app.entry_entry, app.gap_entry, app.adj_entry,
                                                     app.smooth_entry))
UN, LK = ("readonly",) + ("normal",) * 6, ("disabled",) * 7
rows = lambda: [app.summary_tree.item(i, "values")[:2] for i in app.summary_tree.get_children()]

check("unlocked at start", lockw() == UN)
app.add_files([O]); app.update()
check("unlocked after add, no prompts", lockw() == UN and not log and not dialogs)
check("Status column after File", list(app.summary_tree["columns"])[:2] == ["File", "Status"])
check("tabs say not analyzed", "isn't analyzed" in app.bins_note.get())
app.test_var.set("Open Field"); app._on_test_type(); app.bin_var.set("30"); app.update()
check("Open Field row shown for Open Field", app.of_bar.winfo_ismapped())
app.gap_var.set("2"); app.update()
check("file list: File, Type, Status", list(app.file_tree["columns"]) == ["File", "Type", "Status"]
      and app.file_tree.item("0", "values")[1] == "CSV")
check("first file selected, buttons count it", app._sel == [0] and app.analyze_btn.cget("text") == "Analyze (1)")
check("no unreadable-frames section for ezTrack files", not app.gaps_section.winfo_ismapped())
app.select_all(); app.analyze(); app.update()
cols = list(app._summary_df.columns)
check("Open Field measures computed", all(c in cols for c in ("OF_CenterEntries", "OF_Crossings_Total", "OF_CrossingSpeed_Peak_cm_s")))
check("OF thresholds recorded in export", app._summary_df["MinBetweenCenterEntries_s"][0] == 2
      and app._summary_df["MinCenterAdjoiningCrossing_s"][0] == 0.5
      and app._summary_df["SpeedSmoothing_frames"][0] == 5)
check("OF measures on screen by default", "OF_Crossings_Total" in app.summary_tree["columns"])
check("Time Bins include OF crossings and center entries",
      {"OF_Crossings_Total", "OF_CenterEntries", "OF_CrossingSpeed_Mean_cm_s"} <= set(app.files[0].bins.columns)
      and {"OF_Crossings_Total"} <= set(app.bins_tree["columns"]))
check("OF bin crossings add up to the session",
      app.files[0].bins["OF_Crossings_Total"].sum() == app.files[0].summary["OF_Crossings_Total"])
check("locked after Analyze", lockw() == LK)
check("lock note shown", app.lock_note.winfo_ismapped())
check("overlap warning for OF", "Center and periphery overlap" in log)
check("bins use 30 s", "30 s" in app.bins_note.get() and app.bins_tree.get_children())
check("no EPM columns under Open Field", not any(c.startswith("EPM_") for c in app._summary_df.columns))
check("plot controls never lock", all(str(w.cget("state")) != "disabled" for w in (app.tab_heat.winfo_children()[0].winfo_children()) if w.winfo_class() in ("TSpinbox", "TCombobox")))
yesno.append(False); app.add_files([O]); app.update()
check("repeat asked; ignored", "Already in the list" in log and len(rows()) == 1)
yesno.append(True); app.add_files([O]); app.update()
check("repeat added with (2)", len(rows()) == 2 and rows()[1][0].endswith("(2)") and rows()[1][1] == "Not analyzed")
app.toggle_select_all(); app.update()
check("Select all selects every file", app._sel == [0, 1] and app.select_all_btn.cget("text") == "Select none"
      and app.analyze_btn.cget("text") == "Analyze (2)")
app.toggle_select_all(); app.update()
check("Select none clears the selection", app._sel == [] and app.analyze_btn.cget("text") == "Analyze")
log.clear(); app.analyze(); app.update()
check("Analyze with nothing selected says so", "No file selected" in log)
app.summary_tree.selection_set("1"); app.update(); app._on_select()
check("selection drives tabs", "(2)" in app.bins_note.get())
app.clear_files(); app.update()
check("clear empties + unlocks", rows() == [] and lockw() == UN)
app.test_var.set("Elevated Plus Maze"); app._on_test_type(); app.update()
check("Open Field row hidden for EPM", not app.of_bar.winfo_ismapped())
app.add_files([E, O]); log.clear(); dialogs.clear(); app.select_all(); app.analyze(); app.update()
check("EPM test: OF file gets dialog, skipped", dialogs == [["center", "peripheral"]] and "Some files not analyzed" in log)
check("EPM file analyzed with EPM measures", rows()[0][1] == "Analyzed" and "EPM_AnxietyIndex" in app._summary_df.columns)
check("Time Bins include EPM measures", {"EPM_OpenEntries", "EPM_AnxietyIndex", "EPM_PctOpenTime"} <= set(app.files[0].bins.columns))
check("rule recorded in export", app._summary_df["MinEntryFrames"][0] == 5)
# Export, on copies of the samples in a temp folder (never the project folder).
import shutil
import pandas as pd
from core.export import output_paths
tmp = tempfile.mkdtemp()
E2 = shutil.copy(E, tmp)
app._set_selection([1]); app.remove_selected(); app.update()
check("Remove takes the selected file out", [r[0] for r in rows()] == [app.files[0].label] and len(app.files) == 1)
app.clear_files(); app.add_files([E2]); app.analyze(); app.update()
log.clear(); app.export(); app.update()
out = output_paths(E2)
check("export writes _analysis.xlsx, _path.png, _heatmap.png", all(os.path.exists(p) for p in out.values()))
sheets = pd.read_excel(out["analysis"], sheet_name=None)
check("workbook sheets", list(sheets) == ["Summary", "Time Bins", "Settings"])
check("exported Time Bins sheet has the EPM measures", "EPM_AnxietyIndex" in sheets["Time Bins"].columns)
names = set(sheets["Settings"]["Setting"])
check("settings sheet lists entry rule, bins, plot style",
      {"Min entry (frames)", "Bin size (s)", "Point size", "Colormap", "Add background"} <= names)
check("export finished message", "Export finished" in log)

# Videos (ezTrack's short practice clip, if present): added as "Needs setup",
# set up in the setup window, skipped by Analyze until tracked.
CLIP = os.path.join(ROOT, "ezTrack", "PracticeVideos", "LocationTracking_Clip.mp4")
if os.path.exists(CLIP):
    app.clear_files(); log.clear(); app.add_files([CLIP]); app.update()
    vals = app.file_tree.item("0", "values")
    check("video listed as Video / Needs setup", vals[1] == "Video" and vals[2] == "Needs setup")
    check("Set up videos button shown", app.setup_btn.winfo_ismapped())
    app.open_setup(); app.update()
    win = app._setup_win
    check("setup window opens on the video", win.winfo_exists() and "Clip" in win.video_label.cget("text"))
    win.scrub.set(100); win._load_scrub_frame(); win._set_start()
    win.scrub.set(899); win._load_scrub_frame(); win._set_end()
    check("trim set", (app.files[0].video.start, app.files[0].video.end_frame) == (100, 900))
    app.files[0].video.crop = (100, 50, 1100, 650)
    win._step_by(1); app.update()
    check("Next marks trim done and goes to exclusions",
          win.step == "exclusions" and "trim" in app.files[0].video.steps_done)
    for x, y in ((10, 10), (60, 10), (60, 60)):
        sx, sy = win.canvas.to_screen(x, y)
        win._shape_click(type("E", (), {"x": sx, "y": sy})())
    win._finish_shape()
    check("exclusion shape stored in full-size pixels",
          np.allclose(app.files[0].video.exclusions[0], [[110, 160, 160], [60, 60, 110]]))
    win._step_by(1); win.ref_var.set("10"); win._make_reference(); app.update()
    ref = app.files[0].video.reference
    check("reference made at the crop's size", ref is not None and ref.shape == (600, 1000)
          and "reference" in app.files[0].video.steps_done)
    log.clear(); app._set_selection([0]); app.analyze(); app.update()
    check("Analyze skips an untracked video", "Videos not tracked yet" in log)
    win._close(); app.update()
    check("gap-filling section shown when videos are listed", app.gaps_section.winfo_ismapped())
else:
    print("skip video checks (ezTrack practice clip not present)")

app.show_about(); app.update()
about = [w for w in app.winfo_children() if w.winfo_class() == "Toplevel"]
check("About window opens", about and "Behavior Tracker" in about[0].title())
about[0].destroy()
app._on_close()
c = json.load(open(cfg))
check("settings saved", c["test_type"] == "Elevated Plus Maze" and c["bin_seconds"] == 30
      and c["min_entry_frames"] == 5 and c["min_seconds_between_entries"] == 2)

# The two install routes must install the same packages: requirements.txt
# (.venv fallback) and environment.yml (Anaconda; python and pip are conda's
# own tooling, not program packages).
def _names(lines):
    return {l.split("#")[0].strip().lstrip("- ").split("=")[0].split("<")[0].split(">")[0].strip().lower()
            for l in lines if l.split("#")[0].strip()}
reqs = _names(open(os.path.join(ROOT, "requirements.txt")))
env_lines = open(os.path.join(ROOT, "environment.yml")).read().split("dependencies:", 1)[1].splitlines()
env = _names(l for l in env_lines if not l.strip().endswith(":")) - {"python", "pip"}
check(f"requirements.txt and environment.yml list the same packages "
      f"(only in requirements: {sorted(reqs - env)}, only in environment: {sorted(env - reqs)})",
      reqs == env)
print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
