"""
GUI for Bulk Certificate Generator (tkinter).
Workflow: pick blank certificate image + CSV → names stamped on the long line.
Run: python app.py
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import config
from certificate_generator import ensure_blank_template, generate_certificates


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Bulk Certificate Generator")
        self.geometry("640x420")
        self.minsize(560, 380)
        self.resizable(True, True)

        # Ensure folders exist; create sample blank if missing
        config.TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not config.DEFAULT_TEMPLATE.exists():
            ensure_blank_template(config.DEFAULT_TEMPLATE)

        self.template_var = tk.StringVar(value=str(config.DEFAULT_TEMPLATE))
        self.data_var = tk.StringVar(value=str(config.DATA_DIR / "recipients.csv"))
        self.output_var = tk.StringVar(value=str(config.OUTPUT_DIR))
        self.format_var = tk.StringVar(value=config.OUTPUT_FORMAT)
        self.status_var = tk.StringVar(value="Ready — pick your blank certificate + CSV of names.")
        self._busy = False

        self._build()

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 6}
        frm = ttk.Frame(self, padding=16)
        frm.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frm,
            text="Put names on the long line of your certificate image",
            font=("Segoe UI", 12, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", **pad)

        # Template
        ttk.Label(frm, text="Certificate image:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.template_var, width=52).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse…", command=self._browse_template).grid(row=1, column=2, **pad)

        # CSV
        ttk.Label(frm, text="Names CSV / Excel:").grid(row=2, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.data_var, width=52).grid(row=2, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse…", command=self._browse_data).grid(row=2, column=2, **pad)

        # Output
        ttk.Label(frm, text="Output folder:").grid(row=3, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.output_var, width=52).grid(row=3, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse…", command=self._browse_output).grid(row=3, column=2, **pad)

        # Format
        ttk.Label(frm, text="Output format:").grid(row=4, column=0, sticky="w", **pad)
        fmt_row = ttk.Frame(frm)
        fmt_row.grid(row=4, column=1, sticky="w", **pad)
        for label, val in (("PNG + PDF", "both"), ("PNG only", "png"), ("PDF only", "pdf")):
            ttk.Radiobutton(fmt_row, text=label, variable=self.format_var, value=val).pack(side=tk.LEFT, padx=(0, 12))

        # Actions
        btn_row = ttk.Frame(frm)
        btn_row.grid(row=5, column=0, columnspan=3, sticky="ew", pady=16, padx=12)
        self.gen_btn = ttk.Button(btn_row, text="Generate certificates", command=self._on_generate)
        self.gen_btn.pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Open output folder", command=self._open_output).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_row, text="Make sample blank", command=self._make_blank).pack(side=tk.LEFT)

        # Status
        ttk.Separator(frm, orient=tk.HORIZONTAL).grid(row=6, column=0, columnspan=3, sticky="ew", padx=12, pady=8)
        ttk.Label(frm, textvariable=self.status_var, wraplength=580).grid(
            row=7, column=0, columnspan=3, sticky="w", **pad
        )

        hint = (
            "Tip: Use a blank certificate (PNG/JPG) that has a clear long underline for the name. "
            "CSV needs a column named name (or full_name / recipient). "
            "Optional columns: course, date, organization, signatory."
        )
        ttk.Label(frm, text=hint, foreground="#555", wraplength=580).grid(
            row=8, column=0, columnspan=3, sticky="w", **pad
        )

        frm.columnconfigure(1, weight=1)

    def _browse_template(self) -> None:
        path = filedialog.askopenfilename(
            title="Select blank / sample certificate image",
            filetypes=[
                ("Images", "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.tif;*.tiff"),
                ("All files", "*.*"),
            ],
            initialdir=str(config.TEMPLATES_DIR),
        )
        if path:
            self.template_var.set(path)

    def _browse_data(self) -> None:
        path = filedialog.askopenfilename(
            title="Select recipients CSV or Excel",
            filetypes=[
                ("Spreadsheets", "*.csv;*.xlsx;*.xls"),
                ("CSV", "*.csv"),
                ("Excel", "*.xlsx;*.xls"),
                ("All files", "*.*"),
            ],
            initialdir=str(config.DATA_DIR),
        )
        if path:
            self.data_var.set(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Output folder", initialdir=str(config.OUTPUT_DIR))
        if path:
            self.output_var.set(path)

    def _open_output(self) -> None:
        out = Path(self.output_var.get())
        out.mkdir(parents=True, exist_ok=True)
        try:
            import os

            os.startfile(out)  # type: ignore[attr-defined]
        except Exception:
            messagebox.showinfo("Output folder", str(out.resolve()))

    def _make_blank(self) -> None:
        path = ensure_blank_template(config.DEFAULT_TEMPLATE)
        self.template_var.set(str(path))
        self.status_var.set(f"Sample blank saved: {path}")
        messagebox.showinfo("Sample blank", f"Created:\n{path}")

    def _on_generate(self) -> None:
        if self._busy:
            return
        template = Path(self.template_var.get().strip())
        data = Path(self.data_var.get().strip())
        output = Path(self.output_var.get().strip())
        fmt = self.format_var.get()

        if not template.exists():
            messagebox.showerror("Missing template", f"Certificate image not found:\n{template}")
            return
        if not data.exists():
            messagebox.showerror("Missing CSV", f"Recipients file not found:\n{data}")
            return

        self._busy = True
        self.gen_btn.configure(state=tk.DISABLED)
        self.status_var.set("Generating… detecting long line and placing names.")

        def work() -> None:
            err: Exception | None = None
            written: list[Path] = []
            try:
                written = generate_certificates(
                    recipients_path=data,
                    template_path=template,
                    output_dir=output,
                    output_format=fmt,
                )
            except Exception as exc:  # noqa: BLE001
                err = exc

            def done() -> None:
                self._busy = False
                self.gen_btn.configure(state=tk.NORMAL)
                if err:
                    self.status_var.set(f"Error: {err}")
                    messagebox.showerror("Generation failed", str(err))
                else:
                    n = len(written)
                    self.status_var.set(f"Done — {n} file(s) in {output}")
                    messagebox.showinfo("Done", f"Created {n} file(s) in:\n{output.resolve()}")

            self.after(0, done)

        threading.Thread(target=work, daemon=True).start()


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
