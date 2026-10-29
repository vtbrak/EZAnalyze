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
app.analyze(False); app.update()
cols = list(app._summary_df.columns)
check("Open Field measures computed", all(c in cols for c in ("OF_CenterEntries", "OF_Crossings_Total", "OF_CrossingSpeed_Peak_cm_s")))
check("OF thresholds recorded in export", app._summary_df["MinBetweenCenterEntries_s"][0] == 2
      and app._summary_df["MinCenterAdjoiningCrossing_s"][0] == 0.5
      and app._summary_df["SpeedSmoothing_frames"][0] == 5)
check("OF measures on screen by default", "OF_Crossings_Total" in app.summary_tree["columns"])
check("locked after Analyze", lockw() == LK)
check("overlap warning for OF", "Center and periphery overlap" in log)
check("bins use 30 s", "30 s" in app.bins_note.get() and app.bins_tree.get_children())
check("no EPM columns under Open Field", not any(c.startswith("EPM_") for c in app._summary_df.columns))
check("plot controls never lock", all(str(w.cget("state")) != "disabled" for w in (app.tab_heat.winfo_children()[0].winfo_children()) if w.winfo_class() in ("TSpinbox", "TCombobox")))
yesno.append(False); app.add_files([O]); app.update()
check("repeat asked; ignored", "Already in the list" in log and len(rows()) == 1)
yesno.append(True); app.add_files([O]); app.update()
check("repeat added with (2)", len(rows()) == 2 and rows()[1][0].endswith("(2)") and rows()[1][1] == "Not analyzed")
app.summary_tree.selection_set("1"); app.update(); app._on_select()
check("selection drives tabs", "(2)" in app.bins_note.get())
app.clear_files(); app.update()
check("clear empties + unlocks", rows() == [] and lockw() == UN)
app.test_var.set("Elevated Plus Maze"); app._on_test_type(); app.update()
check("Open Field row hidden for EPM", not app.of_bar.winfo_ismapped())
app.add_files([E, O]); log.clear(); dialogs.clear(); app.analyze(False); app.update()
check("EPM test: OF file gets dialog, skipped", dialogs == [["center", "peripheral"]] and "Some files not analyzed" in log)
check("EPM file analyzed with EPM measures", rows()[0][1] == "Analyzed" and "EPM_AnxietyIndex" in app._summary_df.columns)
check("rule recorded in export", app._summary_df["MinEntryFrames"][0] == 5)
app._on_close()
c = json.load(open(cfg))
check("settings saved", c["test_type"] == "Elevated Plus Maze" and c["bin_seconds"] == 30
      and c["min_entry_frames"] == 5 and c["min_seconds_between_entries"] == 2)
print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
