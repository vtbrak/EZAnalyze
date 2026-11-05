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
import setup_window
setup_window.show_info = gui.show_info
setup_window.show_warning = gui.show_warning
setup_window.ask_yes_no = gui.ask_yes_no
import playback_window
playback_window.show_info = gui.show_info
playback_window.show_warning = gui.show_warning
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
check("Open Field row shown for Open Field", bool(app.of_bar.winfo_manager()))
app.gap_var.set("2"); app.update()
check("file list: File, Type, Status", list(app.file_tree["columns"]) == ["File", "Type", "Status"]
      and app.file_tree.item("0", "values")[1] == "CSV")
check("first file selected, buttons count it", app._sel == [0] and app.analyze_btn.cget("text") == "Analyze (1)")
check("no unreadable-frames section for ezTrack files", not bool(app.gaps_section.winfo_manager()))
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
check("lock note shown", bool(app.lock_note.winfo_manager()))
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
check("Open Field row hidden for EPM", not bool(app.of_bar.winfo_manager()))
app.add_files([E, O]); log.clear(); dialogs.clear(); app.select_all(); app.analyze(); app.update()
check("EPM test: OF file gets dialog, skipped", dialogs == [["center", "peripheral"]] and "Some files not analyzed" in log)
check("EPM file analyzed with EPM measures", rows()[0][1] == "Analyzed" and "EPM_AnxietyIndex" in app._summary_df.columns)
KEY = ["EPM_ClosedOpenRatio", "EPM_Center_s", "EPM_PctSession_Center", "EPM_OpenArm_s",
       "EPM_PctOpenTime", "EPM_ClosedArm_s", "EPM_PctClosedTime", "EPM_OpenEntries",
       "EPM_ClosedEntries"]
check("EPM Summary shows the key measures by default, in the user's order",
      list(app.summary_tree["columns"]) == ["File", "Status"] + KEY)
r0 = app.files[0].summary
check("summary row: File, then the key measures; open/closed ratio kept in the details",
      list(r0)[:10] == ["File"] + KEY and "EPM_OpenClosedRatio" in r0
      and abs(r0["EPM_PctOpenTime"] + r0["EPM_PctClosedTime"] - 100) < 0.2)
check("Time Bins start with Bin, Start, End, then the key measures",
      list(app.files[0].bins.columns)[:12] == ["Bin", "Start_s", "End_s"]
      + [k.replace("PctSession", "PctBin") for k in KEY])
check("EPM: the center's per-region columns (repeats of EPM center) are dropped",
      not {"Time_mid_s", "Percent_mid", "Entries_mid"} & set(r0)
      and not {"Time_mid_s", "Percent_mid"} & set(app.files[0].bins.columns)
      and "Time_ol_s" in r0 and "EPM_Center_s" in r0)
app.group_vars["test"].set(True); app._show_summary()
check("More test measures adds the other EPM columns after the key ones",
      list(app.summary_tree["columns"])[:11] == ["File", "Status"] + KEY
      and "EPM_OpenClosedRatio" in app.summary_tree["columns"])
app.group_vars["test"].set(False); app._show_summary()
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
check("exported Summary starts with File and the key measures",
      list(sheets["Summary"].columns)[:10] == ["File"] + KEY)
check("exported Time Bins sheet has the EPM measures", "EPM_AnxietyIndex" in sheets["Time Bins"].columns)
names = set(sheets["Settings"]["Setting"])
check("settings sheet lists entry rule, bins, plot style",
      {"Min entry (frames)", "Bin size (s)", "Point size", "Colormap", "Background"} <= names)
check("export finished message", "Export finished" in log)
# A CSV without a reference image: the choice falls back with a note; an
# ezTrack file (no recorded crop) can't be played back.
app.path_bg_var.set("Reference image"); app.bg_var.set("Reference image"); app._redraw_plots()
e1 = app._selected_entry(); p = app._plot_settings()
texts = lambda fig: {t.get_text() for t in fig.axes[0].texts}
on = texts(app._path_fig(e1, p)) | texts(app._heat_fig(e1, p))
app.path_labels_var.set(False); app.heat_labels_var.set(False); p = app._plot_settings()
off = texts(app._path_fig(e1, p)) | texts(app._heat_fig(e1, p))
check("Region labels toggle shows/hides the region names on Path and Heatmap",
      set(e1.data.regions) <= on and not (set(e1.data.regions) & off))
app.path_labels_var.set(True); app.heat_labels_var.set(True)
# Smallest window: the left panel's buttons and the plot controls stay reachable.
app.geometry("900x600"); app.update()
def inside(w):
    x, y, r = w.winfo_rootx(), w.winfo_rooty(), app.winfo_rootx() + app.winfo_width()
    return w.winfo_ismapped() and x + w.winfo_width() <= r + 1 and x >= app.winfo_rootx()
check("at the smallest window, run buttons are inside the window",
      all(inside(b) for b in (app.analyze_btn, app.export_btn, app.select_all_btn)))
app.nb.select(app.tab_path); app.update()
play = [w for w in app.tab_path.winfo_children()[0].winfo_children()
        if isinstance(w, gui.ttk.Button) and "Play" in str(w.cget("text"))]
check("at the smallest window, the Path controls (Play video) are inside the window",
      play and inside(play[0]))
app.nb.select(app.tab_summary); app.geometry("1080x720"); app.update()
check("no reference image: note shown, plots still drawn",
      "no reference" in app.path_bg_note.cget("text") and "no reference" in app.heat_bg_note.cget("text"))
log.clear(); app.play_video(); app.update()
check("ezTrack CSV without its video or crop can't be played back",
      "This file can't be played back" in log)
app.path_bg_var.set("None"); app.bg_var.set("None"); app._on_background()

# Videos (ezTrack's short practice clip, if present): added as "Needs setup",
# set up in the setup window, skipped by Analyze until tracked.
CLIP = os.path.join(ROOT, "ezTrack", "PracticeVideos", "LocationTracking_Clip.mp4")
if os.path.exists(CLIP):
    app.clear_files(); log.clear(); app.add_files([CLIP]); app.update()
    vals = app.file_tree.item("0", "values")
    check("video listed as Video / Needs setup", vals[1] == "Video" and vals[2] == "Needs setup")
    check("status bar before any regions are drawn points to setup",
          "draw them in Set up videos" in app.status.get())
    check("Set up videos button shown", bool(app.setup_btn.winfo_manager()))
    app.open_setup(); app.update()
    win = app._setup_win
    check("setup window opens on the video", win.winfo_exists() and "Clip" in win.video_label.cget("text"))
    v = app.files[0].video
    check("new video gets the test's default session length (EPM 5 min)", v.length_s == 300)
    win.scrub.set(100); win._load_scrub_frame(); win._set_start()
    # The user's slip: Set end here with the slider still at the start, then
    # leaving the length box. Must ask, and never save a tiny default.
    yesno.append(False); log.clear(); win._set_end()
    check("Set end at the start asks first; length kept",
          "Very short session" in log and v.length_s == 300)
    yesno.append(True); win._set_end(); win._apply_length(quiet=True)
    check("a rounded length shown in the box isn't read back as a new length",
          v.end_frame == 101 and app.config_data["session_minutes"]["Elevated Plus Maze"] == 5)
    app.config_data["session_minutes"]["Elevated Plus Maze"] = 0.001
    check("a tiny saved length falls back to the standard 5 min",
          gui.default_session_minutes(app.config_data, "Elevated Plus Maze") == 5)
    app.config_data["session_minutes"]["Elevated Plus Maze"] = 5.0
    win.length_var.set("0.5"); win._apply_length()
    check("typed session length sets the end", v.end_frame == 100 + round(30 * v.info.fps))
    win.length_var.set("600"); win._apply_length()
    check("session longer than the video: end clamped, with a note",
          v.end_frame == v.info.frame_count and "video ends first" in win.end_text.cget("text"))
    win.scrub.set(899); win._load_scrub_frame(); win._set_end()
    check("trim set", (v.start, v.end_frame) == (100, 900))
    v.crop = (100, 50, 1100, 650)
    win._step_by(1); app.update()
    check("Next marks trim done and goes to exclusions",
          win.step == "exclusions" and "trim" in v.steps_done)
    for x, y in ((10, 10), (60, 10), (60, 60)):
        sx, sy = win.canvas.to_screen(x, y)
        win._shape_click(type("E", (), {"x": sx, "y": sy})())
    win._finish_shape()
    check("exclusion shape stored in full-size pixels",
          np.allclose(v.exclusions[0], [[110, 160, 160], [60, 60, 110]]))
    win._step_by(1); log.clear(); win._step_by(1); app.update()
    check("Next without a reference says what's missing",
          win.step == "reference" and "Make the reference first" in log)
    win.ref_var.set("10"); win._make_reference(); app.update()
    ref = v.reference
    check("reference made at the crop's size", ref is not None and ref.shape == (600, 1000)
          and "reference" in v.steps_done)
    with setup_window.VideoReader(v.path, v.prep(1.0)) as r:
        first = r.read_at(v.start).astype(float)
    check("reference is made from frames across the trial, not just the start",
          np.abs(ref - first).mean() > 0.5)
    win._step_by(1); app.update()
    win.scrub.set(500); win._load_scrub_frame(); shown500 = win.canvas._array.copy()
    win.scrub.set(850); win._load_scrub_frame()
    check("tracking check scrubs to different frames",
          win.scrub.cget("to") == 899 and not np.array_equal(shown500, win.canvas._array))
    check("tracking check previews a position", win.step == "tracking" and win._found
          and np.isfinite(win._found[0]) and "found at" in win.found_text.cget("text"))
    win.view_var.set("dif"); win._preview()
    check("differences view shows a color image", win.canvas._array.ndim == 3)
    win.thresh_var.set("150"); log.clear(); win._step_by(1)
    check("invalid tracking setting stops Next", win.step == "tracking"
          and "Invalid tracking setting" in log)
    win.thresh_var.set("99"); win._step_by(1); app.update()
    check("tracking settings saved and step done", app.config_data["loc_thresh"] == 99
          and "tracking" in v.steps_done and win.step == "regions")
    check("Tracking section shown in the main window", bool(app.tracking_section.winfo_manager())
          and "threshold 99%" in app.tracking_text.cget("text"))
    app.test_var.set("Open Field"); win._go("regions"); app.update()
    check("Open Field lists outline and center",
          list(win.region_list.get_children()) == ["arena outline", "center"])
    yesno.append(False); log.clear(); win._step_by(1)
    check("Next with regions missing asks first", win.step == "regions"
          and "Some regions aren't drawn" in log)
    click = lambda x, y: win._region_press(type("E", (), dict(zip("xy", win.canvas.to_screen(x, y))))())
    for x, y in ((-10, -10), (1010, -10), (1010, 610), (-10, 610), (-10, -10)):
        click(x, y)  # the last click is on the first point: closes the shape
    check("outline points in the black border are kept (outside the video)",
          np.allclose(v.regions["arena outline"], [[90, 1110, 1110, 90], [40, 40, 660, 660]]))
    check("after closing, the next region is picked", win._current_region == "center")
    for x, y in ((300, 200), (700, 200), (700, 400), (300, 400)):
        click(x, y)
    win._close_region()
    regs = {r.name: r for r in v.tracking_regions(1.0, "Open Field")}
    check("Open Field periphery = outline minus center",
          set(regs) == {"periphery", "center"} and regs["periphery"].subtract == ["center"]
          and np.allclose(regs["center"].xs, [300, 700, 700, 300]))
    win._region_press(type("E", (), dict(zip("xy", win.canvas.to_screen(300, 200))))())
    win._region_drag(type("E", (), dict(zip("xy", win.canvas.to_screen(320, 210))))())
    win._region_release(None)
    check("dragging a point moves it", np.allclose(v.regions["center"][0][0], 420))
    scr = lambda x, y, dx=0, dy=0: (lambda p: type("E", (), {"x": p[0] + dx, "y": p[1] + dy})())(
        win.canvas.to_screen(x, y))
    win._extra_names.append("test zone"); win._fill_region_list(select="test zone")
    tap = lambda ev: (win._region_press(ev), win._region_release(ev))
    tap(scr(320, 210, 4, 3))      # a click near the center's corner (not a drag)
    tap(scr(510, 205, 0, -4))     # near the middle of the center's top edge
    tap(scr(450, 60))
    tap(scr(320, 210, 4, 3))      # on the first point: closes
    tz, cz = v.regions["test zone"], v.regions["center"]
    check("a point near another region's point locks onto it exactly",
          (tz[0][0], tz[1][0]) == (cz[0][0], cz[1][0]))
    (ax, bx), (ay, by) = cz[0][:2], cz[1][:2]
    cross = (bx - ax) * (tz[1][1] - ay) - (by - ay) * (tz[0][1] - ax)
    check("a point near another region's edge lands on that edge", abs(cross) < 1e-6)
    win._region_press(scr(320, 210)); win._region_drag(scr(330, 215)); win._region_release(None)
    check("locked points move together", tz[0][0] == cz[0][0] and tz[1][0] == cz[1][0]
          and np.allclose([cz[0][0], cz[1][0]], [430, 265]))
    win.snap_var.set(False)
    win._region_press(scr(330, 215)); win._region_drag(scr(340, 215)); win._region_release(None)
    check("with locking off, a point moves on its own",
          np.isclose(cz[0][0], 440) and np.isclose(tz[0][0], 430))
    win.snap_var.set(True)
    win._current_region = "test zone"; win._delete_region()
    cz[0][0], cz[1][0] = 420, 260
    sx, sy = win.canvas.to_screen(500, 300)
    win.canvas.zoom_by(2, sx, sy)
    check("zoom keeps the point under the pointer in place",
          win.canvas.zoom == 2 and np.allclose(win.canvas.to_image(sx, sy), (500, 300))
          and "200%" in win.zoom_text.cget("text"))
    win.canvas.zoom_by(100); check("zoom is capped", win.canvas.zoom == win.canvas.MAX_ZOOM)
    win.canvas._pan_start(type("E", (), {"x": 100, "y": 100})())
    before = win.canvas.center
    win.canvas._pan_move(type("E", (), {"x": 140, "y": 100})())
    check("dragging pans when zoomed", win.canvas.center[0] < before[0])
    win.canvas.reset_view(); check("Fit returns to the whole image", win.canvas.zoom == 1)
    win._step_by(1); app.update()
    check("regions done, on to scale", win.step == "scale" and "regions" in v.steps_done)
    check("scale uses the Open Field length (40 cm)", win.cm_var.get() == "40"
          and "40 cm" in win.instructions.cget("text"))
    for x, y in ((100, 300), (900, 300)):
        win._scale_press(type("E", (), dict(zip("xy", win.canvas.to_screen(x, y))))())
    sc = v.scale(1.0)
    check("scale from two points", sc and abs(sc.px - 800) < 1e-6 and sc.cm == 40
          and "cm per pixel" in win.scale_text.cget("text"))
    check("last step's Next says Finish", win.next_step_btn.cget("text") == "Finish")
    win._step_by(1); app.update()
    check("Finish closes the window; video Ready to track",
          not win.winfo_exists() and app.file_tree.item("0", "values")[2] == "Ready to track")
    check("status bar counts regions drawn in setup (no 'no center' warning)",
          "⚠" not in app.status.get() and "1 Center" in app.status.get())
    log.clear(); app._set_selection([0]); app.analyze(); app.update()
    check("Analyze skips an untracked video", "Videos not tracked yet" in log)
    check("gap-filling section shown when videos are listed", bool(app.gaps_section.winfo_manager()))

    # Track (C7): a short session so it's quick; outputs land beside the clip
    # (in the gitignored ezTrack folder) and are removed afterwards.
    import time
    outs = [os.path.splitext(CLIP)[0] + s for s in ("_LocationOutput.csv", "_reference.png")]
    for f in outs:
        if os.path.exists(f):
            os.remove(f)
    def pump(limit=120):
        t = time.time()
        while app._runner is not None and time.time() - t < limit:
            app.update(); time.sleep(0.02)
        app.update()
    check("Track button shown with the selected count",
          app.track_btn.winfo_manager() and app.track_btn.cget("text") == "Track (1)")
    v.length_s = 4  # the reference no longer matches, so the run makes its own
    app.fps_var.set("20"); log.clear(); yesno[:] = [True]
    app.track(); app.update()
    check("tracking settings lock while tracking", app._tracking_locked()
          and app.track_bar.winfo_manager() and str(app.clear_btn.cget("state")) == "disabled")
    pump()
    want = v.end_frame - v.start
    check("fps setting filled from the video", "isn't the frame rate setting" in " ".join(log)
          and abs(float(app.fps_var.get()) - round(v.info.fps, 2)) < 1e-9)
    check("tracked: Not analyzed, outputs saved, progress bar gone",
          app.file_tree.item("0", "values")[2] == "Not analyzed"
          and all(os.path.exists(f) for f in outs) and not app.track_bar.winfo_manager()
          and "Tracking finished" in log)
    d = app.files[0].data
    check("tracking file has the session's frames, regions and cm distance",
          d is not None and d.n_frames == want and set(d.regions) == {"periphery", "center"}
          and "Distance_cm" in d.df.columns)
    check("tracking settings stay locked after Track", app._tracking_locked())
    log.clear(); yesno[:] = [True]; app.track(); app.update()
    check("already tracked: use existing tracking, no run",
          "Some videos are already tracked" in log and app._runner is None
          and app.files[0].data is not None)
    log.clear(); yesno[:] = [False]; app.track(); app.cancel_tracking(); pump()
    check("Track again, then Cancel: stopped, earlier tracking kept",
          "Tracking stopped" in log and app._runner is None
          and app.file_tree.item("0", "values")[2] == "Not analyzed")
    log.clear(); app.analyze(); app.update()
    # C8: reference background, playback, saved video.
    e0 = app.files[0]
    app.path_bg_var.set("Reference image"); app.bg_var.set("Reference image")
    p = app._plot_settings()
    pf, hf = app._path_fig(e0, p), app._heat_fig(e0, p) if e0.analyzed else (None, None)
    check("Path on the reference image: image drawn, whole image shown, PNG not transparent",
          pf.axes[0].images and pf.opaque and pf.axes[0].get_xlim()[1] >= e0.data.df.X.max()
          and pf.axes[0].get_ylim()[0] > pf.axes[0].get_ylim()[1]
          and abs(pf.axes[0].get_xlim()[1] - (app._reference(e0).shape[1] - 0.5)) < 1e-6)
    hf = app._heat_fig(e0, p)
    check("Heatmap on the reference image (gray image under the cells)",
          len(hf.axes[0].images) == 2 and hf.opaque)
    app.path_bg_var.set("None"); app.bg_var.set("None")
    log.clear(); app._set_selection([0]); app.play_video(); app.update()
    pw = [w for w in app.winfo_children() if isinstance(w, gui.PlaybackWindow)]
    check("Play video opens the playback window", len(pw) == 1 and not log)
    pw = pw[0]; pw.update(); pw.show(10); pw.update()
    check("playback shows the frame with its info",
          pw.canvas._array is not None and "Frame 11 of" in pw.info.cget("text")
          and pw.canvas._array.shape[:2] == app._reference(e0).shape[:2])
    pw.speed_var.set("8x"); pw.play()
    t = time.time()
    while pw.playing and time.time() - t < 20:
        pw.update(); time.sleep(0.01)
    check("plays to the end and stops", not pw.playing and pw.row == pw.pb.n_frames - 1)
    pw.step(-5); check("frame step back", pw.row == pw.pb.n_frames - 6)
    from core.playback import tracked_video_path
    tv = tracked_video_path(CLIP); outs.append(tv); log.clear()
    pw.save_video()
    t = time.time()
    while pw._save is not None and time.time() - t < 60:
        pw.update(); time.sleep(0.02)
    import cv2
    cap = cv2.VideoCapture(tv); nf = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    vfps = cap.get(cv2.CAP_PROP_FPS); cap.release()
    check(f"saved _tracked.mp4: every frame, at the video's frame rate ({nf} frames, {vfps:.2f} fps)",
          "Video saved" in log and nf == pw.pb.n_frames and abs(vfps - v.info.fps) < 0.05)
    pw.close(); app.update()
    check("a tracked video analyzes", app.files[0].analyzed
          and app.file_tree.item("0", "values")[2] == "Analyzed")
    # C9: the exported Settings sheet describes the tracking and the video.
    log.clear(); app.export(); app.update()
    vout = output_paths(CLIP); outs.extend(vout.values())
    st = pd.read_excel(vout["analysis"], sheet_name="Settings")
    got = dict(zip(st["Setting"], st["Value"]))
    check("Settings sheet: tracking settings, scale, crop, session",
          got.get("Animal is (dark / light / abs = either)") == "dark"
          and abs(float(got.get("cm per pixel")) - 0.05) < 1e-6
          and str(got.get("Crop (x0, y0, x1, y1 in downsampled px)")).startswith("100")
          and abs(float(got.get("Session length (min)")) - round(want / v.info.fps / 60, 3)) < 1e-6
          and set(st["Section"]) >= {"Tracking (recorded in the file)", "Video"})
    app.files[0].video.steps_done.discard("scale"); app.files[0].summary = None
    app.clear_files(); app.add_files([CLIP]); app.update(); log.clear(); yesno[:] = [False]
    app.track(); app.update()
    check("a video not set up is skipped and named", "Some videos aren't set up yet" in log
          and app._runner is None)
    for f in outs:
        if os.path.exists(f):
            os.remove(f)
    app.clear_files()
    app.test_var.set("Elevated Plus Maze"); app._on_test_type()
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
