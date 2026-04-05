#!/usr/bin/env python3
"""
Typos.json Explorer — unified management tool for typos.json

Tabbed Tkinter interface for managing all sections of typos.json:
  - Duplicates: barcode conflict review (absorbs review_duplicates.py)
  - Excluded: mark ramen as excluded from the database
  - Renames: per-item field overrides
  - Corrections: brand/country/style/text typo maps
  - Summary: read-only overview and raw JSON export

Usage:
    python typos_explorer.py
"""

import json
import sys
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
from difflib import SequenceMatcher

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
BG = "#1a1a2e"
BG_CARD = "#16213e"
BG_HEADER = "#0f3460"
FG = "#e0e0e0"
FG_DIM = "#a0a0a0"
YELLOW = "#f7d354"
RED = "#e74c3c"
GREEN = "#6abf69"
BLUE = "#88bbff"


# =========================================================================
# Data layer
# =========================================================================

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


_ramen_cache = None
_urls_cache = None


def invalidate_caches():
    global _ramen_cache, _urls_cache
    _ramen_cache = None
    _urls_cache = None


def get_ramen_db():
    global _ramen_cache
    if _ramen_cache is None:
        _ramen_cache = {r["id"]: r for r in load_json(RAMEN_JSON, [])}
    return _ramen_cache


def get_ramen_list():
    return list(get_ramen_db().values())


def get_urls():
    global _urls_cache
    if _urls_cache is None:
        _urls_cache = load_json(URLS_JSON, {})
    return _urls_cache


def ramen_url(rid):
    urls = get_urls()
    direct = urls.get(str(rid))
    if direct:
        return direct
    return f"https://www.theramenrater.com/?s=%23{rid}%3A"


def ramen_label(rid):
    r = get_ramen_db().get(rid)
    if r:
        return f"#{rid} {r['brand']} — {r['variety']}"
    return f"#{rid} (not in DB)"


def load_typos():
    return load_json(TYPOS_JSON, {})


def save_typos(typos):
    save_json(TYPOS_JSON, typos)


# ---- Fuzzy search (matches fetch_barcodes.py algorithm) ----

def fuzzy_search(query, limit=40):
    q = (query or "").strip()
    if not q:
        return []
    ramen_list = get_ramen_list()

    if q.isdigit():
        rid = int(q)
        for r in ramen_list:
            if r.get("id") == rid:
                return [r]
        return []

    q_fold = q.casefold()
    q_words = q_fold.split()
    scored = []
    for r in ramen_list:
        brand = str(r.get("brand") or "")
        variety = str(r.get("variety") or "")
        country = str(r.get("country") or "")
        style = str(r.get("style") or "")
        hay = f"{brand} {variety} {country} {style}"
        hay_fold = hay.casefold()

        matched_words = sum(1 for w in q_words if w in hay_fold)
        word_ratio = matched_words / len(q_words) if q_words else 0

        if word_ratio == 1.0:
            coverage = len(q_fold) / len(hay_fold) if hay_fold else 0
            score = 85.0 + 15.0 * coverage
        elif word_ratio > 0:
            score = 60.0 + 24.0 * word_ratio
        else:
            score = SequenceMatcher(None, q_fold, hay_fold).ratio() * 100

        scored.append((score, r))

    scored.sort(key=lambda x: (-x[0], x[1].get("id", 0)))
    return [r for s, r in scored[:limit] if s >= 45]


# ---- Thumbnail loader ----

_photo_refs = {}


def load_thumbnail(label, rid, size=100):
    img_path = IMAGES_DIR / f"{rid}.webp"
    if not img_path.exists():
        label.configure(image="", text="No img", fg="#666",
                        font=("Segoe UI", 8), width=size // 10, height=size // 18)
        return
    try:
        from PIL import Image, ImageTk
        pil = Image.open(img_path)
        pil.thumbnail((size, size))
        photo = ImageTk.PhotoImage(pil)
        _photo_refs[rid] = photo
        label.configure(image=photo, text="", width=size, height=size)
    except ImportError:
        label.configure(image="", text="(Pillow)", fg="#666",
                        font=("Segoe UI", 8), width=size // 10, height=size // 18)
    except Exception:
        label.configure(image="", text="Err", fg="#666",
                        font=("Segoe UI", 8), width=size // 10, height=size // 18)


# ---- Conflict groups (from review_duplicates.py) ----

def auto_resolve_singles():
    """Find barcodes with exactly 1 active item, assign barcode, clean duplicates.json.
    Returns list of log messages for what was done."""
    barcode_list = load_json(BARCODES_JSON, [])
    dupes = load_json(DUPES_JSON, [])
    typos = load_typos()
    excluded_ids = set(typos.get("exclude", []))
    ramen_db = get_ramen_db()

    bc_to_ids = {}
    for entry in barcode_list:
        rid = entry["id"]
        for bc in entry.get("barcodes", []):
            bc = str(bc).strip()
            if bc:
                bc_to_ids.setdefault(bc, set()).add(rid)
    for d in dupes:
        bc = str(d["barcode"]).strip()
        for did in (d["id"], d["existing_id"]):
            bc_to_ids.setdefault(bc, set()).add(did)

    logs = []
    barcodes_dirty = False
    dupes_dirty = False

    for bc, all_ids in bc_to_ids.items():
        active_ids = {rid for rid in all_ids if rid not in excluded_ids}
        if len(active_ids) != 1 or len(all_ids) < 2:
            continue

        winner = next(iter(active_ids))
        r = ramen_db.get(winner)
        name = f"#{winner} {r['brand']} — {r['variety']}" if r else f"#{winner}"

        ent = next((e for e in barcode_list if e["id"] == winner), None)
        if ent:
            existing = [str(c) for c in ent.get("barcodes", [])]
            if bc not in existing:
                ent.setdefault("barcodes", []).append(bc)
                barcodes_dirty = True
        else:
            barcode_list.append({"id": winner, "barcodes": [bc]})
            barcodes_dirty = True

        excluded_in_group = all_ids - active_ids
        for eid in excluded_in_group:
            ex_ent = next((e for e in barcode_list if e["id"] == eid), None)
            if ex_ent and bc in [str(c) for c in ex_ent.get("barcodes", [])]:
                ex_ent["barcodes"] = [c for c in ex_ent["barcodes"]
                                      if str(c) != bc]
                barcodes_dirty = True

        before = len(dupes)
        dupes = [d for d in dupes if str(d["barcode"]).strip() != bc]
        removed = before - len(dupes)
        if removed:
            dupes_dirty = True

        logs.append(f"Auto-resolved: {bc} -> {name}"
                    + (f", {removed} duplicates.json entries removed" if removed else ""))

    if barcodes_dirty:
        barcode_list = [e for e in barcode_list if e.get("barcodes")]
        barcode_list.sort(key=lambda e: e.get("id", 0))
        save_json(BARCODES_JSON, barcode_list)
    if dupes_dirty:
        save_json(DUPES_JSON, dupes)

    return logs


def build_conflict_groups():
    barcode_list = load_json(BARCODES_JSON, [])
    dupes = load_json(DUPES_JSON, [])
    ramen_db = get_ramen_db()
    urls = get_urls()

    typos = load_typos()
    excluded_ids = set(typos.get("exclude", []))

    id_to_barcodes = {}
    for entry in barcode_list:
        rid = entry["id"]
        for bc in entry.get("barcodes", []):
            bc = str(bc).strip()
            if bc:
                id_to_barcodes.setdefault(rid, set()).add(bc)

    js_winner = {}
    for entry in sorted(barcode_list, key=lambda e: e.get("id", 0)):
        for bc in entry.get("barcodes", []):
            bc = str(bc).strip()
            if bc:
                js_winner[bc] = entry["id"]

    bc_to_ids = {}
    bc_id_from_barcodes = {}
    bc_id_from_dupes = {}

    for entry in barcode_list:
        rid = entry["id"]
        for bc in entry.get("barcodes", []):
            bc = str(bc).strip()
            if bc:
                bc_to_ids.setdefault(bc, set()).add(rid)
                bc_id_from_barcodes.setdefault(bc, set()).add(rid)

    for d in dupes:
        bc = str(d["barcode"]).strip()
        for did in (d["id"], d["existing_id"]):
            bc_to_ids.setdefault(bc, set()).add(did)
            bc_id_from_dupes.setdefault(bc, set()).add(did)

    groups = []
    for bc, all_ids in bc_to_ids.items():
        active_ids = {rid for rid in all_ids if rid not in excluded_ids}
        if len(active_ids) < 2:
            continue
        items = []
        for rid in sorted(all_ids):
            r = ramen_db.get(rid)
            in_bc = rid in bc_id_from_barcodes.get(bc, set())
            in_dupes = rid in bc_id_from_dupes.get(bc, set())
            if in_bc and in_dupes:
                source = "both"
            elif in_bc:
                source = "barcodes.json"
            else:
                source = "duplicates.json"

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
                "in_barcodes_json": in_bc,
                "is_js_winner": js_winner.get(bc) == rid,
                "in_ramen_db": r is not None,
                "url": url,
                "source": source,
                "excluded": rid in excluded_ids,
            })
        groups.append({"barcode": bc, "items": items})

    groups.sort(key=lambda g: (-len(g["items"]), g["barcode"]))
    return groups


def compute_dupe_changes(groups, progress):
    excludes = []
    barcode_assigns = {}
    bad_barcodes = set()
    ramen_db = get_ramen_db()

    for g in groups:
        bc = g["barcode"]
        decision = progress.get(bc)
        if not decision:
            continue
        if decision.get("bad_barcode"):
            bad_barcodes.add(bc)
            continue
        assign_id = decision.get("assign")
        for did in decision.get("exclude", []):
            r = ramen_db.get(did)
            name = f"#{did} {r['brand']} — {r['variety']}" if r else f"#{did} (not in DB)"
            excludes.append({"id": did, "name": name})
        if assign_id:
            barcode_assigns[bc] = assign_id

    return {
        "excludes": excludes,
        "barcode_assigns": barcode_assigns,
        "bad_barcodes": bad_barcodes,
    }


def apply_dupe_changes(changes):
    typos = load_typos()

    exc_list = typos.get("exclude", [])
    new_exc_ids = {e["id"] for e in changes["excludes"]}
    for eid in new_exc_ids:
        if eid not in exc_list:
            exc_list.append(eid)
    typos["exclude"] = sorted(exc_list)

    save_typos(typos)

    barcode_list = load_json(BARCODES_JSON, [])
    all_remove = {}
    for bc in changes["bad_barcodes"]:
        for entry in barcode_list:
            if bc in [str(c) for c in entry.get("barcodes", [])]:
                all_remove.setdefault(entry["id"], set()).add(bc)
    for mid in new_exc_ids:
        for entry in barcode_list:
            if entry["id"] == mid:
                for bc in list(entry.get("barcodes", [])):
                    all_remove.setdefault(mid, set()).add(str(bc))
    for entry in barcode_list:
        rid = entry["id"]
        removals = all_remove.get(rid, set())
        if removals:
            entry["barcodes"] = [c for c in entry.get("barcodes", [])
                                 if str(c) not in removals]
    for bc, winner_id in changes["barcode_assigns"].items():
        winner_entry = next((e for e in barcode_list if e["id"] == winner_id), None)
        if winner_entry:
            codes = winner_entry.setdefault("barcodes", [])
            if bc not in [str(c) for c in codes]:
                codes.append(bc)
        else:
            barcode_list.append({"id": winner_id, "barcodes": [bc]})
    barcode_list = [e for e in barcode_list if e.get("barcodes")]
    barcode_list.sort(key=lambda e: e.get("id", 0))
    save_json(BARCODES_JSON, barcode_list)

    all_excluded = set(typos.get("exclude", []))
    dupes = load_json(DUPES_JSON, [])
    before_count = len(dupes)
    dupes = [d for d in dupes
             if d["id"] not in all_excluded
             and d["existing_id"] not in all_excluded]
    removed_from_dupes = before_count - len(dupes)
    save_json(DUPES_JSON, dupes)

    return (len(new_exc_ids),
            len(changes["barcode_assigns"]), len(changes["bad_barcodes"]),
            removed_from_dupes)


# =========================================================================
# Shared UI helpers
# =========================================================================

def make_scrollable(parent, bg=BG):
    container = tk.Frame(parent, bg=bg)
    canvas = tk.Canvas(container, bg=bg, highlightthickness=0)
    scrollbar = tk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
    inner = tk.Frame(canvas, bg=bg)
    inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)
    canvas.bind("<Configure>", lambda e: canvas.itemconfig(win_id, width=e.width))

    def _wheel(e):
        canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
    canvas.bind_all("<MouseWheel>", _wheel, add="+")

    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    return container, inner, canvas


def make_btn(parent, text, command, bold=False, bg=BG_CARD, fg=FG, width=None):
    font = ("Segoe UI", 9, "bold") if bold else ("Segoe UI", 9)
    kw = {}
    if width:
        kw["width"] = width
    return tk.Button(parent, text=text, command=command, font=font,
                     bg=bg, fg=fg, activebackground=BG_HEADER,
                     activeforeground=YELLOW, **kw)


# =========================================================================
# Tab: Duplicates
# =========================================================================

class DuplicatesTab:
    def __init__(self, parent, root):
        self._root = root
        self._frame = tk.Frame(parent, bg=BG)
        self._groups = build_conflict_groups()
        self._index = 0
        self._photos = {}
        self._item_widgets = []
        self._build()
        if self._groups:
            self._show_group()

    @property
    def widget(self):
        return self._frame

    def _log(self, msg):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_text.config(state=tk.NORMAL)
        self._log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self._log_text.see(tk.END)
        self._log_text.config(state=tk.DISABLED)

    def _refresh_data(self, target_barcode=None):
        invalidate_caches()
        resolve_logs = auto_resolve_singles()
        for msg in resolve_logs:
            self._log(msg)
        if resolve_logs:
            invalidate_caches()
        self._groups = build_conflict_groups()
        self._pbar.configure(maximum=max(len(self._groups), 1))
        if target_barcode:
            found = next((i for i, g in enumerate(self._groups)
                          if g["barcode"] == target_barcode), None)
            if found is not None:
                self._index = found
            elif self._index >= len(self._groups):
                self._index = max(0, len(self._groups) - 1)
        elif self._index >= len(self._groups):
            self._index = max(0, len(self._groups) - 1)
        if self._groups:
            self._show_group()
        else:
            for w in self._scroll_inner.winfo_children():
                w.destroy()
            self._barcode_var.set("No barcode conflicts found.")
            self._winner_var.set("")
            self._status_var.set("All clear!")
            self._progress_var.set("")
            self._pbar["value"] = 0

    def _build(self):
        f = self._frame

        hdr = tk.Frame(f, bg=BG_HEADER, padx=10, pady=4)
        hdr.pack(fill=tk.X)
        self._title_var = tk.StringVar(value="Barcode Conflict Review")
        tk.Label(hdr, textvariable=self._title_var, font=("Segoe UI", 11, "bold"),
                 fg=YELLOW, bg=BG_HEADER).pack(side=tk.LEFT)
        self._progress_var = tk.StringVar()
        tk.Label(hdr, textvariable=self._progress_var, font=("Segoe UI", 9),
                 fg=FG, bg=BG_HEADER).pack(side=tk.RIGHT)
        make_btn(hdr, "Refresh", self._refresh_data, bg=BG_HEADER).pack(
            side=tk.RIGHT, padx=(0, 8))

        self._pbar = ttk.Progressbar(f, length=200, mode="determinate",
                                     maximum=max(len(self._groups), 1))
        self._pbar.pack(fill=tk.X, padx=10, pady=(4, 0))

        info = tk.Frame(f, bg=BG, padx=10, pady=4)
        info.pack(fill=tk.X)
        self._barcode_var = tk.StringVar()
        tk.Label(info, textvariable=self._barcode_var, font=("Consolas", 10),
                 fg=FG, bg=BG).pack(side=tk.LEFT)
        self._winner_var = tk.StringVar()
        tk.Label(info, textvariable=self._winner_var, font=("Segoe UI", 9),
                 fg=FG_DIM, bg=BG).pack(side=tk.RIGHT)

        self._scroll_container, self._scroll_inner, self._canvas = make_scrollable(f)
        self._scroll_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 0))

        bad_frame = tk.Frame(f, bg=BG, padx=10)
        bad_frame.pack(fill=tk.X, pady=(4, 2))
        self._bad_var = tk.BooleanVar()
        tk.Checkbutton(bad_frame, text="Bad barcode — remove from all items",
                       variable=self._bad_var, command=self._on_bad_toggle,
                       font=("Segoe UI", 9, "bold"), fg=RED, bg=BG,
                       selectcolor=BG_CARD, activebackground=BG,
                       activeforeground=RED).pack(side=tk.LEFT)

        tk.Frame(f, bg="#333", height=1).pack(fill=tk.X, padx=10, pady=(4, 2))

        nav = tk.Frame(f, bg=BG, padx=10, pady=4)
        nav.pack(fill=tk.X)
        self._prev_btn = make_btn(nav, "<< Prev", self._prev, width=10)
        self._prev_btn.pack(side=tk.LEFT, padx=2)
        make_btn(nav, "Skip", self._skip, width=8).pack(side=tk.LEFT, padx=2)
        make_btn(nav, "Save & Next >>", self._save_next, bold=True,
                 bg="#2a6041", width=14).pack(side=tk.LEFT, padx=2)

        jf = tk.Frame(nav, bg=BG)
        jf.pack(side=tk.RIGHT)
        tk.Label(jf, text="Go to:", font=("Segoe UI", 9), fg=FG_DIM, bg=BG).pack(
            side=tk.LEFT, padx=(0, 4))
        self._jump_var = tk.StringVar()
        je = tk.Entry(jf, textvariable=self._jump_var, width=6, font=("Segoe UI", 9),
                      bg=BG_CARD, fg=FG, insertbackground=FG)
        je.pack(side=tk.LEFT)
        je.bind("<Return>", lambda e: self._jump_to())
        make_btn(jf, "Go", self._jump_to).pack(side=tk.LEFT, padx=2)

        bottom = tk.Frame(f, bg=BG, padx=10, pady=4)
        bottom.pack(fill=tk.X)
        self._status_var = tk.StringVar()
        tk.Label(bottom, textvariable=self._status_var, font=("Segoe UI", 9),
                 fg=FG_DIM, bg=BG).pack(side=tk.LEFT)

        log_frame = tk.Frame(f, bg=BG, padx=10)
        log_frame.pack(fill=tk.X, pady=(4, 4))
        tk.Label(log_frame, text="Change log:", font=("Segoe UI", 9, "bold"),
                 fg=FG_DIM, bg=BG).pack(anchor="w")
        self._log_text = tk.Text(log_frame, height=5, wrap=tk.WORD,
                                 font=("Consolas", 9), bg="#1a1a1a", fg=GREEN,
                                 insertbackground=GREEN, state=tk.DISABLED,
                                 relief=tk.SUNKEN, bd=1)
        self._log_text.pack(fill=tk.X)
        log_sb = tk.Scrollbar(self._log_text, command=self._log_text.yview)
        log_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._log_text.config(yscrollcommand=log_sb.set)

        if not self._groups:
            self._barcode_var.set("No barcode conflicts found.")
            self._status_var.set("All clear!")

    def _show_group(self):
        if not self._groups:
            return
        g = self._groups[self._index]
        bc = g["barcode"]
        items = g["items"]
        total = len(self._groups)

        self._progress_var.set(f"[{self._index + 1}/{total}]")
        self._barcode_var.set(f"Barcode: {bc}")

        js_w = next((it for it in items if it["is_js_winner"]), None)
        self._winner_var.set(
            f"JS winner: #{js_w['id']}" if js_w else "No JS winner")

        self._prev_btn.config(state=tk.NORMAL if self._index > 0 else tk.DISABLED)

        for w in self._scroll_inner.winfo_children():
            w.destroy()
        self._item_widgets = []
        self._photos.clear()

        self._bad_var.set(False)
        self._assign_var = tk.IntVar(value=0)

        for item in items:
            self._build_card(item, False)

        self._update_status()
        self._canvas.yview_moveto(0)

    def _build_card(self, item, is_bad):
        rid = item["id"]
        excluded = item.get("excluded", False)
        source = item.get("source", "")

        card_bg = "#2a2a2a" if excluded else BG_CARD
        name_fg = "#777" if excluded else YELLOW
        detail_fg = "#555" if excluded else FG_DIM

        card = tk.Frame(self._scroll_inner, bg=card_bg, padx=8, pady=6,
                        relief=tk.RIDGE, bd=1)
        card.pack(fill=tk.X, padx=4, pady=3)

        img_lbl = tk.Label(card, bg=card_bg, width=100, height=100)
        img_lbl.grid(row=0, column=0, rowspan=3, padx=(0, 8), sticky="n")
        load_thumbnail(img_lbl, rid, 100)

        info = tk.Frame(card, bg=card_bg)
        info.grid(row=0, column=1, sticky="nw")

        id_text = f"#{rid}"
        if item["is_js_winner"]:
            id_text += "  << JS WINNER"
        if excluded:
            id_text += "  [EXCLUDED]"
        id_lbl = tk.Label(info, text=id_text, font=("Segoe UI", 9, "underline"),
                          fg=("#cc4444" if excluded else BLUE), bg=card_bg,
                          cursor="hand2")
        id_lbl.pack(anchor="w")
        id_lbl.bind("<Button-1>", lambda e, u=item["url"]: webbrowser.open(u))

        tk.Label(info, text=f"{item['brand']} — {item['variety']}",
                 font=("Segoe UI", 10, "bold"), fg=name_fg, bg=card_bg,
                 wraplength=440, justify=tk.LEFT).pack(anchor="w")

        detail = f"{item['style']}  |  {item['country']}  |  {item['stars']}*"
        detail += f"  |  [{source}]"
        if not item["in_ramen_db"]:
            detail += "  |  NOT IN DB"
        tk.Label(info, text=detail, font=("Segoe UI", 9),
                 fg=detail_fg, bg=card_bg).pack(anchor="w")

        actions = tk.Frame(card, bg=card_bg)
        actions.grid(row=1, column=1, sticky="w", pady=(4, 0))

        rb = tk.Radiobutton(actions, text="Assign barcode", variable=self._assign_var,
                            value=rid, font=("Segoe UI", 9), fg=FG, bg=card_bg,
                            selectcolor=BG_HEADER, activebackground=card_bg,
                            activeforeground=YELLOW)
        rb.pack(side=tk.LEFT, padx=(0, 10))
        if is_bad or excluded:
            rb.config(state=tk.DISABLED)

        exc_var = tk.BooleanVar(value=False)
        exc_cb = tk.Checkbutton(actions, text="Exclude", variable=exc_var,
                                font=("Segoe UI", 9), fg=RED, bg=card_bg,
                                selectcolor=BG_HEADER, activebackground=card_bg,
                                activeforeground=RED)
        exc_cb.pack(side=tk.LEFT, padx=(0, 10))
        if excluded:
            exc_cb.config(state=tk.DISABLED)

        make_btn(actions, "View Review",
                 lambda u=item["url"]: webbrowser.open(u), bg=card_bg).pack(
                     side=tk.LEFT)
        make_btn(actions, "Edit Barcodes",
                 lambda r=rid, b=item["brand"], v=item["variety"]:
                 self._open_barcode_editor(r, b, v,
                     self._groups[self._index]["barcode"]),
                 bg=card_bg).pack(side=tk.LEFT, padx=(6, 0))

        self._item_widgets.append({
            "id": rid, "radio": rb,
            "exc_var": exc_var,
            "excluded": excluded,
        })
        card.columnconfigure(1, weight=1)

    def _open_barcode_editor(self, rid, brand, variety, group_barcode=""):
        dlg = tk.Toplevel(self._root)
        dlg.title(f"Edit Barcodes — #{rid}")
        dlg.configure(bg=BG)
        dlg.geometry("420x340")
        dlg.transient(self._root)
        dlg.grab_set()

        tk.Label(dlg, text=f"#{rid}  {brand} — {variety}",
                 font=("Segoe UI", 10, "bold"), fg=YELLOW, bg=BG,
                 wraplength=390).pack(padx=10, pady=(10, 4), anchor="w")
        if group_barcode:
            tk.Label(dlg, text=f"Conflict barcode: {group_barcode}",
                     font=("Consolas", 9), fg=FG_DIM, bg=BG).pack(
                         padx=10, anchor="w")

        DUPES_SUFFIX = "  [duplicates.json]"

        def _read_barcodes():
            bl = load_json(BARCODES_JSON, [])
            ent = next((e for e in bl if e["id"] == rid), None)
            return [str(c) for c in ent.get("barcodes", [])] if ent else []

        def _read_dupes_barcodes():
            bc_set = set(_read_barcodes())
            dupes = load_json(DUPES_JSON, [])
            out = set()
            for d in dupes:
                if d["id"] == rid or d["existing_id"] == rid:
                    bc = str(d["barcode"]).strip()
                    if bc and bc not in bc_set:
                        out.add(bc)
            return sorted(out)

        list_frame = tk.Frame(dlg, bg=BG)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        lb = tk.Listbox(list_frame, font=("Consolas", 10), bg=BG_CARD, fg=FG,
                        selectbackground=BLUE, selectforeground=FG, height=8)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb = tk.Scrollbar(list_frame, command=lb.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb.configure(yscrollcommand=sb.set)

        def _populate():
            lb.delete(0, tk.END)
            for bc in _read_barcodes():
                lb.insert(tk.END, bc)
            for bc in _read_dupes_barcodes():
                lb.insert(tk.END, f"{bc}{DUPES_SUFFIX}")

        _populate()

        add_frame = tk.Frame(dlg, bg=BG)
        add_frame.pack(fill=tk.X, padx=10, pady=4)
        prefill = group_barcode if group_barcode not in _read_barcodes() else ""
        bc_var = tk.StringVar(value=prefill)
        bc_entry = tk.Entry(add_frame, textvariable=bc_var, font=("Consolas", 10),
                            bg=BG_CARD, fg=FG, insertbackground=FG, width=20)
        bc_entry.pack(side=tk.LEFT, padx=(0, 6))
        status_var = tk.StringVar()
        tk.Label(dlg, textvariable=status_var, font=("Segoe UI", 9),
                 fg=GREEN, bg=BG).pack(padx=10, anchor="w")

        def _add():
            bc = bc_var.get().strip()
            if not bc:
                return
            bl = load_json(BARCODES_JSON, [])
            ent = next((e for e in bl if e["id"] == rid), None)
            if ent:
                existing = [str(c) for c in ent.get("barcodes", [])]
                if bc in existing:
                    status_var.set(f"Already has {bc}")
                    return
                ent.setdefault("barcodes", []).append(bc)
            else:
                bl.append({"id": rid, "barcodes": [bc]})
            bl.sort(key=lambda e: e.get("id", 0))
            save_json(BARCODES_JSON, bl)
            bc_var.set("")
            _populate()
            status_var.set(f"Added {bc}")
            self._log(f"Edit: added {bc} to #{rid}")

        def _remove():
            sel = lb.curselection()
            if not sel:
                return
            raw = lb.get(sel[0])
            is_dupes_only = raw.endswith(DUPES_SUFFIX)
            bc = raw.replace(DUPES_SUFFIX, "").strip() if is_dupes_only else raw

            if is_dupes_only:
                dupes = load_json(DUPES_JSON, [])
                before = len(dupes)
                dupes = [d for d in dupes
                         if not (str(d["barcode"]).strip() == bc
                                 and (d["id"] == rid or d["existing_id"] == rid))]
                if len(dupes) < before:
                    save_json(DUPES_JSON, dupes)
                _populate()
                status_var.set(f"Removed {bc} (duplicates.json)")
                self._log(f"Edit: removed {bc} from #{rid} (duplicates.json)")
                return

            current = _read_barcodes()
            if len(current) <= 1:
                messagebox.showwarning(
                    "Last barcode",
                    f"This is the only barcode for #{rid}.\n\n"
                    "Add a replacement barcode before removing it.",
                    parent=dlg)
                return

            bl = load_json(BARCODES_JSON, [])
            ent = next((e for e in bl if e["id"] == rid), None)
            if ent:
                ent["barcodes"] = [c for c in ent.get("barcodes", [])
                                   if str(c) != bc]
                if not ent["barcodes"]:
                    bl = [e for e in bl if e["id"] != rid]
            save_json(BARCODES_JSON, bl)

            dupes = load_json(DUPES_JSON, [])
            before = len(dupes)
            dupes = [d for d in dupes
                     if not (str(d["barcode"]).strip() == bc
                             and (d["id"] == rid or d["existing_id"] == rid))]
            if len(dupes) < before:
                save_json(DUPES_JSON, dupes)

            _populate()
            status_var.set(f"Removed {bc}")
            self._log(f"Edit: removed {bc} from #{rid}")

        make_btn(add_frame, "Add", _add, bold=True, bg="#2a6041").pack(
            side=tk.LEFT, padx=(0, 6))
        make_btn(add_frame, "Remove Selected", _remove, fg=RED).pack(side=tk.LEFT)
        bc_entry.bind("<Return>", lambda e: _add())

        btn_frame = tk.Frame(dlg, bg=BG)
        btn_frame.pack(fill=tk.X, padx=10, pady=(4, 10))
        make_btn(btn_frame, "Done", dlg.destroy, bold=True).pack(side=tk.RIGHT)

        dlg.protocol("WM_DELETE_WINDOW", dlg.destroy)
        dlg.bind("<Destroy>",
                 lambda e: self._refresh_data(target_barcode=group_barcode)
                 if e.widget is dlg else None)

    def _on_bad_toggle(self):
        is_bad = self._bad_var.get()
        for w in self._item_widgets:
            if w.get("excluded"):
                continue
            w["radio"].config(state=tk.DISABLED if is_bad else tk.NORMAL)
            if is_bad:
                self._assign_var.set(0)

    def _collect(self):
        g = self._groups[self._index]
        bc = g["barcode"]
        if self._bad_var.get():
            return bc, {"bad_barcode": True, "assign": None, "exclude": []}
        assign = self._assign_var.get() or None
        excludes = [w["id"] for w in self._item_widgets if w["exc_var"].get()]
        return bc, {"assign": assign, "exclude": excludes, "bad_barcode": False}

    def _save_next(self):
        bc, dec = self._collect()
        has_marks = bool(dec["exclude"])
        if not dec["bad_barcode"] and dec["assign"] is None and not has_marks:
            if not messagebox.askyesno(
                    "No decision",
                    "No barcode assigned, no excludes, not marked bad.\n\n"
                    "Save with no assignment (barcode removed from all)?",
                    parent=self._root):
                return

        g = self._groups[self._index]
        single_progress = {bc: dec}
        changes = compute_dupe_changes([g], single_progress)
        n_exc, n_a, n_b, n_dr = apply_dupe_changes(changes)

        parts = []
        if dec["bad_barcode"]:
            parts.append("bad barcode")
        if dec["assign"]:
            parts.append(f"assigned to #{dec['assign']}")
        if dec["exclude"]:
            parts.append(f"excluded: {', '.join(f'#{x}' for x in dec['exclude'])}")
        if n_dr:
            parts.append(f"{n_dr} removed from duplicates.json")

        excluded_set = set(dec.get("exclude", []))
        remaining = [it for it in g["items"]
                     if not it.get("excluded") and it["id"] not in excluded_set]
        if len(remaining) == 1 and not dec.get("assign"):
            parts.append(f"barcode stays with #{remaining[0]['id']}")

        self._log(f"{bc} — {', '.join(parts) or 'no assignment'}")

        self._refresh_data()

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
        for i, g in enumerate(self._groups):
            if g["barcode"] == txt:
                self._index = i
                self._show_group()
                return
        messagebox.showwarning("Not found", f"No group matching '{txt}'",
                               parent=self._root)

    def _update_status(self):
        total = len(self._groups)
        self._status_var.set(f"{total} conflict groups remaining")
        self._progress_var.set(f"[{self._index + 1}/{total}]")
        self._pbar["value"] = 0
        self._pbar.configure(maximum=max(total, 1))



# =========================================================================
# Tab: Discontinued
# =========================================================================

class DiscontinuedTab:
    def __init__(self, parent, root):
        self._root = root
        self._frame = tk.Frame(parent, bg=BG)
        self._build()

    @property
    def widget(self):
        return self._frame

    def _build(self):
        f = self._frame

        hdr = tk.Frame(f, bg=BG_HEADER, padx=10, pady=4)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Excluded Ramen", font=("Segoe UI", 11, "bold"),
                 fg=YELLOW, bg=BG_HEADER).pack(side=tk.LEFT)
        self._count_var = tk.StringVar()
        tk.Label(hdr, textvariable=self._count_var, font=("Segoe UI", 9),
                 fg=FG, bg=BG_HEADER).pack(side=tk.RIGHT)

        # Current list
        list_frame = tk.Frame(f, bg=BG)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        sb = tk.Scrollbar(list_frame)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox = tk.Listbox(list_frame, font=("Consolas", 9), bg=BG_CARD, fg=FG,
                                   selectbackground=BG_HEADER, selectforeground=YELLOW,
                                   yscrollcommand=sb.set, activestyle="dotbox")
        self._listbox.pack(fill=tk.BOTH, expand=True)
        sb.config(command=self._listbox.yview)

        btn_row = tk.Frame(f, bg=BG, padx=10, pady=4)
        btn_row.pack(fill=tk.X)
        make_btn(btn_row, "Remove Selected", self._remove, fg=RED).pack(side=tk.LEFT, padx=2)
        make_btn(btn_row, "View Review", self._view_review).pack(side=tk.LEFT, padx=2)

        tk.Frame(f, bg="#333", height=1).pack(fill=tk.X, padx=10, pady=(6, 4))

        # Add via search
        tk.Label(f, text="Add excluded ramen (search):", font=("Segoe UI", 9, "bold"),
                 fg=FG, bg=BG).pack(fill=tk.X, padx=10, pady=(0, 2))

        sf = tk.Frame(f, bg=BG, padx=10)
        sf.pack(fill=tk.X)
        self._search_var = tk.StringVar()
        se = tk.Entry(sf, textvariable=self._search_var, font=("Segoe UI", 10),
                      bg=BG_CARD, fg=FG, insertbackground=FG)
        se.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        se.bind("<Return>", lambda e: self._do_search())
        make_btn(sf, "Search", self._do_search).pack(side=tk.LEFT)

        rf = tk.Frame(f, bg=BG, padx=10)
        rf.pack(fill=tk.BOTH, expand=False, pady=(4, 4))
        rsb = tk.Scrollbar(rf)
        rsb.pack(side=tk.RIGHT, fill=tk.Y)
        self._result_list = tk.Listbox(rf, height=6, font=("Consolas", 9), bg=BG_CARD, fg=FG,
                                       selectbackground=BG_HEADER, selectforeground=YELLOW,
                                       yscrollcommand=rsb.set, activestyle="dotbox")
        self._result_list.pack(fill=tk.BOTH, expand=True)
        rsb.config(command=self._result_list.yview)
        self._search_ids = []

        abf = tk.Frame(f, bg=BG, padx=10)
        abf.pack(fill=tk.X, pady=(0, 8))
        make_btn(abf, "Add Selected as Excluded", self._add, bold=True,
                 bg="#2a6041").pack(side=tk.LEFT, padx=2)

        self._refresh()

    def _refresh(self):
        typos = load_typos()
        exc = typos.get("exclude", [])
        self._listbox.delete(0, tk.END)
        self._ids = list(exc)
        for rid in exc:
            self._listbox.insert(tk.END, ramen_label(rid))
        self._count_var.set(f"{len(exc)} items")

    def _remove(self):
        sel = self._listbox.curselection()
        if not sel:
            return
        rid = self._ids[sel[0]]
        name = ramen_label(rid)
        if not messagebox.askyesno("Confirm removal",
                                   f"Remove from exclude list?\n\n{name}",
                                   parent=self._root):
            return
        typos = load_typos()
        exc = typos.get("exclude", [])
        if rid in exc:
            exc.remove(rid)
        typos["exclude"] = exc
        save_typos(typos)
        self._refresh()

    def _view_review(self):
        sel = self._listbox.curselection()
        if not sel:
            return
        rid = self._ids[sel[0]]
        webbrowser.open(ramen_url(rid))

    def _do_search(self):
        results = fuzzy_search(self._search_var.get())
        self._result_list.delete(0, tk.END)
        self._search_ids = []
        typos = load_typos()
        already = set(typos.get("exclude", []))
        for r in results:
            rid = r["id"]
            tag = ""
            if rid in already:
                tag = "  [ALREADY EXCLUDED]"
            line = f"#{rid:5d}  {r['brand']} — {r['variety']}{tag}"
            self._result_list.insert(tk.END, line)
            self._search_ids.append(rid)

    def _add(self):
        sel = self._result_list.curselection()
        if not sel:
            return
        rid = self._search_ids[sel[0]]
        name = ramen_label(rid)
        typos = load_typos()
        already = set(typos.get("exclude", []))
        if rid in already:
            messagebox.showwarning("Already excluded",
                                   f"{name} is already excluded.",
                                   parent=self._root)
            return
        if not messagebox.askyesno("Confirm",
                                   f"Mark as excluded?\n\n{name}",
                                   parent=self._root):
            return
        exc = typos.get("exclude", [])
        exc.append(rid)
        typos["exclude"] = sorted(exc)
        save_typos(typos)
        self._refresh()


# =========================================================================
# Tab: Renames
# =========================================================================

class RenamesTab:
    def __init__(self, parent, root):
        self._root = root
        self._frame = tk.Frame(parent, bg=BG)
        self._build()

    @property
    def widget(self):
        return self._frame

    def _build(self):
        f = self._frame

        hdr = tk.Frame(f, bg=BG_HEADER, padx=10, pady=4)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Renames (per-item overrides)", font=("Segoe UI", 11, "bold"),
                 fg=YELLOW, bg=BG_HEADER).pack(side=tk.LEFT)
        self._count_var = tk.StringVar()
        tk.Label(hdr, textvariable=self._count_var, font=("Segoe UI", 9),
                 fg=FG, bg=BG_HEADER).pack(side=tk.RIGHT)

        list_frame = tk.Frame(f, bg=BG)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        sb = tk.Scrollbar(list_frame)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._listbox = tk.Listbox(list_frame, font=("Consolas", 9), bg=BG_CARD, fg=FG,
                                   selectbackground=BG_HEADER, selectforeground=YELLOW,
                                   yscrollcommand=sb.set, activestyle="dotbox")
        self._listbox.pack(fill=tk.BOTH, expand=True)
        sb.config(command=self._listbox.yview)

        btn_row = tk.Frame(f, bg=BG, padx=10, pady=4)
        btn_row.pack(fill=tk.X)
        make_btn(btn_row, "Edit Selected", self._edit).pack(side=tk.LEFT, padx=2)
        make_btn(btn_row, "Remove Selected", self._remove, fg=RED).pack(side=tk.LEFT, padx=2)
        make_btn(btn_row, "Add New Rename", self._add, bold=True,
                 bg="#2a6041").pack(side=tk.RIGHT, padx=2)

        self._refresh()

    def _refresh(self):
        typos = load_typos()
        renames = typos.get("rename", [])
        self._listbox.delete(0, tk.END)
        self._renames = list(renames)
        for r in renames:
            rid = r["id"]
            overrides = []
            for k, v in r.items():
                if k == "id":
                    continue
                field = k.replace("replace_", "")
                overrides.append(f"{field}={v}")
            label = ramen_label(rid)
            self._listbox.insert(tk.END, f"{label}  ->  {', '.join(overrides)}")
        self._count_var.set(f"{len(renames)} renames")

    def _remove(self):
        sel = self._listbox.curselection()
        if not sel:
            return
        entry = self._renames[sel[0]]
        name = ramen_label(entry["id"])
        if not messagebox.askyesno("Confirm removal",
                                   f"Remove rename for {name}?",
                                   parent=self._root):
            return
        typos = load_typos()
        renames = typos.get("rename", [])
        renames = [r for r in renames if r["id"] != entry["id"]]
        typos["rename"] = renames
        save_typos(typos)
        self._refresh()

    def _edit(self):
        sel = self._listbox.curselection()
        if not sel:
            return
        entry = self._renames[sel[0]]
        self._open_rename_dialog(entry)

    def _add(self):
        rid_str = simpledialog.askstring("Add Rename", "Enter ramen ID:",
                                         parent=self._root)
        if not rid_str:
            return
        try:
            rid = int(rid_str.strip().lstrip("#"))
        except ValueError:
            messagebox.showerror("Invalid", "Enter a numeric ramen ID.",
                                 parent=self._root)
            return
        if rid not in get_ramen_db():
            messagebox.showwarning("Not found", f"#{rid} not in ramen.json",
                                   parent=self._root)
            return
        typos = load_typos()
        existing = next((r for r in typos.get("rename", []) if r["id"] == rid), None)
        if existing:
            self._open_rename_dialog(existing)
        else:
            self._open_rename_dialog({"id": rid})

    def _open_rename_dialog(self, entry):
        rid = entry["id"]
        r = get_ramen_db().get(rid, {})

        dlg = tk.Toplevel(self._root)
        dlg.title(f"Rename #{rid}")
        dlg.configure(bg=BG)
        dlg.geometry("500x320")
        dlg.transient(self._root)
        dlg.grab_set()

        tk.Label(dlg, text=ramen_label(rid), font=("Segoe UI", 10, "bold"),
                 fg=YELLOW, bg=BG).pack(fill=tk.X, padx=10, pady=(10, 6))

        fields = [
            ("variety", r.get("variety", ""), entry.get("replace_variety", "")),
            ("brand", r.get("brand", ""), entry.get("replace_brand", "")),
            ("style", r.get("style", ""), entry.get("replace_style", "")),
            ("country", r.get("country", ""), entry.get("replace_country", "")),
            ("stars", str(r.get("stars", "")), str(entry.get("replace_stars", ""))),
        ]
        vars_ = {}
        for field, orig, override in fields:
            row = tk.Frame(dlg, bg=BG, padx=10)
            row.pack(fill=tk.X, pady=2)
            tk.Label(row, text=f"{field}:", font=("Segoe UI", 9, "bold"),
                     fg=FG, bg=BG, width=8, anchor="e").pack(side=tk.LEFT)
            tk.Label(row, text=f"({orig})", font=("Segoe UI", 8),
                     fg=FG_DIM, bg=BG).pack(side=tk.LEFT, padx=(4, 8))
            v = tk.StringVar(value=override)
            tk.Entry(row, textvariable=v, font=("Segoe UI", 9),
                     bg=BG_CARD, fg=FG, insertbackground=FG).pack(
                side=tk.LEFT, fill=tk.X, expand=True)
            vars_[field] = v

        tk.Label(dlg, text="Leave blank to keep original value.",
                 font=("Segoe UI", 8), fg=FG_DIM, bg=BG).pack(
            fill=tk.X, padx=10, pady=(6, 2))

        def save():
            new_entry = {"id": rid}
            for field, var in vars_.items():
                val = var.get().strip()
                if val:
                    key = f"replace_{field}"
                    if field == "stars":
                        try:
                            new_entry[key] = float(val)
                        except ValueError:
                            messagebox.showerror("Invalid", "Stars must be a number.",
                                                 parent=dlg)
                            return
                    else:
                        new_entry[key] = val

            if len(new_entry) == 1:
                messagebox.showwarning("Empty", "No overrides specified.",
                                       parent=dlg)
                return

            typos = load_typos()
            renames = typos.get("rename", [])
            renames = [r for r in renames if r["id"] != rid]
            renames.append(new_entry)
            renames.sort(key=lambda r: r["id"])
            typos["rename"] = renames
            save_typos(typos)
            dlg.destroy()
            self._refresh()

        bf = tk.Frame(dlg, bg=BG)
        bf.pack(fill=tk.X, padx=10, pady=(8, 10))
        make_btn(bf, "Cancel", dlg.destroy, width=10).pack(side=tk.LEFT, padx=4)
        make_btn(bf, "Save", save, bold=True, bg="#2a6041", width=10).pack(
            side=tk.RIGHT, padx=4)


# =========================================================================
# Tab: Corrections
# =========================================================================

class CorrectionsTab:
    SECTIONS = [
        ("country", "Country"),
        ("style", "Style"),
        ("brand", "Brand"),
        ("text", "Text (variety)"),
    ]

    def __init__(self, parent, root):
        self._root = root
        self._frame = tk.Frame(parent, bg=BG)
        self._build()

    @property
    def widget(self):
        return self._frame

    def _build(self):
        f = self._frame

        hdr = tk.Frame(f, bg=BG_HEADER, padx=10, pady=4)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="Corrections (typo maps)", font=("Segoe UI", 11, "bold"),
                 fg=YELLOW, bg=BG_HEADER).pack(side=tk.LEFT)
        self._count_var = tk.StringVar()
        tk.Label(hdr, textvariable=self._count_var, font=("Segoe UI", 9),
                 fg=FG, bg=BG_HEADER).pack(side=tk.RIGHT)

        # Sub-tabs for each correction category
        self._notebook = ttk.Notebook(f)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        self._sub_tabs = {}
        for key, label in self.SECTIONS:
            tab_frame = tk.Frame(self._notebook, bg=BG)
            self._notebook.add(tab_frame, text=label)
            self._sub_tabs[key] = self._build_section(tab_frame, key)

        self._refresh_all()

    def _build_section(self, parent, key):
        lf = tk.Frame(parent, bg=BG)
        lf.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)
        sb = tk.Scrollbar(lf)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        lb = tk.Listbox(lf, font=("Consolas", 9), bg=BG_CARD, fg=FG,
                        selectbackground=BG_HEADER, selectforeground=YELLOW,
                        yscrollcommand=sb.set, activestyle="dotbox")
        lb.pack(fill=tk.BOTH, expand=True)
        sb.config(command=lb.yview)

        bf = tk.Frame(parent, bg=BG, padx=6, pady=4)
        bf.pack(fill=tk.X)
        make_btn(bf, "Edit Selected", lambda: self._edit(key)).pack(side=tk.LEFT, padx=2)
        make_btn(bf, "Remove Selected", lambda: self._remove(key),
                 fg=RED).pack(side=tk.LEFT, padx=2)
        make_btn(bf, "Add New", lambda: self._add(key), bold=True,
                 bg="#2a6041").pack(side=tk.RIGHT, padx=2)

        return {"listbox": lb, "keys": []}

    def _refresh_all(self):
        total = 0
        for key, _ in self.SECTIONS:
            self._refresh_section(key)
            total += len(self._sub_tabs[key]["keys"])
        self._count_var.set(f"{total} corrections total")

    def _refresh_section(self, key):
        typos = load_typos()
        mapping = typos.get(key, {})
        tab = self._sub_tabs[key]
        lb = tab["listbox"]
        lb.delete(0, tk.END)
        tab["keys"] = []
        for k in sorted(mapping.keys(), key=str.lower):
            v = mapping[k]
            lb.insert(tk.END, f"{k}  ->  {v}")
            tab["keys"].append(k)

    def _remove(self, key):
        tab = self._sub_tabs[key]
        sel = tab["listbox"].curselection()
        if not sel:
            return
        map_key = tab["keys"][sel[0]]
        typos = load_typos()
        mapping = typos.get(key, {})
        val = mapping.get(map_key, "")
        if not messagebox.askyesno("Confirm removal",
                                   f"Remove correction?\n\n\"{map_key}\" -> \"{val}\"",
                                   parent=self._root):
            return
        del mapping[map_key]
        typos[key] = mapping
        save_typos(typos)
        self._refresh_all()

    def _edit(self, key):
        tab = self._sub_tabs[key]
        sel = tab["listbox"].curselection()
        if not sel:
            return
        old_key = tab["keys"][sel[0]]
        typos = load_typos()
        old_val = typos.get(key, {}).get(old_key, "")
        self._open_correction_dialog(key, old_key, old_val)

    def _add(self, key):
        self._open_correction_dialog(key, "", "")

    def _open_correction_dialog(self, key, old_key, old_val):
        dlg = tk.Toplevel(self._root)
        section_label = dict(self.SECTIONS).get(key, key)
        dlg.title(f"{'Edit' if old_key else 'Add'} {section_label} Correction")
        dlg.configure(bg=BG)
        dlg.geometry("450x180")
        dlg.transient(self._root)
        dlg.grab_set()

        row1 = tk.Frame(dlg, bg=BG, padx=10)
        row1.pack(fill=tk.X, pady=(10, 4))
        tk.Label(row1, text="From:", font=("Segoe UI", 9, "bold"),
                 fg=FG, bg=BG, width=6, anchor="e").pack(side=tk.LEFT)
        key_var = tk.StringVar(value=old_key)
        ke = tk.Entry(row1, textvariable=key_var, font=("Segoe UI", 10),
                      bg=BG_CARD, fg=FG, insertbackground=FG)
        ke.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        row2 = tk.Frame(dlg, bg=BG, padx=10)
        row2.pack(fill=tk.X, pady=4)
        tk.Label(row2, text="To:", font=("Segoe UI", 9, "bold"),
                 fg=FG, bg=BG, width=6, anchor="e").pack(side=tk.LEFT)
        val_var = tk.StringVar(value=old_val)
        tk.Entry(row2, textvariable=val_var, font=("Segoe UI", 10),
                 bg=BG_CARD, fg=FG, insertbackground=FG).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))

        def save():
            new_key = key_var.get().strip()
            new_val = val_var.get().strip()
            if not new_key:
                messagebox.showwarning("Empty", "\"From\" field cannot be empty.",
                                       parent=dlg)
                return
            typos = load_typos()
            mapping = typos.get(key, {})
            if old_key and old_key != new_key:
                mapping.pop(old_key, None)
            mapping[new_key] = new_val
            typos[key] = mapping
            save_typos(typos)
            dlg.destroy()
            self._refresh_all()

        bf = tk.Frame(dlg, bg=BG)
        bf.pack(fill=tk.X, padx=10, pady=(8, 10))
        make_btn(bf, "Cancel", dlg.destroy, width=10).pack(side=tk.LEFT, padx=4)
        make_btn(bf, "Save", save, bold=True, bg="#2a6041", width=10).pack(
            side=tk.RIGHT, padx=4)


# =========================================================================
# Tab: Summary
# =========================================================================

class SummaryTab:
    def __init__(self, parent, root):
        self._root = root
        self._frame = tk.Frame(parent, bg=BG)
        self._build()

    @property
    def widget(self):
        return self._frame

    def _build(self):
        f = self._frame

        hdr = tk.Frame(f, bg=BG_HEADER, padx=10, pady=4)
        hdr.pack(fill=tk.X)
        tk.Label(hdr, text="typos.json Summary", font=("Segoe UI", 11, "bold"),
                 fg=YELLOW, bg=BG_HEADER).pack(side=tk.LEFT)
        make_btn(hdr, "Refresh", self._refresh).pack(side=tk.RIGHT, padx=2)

        tf = tk.Frame(f, bg=BG)
        tf.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
        sb = tk.Scrollbar(tf)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._text = tk.Text(tf, font=("Consolas", 9), bg=BG_CARD, fg=FG,
                             yscrollcommand=sb.set, wrap=tk.WORD)
        self._text.pack(fill=tk.BOTH, expand=True)
        sb.config(command=self._text.yview)

        bf = tk.Frame(f, bg=BG, padx=10, pady=6)
        bf.pack(fill=tk.X)
        make_btn(bf, "Show Raw JSON", self._show_raw).pack(side=tk.LEFT, padx=2)

        self._refresh()

    def _refresh(self):
        typos = load_typos()
        lines = []
        lines.append("=== typos.json Overview ===\n")

        exc = typos.get("exclude", [])
        renames = typos.get("rename", [])

        lines.append(f"Excluded: {len(exc)} items")
        for rid in exc:
            lines.append(f"  {ramen_label(rid)}")
        lines.append("")

        lines.append(f"Renames: {len(renames)} items")
        for r in renames:
            overrides = [f"{k.replace('replace_', '')}={v}"
                         for k, v in r.items() if k != "id"]
            lines.append(f"  {ramen_label(r['id'])}  ->  {', '.join(overrides)}")
        lines.append("")

        for key, label in [("country", "Country"), ("style", "Style"),
                           ("brand", "Brand"), ("text", "Text")]:
            m = typos.get(key, {})
            lines.append(f"{label} corrections: {len(m)}")
        lines.append("")

        total_corrections = sum(len(typos.get(k, {})) for k in ["country", "style", "brand", "text"])
        lines.append(f"Total excluded: {len(exc)}")
        lines.append(f"Total renames: {len(renames)}")
        lines.append(f"Total corrections: {total_corrections}")

        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.insert("1.0", "\n".join(lines))
        self._text.configure(state=tk.DISABLED)

    def _show_raw(self):
        typos = load_typos()
        raw = json.dumps(typos, indent=2, ensure_ascii=False)

        dlg = tk.Toplevel(self._root)
        dlg.title("Raw typos.json")
        dlg.configure(bg=BG)
        dlg.geometry("600x500")
        dlg.transient(self._root)

        tf = tk.Frame(dlg, bg=BG)
        tf.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        sb = tk.Scrollbar(tf)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        txt = tk.Text(tf, font=("Consolas", 9), bg=BG_CARD, fg=FG,
                      yscrollcommand=sb.set, wrap=tk.NONE)
        txt.insert("1.0", raw)
        txt.configure(state=tk.DISABLED)
        txt.pack(fill=tk.BOTH, expand=True)
        sb.config(command=txt.yview)


# =========================================================================
# Main application
# =========================================================================

class TyposExplorer:
    def __init__(self):
        self._root = tk.Tk()
        self._root.title("Typos Explorer — typos.json Management")
        self._root.configure(bg=BG)
        self._root.geometry("800x850")
        self._root.minsize(720, 650)

        self._notebook = ttk.Notebook(self._root)
        self._notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_CARD, foreground=FG,
                        padding=[12, 4], font=("Segoe UI", 9, "bold"))
        style.map("TNotebook.Tab",
                   background=[("selected", BG_HEADER)],
                   foreground=[("selected", YELLOW)])

        self._dupes = DuplicatesTab(self._notebook, self._root)
        self._notebook.add(self._dupes.widget, text="Duplicates")

        self._disc = DiscontinuedTab(self._notebook, self._root)
        self._notebook.add(self._disc.widget, text="Excluded")

        self._renames = RenamesTab(self._notebook, self._root)
        self._notebook.add(self._renames.widget, text="Renames")

        self._corr = CorrectionsTab(self._notebook, self._root)
        self._notebook.add(self._corr.widget, text="Corrections")

        self._summary = SummaryTab(self._notebook, self._root)
        self._notebook.add(self._summary.widget, text="Summary")

    def run(self):
        self._root.mainloop()


def main():
    if not RAMEN_JSON.exists():
        print(f"Error: {RAMEN_JSON} not found. Run fetch_ramen_data.py first.")
        sys.exit(1)

    print("Loading data...")
    get_ramen_db()
    print(f"  {len(get_ramen_db())} ramen loaded")
    print("Building conflict groups...")
    groups = build_conflict_groups()
    print(f"  {len(groups)} barcode conflicts")
    print("Launching Typos Explorer...")

    app = TyposExplorer()
    app.run()


if __name__ == "__main__":
    main()
