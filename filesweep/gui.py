"""Tkinter desktop app for FileSweep - preview first, undo anytime."""

from __future__ import annotations

import os
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import core
from .core import Rules

CARD = "#ffffff"
MUTED = "#64748b"
BACKGROUND = "#f6f7fb"


def _enable_dpi_awareness() -> None:
    """Crisp text on Windows displays scaled above 100%."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:  # noqa: BLE001
        pass


class FileSweepApp(tk.Tk):
    def __init__(self, initial_folder: str | Path | None = None) -> None:
        _enable_dpi_awareness()
        super().__init__()
        self.title(f"FileSweep {core.VERSION}")
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width = min(1000, max(780, screen_w - 160))
        height = min(680, max(540, screen_h - 200))
        self.geometry(f"{width}x{height}+{(screen_w - width) // 2}+{max(20, (screen_h - height) // 3)}")
        self.minsize(760, 500)
        self.configure(bg=BACKGROUND)

        self.rules = Rules.load()
        self.moves: list[core.Move] = []
        self.last_journal: Path | None = None

        start = Path(initial_folder) if initial_folder else Path.home() / "Downloads"
        self.folder_var = tk.StringVar(value=str(start))
        self.target_var = tk.StringVar(value="")
        self.recursive_var = tk.BooleanVar(value=self.rules.recursive)
        self.bydate_var = tk.BooleanVar(value=self.rules.by_date)
        self.status_var = tk.StringVar(value="Choose a folder, then press Preview.")

        self._build_styles()
        self._build_layout()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(150, self.preview)

    # ------------------------------------------------------------------ ui
    def _build_styles(self) -> None:
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("TFrame", background=BACKGROUND)
        style.configure("Card.TFrame", background=CARD)
        style.configure("TLabel", background=BACKGROUND, foreground="#0f172a")
        style.configure("Muted.TLabel", background=BACKGROUND, foreground=MUTED)
        style.configure("H1.TLabel", background=CARD, foreground="#0f172a",
                        font=("Segoe UI Semibold", 18))
        style.configure("Sub.TLabel", background=CARD, foreground=MUTED,
                        font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#0f172a", foreground="#e2e8f0",
                        font=("Segoe UI", 9), padding=(12, 6))
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10))
        style.configure("Treeview", rowheight=26, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9))

    def _build_layout(self) -> None:
        header = ttk.Frame(self, style="Card.TFrame", padding=(20, 16))
        header.pack(fill="x")
        ttk.Label(header, text="FileSweep", style="H1.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="Sort any folder by file type. Preview first, undo everything with one click.",
            style="Sub.TLabel",
        ).pack(anchor="w", pady=(2, 0))

        body = ttk.Frame(self, padding=(20, 14, 20, 8))
        body.pack(fill="both", expand=True)

        # source folder row
        source = ttk.Frame(body)
        source.pack(fill="x", pady=(0, 8))
        ttk.Label(source, text="Folder", width=8).pack(side="left")
        ttk.Entry(source, textvariable=self.folder_var).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ttk.Button(source, text="Browse...", command=self.pick_folder).pack(side="left")

        # options row
        options = ttk.Frame(body)
        options.pack(fill="x", pady=(0, 8))
        ttk.Label(options, text="Options", width=8).pack(side="left")
        ttk.Checkbutton(options, text="Include subfolders", variable=self.recursive_var).pack(side="left")
        ttk.Checkbutton(options, text="Group by year/month", variable=self.bydate_var).pack(
            side="left", padx=(16, 0)
        )

        # target row
        target = ttk.Frame(body)
        target.pack(fill="x", pady=(0, 12))
        ttk.Label(target, text="Sort into", width=8).pack(side="left")
        ttk.Entry(target, textvariable=self.target_var).pack(
            side="left", fill="x", expand=True, padx=(0, 8)
        )
        ttk.Button(target, text="Browse...", command=self.pick_target).pack(side="left")
        ttk.Label(target, text="(empty = same folder)", style="Muted.TLabel").pack(
            side="left", padx=(8, 0)
        )

        # action buttons
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(0, 12))
        self.preview_btn = ttk.Button(
            actions, text="Preview", style="Accent.TButton", command=self.preview
        )
        self.preview_btn.pack(side="left")
        self.run_btn = ttk.Button(
            actions, text="Organize now", style="Accent.TButton", command=self.organize
        )
        self.run_btn.pack(side="left", padx=(8, 0))
        self.undo_btn = ttk.Button(actions, text="Undo last run", command=self.undo_last)
        self.undo_btn.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open log folder", command=self.open_logs).pack(side="right")

        # preview table
        table_frame = ttk.Frame(body, style="Card.TFrame")
        table_frame.pack(fill="both", expand=True)
        columns = ("file", "type", "destination")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("file", text="File")
        self.tree.heading("type", text="Category")
        self.tree.heading("destination", text="Destination")
        self.tree.column("file", width=250, stretch=False, anchor="w")
        self.tree.column("type", width=110, stretch=False, anchor="w")
        self.tree.column("destination", width=430, stretch=True, anchor="w")
        self.tree.tag_configure("even", background="#ffffff")
        self.tree.tag_configure("odd", background="#f7f9fc")
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        ttk.Label(self, textvariable=self.status_var, style="Status.TLabel", anchor="w").pack(
            fill="x", side="bottom"
        )

    # -------------------------------------------------------------- actions
    def current_rules(self) -> Rules:
        rules = Rules.load()
        rules.recursive = self.recursive_var.get()
        rules.by_date = self.bydate_var.get()
        target = self.target_var.get().strip()
        rules.target_root = target or None
        return rules

    def current_folder(self) -> Path | None:
        raw = self.folder_var.get().strip().strip('"')
        if not raw:
            messagebox.showwarning("FileSweep", "Pick a folder first.")
            return None
        path = Path(os.path.expandvars(raw)).expanduser()
        if not path.is_dir():
            messagebox.showerror("FileSweep", f"This folder does not exist:\n{path}")
            return None
        return path

    def pick_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Folder to tidy", initialdir=self.folder_var.get() or None)
        if chosen:
            self.folder_var.set(chosen)
            self.preview()

    def pick_target(self) -> None:
        chosen = filedialog.askdirectory(title="Where should the sorted folders live?")
        if chosen:
            self.target_var.set(chosen)

    def preview(self) -> None:
        folder = self.current_folder()
        if not folder:
            return
        self.config(cursor="watch")
        self.update_idletasks()
        try:
            self.moves = core.plan_moves(folder, self.current_rules())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("FileSweep", f"Could not scan this folder:\n{exc}")
            self.moves = []
        finally:
            self.config(cursor="")

        self.tree.delete(*self.tree.get_children())
        for index, move in enumerate(self.moves[:800]):
            self.tree.insert(
                "",
                "end",
                values=(move.src.name, move.category, str(move.dst)),
                tags=("odd" if index % 2 else "even",),
            )

        if not self.moves:
            self.status_var.set("Nothing to organise - this folder is already tidy.")
            return
        total = sum(m.size for m in self.moves)
        extra = "" if len(self.moves) <= 800 else f"  (showing 800 of {len(self.moves)})"
        self.status_var.set(
            f"{len(self.moves)} file(s), {core.human_size(total)} ready to move{extra}"
        )

    def organize(self) -> None:
        if not self.moves:
            self.preview()
        if not self.moves:
            return
        total = sum(m.size for m in self.moves)
        if not messagebox.askyesno(
            "Organize now",
            f"Move {len(self.moves)} file(s) ({core.human_size(total)})?\n"
            "You can undo this from the Undo button.",
        ):
            return
        self.config(cursor="watch")
        self.update_idletasks()
        summary, journal = core.execute(self.moves)
        self.config(cursor="")
        self.last_journal = journal
        messagebox.showinfo(
            "Done",
            f"Moved: {summary.get('moved', 0)}\n"
            f"Skipped: {summary.get('skipped', 0)}\n"
            f"Errors: {summary.get('error', 0)}",
        )
        self.preview()

    def undo_last(self) -> None:
        journal = self.last_journal or core.latest_journal()
        if not journal:
            messagebox.showinfo("FileSweep", "No journal yet - there is nothing to undo.")
            return
        if not messagebox.askyesno("Undo", f"Restore the files from:\n{journal.name}?"):
            return
        summary, _ = core.undo(journal)
        self.last_journal = None
        messagebox.showinfo(
            "Undone",
            f"Restored: {summary.get('restored', 0)}\n"
            f"Missing: {summary.get('missing', 0)}\n"
            f"Errors: {summary.get('error', 0)}",
        )
        self.preview()

    def open_logs(self) -> None:
        folder = core.journal_dir()
        folder.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(folder)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            subprocess.Popen(["explorer", str(folder)])


def main(initial_folder: str | Path | None = None) -> None:
    app = FileSweepApp(initial_folder)
    app.mainloop()


if __name__ == "__main__":
    main()
