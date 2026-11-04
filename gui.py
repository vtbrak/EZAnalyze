"""
Behavior Tracker — GUI front end.

A tkinter desktop app over the `core` analysis engine. Files (added one at a
time, by folder, or by drag-and-drop) build up the file list, which stays
visible above the tabs. Analyze and Export act on the selected files (Select
all selects every one); the focused file drives the Time Bins, Path, and
Heatmap tabs. Nothing is computed until Analyze.

The settings in the left-hand panel can be changed after adding files, and
lock at the first Analyze, so every file in a load is analyzed the same way.
Clear empties the list and unlocks them. Plot styling (Path/Heatmap tabs) is
never locked. The list itself is not saved between sessions.

Run:  python gui.py     (or use the "Open Behavior Tracker.command" launcher)
"""

from __future__ import annotations

import os
import traceback
from datetime import datetime
import tkinter as tk
from dataclasses import dataclass
from tkinter import colorchooser, filedialog, ttk

# Drag-and-drop is optional: without tkinterdnd2 (or if its Tcl library won't
# load) the app still works through the Open File / Open Folder buttons.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DnDMixin = TkinterDnD.DnDWrapper
except ImportError:
    TkinterDnD = None
    _DnDMixin = object

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # figures are built off-screen, then embedded
# Plots saved from the toolbar keep a transparent background, so empty heatmap
# cells (and the area around each plot) can be recolored in an image editor.
matplotlib.rcParams["savefig.transparent"] = True
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)

from core import (
    TrackingData,
    load_csv,
    summary_metrics,
    binned_metrics,
    epm_metrics,
    of_metrics,
    epm_binned,
    of_binned,
    path_figure,
    heatmap_figure,
    load_config,
    save_config,
    summary_column_groups,
    ROLE_LABELS,
    TEST_TYPES,
    auto_role,
    center_periphery_overlap,
    check_roles,
    describe_roles,
    resolve_roles,
)
from core.export import output_paths, save_figure, settings_table, write_analysis_workbook
from core.gaps import fill_gaps
from core.video import (VIDEO_EXTENSIONS, UNREADABLE_WARN, check_readable, is_video,
                        video_info)
from core.video_setup import VideoSetup
from about import AboutDialog
from region_dialog import RegionDialog
from setup_window import SetupWindow, default_session_minutes
from dialogs import ask_yes_no, show_error, show_info, show_warning
from tooltip import Tooltip

HEATMAP_CMAPS = ["inferno", "viridis", "magma", "plasma", "hot", "jet", "gray"]

# Summary-table column groups, in checkbox order (keys match summary_column_groups).
SUMMARY_GROUP_LABELS = {
    "basics": "Session basics",
    "test": "Test measures",
    "zones": "Zone time & %",
    "entries": "Entries & transitions",
    "roi": "ROI label time & %",
    "details": "Details",
}

NOT_ANALYZED = "Not analyzed"
ANALYZED = "Analyzed"
# Status text color in the file list (readable on light and dark themes).
STATUS_COLORS = {"analyzed": "#2e7d32", "waiting": "#b26a00", "failed": "#c62828"}

NEEDS_SETUP = "Needs setup"
READY_TO_TRACK = "Ready to track"

LOCKED_TRACKING_TIP = (
    "Locked because videos have been tracked, so every video in this load is "
    "tracked the same way. Click Clear to change it."
)

LOCKED_TIP = (
    "Locked because files have been analyzed, so every file in this load uses "
    "the same settings. Click Clear to change it."
)


@dataclass
class FileEntry:
    """One file in the list. `summary`/`bins` are filled in by Analyze.

    A video has `video` (its setup) and no `data` until it's tracked; a CSV
    has `data` from the start."""

    path: str
    data: TrackingData | None
    label: str                      # name shown in the Summary ("x (2)" for repeats)
    summary: dict | None = None
    bins: pd.DataFrame | None = None
    video: VideoSetup | None = None

    @property
    def analyzed(self) -> bool:
        return self.summary is not None

    @property
    def kind(self) -> str:
        return "Video" if self.video is not None else "CSV"


class BehaviorTrackerApp(tk.Tk, _DnDMixin):
    LOCKED_TRACKING_TIP = LOCKED_TRACKING_TIP

    def __init__(self):
        super().__init__()
        self.title("Behavior Tracker")
        self.geometry("1080x720")
        self.minsize(900, 600)

        self.config_data = load_config()

        # The file list (not saved: it resets when the app closes).
        self.files: list[FileEntry] = []
        self._selected: int | None = None           # file the tabs show (index)
        self._sel: list[int] = []                   # selected files (indices)
        self._summary_df = None                     # last Summary table (for export)
        self._redraw_job = None                     # pending debounced plot redraw

        self._build_controls()
        self._build_tabs()
        self._show_test_settings()
        self._enable_drop()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Settings are editable until Analyze, so keep the status bar current.
        for var in (self.fps_var, self.bin_var, self.entry_var, self.gap_var, self.adj_var,
                    self.smooth_var):
            var.trace_add("write", lambda *_: self._update_status())
        self._refresh()

    # ------------------------------------------------------------------ UI
    def _build_controls(self):
        # Toolbar, in working order: files | (video steps) | act on the selection.
        bar = ttk.Frame(self, padding=(8, 8, 8, 6))
        bar.pack(side=tk.TOP, fill=tk.X)
        add_file = ttk.Button(bar, text="Add files…", command=self.open_file)
        add_file.pack(side=tk.LEFT)
        Tooltip(add_file, "Add tracking CSVs or videos to the list. You can also "
                          "drag files or folders onto the window.")
        add_folder = ttk.Button(bar, text="Add folder…", command=self.open_folder)
        add_folder.pack(side=tk.LEFT, padx=(6, 0))
        Tooltip(add_folder, "Add every CSV and video in a folder to the list.")
        remove = ttk.Button(bar, text="Remove", command=self.remove_selected)
        remove.pack(side=tk.LEFT, padx=(6, 0))
        Tooltip(remove, "Take the selected files out of the list. The files "
                        "themselves aren't touched.")
        self.clear_btn = ttk.Button(bar, text="Clear", command=self.clear_files)
        self.clear_btn.pack(side=tk.LEFT, padx=(6, 0))
        Tooltip(self.clear_btn, "Clears the file list and unlocks the settings so you "
                                "can choose them again (e.g. after analyzing one file, "
                                "before running a folder).")
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=10)

        # Video steps, shown only while videos are in the list.
        self.video_tools = ttk.Frame(bar)
        self.setup_btn = ttk.Button(self.video_tools, text="Set up videos…",
                                    command=self.open_setup)
        self.setup_btn.pack(side=tk.LEFT)
        Tooltip(self.setup_btn, "Trim, crop, and prepare each video for tracking, one "
                                "at a time.")
        self.video_sep = ttk.Separator(self.video_tools, orient=tk.VERTICAL)
        self.video_sep.pack(side=tk.LEFT, fill=tk.Y, padx=10)

        self.select_all_btn = ttk.Button(bar, text="Select all", width=10,
                                         command=self.toggle_select_all)
        self.select_all_btn.pack(side=tk.LEFT)
        Tooltip(self.select_all_btn, "Select every file in the list, so Analyze and "
                                     "Export act on all of them. Ctrl+A (Cmd+A on a "
                                     "Mac) in the list does the same.")
        self.analyze_btn = ttk.Button(bar, text="Analyze", width=12, command=self.analyze)
        self.analyze_btn.pack(side=tk.LEFT, padx=(6, 0))
        Tooltip(self.analyze_btn, "Analyze the selected files. The number shows how "
                                  "many are selected.")
        self.export_btn = ttk.Button(bar, text="Export", width=12, command=self.export)
        self.export_btn.pack(side=tk.LEFT, padx=(6, 0))
        Tooltip(self.export_btn, "Export the selected files that have been analyzed. "
                                 "Each gets <name>_analysis.xlsx, <name>_path.png, and "
                                 "<name>_heatmap.png next to its CSV (existing files "
                                 "are overwritten).")
        about = ttk.Button(bar, text="About", command=self.show_about)
        about.pack(side=tk.RIGHT)
        Tooltip(about, "Credits, citation, and license.")

        self.status = tk.StringVar()
        status_bar = ttk.Label(
            self, textvariable=self.status, relief=tk.SUNKEN, anchor=tk.W, padding=4
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # Body: settings panel on the left; file list over the tabs on the right.
        body = ttk.Frame(self)
        body.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        self.settings_panel = ttk.Frame(body, padding=(8, 0, 4, 8))
        self.settings_panel.grid(row=0, column=0, sticky="ns")
        self._build_settings_panel(self.settings_panel)
        self.content = ttk.PanedWindow(body, orient=tk.VERTICAL)
        self.content.grid(row=0, column=1, sticky="nsew", padx=(4, 8), pady=(0, 8))
        self._build_file_list(self.content)

    def _setting_row(self, section, row: int, label: str, widget) -> None:
        ttk.Label(section, text=label, wraplength=130, justify=tk.LEFT).grid(
            row=row, column=0, sticky="w", pady=2)
        widget.grid(row=row, column=1, sticky="e", padx=(8, 0), pady=2)
        section.columnconfigure(0, weight=1)

    def _build_settings_panel(self, panel) -> None:
        """Settings in sections. The analysis settings lock at the first Analyze
        of a load (so every file is analyzed the same way) and unlock at Clear."""
        self.lock_note = ttk.Label(panel, text="Locked. Clear to change.",
                                   foreground="gray")

        # Session.
        self.session_section = ttk.LabelFrame(panel, text="Session", padding=6)
        if self.config_data["test_type"] not in TEST_TYPES:  # hand-edited config
            self.config_data["test_type"] = TEST_TYPES[0]
        self.test_var = tk.StringVar(value=self.config_data["test_type"])
        self.test_box = ttk.Combobox(
            self.session_section, textvariable=self.test_var, values=TEST_TYPES,
            state="readonly", width=17,
        )
        self.test_box.bind("<<ComboboxSelected>>", lambda _e: self._on_test_type())
        self._setting_row(self.session_section, 0, "Test", self.test_box)
        self.fps_var = tk.StringVar(value=f"{self.config_data['fps']:g}")
        self.fps_entry = ttk.Entry(self.session_section, textvariable=self.fps_var, width=6)
        self._setting_row(self.session_section, 1, "Frame rate (fps)", self.fps_entry)
        self.bin_var = tk.StringVar(value=f"{self.config_data['bin_seconds']:g}")
        self.bin_entry = ttk.Entry(self.session_section, textvariable=self.bin_var, width=6)
        self._setting_row(self.session_section, 2, "Bin size (s)", self.bin_entry)

        # Entries and regions.
        self.entries_section = ttk.LabelFrame(panel, text="Entries and regions", padding=6)
        self.entry_var = tk.StringVar(value=str(self.config_data["min_entry_frames"]))
        self.entry_entry = ttk.Entry(self.entries_section, textvariable=self.entry_var, width=6)
        self._setting_row(self.entries_section, 0, "Min entry (frames)", self.entry_entry)
        regions_btn = ttk.Button(self.entries_section, text="Regions…",
                                 command=self.open_region_dialog)
        regions_btn.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        Tooltip(regions_btn, "Choose what each region in the files represents "
                             "(open arm, center, ...). Saved for next time.")

        # Open Field thresholds, shown only when the test is Open Field.
        self.of_bar = ttk.LabelFrame(panel, text="Open Field", padding=6)
        self.gap_var = tk.StringVar(value=f"{self.config_data['min_seconds_between_entries']:g}")
        self.gap_entry = ttk.Entry(self.of_bar, textvariable=self.gap_var, width=6)
        self._setting_row(self.of_bar, 0, "Min gap between center entries (s)", self.gap_entry)
        self.adj_var = tk.StringVar(value=f"{self.config_data['min_center_seconds_adjoining']:g}")
        self.adj_entry = ttk.Entry(self.of_bar, textvariable=self.adj_var, width=6)
        self._setting_row(self.of_bar, 1, "Min center time, adjoining (s)", self.adj_entry)
        self.smooth_var = tk.StringVar(value=str(self.config_data["speed_smoothing_frames"]))
        self.smooth_entry = ttk.Entry(self.of_bar, textvariable=self.smooth_var, width=6)
        self._setting_row(self.of_bar, 2, "Speed smoothing (frames)", self.smooth_entry)

        # Tracking settings, shown when videos are listed. They're changed in
        # the setup window's Tracking check step, where their effect shows.
        self.tracking_section = ttk.LabelFrame(panel, text="Tracking", padding=6)
        self.tracking_text = ttk.Label(self.tracking_section, justify=tk.LEFT,
                                       wraplength=210)
        self.tracking_text.grid(row=0, column=0, sticky="w")
        Tooltip(self.tracking_section, lambda: LOCKED_TRACKING_TIP if self._tracking_locked()
                else "Shared by every video. Change them in Set up videos…, step 4 "
                     "(Tracking check). They lock at the first Track.")

        # Unreadable video frames, shown only when a listed file has them marked.
        self.gaps_section = ttk.LabelFrame(panel, text="Unreadable video frames", padding=6)
        self.fill_var = tk.BooleanVar(value=self.config_data["fill_gaps"])
        self.fill_check = ttk.Checkbutton(self.gaps_section, text="Fill short gaps",
                                          variable=self.fill_var)
        self.fill_check.grid(row=0, column=0, columnspan=2, sticky="w")
        self.fill_max_var = tk.StringVar(value=str(self.config_data["fill_gaps_max_frames"]))
        self.fill_max_entry = ttk.Entry(self.gaps_section, textvariable=self.fill_max_var,
                                        width=6)
        self._setting_row(self.gaps_section, 1, "Up to (frames)", self.fill_max_entry)

        for widget, unlocked in (
            (self.test_box, "Which test these files are. Locks when you click Analyze."),
            (self.fps_entry, "Video frame rate. Locks when you click Analyze."),
            (self.bin_entry, "Time-bin length in seconds. Locks when you click Analyze."),
            (self.entry_entry, "Entry rule: the animal must stay in a region at least "
                               "this many frames for it to count as an entry (filters "
                               "boundary jitter). Locks when you click Analyze."),
            (self.gap_entry, "Returning to the center sooner than this after leaving "
                             "it counts as the same visit, not a new entry. Locks "
                             "when you click Analyze."),
            (self.adj_entry, "A crossing between adjoining sides (e.g. left to top) "
                             "only counts if the animal spent at least this long in "
                             "the center on the way. Opposite-side crossings always "
                             "count. Locks when you click Analyze."),
            (self.smooth_entry, "Crossing speeds use speed averaged over this many "
                                "frames, so a one-frame tracking jump can't set the "
                                "peak. 1 = no smoothing. Locks when you click Analyze."),
            (self.fill_check, "Video frames that couldn't be read have no position. "
                              "Off: they're left out (no time, distance, or entries). "
                              "On: short gaps get positions on a straight line between "
                              "the frames before and after. The saved tracking file is "
                              "never changed. Locks when you click Analyze."),
            (self.fill_max_entry, "Longest gap, in frames, that gets filled. Longer "
                                  "gaps stay blank. Locks when you click Analyze."),
        ):
            Tooltip(widget, lambda u=unlocked: LOCKED_TIP if self._locked() else u)
        self._layout_sections()

    def _layout_sections(self) -> None:
        """Show the settings sections that apply, in a fixed order."""
        sections = [
            (self.lock_note, self._locked()),
            (self.session_section, True),
            (self.entries_section, True),
            (self.of_bar, self.test_var.get() == "Open Field"),
            (self.tracking_section, any(e.video is not None
                                        for e in getattr(self, "files", []))),
            (self.gaps_section, any(e.video is not None or (
                e.data is not None and "Frame_Unreadable" in e.data.df.columns)
                for e in getattr(self, "files", []))),
        ]
        c = self.config_data
        self.tracking_text.configure(text=(
            f"Animal is {c['track_method']}, threshold {c['loc_thresh']:g}%\n"
            + (f"Window {c['window_size']} px, weight {c['window_weight']:g}\n"
               if c["use_window"] else "No window\n")
            + f"Downsample {c['video_downsample']:g}, reference {c['reference_frames']} frames\n"
            + ("Locked. Clear to change." if hasattr(self, "files") and self._tracking_locked() else
               "Change in Set up videos…, step 4.")))
        for widget, _ in sections:
            widget.pack_forget()
        for widget, show in sections:
            if show:
                widget.pack(side=tk.TOP, fill=tk.X, pady=(0, 8), anchor="n")

    def _build_file_list(self, parent) -> None:
        """The file list (always visible) above the tabs. Several files can be
        selected; the focused one drives the Time Bins, Path, and Heatmap tabs."""
        wrap = ttk.Frame(parent)
        parent.add(wrap, weight=1)
        self.file_tree = ttk.Treeview(wrap, columns=("File", "Type", "Status"),
                                      show="headings", selectmode="extended", height=6)
        for col, width, anchor in (("File", 360, tk.W), ("Type", 70, tk.CENTER),
                                   ("Status", 140, tk.CENTER)):
            self.file_tree.heading(col, text=col)
            self.file_tree.column(col, width=width, anchor=anchor,
                                  stretch=(col == "File"))
        for tag, color in STATUS_COLORS.items():
            self.file_tree.tag_configure(tag, foreground=color)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=vsb.set)
        self.file_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        self.file_tree.bind("<<TreeviewSelect>>", self._on_select)
        for seq in ("<Control-a>", "<Command-a>"):
            try:
                self.file_tree.bind(seq, lambda _e: (self.select_all(), "break")[1])
            except tk.TclError:
                pass  # <Command-a> only exists on a Mac

    def _build_path_controls(self, parent):
        """Path-tab styling row. Changes redraw the plots."""
        p = self.config_data["plot"]
        bar = ttk.Frame(parent, padding=(4, 6))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(bar, text="Point size:").pack(side=tk.LEFT)
        self.size_var = tk.StringVar(value=f"{p['point_size']:g}")
        ttk.Spinbox(
            bar, from_=0.5, to=50, increment=0.5, width=5, textvariable=self.size_var
        ).pack(side=tk.LEFT, padx=(4, 12))

        ttk.Label(bar, text="Transparency (alpha):").pack(side=tk.LEFT)
        self.alpha_var = tk.StringVar(value=f"{p['alpha']:g}")
        ttk.Spinbox(
            bar, from_=0.05, to=1.0, increment=0.05, width=5, textvariable=self.alpha_var
        ).pack(side=tk.LEFT, padx=(4, 12))

        self.speed_var = tk.BooleanVar(value=p["color_by_speed"])
        ttk.Checkbutton(
            bar, text="Color by speed", variable=self.speed_var,
            command=self._on_color_mode,
        ).pack(side=tk.LEFT, padx=(0, 8))

        self.point_color = p["point_color"]
        self.color_btn = ttk.Button(bar, text="Point color…", command=self._pick_color)
        self.color_btn.pack(side=tk.LEFT)
        # A plain tk.Label so its background can show the chosen color.
        self.color_swatch = tk.Label(
            bar, width=2, background=self.point_color, relief=tk.SOLID, borderwidth=1
        )
        self.color_swatch.pack(side=tk.LEFT, padx=(4, 0))

        for var in (self.size_var, self.alpha_var):
            var.trace_add("write", lambda *_: self._schedule_redraw())
        self._on_color_mode(redraw=False)

    def _build_heatmap_controls(self, parent):
        """Heatmap-tab styling row. Changes redraw the plots."""
        p = self.config_data["plot"]
        bar = ttk.Frame(parent, padding=(4, 6))
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(bar, text="Bins:").pack(side=tk.LEFT)
        self.hbins_var = tk.StringVar(value=str(p["heatmap_bins"]))
        ttk.Spinbox(
            bar, from_=5, to=300, increment=5, width=5, textvariable=self.hbins_var
        ).pack(side=tk.LEFT, padx=(4, 12))

        ttk.Label(bar, text="Colormap:").pack(side=tk.LEFT)
        if p["heatmap_cmap"] not in HEATMAP_CMAPS:  # hand-edited config
            p["heatmap_cmap"] = HEATMAP_CMAPS[0]
        self.cmap_var = tk.StringVar(value=p["heatmap_cmap"])
        ttk.Combobox(
            bar, textvariable=self.cmap_var, values=HEATMAP_CMAPS,
            state="readonly", width=10,
        ).pack(side=tk.LEFT, padx=(4, 16))

        self.bg_var = tk.BooleanVar(value=p["heatmap_background"])
        bg_check = ttk.Checkbutton(
            bar, text="Add background", variable=self.bg_var,
            command=self._on_background,
        )
        bg_check.pack(side=tk.LEFT, padx=(0, 8))
        Tooltip(bg_check, "Fill every cell the animal never entered with one flat "
                          "color. Off: those cells are left empty, and transparent "
                          "in a saved PNG.")
        self.bg_color = p["heatmap_bg_color"]
        self.bg_btn = ttk.Button(bar, text="Background color…", command=self._pick_bg_color)
        self.bg_btn.pack(side=tk.LEFT)
        self.bg_swatch = tk.Label(
            bar, width=2, background=self.bg_color, relief=tk.SOLID, borderwidth=1
        )
        self.bg_swatch.pack(side=tk.LEFT, padx=(4, 0))

        for var in (self.hbins_var, self.cmap_var):
            var.trace_add("write", lambda *_: self._schedule_redraw())
        self._on_background(redraw=False)

    def _build_summary_controls(self, parent):
        """Checkboxes choosing which column groups the Summary table shows."""
        groups = self.config_data["summary_groups"]
        bar = ttk.Frame(parent, padding=(4, 6))
        bar.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(bar, text="Show:").pack(side=tk.LEFT, padx=(0, 6))
        self.group_vars = {}
        for key, label in SUMMARY_GROUP_LABELS.items():
            var = tk.BooleanVar(value=groups.get(key, False))
            ttk.Checkbutton(
                bar, text=label, variable=var, command=self._show_summary
            ).pack(side=tk.LEFT, padx=(0, 10))
            self.group_vars[key] = var
        ttk.Label(
            bar, text="(Export includes all columns)", foreground="gray"
        ).pack(side=tk.RIGHT)

    def _enable_drop(self) -> None:
        """Register the window as a drop target for files and folders."""
        if TkinterDnD is None:
            return
        try:
            TkinterDnD._require(self)
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop)
        except (RuntimeError, tk.TclError):
            traceback.print_exc()  # fall back to the Open buttons only

    def _build_tabs(self):
        self.nb = ttk.Notebook(self.content)
        self.content.add(self.nb, weight=3)

        # Summary tab (column-group checkboxes over a Treeview table). Clicking
        # a row selects that file in the file list.
        self.tab_summary = ttk.Frame(self.nb)
        self.nb.add(self.tab_summary, text="Summary")
        self._build_summary_controls(self.tab_summary)
        self.summary_tree = self._make_tree(self.tab_summary)

        self.summary_tree.bind("<<TreeviewSelect>>", self._on_summary_select)

        # Time-bins tab: a note line (which file / why empty) over the table.
        self.tab_bins = ttk.Frame(self.nb)
        self.nb.add(self.tab_bins, text="Time Bins")
        self.bins_note = tk.StringVar()
        ttk.Label(self.tab_bins, textvariable=self.bins_note, padding=(4, 6)).pack(
            side=tk.TOP, anchor=tk.W
        )
        self.bins_tree = self._make_tree(self.tab_bins)

        # Plot tabs: a control row on top, and an area the figure is redrawn into
        # (kept separate so redrawing never removes the controls).
        self.tab_path = ttk.Frame(self.nb)
        self.nb.add(self.tab_path, text="Path")
        self._build_path_controls(self.tab_path)
        self.path_area = ttk.Frame(self.tab_path)
        self.path_area.pack(fill=tk.BOTH, expand=True)

        self.tab_heat = ttk.Frame(self.nb)
        self.nb.add(self.tab_heat, text="Heatmap")
        self._build_heatmap_controls(self.tab_heat)
        self.heat_area = ttk.Frame(self.tab_heat)
        self.heat_area.pack(fill=tk.BOTH, expand=True)

    def _make_tree(self, parent) -> ttk.Treeview:
        wrap = ttk.Frame(parent)
        wrap.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(wrap, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(wrap, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)
        return tree

    # -------------------------------------------------------------- helpers
    def _fps(self) -> float:
        try:
            v = float(self.fps_var.get())
            if v <= 0:
                raise ValueError
            return v
        except ValueError:
            show_warning(self, "Invalid frame rate",
                         "The frame rate must be a number above 0. Using 20 fps instead.")
            self.fps_var.set("20")
            return 20.0

    def _bin_seconds(self) -> float:
        try:
            v = float(self.bin_var.get())
            if v <= 0:
                raise ValueError
            return v
        except ValueError:
            show_warning(self, "Invalid bin size",
                         "The bin size must be a number above 0. Using 60 s instead.")
            self.bin_var.set("60")
            return 60.0

    def _min_entry_frames(self) -> int:
        try:
            v = int(float(self.entry_var.get()))
            if v < 1:
                raise ValueError
            return v
        except ValueError:
            show_warning(self, "Invalid entry rule",
                         "The minimum entry length must be a whole number of frames, "
                         "1 or more. Using 5 frames instead.")
            self.entry_var.set("5")
            return 5

    def _frames_setting(self, var, name: str, default: int) -> int:
        """A whole number of frames (1 or more), resetting to `default` if invalid."""
        try:
            v = int(float(var.get()))
            if v < 1:
                raise ValueError
            return v
        except ValueError:
            show_warning(self, f"Invalid {name}",
                         f"The {name} must be a whole number of frames, 1 or more. "
                         f"Using {default} frames instead.")
            var.set(str(default))
            return default

    def _seconds_setting(self, var, name: str, default: float) -> float:
        """A threshold in seconds (0 or more), resetting to `default` if invalid."""
        try:
            v = float(var.get())
            if v < 0:
                raise ValueError
            return v
        except ValueError:
            show_warning(self, f"Invalid {name}",
                         f"The {name} must be a number of seconds, 0 or more. "
                         f"Using {default:g} s instead.")
            var.set(f"{default:g}")
            return default

    def _plot_settings(self) -> dict:
        """Current plot style. A box that's mid-edit or invalid keeps its last good
        value instead of interrupting the user with a warning on every keystroke."""
        p = self.config_data["plot"]

        def read(var, cast, lo, hi, key):
            try:
                v = cast(float(var.get()))
            except ValueError:
                return p[key]
            return min(max(v, lo), hi)

        p["point_size"] = read(self.size_var, float, 0.5, 50, "point_size")
        p["alpha"] = read(self.alpha_var, float, 0.05, 1.0, "alpha")
        p["heatmap_bins"] = read(self.hbins_var, int, 5, 300, "heatmap_bins")
        p["heatmap_cmap"] = self.cmap_var.get() or p["heatmap_cmap"]
        p["color_by_speed"] = bool(self.speed_var.get())
        p["point_color"] = self.point_color
        p["heatmap_background"] = bool(self.bg_var.get())
        p["heatmap_bg_color"] = self.bg_color
        return p

    def _schedule_redraw(self) -> None:
        """Redraw plots shortly after the last change, not on every keystroke."""
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after(400, self._redraw_plots)

    def _redraw_plots(self) -> None:
        self._redraw_job = None
        p = self._plot_settings()
        entry = self._selected_entry()
        if entry is None or not entry.analyzed:
            return
        try:
            self._show_figure(self.path_area, self._path_fig(entry, p))
            self._show_figure(self.heat_area, self._heat_fig(entry, p))
        except Exception:
            traceback.print_exc()

    # The same builders draw the on-screen plots and the exported images, so
    # exports always match what's shown.
    @staticmethod
    def _path_fig(entry, p):
        return path_figure(
            entry.data,
            color_by_speed=p["color_by_speed"],
            point_size=p["point_size"],
            point_color=p["point_color"],
            alpha=p["alpha"],
        )

    @staticmethod
    def _heat_fig(entry, p):
        return heatmap_figure(
            entry.data, bins=p["heatmap_bins"], cmap=p["heatmap_cmap"],
            background=p["heatmap_bg_color"] if p["heatmap_background"] else None,
        )

    def _on_color_mode(self, redraw: bool = True) -> None:
        # The solid color only applies when not coloring by speed.
        state = tk.DISABLED if self.speed_var.get() else tk.NORMAL
        self.color_btn.configure(state=state)
        if redraw:
            self._schedule_redraw()

    def _on_background(self, redraw: bool = True) -> None:
        # The color only matters while the background is on.
        self.bg_btn.configure(state=tk.NORMAL if self.bg_var.get() else tk.DISABLED)
        if redraw:
            self._schedule_redraw()

    def _pick_bg_color(self) -> None:
        _, hex_color = colorchooser.askcolor(
            color=self.bg_color, title="Heatmap background color", parent=self
        )
        if hex_color:
            self.bg_color = hex_color
            self.bg_swatch.configure(background=hex_color)
            self._schedule_redraw()

    def _pick_color(self) -> None:
        _, hex_color = colorchooser.askcolor(
            color=self.point_color, title="Point color", parent=self
        )
        if hex_color:
            self.point_color = hex_color
            self.color_swatch.configure(background=hex_color)
            self._schedule_redraw()

    def _save_settings(self, fps: float, bin_s: float) -> None:
        self.config_data["fps"] = fps
        self.config_data["bin_seconds"] = bin_s
        self.config_data["fill_gaps"] = bool(self.fill_var.get())
        try:
            self.config_data["fill_gaps_max_frames"] = max(1, int(float(self.fill_max_var.get())))
        except ValueError:
            pass  # keep the last good value
        self._plot_settings()
        self.config_data["summary_groups"] = {
            k: bool(v.get()) for k, v in self.group_vars.items()
        }
        try:
            save_config(self.config_data)
        except OSError:
            traceback.print_exc()  # settings just won't persist this time

    def _on_close(self) -> None:
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
        self._save_settings(self._fps(), self._bin_seconds())
        self.destroy()

    def _build_summary_df(self) -> pd.DataFrame:
        """Every file in the list: File, Status, then its metrics (blank until
        analyzed). This is also what Export saves for the Summary."""
        rows = []
        for e in self.files:
            row = {"File": e.label, "Status": ANALYZED if e.analyzed else NOT_ANALYZED}
            if e.analyzed:
                row.update({k: v for k, v in e.summary.items() if k != "File"})
            rows.append(row)
        return pd.DataFrame(rows)

    def _show_summary(self) -> None:
        """Fill the Summary table: File and Status, then the checked groups."""
        df = self._summary_df = self._build_summary_df()
        if df.empty:
            self._fill_tree(self.summary_tree, df)
            return
        groups = summary_column_groups([c for c in df.columns if c != "Status"])
        cols = ["File", "Status"]
        for key, var in self.group_vars.items():
            if var.get():
                cols += groups.get(key, [])  # group order, so Details stay last
        self._fill_tree(self.summary_tree, df[cols], iids=[str(i) for i in df.index])
        self._sync_summary_selection()

    def _fill_tree(self, tree: ttk.Treeview, df, iids=None) -> None:
        tree.delete(*tree.get_children())
        if df is None or df.empty:
            tree["columns"] = ()
            return
        cols = list(df.columns)
        tree["columns"] = cols
        for c in cols:
            tree.heading(c, text=c)
            # Wide enough for the header and the longest value, so file names
            # (and the "(2)" on repeats) aren't cut off.
            longest = max([len(str(c))] + [len(str(v)) for v in df[c].dropna()])
            anchor = tk.W if c == "File" else tk.CENTER
            tree.column(c, width=max(80, min(420, 8 * longest + 16)), anchor=anchor,
                        stretch=False)
        for n, (_, row) in enumerate(df.iterrows()):
            values = ["" if pd.isna(row[c]) else row[c] for c in cols]
            tree.insert("", tk.END, iid=iids[n] if iids else None, values=values)

    def _show_figure(self, parent, fig) -> None:
        # Clear whatever was in this tab before.
        for child in parent.winfo_children():
            child.destroy()
        canvas = FigureCanvasTkAgg(fig, master=parent)
        canvas.draw()
        toolbar = NavigationToolbar2Tk(canvas, parent, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side=tk.BOTTOM, fill=tk.X)
        canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    def _clear_tab(self, parent, message: str) -> None:
        for child in parent.winfo_children():
            child.destroy()
        ttk.Label(parent, text=message, padding=20).pack()

    # ------------------------------------------------------------ selection
    def _selected_entry(self) -> FileEntry | None:
        """The file the tabs show: the focused one among those selected."""
        if self._selected is None or self._selected >= len(self.files):
            return None
        return self.files[self._selected]

    def _selected_entries(self) -> list[FileEntry]:
        """The files Analyze and Export act on."""
        return [self.files[i] for i in self._sel if i < len(self.files)]

    def _on_select(self, _event=None) -> None:
        sel = sorted(int(i) for i in self.file_tree.selection())
        focus = self.file_tree.focus()
        shown = int(focus) if focus and int(focus) in sel else (sel[0] if sel else None)
        self._sel = sel
        self._update_action_buttons()
        if shown != self._selected:
            self._selected = shown
            self._sync_summary_selection()
            self._show_selected()

    def _on_summary_select(self, _event=None) -> None:
        """Clicking a Summary row selects that file in the file list."""
        sel = self.summary_tree.selection()
        if sel and int(sel[0]) != self._selected:
            self._set_selection([int(sel[0])])

    def _set_selection(self, indices: list[int], focus: int | None = None) -> None:
        """Select these files in the list; `focus` (default: the first) is the
        one the tabs show."""
        self.file_tree.selection_set([str(i) for i in indices])
        shown = None
        if indices:
            shown = focus if focus in indices else indices[0]
            self.file_tree.focus(str(shown))
            self.file_tree.see(str(shown))
        self._sel = list(indices)
        self._update_action_buttons()
        if shown != self._selected:
            self._selected = shown
            self._show_selected()
        self._sync_summary_selection()

    def _sync_summary_selection(self) -> None:
        # The Summary table highlights the file the tabs show. Its selection
        # event is ignored because that file is already the shown one.
        if self._selected is not None and self.summary_tree.exists(str(self._selected)):
            self.summary_tree.selection_set(str(self._selected))
            self.summary_tree.see(str(self._selected))
        else:
            self.summary_tree.selection_set(())

    def _update_action_buttons(self) -> None:
        n = len(self._sel)
        self.analyze_btn.configure(text=f"Analyze ({n})" if n else "Analyze")
        self.export_btn.configure(text=f"Export ({n})" if n else "Export")
        everything = bool(self.files) and n == len(self.files)
        self.select_all_btn.configure(text="Select none" if everything else "Select all")

    def select_all(self) -> None:
        if self.files:
            self._set_selection(list(range(len(self.files))), focus=self._selected)

    def toggle_select_all(self) -> None:
        if self.files and len(self._sel) == len(self.files):
            self._set_selection([])
        else:
            self.select_all()

    def _show_selected(self) -> None:
        """Point Time Bins, Path, and Heatmap at the selected file."""
        entry = self._selected_entry()
        if entry is None:
            note = ("Add files, then select one in the file list." if not self.files
                    else "Select a file in the file list.")
        elif not entry.analyzed:
            note = f"{entry.label} isn't analyzed yet. Select it and click Analyze."
        else:
            note = None

        if note:
            self.bins_note.set(note)
            self._fill_tree(self.bins_tree, None)
            self._clear_tab(self.path_area, note)
            self._clear_tab(self.heat_area, note)
            return
        self.bins_note.set(f"{entry.label}: {self._bin_seconds_locked():g} s bins")
        self._fill_tree(self.bins_tree, entry.bins)
        self._redraw_plots()

    # -------------------------------------------------------------- locking
    def _locked(self) -> bool:
        """Settings lock at the first Analyze of a load and stay locked until
        Clear (analyzed files only exist between those two points)."""
        return any(e.analyzed for e in self.files)

    def _apply_lock(self) -> None:
        """Grey out test type, fps, and bin size once anything is analyzed.
        The Path/Heatmap plot controls are never locked."""
        locked = self._locked()
        self.test_box.configure(state="disabled" if locked else "readonly")
        for entry in (self.fps_entry, self.bin_entry, self.entry_entry,
                      self.gap_entry, self.adj_entry, self.smooth_entry,
                      self.fill_check, self.fill_max_entry):
            entry.configure(state="disabled" if locked else "normal")
        self._layout_sections()  # shows or hides "Locked. Clear to change."

    def _fps_locked(self) -> float:
        return self.config_data["fps"]

    def _bin_seconds_locked(self) -> float:
        return self.config_data["bin_seconds"]

    def _lock_in_settings(self) -> None:
        """Validate and save the toolbar's test/fps/bin/entry values as this
        load's settings (called at Analyze, before anything is locked)."""
        self.config_data["test_type"] = self.test_var.get()
        self.config_data["min_entry_frames"] = self._min_entry_frames()
        self.config_data["min_seconds_between_entries"] = self._seconds_setting(
            self.gap_var, "time between center entries", 1.0)
        self.config_data["min_center_seconds_adjoining"] = self._seconds_setting(
            self.adj_var, "center time for adjoining crossings", 0.5)
        self.config_data["speed_smoothing_frames"] = self._frames_setting(
            self.smooth_var, "speed smoothing", 5)
        self.config_data["fill_gaps"] = bool(self.fill_var.get())
        self.config_data["fill_gaps_max_frames"] = self._frames_setting(
            self.fill_max_var, "gap length to fill", 5)
        self._save_settings(self._fps(), self._bin_seconds())

    # -------------------------------------------------------------- regions
    def _region_overview(self, entries=None) -> list[tuple[str, float]]:
        """Every region across the given files (first-seen order) with its
        share of their frames."""
        frames: dict[str, int] = {}
        total = 0
        for e in self.files if entries is None else entries:
            if e.data is None:
                continue  # a video not tracked yet
            total += e.data.n_frames
            for r in e.data.regions:
                frames[r] = frames.get(r, 0) + int(e.data.df[r].sum())
        return [(r, 100.0 * n / total if total else 0.0) for r, n in frames.items()]

    def _current_roles(self, entries=None) -> dict[str, str]:
        names = [r for r, _ in self._region_overview(entries)]
        return resolve_roles(names, self.config_data["region_roles"])

    def _unfit(self, entries) -> list[tuple[FileEntry, list[str]]]:
        """Files whose own regions don't fit the chosen test, with the problems."""
        test = self.test_var.get()
        out = []
        for e in entries:
            problems = check_roles(test, self._current_roles([e]))
            if problems:
                out.append((e, problems))
        return out

    def _ready_to_analyze(self, entries) -> list[FileEntry]:
        """Before analyzing: check each file's regions fit the test, asking the
        user to match them if not. Returns the files that can be analyzed;
        any that still don't fit are skipped, with a message naming them."""
        unfit = self._unfit(entries)
        if not unfit:
            return list(entries)
        test = self.test_var.get()
        bad = [e for e, _ in unfit]
        if any("" in self._current_roles([e]).values() for e in bad):
            reason = ("Some region names in these files couldn't be matched "
                      "automatically. Please choose a role for each.")
        else:
            reason = (f"Some files' regions don't fit the {test} test "
                      f"({'; '.join(unfit[0][1])}). Adjust the roles, or if the "
                      "test is wrong, cancel and click Clear to choose it again.")
        self.open_region_dialog(reason=reason, entries=bad)

        still = self._unfit(entries)
        if still:
            lines = "\n".join(f"• {e.label}: {'; '.join(pr)}" for e, pr in still)
            show_warning(
                self, "Some files not analyzed",
                f"These files don't fit the {test} test and were skipped.\n\n"
                f"{lines}\n\nUse Regions… to assign their regions, or click "
                "Clear to choose a different test.",
            )
        skipped = {id(e) for e, _ in still}
        return [e for e in entries if id(e) not in skipped]

    def _warn_overlaps(self, entries) -> None:
        """Center and periphery should never overlap; warn about files where
        they do (the file's ROIs are wrong)."""
        roles = self._current_roles(entries)
        overlaps = []
        for e in entries:
            n = center_periphery_overlap(e.data, roles)
            if n:
                overlaps.append((e.label, n, 100.0 * n / e.data.n_frames))
        if not overlaps:
            return
        lines = "\n".join(
            f"• {name}: {n:,} frames ({pct:.1f}% of the session)"
            for name, n, pct in overlaps
        )
        show_warning(
            self, "Center and periphery overlap",
            "Center and periphery overlap in these files, which is an error "
            "in the file.\n\n"
            "Center and periphery should always be separate, but these frames "
            f"are marked as both:\n{lines}\n\n"
            "Usually the periphery ROI was drawn around the whole arena instead "
            "of only the outer ring. Re-drawing the ROIs in the tracking "
            "software is the real fix. Until then, these frames are counted as "
            "center (not periphery).",
        )

    def open_region_dialog(self, reason: str = "", entries=None) -> None:
        entries = self.files if entries is None else entries
        overview = self._region_overview(entries)
        if not overview:
            show_info(self, "No regions", "Add a file with region columns first.")
            return
        preview = next((e.data for e in entries if e.data is not None and e.data.regions),
                       None)
        dlg = RegionDialog(
            self, self.test_var.get(), overview, self._current_roles(entries),
            preview=preview, reason=reason,
        )
        self.wait_window(dlg)
        if dlg.result is None:
            return
        # Save only real overrides, so later improvements to the automatic
        # suggestions still reach names the user never changed.
        saved = self.config_data["region_roles"]
        for name, role in dlg.result.items():
            if role == auto_role(name):
                saved.pop(name, None)
            else:
                saved[name] = role
        self._save_settings(self._fps_locked(), self._bin_seconds_locked())
        self._update_status()

    def _on_test_type(self) -> None:
        # Only reachable while unlocked; regions are checked at Analyze.
        self.config_data["test_type"] = self.test_var.get()
        self._save_settings(self._fps(), self._bin_seconds())
        self._show_test_settings()
        self._update_status()

    def _show_test_settings(self) -> None:
        """Show the Open Field section only when Open Field is chosen."""
        self._layout_sections()

    # --------------------------------------------------------------- status
    def _update_status(self) -> None:
        if not self.files:
            self.status.set("Add or drop files, choose the test, frame rate, and "
                            "bin size, then click Analyze.")
            return
        done = sum(e.analyzed for e in self.files)
        roles = self._current_roles()
        problems = check_roles(self.test_var.get(), roles)
        regions = f"⚠ {'; '.join(problems)}" if problems else describe_roles(roles)
        if self._locked():
            settings = (f"{self.test_var.get()}, {self._fps_locked():g} fps, "
                        f"{self._bin_seconds_locked():g} s bins, "
                        f"entry ≥ {self.config_data['min_entry_frames']} frames"
                        f"{self._of_status(locked=True)} (locked)")
        else:
            settings = (f"{self.test_var.get()}, {self.fps_var.get()} fps, "
                        f"{self.bin_var.get()} s bins, entry ≥ {self.entry_var.get()} "
                        f"frames{self._of_status(locked=False)} (locks at Analyze)")
        self.status.set(
            f"{len(self.files)} file(s), {done} analyzed — {settings} — "
            f"Regions: {regions}"
        )

    def _of_status(self, locked: bool) -> str:
        if self.test_var.get() != "Open Field":
            return ""
        if locked:
            gap = f"{self.config_data['min_seconds_between_entries']:g}"
            adj = f"{self.config_data['min_center_seconds_adjoining']:g}"
        else:
            gap, adj = self.gap_var.get(), self.adj_var.get()
        return f", entry gap {gap} s, adjoining center {adj} s"

    def _refresh(self) -> None:
        """Re-sync everything that depends on the file list."""
        if any(e.video is not None for e in self.files):
            if not self.video_tools.winfo_ismapped():
                self.video_tools.pack(side=tk.LEFT, before=self.select_all_btn)
        else:
            self.video_tools.pack_forget()
        self._apply_lock()
        self._fill_file_list()
        self._show_summary()
        self._show_selected()
        self._update_status()

    def _file_status(self, entry: FileEntry) -> tuple[str, str]:
        """(status text, color tag) for the file list."""
        if entry.analyzed:
            return ANALYZED, "analyzed"
        if entry.data is None:  # a video, not tracked yet
            if entry.video is not None and entry.video.ready:
                return READY_TO_TRACK, "waiting"
            return NEEDS_SETUP, "waiting"
        return NOT_ANALYZED, ""

    def _tracking_locked(self) -> bool:
        """Tracking settings lock at the first Track of a load (until Clear)."""
        return any(e.video is not None and e.data is not None for e in self.files)

    def open_setup(self) -> None:
        """Open the video setup window at the selected video (or the first one
        that still needs setting up)."""
        videos = [e for e in self.files if e.video is not None]
        if not videos:
            show_info(self, "No videos", "Add a video first.")
            return
        win = getattr(self, "_setup_win", None)
        if win is not None and win.winfo_exists():
            win.lift()
            return
        chosen = [e for e in self._selected_entries() if e.video is not None]
        start = chosen[0] if chosen else next(
            (e for e in videos if e.data is None), videos[0])
        self._setup_win = SetupWindow(self, videos, videos.index(start))

    def _fill_file_list(self) -> None:
        self.file_tree.delete(*self.file_tree.get_children())
        for i, e in enumerate(self.files):
            status, tag = self._file_status(e)
            self.file_tree.insert("", tk.END, iid=str(i), values=(e.label, e.kind, status),
                                  tags=(tag,) if tag else ())
        keep = [i for i in self._sel if i < len(self.files)]
        self._set_selection(keep, focus=self._selected)

    # --------------------------------------------------------------- actions
    def open_file(self):
        videos = " ".join(f"*{ext}" for ext in VIDEO_EXTENSIONS)
        paths = filedialog.askopenfilenames(
            title="Add tracking CSVs or videos",
            filetypes=[("CSVs and videos", f"*.csv {videos}"), ("CSV files", "*.csv"),
                       ("Videos", videos), ("All files", "*.*")],
        )
        if paths:
            self.add_files(list(paths))

    def open_folder(self):
        folder = filedialog.askdirectory(title="Add a folder of CSVs or videos")
        if not folder:
            return
        found = self._files_in(folder)
        if not found:
            show_info(self, "Nothing to add", "That folder has no CSVs or videos.")
            return
        self.add_files(found)

    def _on_drop(self, event):
        """Dropped CSVs, videos, and folders (their CSVs and videos) are added
        to the list. Anything else is ignored."""
        found = []
        for p in self.tk.splitlist(event.data):
            if os.path.isdir(p):
                found.extend(self._files_in(p))
            elif os.path.isfile(p) and self._addable(p):
                found.append(p)
        if found:
            self.add_files(found)
        else:
            show_info(self, "Nothing to add",
                      "Nothing dropped was a CSV, a video, or a folder of them.")
        return event.action

    @staticmethod
    def _addable(path: str) -> bool:
        return path.lower().endswith(".csv") or is_video(path)

    @classmethod
    def _files_in(cls, folder: str) -> list[str]:
        return sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if cls._addable(f) and not f.startswith(".")
        )

    @staticmethod
    def _same_file_key(path: str) -> str:
        # normcase: Windows paths are case-insensitive.
        return os.path.normcase(os.path.abspath(path))

    def add_files(self, paths: list[str]) -> None:
        """Add files to the list (never analyzes them; that waits for Analyze)."""
        # The same file twice in one add (e.g. a file and its folder) is just once.
        paths = list(dict.fromkeys(paths, None))
        in_list = {self._same_file_key(e.path) for e in self.files}
        repeats = [p for p in paths if self._same_file_key(p) in in_list]
        if repeats:
            names = "\n".join(f"• {os.path.basename(p)}" for p in repeats[:10])
            if len(repeats) > 10:
                names += f"\n…and {len(repeats) - 10} more"
            add_again = ask_yes_no(
                self, "Already in the list",
                f"{len(repeats)} file(s) are already in the list.\n\n{names}\n\n"
                "Add them again, or ignore them?",
                yes="Add Again", no="Ignore",
            )
            if not add_again:
                paths = [p for p in paths if p not in repeats]
        if not paths:
            return

        errors, hard_to_read = [], []
        first_new = len(self.files)
        new = []
        for p in paths:
            try:
                if is_video(p):
                    setup = VideoSetup(path=p, info=video_info(p))
                    setup.length_s = 60 * default_session_minutes(self.config_data,
                                                                  self.test_var.get())
                    setup.unreadable = check_readable(p)
                    bad, checked = setup.unreadable
                    if checked and bad / checked > UNREADABLE_WARN:
                        hard_to_read.append((p, bad, checked))
                    data, name = None, os.path.basename(p)
                else:
                    setup, data = None, load_csv(p)
                    name = data.name
            except Exception as exc:  # report bad files, keep the good ones
                errors.append(f"{os.path.basename(p)}: {exc}")
                continue
            new.append((p, data, setup, name))

        if hard_to_read:
            lines = "\n".join(f"• {os.path.basename(p)}: {bad} of the first {checked} "
                              f"frames" for p, bad, checked in hard_to_read)
            keep = ask_yes_no(
                self, "Some videos are hard to read",
                "Some videos have frames that couldn't be read.\n\n"
                f"{lines}\n\nThese frames are kept as blank rows when tracking, but "
                "if there are many, converting the video (e.g. to .mp4 with H.264) "
                "usually fixes it. Add these videos anyway?",
                yes="Add Anyway", no="Skip Them",
            )
            if not keep:
                skip = {p for p, _, _ in hard_to_read}
                new = [n for n in new if n[0] not in skip]

        for p, data, setup, name in new:
            key = self._same_file_key(p)
            copies = sum(self._same_file_key(e.path) == key for e in self.files)
            label = name if not copies else f"{name} ({copies + 1})"
            self.files.append(FileEntry(path=p, data=data, label=label, video=setup))

        if not self._sel and len(self.files) > first_new:
            self._sel = [first_new]  # the first new file, ready for Analyze
            self._selected = first_new
        self._refresh()
        if errors:
            show_warning(
                self, "Some files weren't added",
                "Some files couldn't be read and weren't added.\n\n"
                + "\n".join(errors),
            )

    def clear_files(self) -> None:
        """Empty the list and unlock the per-load settings."""
        self.files = []
        self._sel = []
        self._selected = None
        self._refresh()

    def show_about(self) -> None:
        AboutDialog(self)

    def remove_selected(self) -> None:
        """Take the selected files out of the list (the files aren't touched)."""
        if not self._sel:
            show_info(self, "No file selected", "Select files in the list first.")
            return
        gone = set(self._sel)
        self.files = [e for i, e in enumerate(self.files) if i not in gone]
        self._sel = [0] if self.files else []
        self._selected = 0 if self.files else None
        self._refresh()

    def analyze(self) -> None:
        """Analyze the selected files."""
        if not self.files:
            show_info(self, "No files", "Add files first.")
            return
        targets = self._selected_entries()
        if not targets:
            show_info(self, "No file selected",
                      "Select a file in the list first, or click Select all.")
            return
        untracked = [e for e in targets if e.data is None]
        targets = [e for e in targets if e.data is not None]
        if untracked:
            names = "\n".join(f"• {e.label}" for e in untracked[:10])
            show_info(self, "Videos not tracked yet",
                      "These videos haven't been tracked, so they can't be analyzed "
                      f"yet.\n\n{names}\n\nSet them up and track them first.")
        if not targets:
            return

        if not self._locked():
            self._lock_in_settings()  # the first Analyze of a load sets them
        targets = self._ready_to_analyze(targets)
        if not targets:
            self._update_status()
            return
        self._warn_overlaps(targets)

        fps, bin_s = self._fps_locked(), self._bin_seconds_locked()
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            test = self.test_var.get()
            min_entry = self.config_data["min_entry_frames"]
            fill = bool(self.config_data["fill_gaps"])
            fill_max = int(self.config_data["fill_gaps_max_frames"])
            for e in targets:
                # Gap filling works on a copy; the file's own data is untouched.
                data = fill_gaps(e.data, fill_max) if fill else e.data
                summary = summary_metrics(data, fps=fps)
                roles = self._current_roles([e])
                # Record the settings behind these numbers in the row itself, so
                # an exported table shows how it was produced.
                settings = {"Test": test, "MinEntryFrames": min_entry,
                            "FillGaps": fill, "FillGapsMaxFrames": fill_max}
                bins = binned_metrics(data, fps=fps, bin_seconds=bin_s)
                test_bins = None
                if test == "Elevated Plus Maze":
                    summary.update(epm_metrics(
                        data, roles, fps=fps, min_entry_frames=min_entry,
                    ))
                    test_bins = epm_binned(data, roles, fps=fps, bin_seconds=bin_s,
                                           min_entry_frames=min_entry)
                elif test == "Open Field":
                    gap = self.config_data["min_seconds_between_entries"]
                    adj = self.config_data["min_center_seconds_adjoining"]
                    smooth = self.config_data["speed_smoothing_frames"]
                    summary.update(of_metrics(
                        data, roles, fps=fps, min_entry_frames=min_entry,
                        min_between_entries_s=gap, min_center_adjoining_s=adj,
                        speed_smoothing_frames=smooth,
                    ))
                    test_bins = of_binned(
                        data, roles, fps=fps, bin_seconds=bin_s,
                        min_entry_frames=min_entry, min_between_entries_s=gap,
                        min_center_adjoining_s=adj, speed_smoothing_frames=smooth,
                    )
                    settings.update({"MinBetweenCenterEntries_s": gap,
                                     "MinCenterAdjoiningCrossing_s": adj,
                                     "SpeedSmoothing_frames": smooth})
                summary.update(settings)
                e.summary = summary
                # The test's measures per bin go after the general bin columns.
                if test_bins is not None and not bins.empty:
                    bins = bins.merge(test_bins, on="Bin", how="left")
                e.bins = bins
        finally:
            self.config(cursor="")
        self._refresh()

    def _settings_sheet(self, entry, plot: dict):
        """Everything that produced this file's numbers and images."""
        row = entry.summary
        test = row.get("Test", self.test_var.get())
        analysis = {
            "Test": test,
            "Frame rate (fps)": row.get("FPS"),
            "Min entry (frames)": row.get("MinEntryFrames"),
            "Fill gaps of unreadable frames": bool(row.get("FillGaps", False)),
            "Fill gaps up to (frames)": row.get("FillGapsMaxFrames"),
        }
        if test == "Open Field":
            analysis.update({
                "Min gap between center entries (s)": row.get("MinBetweenCenterEntries_s"),
                "Min center time, adjoining crossings (s)":
                    row.get("MinCenterAdjoiningCrossing_s"),
                "Speed smoothing (frames)": row.get("SpeedSmoothing_frames"),
            })
        roles = self._current_roles([entry])
        return settings_table({
            "Source": {
                "Source file": entry.path,
                "Video (File column)": entry.data.name,
                "Exported": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
            "Analysis": analysis,
            "Region roles": {r: ROLE_LABELS.get(k, k) or "Unassigned"
                             for r, k in roles.items()},
            "Time Bins": {"Bin size (s)": self._bin_seconds_locked()},
            "Path": {
                "Point size": plot["point_size"],
                "Transparency (alpha)": plot["alpha"],
                "Color by speed": plot["color_by_speed"],
                "Point color": plot["point_color"],
            },
            "Heatmap": {
                "Bins": plot["heatmap_bins"],
                "Colormap": plot["heatmap_cmap"],
                "Add background": plot["heatmap_background"],
                "Background color": plot["heatmap_bg_color"],
            },
            "Tracking (from file)": dict(entry.data.settings),
        })

    def export(self) -> None:
        """Write each selected, analyzed file's _analysis.xlsx, _path.png, and
        _heatmap.png next to its source CSV, overwriting existing files."""
        selected = self._selected_entries()
        if not selected:
            show_info(self, "No file selected",
                      "Select a file in the list first, or click Select all.")
            return
        targets = [e for e in selected if e.analyzed]
        if not targets:
            show_info(self, "Not analyzed yet",
                      "The selected files haven't been analyzed. Click Analyze "
                      "first, then export.")
            return
        # A file added twice writes to the same names, so export it once.
        seen, unique = set(), []
        for e in targets:
            key = self._same_file_key(e.path)
            if key not in seen:
                seen.add(key)
                unique.append(e)

        plot = dict(self._plot_settings())  # the on-screen plot settings, now
        written, errors = [], []
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            for e in unique:
                out = output_paths(e.path)
                try:
                    write_analysis_workbook(
                        out["analysis"], {k: v for k, v in e.summary.items()},
                        e.bins, self._settings_sheet(e, plot),
                    )
                    save_figure(self._path_fig(e, plot), out["path"])
                    save_figure(self._heat_fig(e, plot), out["heatmap"])
                    written.append(e)
                except PermissionError:
                    errors.append(f"• {e.label}: a file is open in another program "
                                  "(e.g. the workbook in Excel). Close it and try again.")
                except Exception as exc:  # report and carry on with the rest
                    errors.append(f"• {e.label}: {exc}")
                    traceback.print_exc()
        finally:
            self.config(cursor="")

        skipped = len(selected) - len(targets)
        if written:
            folders = sorted({os.path.dirname(e.path) for e in written})
            where = folders[0] if len(folders) == 1 else f"{len(folders)} folders"
            self.status.set(f"Exported {len(written)} file(s) → {where}")
        if errors:
            show_warning(
                self, "Some files weren't exported",
                f"{len(errors)} file(s) couldn't be exported.\n\n" + "\n".join(errors),
            )
        if written:
            names = "\n".join(f"• {os.path.basename(output_paths(e.path)['analysis'])}"
                              for e in written[:10])
            if len(written) > 10:
                names += f"\n…and {len(written) - 10} more"
            note = ("" if not skipped
                    else f"\n\n{skipped} selected file(s) weren't analyzed, so "
                         "they weren't exported.")
            show_info(
                self, "Export finished",
                f"Exported {len(written)} file(s) next to their CSVs.\n\n"
                "Each has an _analysis.xlsx workbook (Summary, Time Bins, and "
                f"Settings sheets) plus _path.png and _heatmap.png images.\n\n"
                f"{names}{note}",
            )


def main():
    app = BehaviorTrackerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
