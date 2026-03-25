#!/usr/bin/env python3
"""
Ramen Barcode Editor

Standalone Tkinter tool for manually searching ramen items and adding/removing
barcodes. No browser or scraping — just a quick way to edit barcodes.json.

Usage:
    python barcode_editor.py
"""

import json
import signal
import sys
import tkinter as tk
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", "urllib3.*doesn't match a supported version")

_venv = Path(__file__).resolve().parent.parent / ".venv"
if _venv.is_dir() and not (hasattr(sys, 'real_prefix') or sys.base_prefix != sys.prefix):
    _sp = _venv / "Lib" / "site-packages"
    if not _sp.is_dir():
        _py = f"python{sys.version_info.major}.{sys.version_info.minor}"
        _sp = _venv / "lib" / _py / "site-packages"
    if _sp.is_dir() and str(_sp) not in sys.path:
        sys.path.insert(0, str(_sp))

from fetch_barcodes import (
    load_ramen, load_barcodes, save_barcodes,
    _valid_barcode, _detect_barcode_type,
    _barcode_already_used, _add_barcode,
    _fuzzy_rank_ramen,
)

BG = "#1a1a2e"
FG = "#e0e0e0"
ACCENT = "#f7d354"
ENTRY_BG = "#16213e"
SELECT_BG = "#0f3460"
GREEN = "#6abf69"
RED = "#e74c3c"


class BarcodeEditor:
    def __init__(self):
        self._ramen_list = load_ramen()
        self._selected_rid = None

        root = tk.Tk()
        self._root = root
        root.title("Ramen Barcode Editor")
        root.geometry("700x650")
        root.minsize(600, 550)
        root.configure(bg=BG)

        # --- Search ---
        tk.Label(root, text="Search ramen:", font=("Segoe UI", 10, "bold"),
                 fg=FG, bg=BG, anchor="w").pack(fill=tk.X, padx=12, pady=(10, 2))

        search_frame = tk.Frame(root, bg=BG)
        search_frame.pack(fill=tk.X, padx=12, pady=(0, 4))
        self._search_var = tk.StringVar()
        search_ent = tk.Entry(search_frame, textvariable=self._search_var,
                              font=("Segoe UI", 11), bg=ENTRY_BG, fg=FG,
                              insertbackground=FG)
        search_ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        search_ent.bind("<Return>", lambda e: self._do_search())
        search_ent.bind("<KeyRelease>", lambda e: self._do_search())
        tk.Button(search_frame, text="Search", command=self._do_search,
                  font=("Segoe UI", 9), bg=ENTRY_BG, fg=FG,
                  activebackground=SELECT_BG, activeforeground=ACCENT).pack(side=tk.LEFT)

        # --- Results list ---
        results_frame = tk.Frame(root, bg=BG)
        results_frame.pack(fill=tk.BOTH, padx=12, pady=(0, 4), expand=True)
        yscroll = tk.Scrollbar(results_frame, orient=tk.VERTICAL)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._results_list = tk.Listbox(
            results_frame, height=8, font=("Consolas", 9),
            bg=ENTRY_BG, fg=FG, selectbackground=SELECT_BG,
            selectforeground=ACCENT, yscrollcommand=yscroll.set,
            exportselection=False, activestyle="dotbox",
        )
        self._results_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.config(command=self._results_list.yview)
        self._results_list.bind("<<ListboxSelect>>", self._on_select)
        self._result_ids = []

        # --- Selected item info ---
        tk.Frame(root, bg="#333", height=1).pack(fill=tk.X, padx=12, pady=(6, 4))
        self._info_var = tk.StringVar(value="Select a ramen above")
        tk.Label(root, textvariable=self._info_var, font=("Segoe UI", 11, "bold"),
                 fg=ACCENT, bg=BG, anchor="w", wraplength=660).pack(fill=tk.X, padx=12, pady=(0, 4))

        # --- Current barcodes ---
        tk.Label(root, text="Current barcodes:", font=("Segoe UI", 9, "bold"),
                 fg=FG, bg=BG, anchor="w").pack(fill=tk.X, padx=12, pady=(0, 2))

        bc_frame = tk.Frame(root, bg=BG)
        bc_frame.pack(fill=tk.X, padx=12, pady=(0, 4))
        self._bc_list = tk.Listbox(
            bc_frame, height=4, font=("Consolas", 11),
            bg=ENTRY_BG, fg=GREEN, selectbackground=SELECT_BG,
            selectforeground=ACCENT, exportselection=False, activestyle="dotbox",
        )
        self._bc_list.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(bc_frame, text="Delete\nselected", command=self._delete_barcode,
                  font=("Segoe UI", 9), bg="#3a1a1a", fg=FG,
                  activebackground="#5a2020", activeforeground=ACCENT,
                  width=8).pack(side=tk.LEFT, padx=(6, 0), fill=tk.Y)

        # --- Add barcode ---
        add_frame = tk.Frame(root, bg=BG)
        add_frame.pack(fill=tk.X, padx=12, pady=(6, 2))
        tk.Label(add_frame, text="Add barcode:", font=("Segoe UI", 10, "bold"),
                 fg=FG, bg=BG).pack(side=tk.LEFT, padx=(0, 6))
        self._add_var = tk.StringVar()
        add_ent = tk.Entry(add_frame, textvariable=self._add_var,
                           font=("Segoe UI", 12), width=20, bg=ENTRY_BG,
                           fg=ACCENT, insertbackground=ACCENT)
        add_ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        add_ent.bind("<Return>", lambda e: self._add_barcode())
        tk.Button(add_frame, text="Add", command=self._add_barcode,
                  font=("Segoe UI", 10, "bold"), bg="#2a6041", fg=FG,
                  activebackground="#1e8449", activeforeground="#fff",
                  width=8).pack(side=tk.LEFT)

        # --- Status ---
        self._status_var = tk.StringVar(value="")
        tk.Label(root, textvariable=self._status_var, font=("Segoe UI", 9),
                 fg=FG, bg=BG, anchor="w", wraplength=660).pack(fill=tk.X, padx=12, pady=(4, 10))

        search_ent.focus_set()

        def _check_sigint():
            root.after(200, _check_sigint)
        root.after(200, _check_sigint)

        signal.signal(signal.SIGINT, lambda *_: root.destroy())
        root.mainloop()

    def _do_search(self):
        text = (self._search_var.get() or "").strip()
        if len(text) < 2:
            return
        matches = _fuzzy_rank_ramen(text, self._ramen_list, limit=30)
        self._results_list.delete(0, tk.END)
        self._result_ids.clear()
        for r in matches:
            rid = r.get("id", "?")
            brand = r.get("brand", "")
            variety = r.get("variety", "")
            style = r.get("style", "")
            line = f"#{rid:<5}  {brand} — {variety}  [{style}]"
            self._results_list.insert(tk.END, line)
            self._result_ids.append(rid)

    def _on_select(self, event=None):
        sel = self._results_list.curselection()
        if not sel:
            return
        rid = self._result_ids[sel[0]]
        self._selected_rid = rid
        r = next((r for r in self._ramen_list if r["id"] == rid), None)
        if r:
            self._info_var.set(f"#{rid}  {r.get('brand','')} — {r.get('variety','')}  [{r.get('style','')}]")
        else:
            self._info_var.set(f"#{rid}")
        self._refresh_barcodes()

    def _refresh_barcodes(self):
        self._bc_list.delete(0, tk.END)
        if self._selected_rid is None:
            return
        bl = load_barcodes()
        entry = next((e for e in bl if e["id"] == self._selected_rid), None)
        if entry:
            for bc in entry.get("barcodes", []):
                btype = _detect_barcode_type(str(bc))
                self._bc_list.insert(tk.END, f"{bc}  ({btype})")

    def _add_barcode(self):
        if self._selected_rid is None:
            self._status_var.set("Select a ramen first")
            return
        barcode = self._add_var.get().strip()
        if not barcode:
            return
        if not barcode.isdigit() or len(barcode) not in (8, 12, 13, 14):
            self._status_var.set(f"Invalid: must be 8, 12, 13, or 14 digits")
            return
        if not _valid_barcode(barcode):
            digits = [int(d) for d in barcode]
            payload = digits[:-1]
            total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(payload)))
            expected = (10 - (total % 10)) % 10
            self._status_var.set(f"Check digit failed: last digit is {barcode[-1]}, expected {expected}")
            return

        bl = load_barcodes()
        rid = self._selected_rid

        # Already on this item?
        entry = next((e for e in bl if e["id"] == rid), None)
        if entry and barcode in [str(c) for c in entry.get("barcodes", [])]:
            self._status_var.set(f"{barcode} already on this item")
            return

        dupe_id = _barcode_already_used(bl, barcode, rid)
        if dupe_id:
            r = next((r for r in self._ramen_list if r["id"] == dupe_id), None)
            dupe_label = f"#{dupe_id}"
            if r:
                dupe_label = f"#{dupe_id} {r.get('brand','')} — {r.get('variety','')}"
            self._status_var.set(f"DUPLICATE: {barcode} already belongs to {dupe_label}")
            return

        _add_barcode(bl, rid, barcode)
        save_barcodes(bl)
        btype = _detect_barcode_type(barcode)
        self._status_var.set(f"Added {barcode} ({btype}) to #{rid}")
        self._add_var.set("")
        self._refresh_barcodes()
        print(f"  Added {barcode} ({btype}) to #{rid}")

    def _delete_barcode(self):
        if self._selected_rid is None:
            return
        sel = self._bc_list.curselection()
        if not sel:
            self._status_var.set("Select a barcode to delete")
            return
        text = self._bc_list.get(sel[0])
        barcode = text.split()[0].strip()

        bl = load_barcodes()
        entry = next((e for e in bl if e["id"] == self._selected_rid), None)
        if entry and barcode in entry.get("barcodes", []):
            entry["barcodes"].remove(barcode)
            save_barcodes(bl)
            self._status_var.set(f"Removed {barcode} from #{self._selected_rid}")
            self._refresh_barcodes()
            print(f"  Removed {barcode} from #{self._selected_rid}")
        else:
            self._status_var.set(f"Barcode {barcode} not found on this item")


if __name__ == "__main__":
    BarcodeEditor()
