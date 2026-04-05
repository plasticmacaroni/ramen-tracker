#!/usr/bin/env python3
"""
Duplicate Barcode Review Tool

Presents every barcode conflict group (barcodes claimed by multiple ramen items)
and lets the user decide per-item: assign barcode, exclude item, or mark barcode
as invalid. Changes are staged and applied only after explicit confirmation.

Usage:
    python review_duplicates.py
"""

import json
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

_venv = Path(__file__).resolve().parent.parent / ".venv"
if _venv.is_dir() and not (hasattr(sys, 'real_prefix') or sys.base_prefix != sys.prefix):
    _sp = _venv / "Lib" / "site-packages"
    if not _sp.is_dir():
        _py = f"python{sys.version_info.major}.{sys.version_info.minor}"
        _sp = _venv / "lib" / _py / "site-packages"
    if _sp.is_dir() and str(_sp) not in sys.path:
        sys.path.insert(0, str(_sp))

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
IMAGES_DIR = ROOT_DIR / "images" / "ramen"
TOOLS_DIR = ROOT_DIR / "tools"

RAMEN_JSON = DATA_DIR / "ramen.json"
BARCODES_JSON = DATA_DIR / "barcodes.json"
DUPES_JSON = DATA_DIR / "duplicates.json"
TYPOS_JSON = TOOLS_DIR / "typos.json"
URLS_JSON = DATA_DIR / "urls.json"
PROGRESS_JSON = TOOLS_DIR / ".dupe_review_progress.json"


# ---------------------------------------------------------------------------
# Data layer
# ---------------------------------------------------------------------------

def load_json(path, default=None):
    if default is None:
        default = []
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        return default


def save_json(path, data, indent=2):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
        f.write("\n")


def build_conflict_groups():
    """Build barcode -> set of ramen IDs from both barcodes.json and duplicates.json."""
    barcode_list = load_json(BARCODES_JSON, [])
    dupes = load_json(DUPES_JSON, [])
    ramen_db = {r["id"]: r for r in load_json(RAMEN_JSON, [])}
    urls = load_json(URLS_JSON, {})

    # Track which IDs actually own each barcode in barcodes.json
    id_to_barcodes = {}
    for entry in barcode_list:
        rid = entry["id"]
        for bc in entry.get("barcodes", []):
            bc = str(bc).strip()
            if bc:
                id_to_barcodes.setdefault(rid, set()).add(bc)

    # Simulate JS barcodeMap (last-write-wins, sorted by id ascending)
    js_winner = {}
    for entry in sorted(barcode_list, key=lambda e: e.get("id", 0)):
        for bc in entry.get("barcodes", []):
            bc = str(bc).strip()
            if bc:
                js_winner[bc] = entry["id"]

    # Collect all barcode -> ID associations
    bc_to_ids = {}
    for entry in barcode_list:
        rid = entry["id"]
        for bc in entry.get("barcodes", []):
            bc = str(bc).strip()
            if bc:
                bc_to_ids.setdefault(bc, set()).add(rid)

    for d in dupes:
        bc = str(d["barcode"]).strip()
        bc_to_ids.setdefault(bc, set()).add(d["id"])
        bc_to_ids.setdefault(bc, set()).add(d["existing_id"])

    # Filter to conflicts (2+ IDs)
    groups = []
    for bc, ids in bc_to_ids.items():
        if len(ids) < 2:
            continue
        items = []
        for rid in sorted(ids):
            r = ramen_db.get(rid)
            in_barcodes_json = bc in id_to_barcodes.get(rid, set())
            is_js_winner = js_winner.get(bc) == rid
            url = urls.get(str(rid), "")
            if not url:
                url = f"https://www.theramenrater.com/?s=%23{rid}%3A"
            items.append({
                "id": rid,
                "brand": r.get("brand", "???") if r else "NOT IN DB",
                "variety": r.get("variety", "???") if r else "NOT IN DB",
                "style": r.get("style", "?") if r else "?",
                "country": r.get("country", "?") if r else "?",
                "stars": r.get("stars", "?") if r else "?",
                "in_barcodes_json": in_barcodes_json,
                "is_js_winner": is_js_winner,
                "in_ramen_db": r is not None,
                "url": url,
            })
        groups.append({"barcode": bc, "items": items})

    # Sort: largest groups first, then by barcode
    groups.sort(key=lambda g: (-len(g["items"]), g["barcode"]))
    return groups


# ---------------------------------------------------------------------------
# Progress persistence
# ---------------------------------------------------------------------------

def load_progress():
    return load_json(PROGRESS_JSON, {})


def save_progress(progress):
    save_json(PROGRESS_JSON, progress)


# ---------------------------------------------------------------------------
# Apply changes
# ---------------------------------------------------------------------------

def compute_changes(groups, progress):
    """From progress decisions, compute concrete file changes."""
    excludes = []
    barcode_assigns = {}  # barcode -> winner_id
    bad_barcodes = set()
    barcode_removals = {}  # barcode -> set of IDs to remove it from

    ramen_db = {r["id"]: r for r in load_json(RAMEN_JSON, [])}

    for g in groups:
        bc = g["barcode"]
        decision = progress.get(bc)
        if not decision:
            continue

        if decision.get("bad_barcode"):
            bad_barcodes.add(bc)
            continue

        assign_id = decision.get("assign")
        exclude_ids = set(decision.get("exclude", []))

        for ex_id in exclude_ids:
            r = ramen_db.get(ex_id)
            name = f"#{ex_id} {r['brand']} — {r['variety']}" if r else f"#{ex_id} (not in DB)"
            excludes.append({"id": ex_id, "name": name})

        if assign_id:
            barcode_assigns[bc] = assign_id
            # Remove barcode from all other items that have it in barcodes.json
            for item in g["items"]:
                if item["id"] != assign_id and item["in_barcodes_json"]:
                    barcode_removals.setdefault(bc, set()).add(item["id"])
        else:
            # No one assigned — remove from all that have it
            for item in g["items"]:
                if item["in_barcodes_json"]:
                    barcode_removals.setdefault(bc, set()).add(item["id"])

    return {
        "excludes": excludes,
        "barcode_assigns": barcode_assigns,
        "bad_barcodes": bad_barcodes,
        "barcode_removals": barcode_removals,
    }


def apply_changes(changes):
    """Write changes to typos.json, barcodes.json, and duplicates.json."""
    # --- typos.json: add excludes ---
    typos = load_json(TYPOS_JSON, {})
    exclude_list = typos.get("exclude", [])
    new_exclude_ids = {e["id"] for e in changes["excludes"]}
    for eid in sorted(new_exclude_ids):
        if eid not in exclude_list:
            exclude_list.append(eid)
    typos["exclude"] = exclude_list
    save_json(TYPOS_JSON, typos)

    # --- barcodes.json: reassign and remove ---
    barcode_list = load_json(BARCODES_JSON, [])
    all_remove = {}  # id -> set of barcodes to remove
    for bc, ids_to_remove in changes["barcode_removals"].items():
        for rid in ids_to_remove:
            all_remove.setdefault(rid, set()).add(bc)
    for bc in changes["bad_barcodes"]:
        for entry in barcode_list:
            if bc in [str(c) for c in entry.get("barcodes", [])]:
                all_remove.setdefault(entry["id"], set()).add(bc)

    # Also remove barcodes from excluded items
    for e in changes["excludes"]:
        eid = e["id"]
        for entry in barcode_list:
            if entry["id"] == eid:
                for bc in list(entry.get("barcodes", [])):
                    all_remove.setdefault(eid, set()).add(str(bc))

    for entry in barcode_list:
        rid = entry["id"]
        removals = all_remove.get(rid, set())
        if removals:
            entry["barcodes"] = [c for c in entry.get("barcodes", [])
                                 if str(c) not in removals]

    # Ensure assigned barcodes are on the winner
    for bc, winner_id in changes["barcode_assigns"].items():
        winner_entry = next((e for e in barcode_list if e["id"] == winner_id), None)
        if winner_entry:
            codes = winner_entry.setdefault("barcodes", [])
            if bc not in [str(c) for c in codes]:
                codes.append(bc)
        else:
            barcode_list.append({"id": winner_id, "barcodes": [bc]})

    # Remove empty entries
    barcode_list = [e for e in barcode_list if e.get("barcodes")]
    barcode_list.sort(key=lambda e: e.get("id", 0))
    save_json(BARCODES_JSON, barcode_list)

    # --- duplicates.json: remove resolved entries ---
    dupes = load_json(DUPES_JSON, [])
    resolved_barcodes = (set(changes["barcode_assigns"].keys())
                         | changes["bad_barcodes"]
                         | set(changes["barcode_removals"].keys()))
    dupes = [d for d in dupes if str(d["barcode"]) not in resolved_barcodes]
    save_json(DUPES_JSON, dupes)

    return len(new_exclude_ids), len(changes["barcode_assigns"]), len(changes["bad_barcodes"])


# ---------------------------------------------------------------------------
# Tkinter GUI
# ---------------------------------------------------------------------------

class ReviewApp:
    def __init__(self, groups):
        self._groups = groups
        self._progress = load_progress()
        self._index = self._find_first_undecided()
        self._photos = {}

        self._root = tk.Tk()
        self._root.title("Duplicate Barcode Review")
        self._root.configure(bg="#1a1a2e")
        self._root.geometry("750x820")
        self._root.minsize(680, 700)

        self._build_ui()
        self._show_group()

    def _find_first_undecided(self):
        for i, g in enumerate(self._groups):
            if g["barcode"] not in self._progress:
                return i
        return 0

    # --- UI construction ---

    def _build_ui(self):
        root = self._root

        # Header
        hdr = tk.Frame(root, bg="#0f3460", padx=10, pady=6)
        hdr.pack(fill=tk.X)
        self._title_var = tk.StringVar()
        tk.Label(hdr, textvariable=self._title_var, font=("Segoe UI", 12, "bold"),
                 fg="#f7d354", bg="#0f3460").pack(side=tk.LEFT)
        self._progress_var = tk.StringVar()
        tk.Label(hdr, textvariable=self._progress_var, font=("Segoe UI", 10),
                 fg="#e0e0e0", bg="#0f3460").pack(side=tk.RIGHT)

        # Progress bar
        self._pbar = ttk.Progressbar(root, length=200, mode="determinate",
                                     maximum=len(self._groups))
        self._pbar.pack(fill=tk.X, padx=10, pady=(4, 0))

        # Barcode info
        info = tk.Frame(root, bg="#1a1a2e", padx=10, pady=6)
        info.pack(fill=tk.X)
        self._barcode_var = tk.StringVar()
        tk.Label(info, textvariable=self._barcode_var, font=("Consolas", 11),
                 fg="#e0e0e0", bg="#1a1a2e").pack(side=tk.LEFT)
        self._winner_var = tk.StringVar()
        tk.Label(info, textvariable=self._winner_var, font=("Segoe UI", 9),
                 fg="#a0a0a0", bg="#1a1a2e").pack(side=tk.RIGHT)

        # Scrollable item area
        container = tk.Frame(root, bg="#1a1a2e")
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 0))

        self._canvas = tk.Canvas(container, bg="#1a1a2e", highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient=tk.VERTICAL, command=self._canvas.yview)
        self._scroll_frame = tk.Frame(self._canvas, bg="#1a1a2e")

        self._scroll_frame.bind("<Configure>",
                                lambda e: self._canvas.configure(scrollregion=self._canvas.bbox("all")))
        self._canvas_window = self._canvas.create_window((0, 0), window=self._scroll_frame,
                                                          anchor="nw")
        self._canvas.configure(yscrollcommand=scrollbar.set)
        self._canvas.bind("<Configure>", self._on_canvas_resize)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Bad barcode option
        bad_frame = tk.Frame(root, bg="#1a1a2e", padx=10)
        bad_frame.pack(fill=tk.X, pady=(4, 2))
        self._bad_barcode_var = tk.BooleanVar(value=False)
        self._bad_barcode_cb = tk.Checkbutton(
            bad_frame, text="Bad barcode — remove from all items (barcode database error)",
            variable=self._bad_barcode_var, command=self._on_bad_barcode_toggle,
            font=("Segoe UI", 9, "bold"), fg="#e74c3c", bg="#1a1a2e",
            selectcolor="#16213e", activebackground="#1a1a2e", activeforeground="#e74c3c")
        self._bad_barcode_cb.pack(side=tk.LEFT)

        # Separator
        tk.Frame(root, bg="#333", height=1).pack(fill=tk.X, padx=10, pady=(6, 2))

        # Navigation
        nav = tk.Frame(root, bg="#1a1a2e", padx=10, pady=4)
        nav.pack(fill=tk.X)

        self._prev_btn = tk.Button(nav, text="<< Prev", command=self._prev,
                                   font=("Segoe UI", 10), bg="#16213e", fg="#e0e0e0",
                                   activebackground="#0f3460", activeforeground="#f7d354",
                                   width=10)
        self._prev_btn.pack(side=tk.LEFT, padx=4)

        tk.Button(nav, text="Skip", command=self._skip,
                  font=("Segoe UI", 10), bg="#16213e", fg="#e0e0e0",
                  activebackground="#0f3460", activeforeground="#f7d354",
                  width=10).pack(side=tk.LEFT, padx=4)

        self._save_btn = tk.Button(nav, text="Save & Next >>", command=self._save_and_next,
                                   font=("Segoe UI", 10, "bold"), bg="#2a6041", fg="#e0e0e0",
                                   activebackground="#1e8449", activeforeground="#fff",
                                   width=14)
        self._save_btn.pack(side=tk.LEFT, padx=4)

        # Jump
        jump_frame = tk.Frame(nav, bg="#1a1a2e")
        jump_frame.pack(side=tk.RIGHT)
        tk.Label(jump_frame, text="Go to:", font=("Segoe UI", 9),
                 fg="#a0a0a0", bg="#1a1a2e").pack(side=tk.LEFT, padx=(0, 4))
        self._jump_var = tk.StringVar()
        jump_entry = tk.Entry(jump_frame, textvariable=self._jump_var, width=6,
                              font=("Segoe UI", 10), bg="#16213e", fg="#e0e0e0",
                              insertbackground="#e0e0e0")
        jump_entry.pack(side=tk.LEFT)
        jump_entry.bind("<Return>", lambda e: self._jump_to())
        tk.Button(jump_frame, text="Go", command=self._jump_to,
                  font=("Segoe UI", 9), bg="#16213e", fg="#e0e0e0",
                  activebackground="#0f3460", activeforeground="#f7d354").pack(side=tk.LEFT, padx=2)

        # Status + apply
        status = tk.Frame(root, bg="#1a1a2e", padx=10, pady=4)
        status.pack(fill=tk.X)
        self._status_var = tk.StringVar()
        tk.Label(status, textvariable=self._status_var, font=("Segoe UI", 9),
                 fg="#a0a0a0", bg="#1a1a2e").pack(side=tk.LEFT)

        tk.Button(status, text="Review & Apply All Changes",
                  command=self._review_and_apply,
                  font=("Segoe UI", 10, "bold"), bg="#8b4513", fg="#e0e0e0",
                  activebackground="#a0522d", activeforeground="#fff").pack(side=tk.RIGHT, padx=4)

        # Last action
        self._last_action_var = tk.StringVar()
        tk.Label(root, textvariable=self._last_action_var, font=("Segoe UI", 9),
                 fg="#6abf69", bg="#1a1a2e").pack(fill=tk.X, padx=10, pady=(0, 6))

    def _on_canvas_resize(self, event):
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # --- Display ---

    def _show_group(self):
        if not self._groups:
            return

        g = self._groups[self._index]
        bc = g["barcode"]
        items = g["items"]
        total = len(self._groups)
        decided = sum(1 for gg in self._groups if gg["barcode"] in self._progress)

        self._title_var.set(f"Barcode Conflict Review")
        self._progress_var.set(f"[{self._index + 1}/{total}]  Decided: {decided}/{total}")
        self._pbar["value"] = decided
        self._barcode_var.set(f"Barcode: {bc}")

        js_winner = next((it for it in items if it["is_js_winner"]), None)
        if js_winner:
            self._winner_var.set(f"Current JS winner: #{js_winner['id']} (last-write-wins)")
        else:
            self._winner_var.set("No current JS winner")

        self._prev_btn.config(state=tk.NORMAL if self._index > 0 else tk.DISABLED)

        # Clear scroll frame
        for w in self._scroll_frame.winfo_children():
            w.destroy()
        self._item_widgets = []
        self._photos.clear()

        # Load saved decision if any
        saved = self._progress.get(bc, {})
        saved_assign = saved.get("assign")
        saved_excludes = set(saved.get("exclude", []))
        saved_bad = saved.get("bad_barcode", False)

        self._bad_barcode_var.set(saved_bad)

        # Radio variable for barcode assignment
        self._assign_var = tk.IntVar(value=saved_assign if saved_assign else 0)

        for i, item in enumerate(items):
            card = self._build_item_card(self._scroll_frame, item, i,
                                         is_assigned=(saved_assign == item["id"]),
                                         is_excluded=(item["id"] in saved_excludes),
                                         is_bad=saved_bad)
            card.pack(fill=tk.X, padx=4, pady=3)

        self._update_status()
        self._canvas.yview_moveto(0)

    def _build_item_card(self, parent, item, idx, is_assigned, is_excluded, is_bad):
        rid = item["id"]
        card = tk.Frame(parent, bg="#16213e", padx=8, pady=6, relief=tk.RIDGE, bd=1)

        # Left: image
        img_label = tk.Label(card, bg="#16213e", width=120, height=120)
        img_label.grid(row=0, column=0, rowspan=3, padx=(0, 10), sticky="n")
        self._load_thumbnail(img_label, rid)

        # Right: info
        info_frame = tk.Frame(card, bg="#16213e")
        info_frame.grid(row=0, column=1, sticky="nw")

        # ID + name row
        id_text = f"#{rid}"
        if item["is_js_winner"]:
            id_text += "  << JS WINNER"
        id_label = tk.Label(info_frame, text=id_text, font=("Segoe UI", 9, "underline"),
                            fg="#88bbff", bg="#16213e", cursor="hand2")
        id_label.pack(anchor="w")
        id_label.bind("<Button-1>", lambda e, url=item["url"]: webbrowser.open(url))

        name = f"{item['brand']} — {item['variety']}"
        tk.Label(info_frame, text=name, font=("Segoe UI", 10, "bold"),
                 fg="#f7d354", bg="#16213e", wraplength=480, justify=tk.LEFT).pack(anchor="w")

        detail = f"{item['style']}  |  {item['country']}  |  {item['stars']}★"
        if item["in_barcodes_json"]:
            detail += "  |  [in barcodes.json]"
        if not item["in_ramen_db"]:
            detail += "  |  NOT IN DB"
        tk.Label(info_frame, text=detail, font=("Segoe UI", 9),
                 fg="#a0a0a0", bg="#16213e").pack(anchor="w")

        # Actions row
        actions = tk.Frame(card, bg="#16213e")
        actions.grid(row=1, column=1, sticky="w", pady=(4, 0))

        rb = tk.Radiobutton(actions, text="Assign barcode", variable=self._assign_var,
                            value=rid, font=("Segoe UI", 9), fg="#e0e0e0", bg="#16213e",
                            selectcolor="#0f3460", activebackground="#16213e",
                            activeforeground="#f7d354")
        rb.pack(side=tk.LEFT, padx=(0, 12))
        if is_bad:
            rb.config(state=tk.DISABLED)

        exclude_var = tk.BooleanVar(value=is_excluded)
        cb = tk.Checkbutton(actions, text="Exclude", variable=exclude_var,
                            font=("Segoe UI", 9), fg="#e74c3c", bg="#16213e",
                            selectcolor="#0f3460", activebackground="#16213e",
                            activeforeground="#e74c3c")
        cb.pack(side=tk.LEFT, padx=(0, 12))

        tk.Button(actions, text="View Review", command=lambda url=item["url"]: webbrowser.open(url),
                  font=("Segoe UI", 8), fg="#88bbff", bg="#16213e",
                  activebackground="#0f3460", activeforeground="#f7d354",
                  borderwidth=1, cursor="hand2").pack(side=tk.LEFT)

        self._item_widgets.append({
            "id": rid,
            "radio": rb,
            "exclude_var": exclude_var,
            "exclude_cb": cb,
        })

        card.columnconfigure(1, weight=1)
        return card

    def _load_thumbnail(self, label, rid):
        img_path = IMAGES_DIR / f"{rid}.webp"
        if not img_path.exists():
            label.configure(image="", text="No image", fg="#666",
                            font=("Segoe UI", 9), width=14, height=7)
            return
        try:
            from PIL import Image, ImageTk
            pil = Image.open(img_path)
            pil.thumbnail((120, 120))
            photo = ImageTk.PhotoImage(pil)
            self._photos[rid] = photo
            label.configure(image=photo, text="", width=120, height=120)
        except ImportError:
            label.configure(image="", text="(Pillow\nneeded)", fg="#666",
                            font=("Segoe UI", 8), width=14, height=7)
        except Exception:
            label.configure(image="", text="Error", fg="#666",
                            font=("Segoe UI", 9), width=14, height=7)

    def _on_bad_barcode_toggle(self):
        is_bad = self._bad_barcode_var.get()
        for w in self._item_widgets:
            if is_bad:
                w["radio"].config(state=tk.DISABLED)
                self._assign_var.set(0)
            else:
                w["radio"].config(state=tk.NORMAL)

    # --- Navigation ---

    def _collect_decision(self):
        """Read current UI state into a decision dict."""
        g = self._groups[self._index]
        bc = g["barcode"]

        if self._bad_barcode_var.get():
            return bc, {"bad_barcode": True, "assign": None, "exclude": []}

        assign_id = self._assign_var.get()
        if assign_id == 0:
            assign_id = None

        excludes = []
        for w in self._item_widgets:
            if w["exclude_var"].get():
                excludes.append(w["id"])

        return bc, {"assign": assign_id, "exclude": excludes, "bad_barcode": False}

    def _save_and_next(self):
        bc, decision = self._collect_decision()

        if not decision["bad_barcode"] and decision["assign"] is None:
            items = self._groups[self._index]["items"]
            has_exclude = bool(decision["exclude"])
            if not has_exclude:
                if not messagebox.askyesno(
                    "No decision",
                    "You haven't assigned the barcode to any item or marked it as bad.\n\n"
                    "Save with no barcode assignment (barcode will be removed from all items)?",
                    parent=self._root):
                    return

        self._progress[bc] = decision
        save_progress(self._progress)

        g = self._groups[self._index]
        items = g["items"]
        action_parts = []
        if decision["bad_barcode"]:
            action_parts.append("bad barcode")
        if decision["assign"]:
            action_parts.append(f"assigned to #{decision['assign']}")
        if decision["exclude"]:
            action_parts.append(f"excluding {', '.join(f'#{x}' for x in decision['exclude'])}")
        self._last_action_var.set(
            f"Saved: {bc} — {', '.join(action_parts) if action_parts else 'no barcode assignment'}")

        if self._index < len(self._groups) - 1:
            self._index += 1
        self._show_group()

    def _skip(self):
        if self._index < len(self._groups) - 1:
            self._index += 1
            self._show_group()

    def _prev(self):
        if self._index > 0:
            self._index -= 1
            self._show_group()

    def _jump_to(self):
        txt = self._jump_var.get().strip()
        if not txt:
            return
        try:
            n = int(txt)
            if 1 <= n <= len(self._groups):
                self._index = n - 1
                self._show_group()
                return
        except ValueError:
            pass
        # Try matching by barcode
        for i, g in enumerate(self._groups):
            if g["barcode"] == txt:
                self._index = i
                self._show_group()
                return
        messagebox.showwarning("Not found", f"No group matching '{txt}'", parent=self._root)

    def _update_status(self):
        decided = sum(1 for g in self._groups if g["barcode"] in self._progress)
        total = len(self._groups)

        n_excludes = 0
        n_assigns = 0
        n_bad = 0
        for g in self._groups:
            d = self._progress.get(g["barcode"])
            if not d:
                continue
            n_excludes += len(d.get("exclude", []))
            if d.get("assign"):
                n_assigns += 1
            if d.get("bad_barcode"):
                n_bad += 1

        self._status_var.set(
            f"Decided: {decided}/{total}  |  "
            f"Pending: {n_excludes} excludes, {n_assigns} assignments, {n_bad} bad barcodes")
        self._progress_var.set(f"[{self._index + 1}/{total}]  Decided: {decided}/{total}")
        self._pbar["value"] = decided

    # --- Apply ---

    def _review_and_apply(self):
        decided = sum(1 for g in self._groups if g["barcode"] in self._progress)
        if decided == 0:
            messagebox.showinfo("Nothing to apply", "No decisions have been saved yet.",
                                parent=self._root)
            return

        changes = compute_changes(self._groups, self._progress)

        # Build summary text
        lines = []
        lines.append(f"=== CHANGES SUMMARY ===\n")

        if changes["excludes"]:
            lines.append(f"EXCLUDE FROM DB ({len(changes['excludes'])} items):")
            lines.append(f"  (Will be added to typos.json exclude list)")
            for e in sorted(changes["excludes"], key=lambda x: x["id"]):
                lines.append(f"  - {e['name']}")
            lines.append("")

        if changes["barcode_assigns"]:
            lines.append(f"BARCODE ASSIGNMENTS ({len(changes['barcode_assigns'])}):")
            ramen_db = {r["id"]: r for r in load_json(RAMEN_JSON, [])}
            for bc, winner_id in sorted(changes["barcode_assigns"].items()):
                r = ramen_db.get(winner_id)
                name = f"{r['brand']} — {r['variety']}" if r else "???"
                lines.append(f"  {bc} -> #{winner_id} {name}")
            lines.append("")

        if changes["bad_barcodes"]:
            lines.append(f"BAD BARCODES (removed from all items): {len(changes['bad_barcodes'])}")
            for bc in sorted(changes["bad_barcodes"]):
                lines.append(f"  {bc}")
            lines.append("")

        removals_count = sum(len(ids) for ids in changes["barcode_removals"].values())
        if removals_count:
            lines.append(f"BARCODE REMOVALS ({removals_count} removals across "
                         f"{len(changes['barcode_removals'])} barcodes)")
            lines.append("")

        summary = "\n".join(lines)

        # Show in a scrollable dialog
        dlg = tk.Toplevel(self._root)
        dlg.title("Review Changes Before Applying")
        dlg.configure(bg="#1a1a2e")
        dlg.geometry("700x550")
        dlg.transient(self._root)
        dlg.grab_set()

        tk.Label(dlg, text=f"Review all pending changes ({decided} decisions)",
                 font=("Segoe UI", 11, "bold"), fg="#f7d354", bg="#1a1a2e").pack(
            fill=tk.X, padx=10, pady=(10, 4))

        txt_frame = tk.Frame(dlg, bg="#1a1a2e")
        txt_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        scrollbar = tk.Scrollbar(txt_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        txt = tk.Text(txt_frame, font=("Consolas", 9), bg="#16213e", fg="#e0e0e0",
                      yscrollcommand=scrollbar.set, wrap=tk.WORD, state=tk.NORMAL)
        txt.insert("1.0", summary)
        txt.configure(state=tk.DISABLED)
        txt.pack(fill=tk.BOTH, expand=True)
        scrollbar.config(command=txt.yview)

        btn_frame = tk.Frame(dlg, bg="#1a1a2e")
        btn_frame.pack(fill=tk.X, padx=10, pady=(4, 10))

        def do_apply():
            n_ex, n_assign, n_bad = apply_changes(changes)
            # Clear applied decisions from progress
            resolved_barcodes = (set(changes["barcode_assigns"].keys())
                                 | changes["bad_barcodes"]
                                 | set(changes["barcode_removals"].keys()))
            for bc in resolved_barcodes:
                self._progress.pop(bc, None)
            save_progress(self._progress)

            dlg.destroy()
            messagebox.showinfo(
                "Applied",
                f"Changes applied successfully!\n\n"
                f"  {n_ex} items excluded\n"
                f"  {n_assign} barcodes reassigned\n"
                f"  {n_bad} bad barcodes removed\n\n"
                f"Reload the tool to see updated conflict groups.",
                parent=self._root)

        tk.Button(btn_frame, text="Cancel", command=dlg.destroy,
                  font=("Segoe UI", 10), bg="#16213e", fg="#e0e0e0",
                  activebackground="#0f3460", activeforeground="#f7d354",
                  width=10).pack(side=tk.LEFT, padx=4)
        tk.Button(btn_frame, text="APPLY CHANGES", command=do_apply,
                  font=("Segoe UI", 10, "bold"), bg="#8b4513", fg="#e0e0e0",
                  activebackground="#a0522d", activeforeground="#fff",
                  width=18).pack(side=tk.RIGHT, padx=4)

    def run(self):
        self._root.mainloop()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if not RAMEN_JSON.exists():
        print(f"Error: {RAMEN_JSON} not found. Run fetch_ramen_data.py first.")
        sys.exit(1)

    print("Building conflict groups...")
    groups = build_conflict_groups()
    print(f"  {len(groups)} barcode conflicts found across "
          f"{sum(len(g['items']) for g in groups)} ramen items")

    progress = load_progress()
    decided = sum(1 for g in groups if g["barcode"] in progress)
    if decided:
        print(f"  {decided} already decided (from previous session)")

    if not groups:
        print("No barcode conflicts found!")
        sys.exit(0)

    app = ReviewApp(groups)
    app.run()


if __name__ == "__main__":
    main()
