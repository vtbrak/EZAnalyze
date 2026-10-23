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
from tkinter import filedialog, messagebox, ttk

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
)


class BehaviorTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Behavior Tracker")
        self.geometry("1080x720")
        self.minsize(880, 560)

        # Loaded state.
        self.current: TrackingData | None = None   # single-file mode
        self.batch: list[TrackingData] = []         # batch mode
        self._summary_df = None                     # last table shown (for export)
        self._bins_df = None
        self._canvas = None                         # active embedded figure canvas
        self._toolbar = None

        self._build_controls()
        self._build_tabs()

    # ------------------------------------------------------------------ UI
    def _build_controls(self):
        bar = ttk.Frame(self, padding=8)
        bar.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(bar, text="Open File…", command=self.open_file).pack(side=tk.LEFT)
        ttk.Button(bar, text="Open Folder…", command=self.open_folder).pack(
            side=tk.LEFT, padx=(6, 16)
        )

        ttk.Label(bar, text="Frame rate (fps):").pack(side=tk.LEFT)
        self.fps_var = tk.StringVar(value="20")
        ttk.Entry(bar, textvariable=self.fps_var, width=6).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Label(bar, text="Bin size (s):").pack(side=tk.LEFT)
        self.bin_var = tk.StringVar(value="60")
        ttk.Entry(bar, textvariable=self.bin_var, width=6).pack(side=tk.LEFT, padx=(4, 16))

        ttk.Button(bar, text="Recompute", command=self.recompute).pack(side=tk.LEFT)
        ttk.Button(bar, text="Export Table…", command=self.export_table).pack(
            side=tk.RIGHT
        )

        self.status = tk.StringVar(value="Open a file or folder to begin.")
        status_bar = ttk.Label(
            self, textvariable=self.status, relief=tk.SUNKEN, anchor=tk.W, padding=4
        )
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        # Summary tab (a Treeview table).
        self.tab_summary = ttk.Frame(self.nb)
        self.nb.add(self.tab_summary, text="Summary")
        self.summary_tree = self._make_tree(self.tab_summary)

        # Time-bins tab.
        self.tab_bins = ttk.Frame(self.nb)
        self.nb.add(self.tab_bins, text="Time Bins")
        self.bins_tree = self._make_tree(self.tab_bins)

        # Plot tabs.
        self.tab_path = ttk.Frame(self.nb)
        self.nb.add(self.tab_path, text="Path")
        self.tab_heat = ttk.Frame(self.nb)
        self.nb.add(self.tab_heat, text="Heatmap")

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
        if not path:
            return
        try:
            self.current = load_csv(path)
            self.batch = []
            self.recompute()
            self.status.set(f"Loaded {self.current.name} ({self.current.n_frames} frames)")
        except Exception as exc:  # surface load errors to the user
            messagebox.showerror("Could not load file", str(exc))
            traceback.print_exc()

    def open_folder(self):
        folder = filedialog.askdirectory(title="Open a folder of CSVs")
        if not folder:
            return
        csvs = sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if f.lower().endswith(".csv")
        )
        if not csvs:
            messagebox.showinfo("No CSVs", "That folder has no .csv files.")
            return
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

        if self.batch:
            self._recompute_batch(fps, bin_s)
        elif self.current:
            self._recompute_single(fps, bin_s)

    def _recompute_single(self, fps: float, bin_s: float):
        d = self.current
        self._summary_df = batch_summary([d], fps=fps)
        self._bins_df = binned_metrics(d, fps=fps, bin_seconds=bin_s)
        self._fill_tree(self.summary_tree, self._summary_df)
        self._fill_tree(self.bins_tree, self._bins_df)
        try:
            self._show_figure(self.tab_path, path_figure(d))
            self._show_figure(self.tab_heat, heatmap_figure(d))
        except Exception:
            traceback.print_exc()

    def _recompute_batch(self, fps: float, bin_s: float):
        self._summary_df = batch_summary(self.batch, fps=fps)
        self._bins_df = None
        self._fill_tree(self.summary_tree, self._summary_df)
        self._fill_tree(self.bins_tree, None)
        # Plots are per-file; in batch mode point the user back to single-file.
        note = "Plots and time bins show for a single file.\nUse “Open File…” to view one."
        self._clear_tab(self.tab_bins, note)
        self._clear_tab(self.tab_path, note)
        self._clear_tab(self.tab_heat, note)

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
