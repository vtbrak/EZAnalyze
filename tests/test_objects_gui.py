"""Object recognition in the GUI (ROADMAP §15): the setup window's Objects
step, the tracking file's object columns, the Review tab's zone visits and
scoring, and the results.

Uses ezTrack's practice clip (ezTrack/PracticeVideos/LocationTracking_Clip.mp4,
gitignored), copied to a temporary folder. Settings go to a temporary config.

Run from the project folder:  .venv/bin/python tests/test_objects_gui.py
"""
import os
import shutil
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
tmp = tempfile.mkdtemp()
cfg = os.path.join(tmp, "config.json")
import gui, core
gui.load_config = lambda: core.load_config(cfg)
gui.save_config = lambda c: core.save_config(c, cfg)
log, yesno = [], []
gui.show_warning = lambda p, t, m, **k: log.append(t)
gui.show_info = lambda p, t, m, **k: log.append(t)
gui.show_error = lambda p, t, m, **k: log.append(t)
gui.ask_yes_no = lambda p, t, m, **k: (log.append(t), yesno.pop(0) if yesno else True)[1]
import setup_window, review_panel
for mod in (setup_window, review_panel):
    mod.show_info, mod.show_warning = gui.show_info, gui.show_warning
setup_window.ask_yes_no = gui.ask_yes_no
gui.BehaviorTrackerApp.wait_window = lambda self, w=None: None

SRC = os.path.join(ROOT, "ezTrack", "PracticeVideos", "LocationTracking_Clip.mp4")
if not os.path.exists(SRC):
    sys.exit("ezTrack's practice clip isn't in the project folder.")
CLIP = os.path.join(tmp, "clip.mp4")
shutil.copy(SRC, CLIP)

fails = 0
def check(label, cond):
    global fails; fails += not cond; print(("ok  " if cond else "FAIL"), label)


app = gui.BehaviorTrackerApp(); app.update()
app.test_var.set("Object Recognition"); app._on_test_type(); app.update()
check("Object Recognition settings section with the zone distance box",
      bool(app.or_bar.winfo_manager()) and not app.of_bar.winfo_manager()
      and app.zone_var.get() == "2")
app.add_files([CLIP]); app.update()
app.open_setup(); app.update()
win = app._setup_win
v = app.files[0].video
win._go("regions"); app.update()
check("step 5 is Objects, listing two objects", win.step_buttons["regions"].cget("text").strip()
      .endswith("5  Objects") and list(win.object_list.get_children()) == ["object 1", "object 2"])
check("Remove is hidden for the first two objects", not win.remove_obj_btn.winfo_manager())
ev = lambda x, y: type("E", (), dict(zip("xy", win.canvas.to_screen(x, y))))()
win._object_press(ev(300, 300)); win._object_drag(ev(340, 300)); win._object_release(ev(340, 300))
check("press at the center and drag to the edge draws a circle",
      np.allclose(v.objects["object 1"], (300, 300, 40), atol=0.6)
      and win._current_object == "object 2")
win._object_press(ev(700, 300)); win._object_drag(ev(700, 330)); win._object_release(ev(700, 330))
win._object_press(ev(700, 300)); win._object_drag(ev(720, 310)); win._object_release(ev(720, 310))
check("drag a drawn object's center to move it", np.allclose(v.objects["object 2"][:2], (720, 310), atol=0.6))
win._object_press(ev(750, 310)); win._object_drag(ev(760, 310)); win._object_release(ev(760, 310))
check("drag its edge to resize it", np.allclose(v.objects["object 2"][2], 40, atol=0.6))
win._object_press(ev(100, 100)); win._object_release(ev(100, 100))
check("a click off the objects doesn't draw (object 2 already drawn)",
      set(v.objects) == {"object 1", "object 2"})
win.kind_var.set("Novel"); win._set_kind()
win.day_var.set("3"); win.phase_var.set("Test"); win._set_trial()
check("type, day and phase saved to the video's setup",
      v.object_kinds == {"object 2": "Novel"} and v.trial_day == "3" and v.trial_phase == "Test")
win._add_object(); app.update()
check("Add object lists a third, with Remove shown",
      v.object_names[-1] == "object 3" and bool(win.remove_obj_btn.winfo_manager()))
check("an undrawn third object counts as missing", v.missing_regions("Object Recognition") == ["object 3"])
win._remove_object()
check("Remove takes it off again", v.object_names == ["object 1", "object 2"]
      and not v.missing_regions("Object Recognition"))
app.update()
circles = [i for i in win.canvas.find_withtag("overlay") if win.canvas.type(i) == "oval"]
check("circles drawn with see-through fills", circles and win.canvas.find_withtag("fills"))
check("no zone ring before the scale (a note says why)", "scale is set" in win.object_note.cget("text"))
v.scale_points, v.scale_cm = [(100, 100), (500, 100)], 40.0   # 10 px per cm
app.zone_var.set("3"); app.update()
dashed = [i for i in win.canvas.find_withtag("overlay")
          if win.canvas.type(i) == "oval" and win.canvas.itemcget(i, "dash")]
check("zone rings drawn once scaled, following the zone box", len(dashed) == 2
      and app.config_data["object_zone_cm"] == 3.0)
from core.track_run import make_job
job = make_job(v, core.tracking.TrackingParams() if hasattr(core, "tracking") else
               __import__("core.tracking", fromlist=["x"]).TrackingParams(), 1.0, 10,
               "Object Recognition")
check("Track writes the objects, day and phase (no regions)",
      job.regions == [] and job.extra["Trial_Day"] == "3" and job.extra["Trial_Phase"] == "Test"
      and '"kind": "Novel"' in job.extra["Objects"])
win._close()
app.update()

print(f"\n{fails} failure(s)")
app.destroy()
shutil.rmtree(tmp, ignore_errors=True)
sys.exit(1 if fails else 0)
