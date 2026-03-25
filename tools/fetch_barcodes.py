#!/usr/bin/env python3
"""
Ramen Barcode Gathering Tool

Walks through ramen items that don't yet have barcodes, searches multiple
databases (Open Food Facts, barcodelookup.com, theramenrater.com), and
presents results in a Tkinter GUI for confirmation.

Usage:
    python fetch_barcodes.py
"""

import json
import re
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from io import BytesIO
from urllib.parse import quote_plus

_venv = Path(__file__).resolve().parent.parent / ".venv"
if _venv.is_dir() and not (hasattr(sys, 'real_prefix') or sys.base_prefix != sys.prefix):
    _sp = _venv / "Lib" / "site-packages"
    if not _sp.is_dir():
        _py = f"python{sys.version_info.major}.{sys.version_info.minor}"
        _sp = _venv / "lib" / _py / "site-packages"
    if _sp.is_dir() and str(_sp) not in sys.path:
        sys.path.insert(0, str(_sp))

import requests

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
IMAGES_DIR = ROOT_DIR / "images" / "ramen"
CACHE_DIR = ROOT_DIR / "tools" / ".cache"
RAMEN_JSON = DATA_DIR / "ramen.json"
BARCODES_JSON = DATA_DIR / "barcodes.json"
POPULARITY_JSON = DATA_DIR / "popularity.json"

OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"

UBLOCK_ID = "ddkjiahejlhfcafbddmgiahcphecmpfh"
UBLOCK_DIR = CACHE_DIR / "ublock"
UBLOCK_VERSION_FILE = CACHE_DIR / "ublock-version"
PW_VERSION_FILE = CACHE_DIR / "playwright-version"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

BARCODE_RE = re.compile(r'\b(\d{8}|\d{12,14})\b')
BARCODE_SPACED_RE = re.compile(r'\b(\d[\d \-]{6,16}\d)\b')

SOURCE_NAMES = ["Open Food Facts", "UPCitemdb", "Google", "The Ramen Rater"]


def _valid_barcode(code):
    """Check digit validation for EAN-8, UPC-A (12), EAN-13, and EAN-14 / ITF-14."""
    if len(code) not in (8, 12, 13, 14):
        return False
    digits = [int(d) for d in code]
    check = digits[-1]
    payload = digits[:-1]
    total = 0
    for i, d in enumerate(reversed(payload)):
        total += d * (3 if i % 2 == 0 else 1)
    expected = (10 - (total % 10)) % 10
    return check == expected


def _detect_barcode_type(code):
    """Return barcode type string based on digit count."""
    n = len(code)
    if n == 8:
        return "ean_8"
    if n == 12:
        return "upc_a"
    if n == 13:
        return "ean_13"
    if n == 14:
        return "itf_14"
    return "unknown"


# ---------------------------------------------------------------------------
# Browser setup (uBlock + Playwright)
# ---------------------------------------------------------------------------

def _ensure_ublock():
    """Download/update uBlock Origin Lite if needed. Returns path to unpacked extension."""
    import zipfile

    crx_url = (
        f"https://clients2.google.com/service/update2/crx"
        f"?response=redirect&prodversion=130.0&acceptformat=crx2,crx3"
        f"&x=id%3D{UBLOCK_ID}%26uc"
    )

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = UBLOCK_DIR / "manifest.json"
    local_ver = ""
    if UBLOCK_VERSION_FILE.exists():
        local_ver = UBLOCK_VERSION_FILE.read_text().strip()

    try:
        head = requests.head(crx_url, headers=BROWSER_HEADERS, timeout=10, allow_redirects=True)
        remote_tag = head.headers.get("ETag", "") or head.headers.get("Last-Modified", "")
    except Exception:
        remote_tag = ""

    if manifest_path.exists() and local_ver and local_ver == remote_tag and remote_tag:
        print(f"  uBlock Origin Lite: up to date")
        return str(UBLOCK_DIR)

    print(f"  Downloading uBlock Origin Lite...")
    resp = requests.get(crx_url, headers=BROWSER_HEADERS, timeout=30, allow_redirects=True)
    resp.raise_for_status()
    crx_data = resp.content

    zip_start = crx_data.find(b'PK\x03\x04')
    if zip_start < 0:
        raise RuntimeError("Could not find ZIP data in CRX file")

    if UBLOCK_DIR.exists():
        import shutil
        shutil.rmtree(UBLOCK_DIR)
    UBLOCK_DIR.mkdir(parents=True)

    with zipfile.ZipFile(BytesIO(crx_data[zip_start:])) as zf:
        zf.extractall(UBLOCK_DIR)

    version_tag = remote_tag or "downloaded"
    UBLOCK_VERSION_FILE.write_text(version_tag)

    if manifest_path.exists():
        mf = json.loads(manifest_path.read_text(encoding="utf-8"))
        print(f"  uBlock Origin Lite v{mf.get('version', '?')} installed")
    else:
        print(f"  uBlock Origin Lite installed")

    return str(UBLOCK_DIR)


def _ensure_playwright_browser():
    """Run 'playwright install chromium' if the Playwright version has changed."""
    import playwright
    current_ver = getattr(playwright, '__version__', '')

    saved_ver = ""
    if PW_VERSION_FILE.exists():
        saved_ver = PW_VERSION_FILE.read_text().strip()

    if current_ver and current_ver == saved_ver:
        return

    import subprocess
    print(f"  Installing Playwright Chromium (v{current_ver})...")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"],
                   check=True, capture_output=True)
    PW_VERSION_FILE.write_text(current_ver)
    print(f"  Playwright Chromium ready")


def _create_browser():
    """Launch a Playwright browser with uBlock Origin Lite. Returns (pw, context, page)."""
    from playwright.sync_api import sync_playwright

    _ensure_playwright_browser()
    ext_path = _ensure_ublock()

    pw = sync_playwright().start()
    user_data = str(CACHE_DIR / "pw-barcode-profile")
    context = pw.chromium.launch_persistent_context(
        user_data,
        headless=False,
        args=[
            f"--disable-extensions-except={ext_path}",
            f"--load-extension={ext_path}",
        ],
    )
    page = context.new_page()
    return pw, context, page


def _active_page(context):
    """Return the most recently used page in the browser context."""
    try:
        pages = context.pages
        if pages:
            return pages[-1]
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def load_ramen():
    with open(RAMEN_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def load_barcodes():
    if BARCODES_JSON.exists():
        try:
            with open(BARCODES_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    needs_migrate = any("barcode" in e for e in data)
                    if needs_migrate:
                        merged = {}
                        for entry in data:
                            rid = entry["id"]
                            if rid not in merged:
                                merged[rid] = {"id": rid}
                            if "barcode" in entry:
                                code = str(entry["barcode"])
                                btype = entry.get("type", _detect_barcode_type(code))
                                merged[rid][btype] = code
                            else:
                                for k, v in entry.items():
                                    if k != "id":
                                        merged[rid][k] = v
                        data = list(merged.values())
                        save_barcodes(data)
                    return data
        except (json.JSONDecodeError, ValueError):
            pass
    return []


def save_barcodes(barcode_list):
    with open(BARCODES_JSON, "w", encoding="utf-8") as f:
        json.dump(barcode_list, f, indent=2, ensure_ascii=False)
        f.write("\n")


def barcoded_ids(barcode_list):
    return {entry["id"] for entry in barcode_list}


def load_popularity():
    if POPULARITY_JSON.exists():
        try:
            with open(POPULARITY_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def sort_by_popularity(ramen_list):
    """Sort ramen by popularity (highest first). Re-reads popularity.json each call."""
    pop = load_popularity()
    has_image_set = {r["id"] for r in ramen_list if (IMAGES_DIR / f"{r['id']}.webp").exists()}
    return sorted(ramen_list, key=lambda r: (
        0 if r["id"] in has_image_set else 1,
        -(pop.get(str(r["id"]), 0)),
        r["id"],
    ))


# ---------------------------------------------------------------------------
# Fuzzy search (same algorithm as fetch_ramen_data.py)
# ---------------------------------------------------------------------------

def _fuzzy_rank_ramen(query, ramen_list, limit=50):
    q = (query or "").strip()
    if not q:
        return []
    if q.isdigit():
        rid = int(q)
        for r in ramen_list:
            if r.get("id") == rid:
                return [r]
        return []

    try:
        from rapidfuzz import fuzz
    except ImportError:
        fuzz = None

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
        elif fuzz:
            score = max(
                fuzz.partial_ratio(q, hay),
                fuzz.token_set_ratio(q, hay),
                fuzz.WRatio(q, hay),
            )
        else:
            from difflib import SequenceMatcher
            score = SequenceMatcher(None, q_fold, hay_fold).ratio() * 100

        scored.append((score, r))

    scored.sort(key=lambda x: (-x[0], x[1].get("id", 0)))
    cutoff = 45
    return [r for s, r in scored[:limit] if s >= cutoff]


# ---------------------------------------------------------------------------
# Search: Open Food Facts (requests, no browser)
# ---------------------------------------------------------------------------

def search_openfoodfacts(page, brand, variety):
    """Navigate OFF search — scanning is handled by the poll loop."""
    query = f"{brand} {variety}"
    url = f"{OFF_SEARCH_URL}?search_terms={quote_plus(query)}&search_simple=1&action=process"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Search: barcodelookup.com (Playwright)
# ---------------------------------------------------------------------------

def search_upcitemdb(page, brand, variety):
    """Navigate upcitemdb.com search — scanning is handled by the poll loop."""
    query = f"{brand} {variety}"
    url = f"https://www.upcitemdb.com/query?s={quote_plus(query)}&type=2"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except Exception:
        pass
    return []


def scan_current_page(page):
    """Scan whatever page the browser is currently on for barcode-like numbers.
    Uses evaluate() for reliability, falls back to content() for raw HTML scan."""
    results = []
    seen = set()

    body_text = ""
    try:
        body_text = page.evaluate("() => document.body ? document.body.textContent : ''") or ""
    except Exception as e:
        print(f"      scan: evaluate failed ({e}), trying content()")
        try:
            html = page.content() or ""
            body_text = re.sub(r'<[^>]+>', ' ', html)
        except Exception as e2:
            print(f"      scan: content() also failed ({e2})")
            return results

    hits = []
    for m in BARCODE_RE.finditer(body_text):
        code = m.group(1)
        if len(code) in (8, 12, 13, 14) and code not in seen and _valid_barcode(code):
            ctx = body_text[max(0, m.start()-40):m.end()+40].replace("\n", " ").strip()
            seen.add(code)
            hits.append((m.start(), code, ctx[:80]))

    for m in BARCODE_SPACED_RE.finditer(body_text):
        digits = re.sub(r'[\s\-]', '', m.group(1))
        if len(digits) in (8, 12, 13, 14) and digits not in seen and _valid_barcode(digits):
            ctx = body_text[max(0, m.start()-40):m.end()+40].replace("\n", " ").strip()
            seen.add(digits)
            hits.append((m.start(), digits, ctx[:80]))

    hits.sort(key=lambda h: h[0])
    return [(code, ctx) for _, code, ctx in hits]


def search_google_barcode(page, brand, variety):
    """Navigate Google barcode search — scanning is handled by the poll loop."""
    query = f"{brand} {variety} barcode UPC EAN"
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Search: theramenrater.com review page (Playwright, last resort)
# ---------------------------------------------------------------------------

def search_ramenrater(page, ramen):
    """Visit the ramen rater review URL and look for barcodes in the page text."""
    url = ramen.get("url", "")
    if not url:
        return []

    search_url = url
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=15000)
    except Exception:
        pass
    return []


# ---------------------------------------------------------------------------
# Tkinter GUI
# ---------------------------------------------------------------------------

class BarcodePanel:
    """Tkinter panel for reviewing and confirming barcodes."""

    def __init__(self, ramen_list, needs_barcode):
        self._ramen_list = ramen_list
        self._needs_barcode = needs_barcode
        self._lock = threading.Lock()
        self._action = None          # "confirm", "skip", "jump"
        self._action_event = threading.Event()
        self._jump_id = None
        self._goto_source = None
        self.shutting_down = False
        self._photo = None

        self._root = tk.Tk()
        root = self._root
        root.title("Ramen Barcode Gatherer")
        root.attributes("-topmost", True)
        root.resizable(True, True)
        root.geometry("660x780")
        root.minsize(500, 650)
        root.configure(bg="#1a1a2e")

        # --- Current ramen display ---
        info_frame = tk.Frame(root, bg="#1a1a2e")
        info_frame.pack(fill=tk.X, padx=12, pady=(10, 4))

        self._img_label = tk.Label(info_frame, bg="#1a1a2e", width=120, height=120)
        self._img_label.pack(side=tk.LEFT, padx=(0, 10))

        text_frame = tk.Frame(info_frame, bg="#1a1a2e")
        text_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._id_text = self._make_copyable(text_frame, font=("Segoe UI", 9), fg="#888", height=1)
        self._id_text.pack(fill=tk.X)

        self._name_text = self._make_copyable(text_frame, font=("Segoe UI", 11, "bold"), fg="#f7d354", height=2)
        self._name_text.pack(fill=tk.X, pady=(2, 2))

        self._detail_text = self._make_copyable(text_frame, font=("Segoe UI", 9), fg="#a0a0a0", height=1)
        self._detail_text.pack(fill=tk.X)

        # --- Search status ---
        self._search_var = tk.StringVar(value="")
        tk.Label(root, textvariable=self._search_var, font=("Segoe UI", 9),
                 fg="#e0e0e0", bg="#1a1a2e", anchor="w").pack(fill=tk.X, padx=12, pady=(6, 2))

        # --- Candidates list ---
        tk.Label(root, text="Candidates found:", font=("Segoe UI", 9, "bold"),
                 fg="#e0e0e0", bg="#1a1a2e", anchor="w").pack(fill=tk.X, padx=12, pady=(6, 2))

        cand_frame = tk.Frame(root, bg="#1a1a2e")
        cand_frame.pack(fill=tk.BOTH, padx=12, pady=(0, 4), expand=False)
        yscroll = tk.Scrollbar(cand_frame, orient=tk.VERTICAL)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._cand_list = tk.Listbox(
            cand_frame, height=6, font=("TkFixedFont", 9),
            bg="#16213e", fg="#e0e0e0", selectbackground="#0f3460",
            selectforeground="#f7d354",
            yscrollcommand=yscroll.set, exportselection=False, activestyle="dotbox",
        )
        self._cand_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.config(command=self._cand_list.yview)
        self._cand_list.bind("<<ListboxSelect>>", self._on_candidate_select)
        self._candidates = []

        # --- Barcode entry ---
        entry_frame = tk.Frame(root, bg="#1a1a2e")
        entry_frame.pack(fill=tk.X, padx=12, pady=(4, 2))
        tk.Label(entry_frame, text="Barcode:", font=("Segoe UI", 10, "bold"),
                 fg="#e0e0e0", bg="#1a1a2e").pack(side=tk.LEFT, padx=(0, 6))
        self._barcode_var = tk.StringVar(value="")
        self._barcode_entry = tk.Entry(entry_frame, textvariable=self._barcode_var,
                                        font=("Segoe UI", 12), width=28,
                                        bg="#16213e", fg="#f7d354", insertbackground="#f7d354")
        self._barcode_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._barcode_entry.bind("<Return>", lambda e: self._on_confirm())

        # --- Source label ---
        self._source_var = tk.StringVar(value="")
        tk.Label(root, textvariable=self._source_var, font=("Segoe UI", 8),
                 fg="#666", bg="#1a1a2e", anchor="w").pack(fill=tk.X, padx=12, pady=(0, 4))

        # --- Action buttons ---
        btn_row = tk.Frame(root, bg="#1a1a2e")
        btn_row.pack(pady=(4, 6))
        self._confirm_btn = tk.Button(btn_row, text="Confirm", command=self._on_confirm,
                  font=("Segoe UI", 10, "bold"), bg="#2a6041", fg="#e0e0e0",
                  activebackground="#1e8449", activeforeground="#fff", width=10)
        self._confirm_btn.pack(side=tk.LEFT, padx=6)
        tk.Button(btn_row, text="Next Source", command=self._on_skip,
                  font=("Segoe UI", 10), bg="#16213e", fg="#e0e0e0",
                  activebackground="#0f3460", activeforeground="#f7d354", width=10).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_row, text="Skip Item", command=self._on_skip_item,
                  font=("Segoe UI", 10), bg="#3a1a1a", fg="#e0e0e0",
                  activebackground="#5a2020", activeforeground="#f7d354", width=10).pack(side=tk.LEFT, padx=6)

        # --- Separator ---
        tk.Frame(root, bg="#333", height=1).pack(fill=tk.X, padx=12, pady=(6, 6))

        # --- Jump to ramen (fuzzy search) ---
        tk.Label(root, text="Jump to ramen (fuzzy search):", font=("Segoe UI", 9, "bold"),
                 fg="#e0e0e0", bg="#1a1a2e", anchor="w").pack(fill=tk.X, padx=12, pady=(0, 2))

        jump_entry_frame = tk.Frame(root, bg="#1a1a2e")
        jump_entry_frame.pack(fill=tk.X, padx=12, pady=(0, 4))
        self._jump_var = tk.StringVar()
        jump_ent = tk.Entry(jump_entry_frame, textvariable=self._jump_var, font=("Segoe UI", 10),
                            width=40, bg="#16213e", fg="#e0e0e0", insertbackground="#e0e0e0")
        jump_ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        jump_ent.bind("<Return>", lambda e: self._on_jump_search())
        tk.Button(jump_entry_frame, text="Search", command=self._on_jump_search,
                  font=("Segoe UI", 9), bg="#16213e", fg="#e0e0e0",
                  activebackground="#0f3460", activeforeground="#f7d354").pack(side=tk.LEFT)

        jump_list_frame = tk.Frame(root, bg="#1a1a2e")
        jump_list_frame.pack(fill=tk.BOTH, padx=12, pady=(0, 4), expand=True)
        jyscroll = tk.Scrollbar(jump_list_frame, orient=tk.VERTICAL)
        jyscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._jump_list = tk.Listbox(
            jump_list_frame, height=6, font=("TkFixedFont", 9),
            bg="#16213e", fg="#e0e0e0", selectbackground="#0f3460",
            selectforeground="#f7d354",
            yscrollcommand=jyscroll.set, exportselection=False, activestyle="dotbox",
        )
        self._jump_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        jyscroll.config(command=self._jump_list.yview)
        self._jump_list.bind("<Double-Button-1>", lambda e: self._on_jump_go())
        self._jump_ids = []

        jump_btn_frame = tk.Frame(root, bg="#1a1a2e")
        jump_btn_frame.pack(pady=(0, 4))
        tk.Button(jump_btn_frame, text="Jump to selected", command=self._on_jump_go,
                  font=("Segoe UI", 9), bg="#16213e", fg="#e0e0e0",
                  activebackground="#0f3460", activeforeground="#f7d354").pack()

        # --- Sources toggle + go-to buttons ---
        tk.Frame(root, bg="#333", height=1).pack(fill=tk.X, padx=12, pady=(6, 4))
        tk.Label(root, text="Sources (uncheck to skip in auto-cascade, click name to jump):",
                 font=("Segoe UI", 9, "bold"),
                 fg="#e0e0e0", bg="#1a1a2e", anchor="w").pack(fill=tk.X, padx=12, pady=(0, 2))

        src_frame = tk.Frame(root, bg="#1a1a2e")
        src_frame.pack(fill=tk.X, padx=12, pady=(0, 4))
        self._source_vars = {}
        for name in SOURCE_NAMES:
            var = tk.BooleanVar(value=True)
            self._source_vars[name] = var
            item_frame = tk.Frame(src_frame, bg="#1a1a2e")
            item_frame.pack(side=tk.LEFT, padx=(0, 6))
            tk.Checkbutton(item_frame, variable=var,
                           bg="#1a1a2e", selectcolor="#16213e",
                           activebackground="#1a1a2e").pack(side=tk.LEFT)
            _name = name
            tk.Button(item_frame, text=name,
                      command=lambda n=_name: self._on_goto_source(n),
                      font=("Segoe UI", 8), fg="#88bbff", bg="#1a1a2e",
                      activebackground="#1a1a2e", activeforeground="#f7d354",
                      borderwidth=0, cursor="hand2", relief="flat").pack(side=tk.LEFT)

        # --- Progress ---
        self._progress_var = tk.StringVar(value="Starting...")
        tk.Label(root, textvariable=self._progress_var, font=("Segoe UI", 9),
                 fg="#a0a0a0", bg="#1a1a2e").pack(pady=(4, 4))

        # --- Last saved barcode ---
        self._last_saved_var = tk.StringVar(value="")
        tk.Label(root, textvariable=self._last_saved_var, font=("Segoe UI", 9),
                 fg="#6abf69", bg="#1a1a2e").pack(pady=(0, 8))

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    @staticmethod
    def _make_copyable(parent, font, fg, height=1):
        """Create a read-only Text widget that supports select-all and copy."""
        w = tk.Text(parent, font=font, fg=fg, bg="#1a1a2e", height=height,
                    wrap="word", borderwidth=0, highlightthickness=0,
                    selectbackground="#0f3460", selectforeground="#fff",
                    cursor="arrow")
        w.insert("1.0", "")
        w.configure(state="disabled")
        w.bind("<Control-a>", lambda e: (w.tag_add("sel", "1.0", "end"), "break"))
        w.bind("<Control-c>", lambda e: None)
        return w

    @staticmethod
    def _set_copyable(widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    # --- Display methods (called from worker thread via root.after) ---

    def show_ramen(self, ramen, remaining, found_so_far):
        def _update():
            rid = ramen.get("id", "?")
            brand = ramen.get("brand", "")
            variety = ramen.get("variety", "")
            country = ramen.get("country", "")
            style = ramen.get("style", "")

            self._set_copyable(self._id_text, f"#{rid}")
            self._set_copyable(self._name_text, f"{brand} — {variety}")
            self._set_copyable(self._detail_text, f"{style}  |  {country}")
            self._progress_var.set(f"{remaining} remaining  |  {found_so_far} barcodes saved")
            self._search_var.set("Searching...")
            self._barcode_var.set("")
            self._source_var.set("")
            self._cand_list.delete(0, tk.END)
            self._candidates.clear()

            self._load_thumbnail(rid)
        self._root.after(0, _update)

    def _load_thumbnail(self, rid):
        img_path = IMAGES_DIR / f"{rid}.webp"
        if not img_path.exists():
            self._img_label.configure(image="", text="No image", fg="#666",
                                       font=("Segoe UI", 9), width=14, height=7)
            self._photo = None
            return
        try:
            from PIL import Image, ImageTk
            pil = Image.open(img_path)
            pil.thumbnail((120, 120))
            self._photo = ImageTk.PhotoImage(pil)
            self._img_label.configure(image=self._photo, text="", width=120, height=120)
        except ImportError:
            self._img_label.configure(image="", text="(Pillow\nneeded)", fg="#666",
                                       font=("Segoe UI", 8), width=14, height=7)
            self._photo = None
        except Exception:
            self._img_label.configure(image="", text="Error", fg="#666",
                                       font=("Segoe UI", 9), width=14, height=7)
            self._photo = None

    def set_search_status(self, text):
        self._root.after(0, lambda: self._search_var.set(text))

    def set_last_saved(self, rid, barcode, btype=""):
        label = f"Last saved: #{rid} \u2192 {barcode}"
        if btype:
            label += f" ({btype})"
        self._root.after(0, lambda: self._last_saved_var.set(label))

    def set_candidates(self, candidates, source):
        """candidates: list of (barcode, label)."""
        def _update():
            self._cand_list.delete(0, tk.END)
            self._candidates = list(candidates)
            for code, label in candidates:
                self._cand_list.insert(tk.END, f"{code}  —  {label}")
            if candidates:
                current = self._barcode_var.get().strip()
                if not current:
                    self._barcode_var.set(candidates[0][0])
                    self._cand_list.selection_set(0)
                self._source_var.set(f"Source: {source}")
            else:
                self._source_var.set("")
        self._root.after(0, _update)

    def set_no_results(self):
        def _update():
            self._search_var.set("No barcode found in any source")
            self._source_var.set("Enter manually or skip")
        self._root.after(0, _update)

    # --- User actions ---

    def _on_candidate_select(self, event):
        sel = self._cand_list.curselection()
        if sel and sel[0] < len(self._candidates):
            code, label = self._candidates[sel[0]]
            self._barcode_var.set(code)

    def _on_confirm(self):
        val = self._barcode_var.get().strip()
        if not val:
            return
        with self._lock:
            self._action = "confirm"
        self._action_event.set()

    def _on_skip(self):
        with self._lock:
            self._action = "skip"
        self._action_event.set()

    def _on_skip_item(self):
        with self._lock:
            self._action = "skip_item"
        self._action_event.set()

    def _on_goto_source(self, name):
        with self._lock:
            self._goto_source = name
            self._action = "goto_source"
        self._action_event.set()

    def get_goto_source(self):
        with self._lock:
            s = getattr(self, '_goto_source', None)
            self._goto_source = None
            return s

    def _on_close(self):
        self.shutting_down = True
        self._action_event.set()
        try:
            self._root.destroy()
        except Exception:
            pass

    def _on_jump_search(self):
        text = (self._jump_var.get() or "").strip()
        if not text:
            return
        matches = _fuzzy_rank_ramen(text, self._ramen_list, limit=30)
        self._jump_list.delete(0, tk.END)
        self._jump_ids.clear()
        if not matches:
            return
        for r in matches:
            brand = r.get("brand") or ""
            variety = r.get("variety") or ""
            line = f"#{r['id']:5d}  {brand} — {variety}"
            self._jump_list.insert(tk.END, line)
            self._jump_ids.append(r["id"])

    def _on_jump_go(self):
        sel = self._jump_list.curselection()
        if not sel:
            return
        rid = self._jump_ids[sel[0]]
        with self._lock:
            self._jump_id = rid
            self._action = "jump"
        self._action_event.set()

    def is_source_enabled(self, name):
        var = self._source_vars.get(name)
        return var.get() if var else True

    def get_barcode(self):
        return self._barcode_var.get().strip()

    def wait_for_action(self):
        """Block until user clicks Confirm, Skip, or Jump. Returns action string."""
        self._action_event.clear()
        with self._lock:
            self._action = None
        self._action_event.wait()
        with self._lock:
            return self._action

    def poll_for_action(self, timeout=0.5):
        """Check if user has taken an action, with a short timeout.
        Returns action string or None if no action yet."""
        self._action_event.wait(timeout=timeout)
        with self._lock:
            action = self._action
            if action:
                self._action = None
                self._action_event.clear()
            return action

    def get_jump_id(self):
        with self._lock:
            jid = self._jump_id
            self._jump_id = None
            return jid

    def run_with_panel(self, fn, *args, **kwargs):
        """Run fn in a background thread while tkinter mainloop owns main thread."""
        error = [None]

        def _worker():
            try:
                fn(*args, **kwargs)
            except KeyboardInterrupt:
                self.shutting_down = True
            except Exception as e:
                error[0] = e
                import traceback
                traceback.print_exc()
            finally:
                try:
                    self._root.after(0, self._root.destroy)
                except Exception:
                    pass

        def _signal_check():
            if self.shutting_down:
                self._root.destroy()
                return
            try:
                self._root.after(200, _signal_check)
            except Exception:
                pass

        import signal
        prev_handler = signal.getsignal(signal.SIGINT)

        def _ctrl_c(sig, frame):
            print("\n\nCtrl+C — shutting down...")
            self.shutting_down = True
            self._action_event.set()
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass

        signal.signal(signal.SIGINT, _ctrl_c)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        self._root.after(200, _signal_check)
        try:
            self._root.mainloop()
        except Exception:
            pass
        finally:
            signal.signal(signal.SIGINT, prev_handler)

        if error[0]:
            print(f"\nError: {error[0]}")


# ---------------------------------------------------------------------------
# Main processing loop
# ---------------------------------------------------------------------------

def _wait_with_url_watch(panel, context):
    """Wait for user action while continuously scanning the active page for barcodes.
    Always uses the currently active tab so new tabs work automatically."""
    if not context:
        return panel.wait_for_action()

    # Check for action that was set during the search phase
    with panel._lock:
        if panel._action:
            a = panel._action
            panel._action = None
            panel._action_event.clear()
            return a

    last_url = None
    known_codes = set()

    while not panel.shutting_down:
        action = panel.poll_for_action(timeout=0.3)
        if action:
            return action

        page = _active_page(context)
        if not page:
            continue

        try:
            current_url = page.url
        except Exception:
            current_url = last_url

        if current_url != last_url:
            if last_url is not None:
                print(f"    URL changed: {current_url[:80]}")
            known_codes.clear()
            last_url = current_url

        results = scan_current_page(page)

        with panel._lock:
            if panel._action:
                a = panel._action
                panel._action = None
                panel._action_event.clear()
                return a

        new_codes = {c for c, _ in results}
        if new_codes != known_codes:
            known_codes = new_codes
            if results:
                panel.set_search_status(f"Found {len(results)} barcode(s) on current page")
                panel.set_candidates(results, f"Page: {(current_url or '')[:50]}")
                print(f"    Scan: {len(results)} barcode(s) found")
            else:
                panel.set_search_status("No barcodes yet — page may still be loading")
                panel.set_candidates([], "")

    return None


def _rebuild_queue(ramen_list):
    """Build a fresh sorted queue of ramen needing barcodes, sorted by popularity."""
    existing = barcoded_ids(load_barcodes())
    needs = [r for r in ramen_list if r["id"] not in existing]
    return sort_by_popularity(needs)


def _run_barcode_gathering(ramen_list, panel):
    barcode_list = load_barcodes()
    existing = barcoded_ids(barcode_list)
    found_count = len(barcode_list)

    needs_sorted = _rebuild_queue(ramen_list)
    total_remaining = len(needs_sorted)
    skipped_ids = set()

    print(f"\n  {len(ramen_list)} ramen total, {len(existing)} already have barcodes, {total_remaining} remaining\n")

    pw = None
    context = None
    page = None

    try:
        pw, context, page = _create_browser()
        print("  Playwright browser launched with uBlock Origin Lite")
    except Exception as e:
        print(f"  Playwright unavailable ({e}) — browser sources won't work")

    while not panel.shutting_down:
        needs_sorted = _rebuild_queue(ramen_list)
        needs_sorted = [r for r in needs_sorted if r["id"] not in skipped_ids]
        total_remaining = len(needs_sorted)
        found_count = len(load_barcodes())

        if not needs_sorted:
            print("  All ramen have barcodes or have been skipped!")
            break

        ramen = needs_sorted[0]
        rid = ramen["id"]
        brand = ramen.get("brand", "")
        variety = ramen.get("variety", "")
        pop = load_popularity()
        pop_count = pop.get(str(rid), 0)
        pop_label = f"  (pop: {pop_count:,})" if pop_count else ""
        print(f"  [1/{total_remaining}] #{rid} {brand} — {variety}{pop_label}")

        panel.show_ramen(ramen, total_remaining, found_count)
        time.sleep(0.2)

        sources = [
            ("Open Food Facts", lambda: search_openfoodfacts(_active_page(context), brand, variety)),
            ("UPCitemdb", lambda: search_upcitemdb(_active_page(context), brand, variety)),
            ("Google", lambda: search_google_barcode(_active_page(context), brand, variety)),
            ("The Ramen Rater", lambda: search_ramenrater(_active_page(context), ramen)),
        ]

        resolved = False
        start_at = 0

        while not resolved and not panel.shutting_down:
            ran_any = False
            for si, (source_name, search_fn) in enumerate(sources):
                if si < start_at:
                    continue
                if not context:
                    break
                if not panel.is_source_enabled(source_name):
                    print(f"    {source_name}: disabled, skipping")
                    continue
                remaining = [(n, _) for n, _ in sources[si+1:] if panel.is_source_enabled(n)]
                next_name = remaining[0][0] if remaining else None
                ran_any = True

                panel.set_search_status(f"Searching {source_name}... check browser")
                print(f"    Searching {source_name}...")
                results = search_fn()

                if results:
                    hint = f"Found {len(results)} candidate(s) on {source_name} — check browser"
                    panel.set_candidates(results, source_name)
                else:
                    skip_hint = f"Next Source to try {next_name}" if next_name else "enter manually or Skip Item"
                    hint = f"No results on {source_name} — check browser, {skip_hint}"
                    panel.set_candidates([], "")
                panel.set_search_status(hint)
                print(f"    {source_name}: {len(results)} result(s)" if results else f"    {source_name}: no results")

                action = _wait_with_url_watch(panel, context)
                if panel.shutting_down:
                    break

                if action == "confirm":
                    barcode = panel.get_barcode()
                    if barcode:
                        btype = _detect_barcode_type(barcode)
                        bl = load_barcodes()
                        existing = next((e for e in bl if e["id"] == rid), None)
                        if existing:
                            existing[btype] = barcode
                        else:
                            bl.append({"id": rid, btype: barcode})
                        save_barcodes(bl)
                        panel.set_last_saved(rid, barcode, btype)
                        print(f"    SAVED: {barcode} ({btype})")
                    resolved = True
                    break
                elif action == "skip_item":
                    skipped_ids.add(rid)
                    print(f"    Skipped item")
                    resolved = True
                    break
                elif action == "skip":
                    continue
                elif action == "goto_source":
                    name = panel.get_goto_source()
                    goto_idx = next((i for i, (n, _) in enumerate(sources) if n == name), None)
                    if goto_idx is not None:
                        start_at = goto_idx
                        print(f"    Jumping to source: {name} (index {goto_idx})")
                    else:
                        print(f"    Source '{name}' not found, staying put")
                        continue
                    break
                elif action == "jump":
                    jump_id = panel.get_jump_id()
                    if jump_id is not None:
                        skipped_ids.discard(jump_id)
                        found = next((r for r in ramen_list if r["id"] == jump_id), None)
                        if found:
                            needs_sorted.insert(0, found)
                            ramen = found
                            rid = found["id"]
                            brand = found.get("brand", "")
                            variety = found.get("variety", "")
                            print(f"    Jumped to #{jump_id}")
                            panel.show_ramen(found, total_remaining, found_count)
                            time.sleep(0.2)
                            start_at = 0
                        else:
                            print(f"    #{jump_id} not found")
                    break
            else:
                break
            if resolved:
                break

            if not ran_any and not context:
                panel.set_no_results()
                print(f"    No candidates (no browser available)")
                action = panel.wait_for_action()
                if panel.shutting_down:
                    break
                if action == "confirm":
                    barcode = panel.get_barcode()
                    if barcode:
                        btype = _detect_barcode_type(barcode)
                        bl = load_barcodes()
                        existing = next((e for e in bl if e["id"] == rid), None)
                        if existing:
                            existing[btype] = barcode
                        else:
                            bl.append({"id": rid, btype: barcode})
                        save_barcodes(bl)
                        panel.set_last_saved(rid, barcode, btype)
                        print(f"    SAVED: {barcode} ({btype})")
                elif action == "skip_item":
                    skipped_ids.add(rid)
                    print(f"    Skipped item")
                break

    if context:
        context.close()
    if pw:
        pw.stop()

    final_count = len(load_barcodes())
    print(f"\n  Done! {final_count} total barcodes in {BARCODES_JSON.name}")


def main():
    if not RAMEN_JSON.exists():
        print(f"Error: {RAMEN_JSON} not found. Run fetch_ramen_data.py first.")
        sys.exit(1)

    ramen_list = load_ramen()
    if not ramen_list:
        print("No ramen data found.")
        sys.exit(1)

    barcode_list = load_barcodes()
    existing = barcoded_ids(barcode_list)
    needs = [r for r in ramen_list if r["id"] not in existing]
    has_img = sum(1 for r in needs if (IMAGES_DIR / f"{r['id']}.webp").exists())
    pop = load_popularity()
    has_pop = sum(1 for r in needs if str(r["id"]) in pop)
    print(f"Ramen Barcode Gatherer")
    print(f"  {len(ramen_list)} ramen total, {len(existing)} already have barcodes")
    print(f"  {len(needs)} still need barcodes ({has_img} have images, {has_pop} have popularity)")
    print(f"  Sorted by: has image > popularity (highest first)")

    panel = BarcodePanel(ramen_list, needs)
    panel.run_with_panel(_run_barcode_gathering, ramen_list, panel)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
