"""
Behavior Tracker — GUI front end.

A tkinter desktop app over the `core` analysis engine. Two modes:
  * Single file  — load one CSV, view summary, time bins, path & heatmap.
  * Batch folder — analyze every CSV in a folder into one summary table.

Run:  python gui.py     (or use the "Open Behavior Tracker.command" launcher)
"""

from __future__ import annotations

import os
import traceback
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

# Drag-and-drop is optional: without tkinterdnd2 (or if its Tcl library won't
# load) the app still works through the Open File / Open Folder buttons.
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    _DnDMixin = TkinterDnD.DnDWrapper
except ImportError:
    TkinterDnD = None
    _DnDMixin = object

import matplotlib
matplotlib.use("Agg")  # figures are built off-screen, then embedded
from matplotlib.backends.backend_tkagg import (
    FigureCanvasTkAgg,
    NavigationToolbar2Tk,
)

from core import (
    TrackingData,
    load_csv,
    summary_metrics,
    binned_metrics,
    batch_summary,
    path_figure,
    heatmap_figure,
    load_config,
    save_config,
    summary_column_groups,
)

HEATMAP_CMAPS = ["inferno", "viridis", "magma", "plasma", "hot", "jet", "gray"]

# Summary-table column groups, in checkbox order (keys match summary_column_groups).
SUMMARY_GROUP_LABELS = {
    "basics": "Session basics",
    "zones": "Zone time & %",
    "entries": "Entries & transitions",
    "roi": "ROI label time & %",
    "details": "Details",
}


class BehaviorTrackerApp(tk.Tk, _DnDMixin):
    def __init__(self):
        super().__init__()
        self.title("Behavior Tracker")
        self.geometry("1080x720")
        self.minsize(880, 560)

        self.config_data = load_config()

        # Loaded state.
        self.current: TrackingData | None = None   # single-file mode
        self.batch: list[TrackingData] = []         # batch mode
        self._summary_df = None                     # last table shown (for export)
        self._bins_df = None
        self._canvas = None                         # active embedded figure canvas
        self._toolbar = None
        self._redraw_job = None                     # pending debounced plot redraw

        self._build_controls()
        self._build_tabs()
        self._enable_drop()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _build_controls(self):
        bar = ttk.Frame(self, padding=8)
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(bar, text="Open File…", command=self.open_file).pack(side=tk.LEFT)
        ttk.Button(bar, text="Open Folder…", command=self.open_folder).pack(
            side=tk.LEFT, padx=(6, 16)
        )

        ttk.Label(bar, text="Frame rate (fps):").pack(side=tk.LEFT)
        self.fps_var = tk.StringVar(value=f"{self.config_data['fps']:g}")
        ttk.Entry(bar, textvariable=self.fps_var, width=6).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Label(bar, text="Bin size (s):").pack(side=tk.LEFT)
        self.bin_var = tk.StringVar(value=f"{self.config_data['bin_seconds']:g}")
        ttk.Entry(bar, textvariable=self.bin_var, width=6).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Button(bar, text="Recompute", command=self.recompute).pack(side=tk.LEFT)
        ttk.Button(bar, text="Export Table…", command=self.export_table).pack(
            side=tk.RIGHT
        )

        self.status = tk.StringVar(value="Open or drop a file or folder to begin.")
        status_bar = ttk.Label(
            self, textvariable=self.status, relief=tk.SUNKEN, anchor=tk.W, padding=4
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

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
        ).pack(side=tk.LEFT, padx=(4, 0))

        for var in (self.hbins_var, self.cmap_var):
            var.trace_add("write", lambda *_: self._schedule_redraw())

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
            bar, text="(Export always includes every column)", foreground="gray"
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
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Summary tab (column-group checkboxes over a Treeview table).
        self.tab_summary = ttk.Frame(self.nb)
        self.nb.add(self.tab_summary, text="Summary")
        self._build_summary_controls(self.tab_summary)
        self.summary_tree = self._make_tree(self.tab_summary)

        # Time-bins tab.
        self.tab_bins = ttk.Frame(self.nb)
        self.nb.add(self.tab_bins, text="Time Bins")
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
        tree = ttk.Treeview(wrap, show="headings")
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
            messagebox.showwarning("Invalid frame rate", "Using 20 fps instead.")
            self.fps_var.set("20")
            return 20.0

    def _bin_seconds(self) -> float:
        try:
            v = float(self.bin_var.get())
            if v <= 0:
                raise ValueError
            return v
        except ValueError:
            messagebox.showwarning("Invalid bin size", "Using 60 s instead.")
            self.bin_var.set("60")
            return 60.0

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
        return p

    def _schedule_redraw(self) -> None:
        """Redraw plots shortly after the last change, not on every keystroke."""
        if self._redraw_job is not None:
            self.after_cancel(self._redraw_job)
        self._redraw_job = self.after(400, self._redraw_plots)

    def _redraw_plots(self) -> None:
        self._redraw_job = None
        p = self._plot_settings()
        if self.current is None:
            return
        try:
            self._show_figure(
                self.path_area,
                path_figure(
                    self.current,
                    color_by_speed=p["color_by_speed"],
                    point_size=p["point_size"],
                    point_color=p["point_color"],
                    alpha=p["alpha"],
                ),
            )
            self._show_figure(
                self.heat_area,
                heatmap_figure(
                    self.current, bins=p["heatmap_bins"], cmap=p["heatmap_cmap"]
                ),
            )
        except Exception:
            traceback.print_exc()

    def _on_color_mode(self, redraw: bool = True) -> None:
        # The solid color only applies when not coloring by speed.
        state = tk.DISABLED if self.speed_var.get() else tk.NORMAL
        self.color_btn.configure(state=state)
        if redraw:
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

    def _show_summary(self) -> None:
        """Fill the Summary table with File plus the checked column groups."""
        df = self._summary_df
        if df is None or df.empty:
            self._fill_tree(self.summary_tree, df)
            return
        groups = summary_column_groups(df.columns)
        cols = [c for c in df.columns if c == "File"]
        for key, var in self.group_vars.items():
            if var.get():
                cols += groups.get(key, [])  # group order, so Details stay last
        self._fill_tree(self.summary_tree, df[cols])

    def _fill_tree(self, tree: ttk.Treeview, df) -> None:
        tree.delete(*tree.get_children())
        if df is None or df.empty:
            tree["columns"] = ()
            return
        cols = list(df.columns)
        tree["columns"] = cols
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=max(80, min(220, 9 * len(str(c)))), anchor=tk.CENTER)
        for _, row in df.iterrows():
            tree.insert("", tk.END, values=[row[c] for c in cols])

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

    # --------------------------------------------------------------- actions
    def open_file(self):
        path = filedialog.askopenfilename(
            title="Open a LocationOutput CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if path:
            self.load_file(path)

    def open_folder(self):
        folder = filedialog.askdirectory(title="Open a folder of CSVs")
        if folder:
            self.load_folder(folder)

    def _on_drop(self, event):
        """Dropped items: one CSV → single-file mode; a folder or several CSVs →
        batch mode. Non-CSV files are ignored."""
        paths = self.tk.splitlist(event.data)
        dirs = [p for p in paths if os.path.isdir(p)]
        csvs = [p for p in paths if os.path.isfile(p) and p.lower().endswith(".csv")]
        if len(dirs) == 1 and not csvs:
            self.load_folder(dirs[0])
        elif len(csvs) == 1 and not dirs:
            self.load_file(csvs[0])
        else:
            for d in dirs:
                csvs.extend(self._csvs_in(d))
            if csvs:
                self._load_batch(sorted(set(csvs)))
            else:
                messagebox.showinfo("No CSVs", "Nothing dropped was a .csv file or folder.")
        return event.action

    @staticmethod
    def _csvs_in(folder: str) -> list[str]:
        return sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(".csv")
        )

    def load_file(self, path: str) -> None:
        try:
            self.current = load_csv(path)
            self.batch = []
            self.recompute()
            self.status.set(f"Loaded {self.current.name} ({self.current.n_frames} frames)")
        except Exception as exc:  # surface load errors to the user
            messagebox.showerror("Could not load file", str(exc))
            traceback.print_exc()

    def load_folder(self, folder: str) -> None:
        csvs = self._csvs_in(folder)
        if not csvs:
            messagebox.showinfo("No CSVs", "That folder has no .csv files.")
            return
        self._load_batch(csvs)

    def _load_batch(self, csvs: list[str]) -> None:
        loaded, errors = [], []
        for p in csvs:
            try:
                loaded.append(load_csv(p))
            except Exception as exc:
                errors.append(f"{os.path.basename(p)}: {exc}")
        if not loaded:
            messagebox.showerror("No files loaded", "\n".join(errors))
            return
        self.batch = loaded
        self.current = None
        self.recompute()
        msg = f"Loaded {len(loaded)} file(s)"
        if errors:
            msg += f", skipped {len(errors)}"
        self.status.set(msg)
        if errors:
            messagebox.showwarning("Some files skipped", "\n".join(errors))

    def recompute(self):
        """(Re)build every view from the current fps / bin settings."""
        fps = self._fps()
        bin_s = self._bin_seconds()
        self._save_settings(fps, bin_s)

        if self.batch:
            self._recompute_batch(fps, bin_s)
        elif self.current:
            self._recompute_single(fps, bin_s)

    def _recompute_single(self, fps: float, bin_s: float):
        d = self.current
        self._summary_df = batch_summary([d], fps=fps)
        self._bins_df = binned_metrics(d, fps=fps, bin_seconds=bin_s)
        self._show_summary()
        self._fill_tree(self.bins_tree, self._bins_df)
        self._redraw_plots()

    def _recompute_batch(self, fps: float, bin_s: float):
        self._summary_df = batch_summary(self.batch, fps=fps)
        self._bins_df = None
        self._show_summary()
        self._fill_tree(self.bins_tree, None)
        # Plots are per-file; in batch mode point the user back to single-file.
        # The Time Bins table is left in place (just emptied) so single-file mode
        # can fill it again; the plot tabs are rebuilt on every draw anyway.
        note = "Plots and time bins show for a single file.\nUse “Open File…” to view one."
        self._clear_tab(self.path_area, note)
        self._clear_tab(self.heat_area, note)

    def export_table(self):
        """Export whichever table is on the active tab (Summary or Time Bins)."""
        active = self.nb.tab(self.nb.select(), "text")
        df = self._bins_df if active == "Time Bins" else self._summary_df
        if df is None or df.empty:
            messagebox.showinfo("Nothing to export", "Load data first.")
            return
        path = filedialog.asksaveasfilename(
            title=f"Export {active}",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Excel", "*.xlsx")],
            initialfile=f"{active.lower().replace(' ', '_')}.csv",
        )
        if not path:
            return
        try:
            if path.lower().endswith(".xlsx"):
                df.to_excel(path, index=False)
            else:
                df.to_csv(path, index=False)
            self.status.set(f"Exported {active} → {path}")
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc))


def main():
    app = BehaviorTrackerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
