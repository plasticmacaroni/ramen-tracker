#!/usr/bin/env python3
"""
Ramen Image Finder — Tkinter GUI

For every ramen missing an image, navigates to its theramenrater.com review page,
extracts the first content image, and saves it as WebP.

Failures are tracked in two categories:
  1. No URL — couldn't find a review page on theramenrater.com
  2. No Image — found the page but couldn't extract/download an image

Failed items are shown in the UI and can be retried.

Usage:
    python image_finder.py              # default 4 workers
    python image_finder.py -w 8         # 8 workers
"""

import argparse
import json
import queue
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path
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

from fetch_barcodes import (
    ROOT_DIR, DATA_DIR, IMAGES_DIR, CACHE_DIR,
    BROWSER_HEADERS,
    load_ramen, load_popularity, load_urls, save_url,
    _ensure_playwright_browser, _ensure_ublock,
    UBLOCK_DIR,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_WIDTH = 400
WEBP_QUALITY = 75
RESULTS_JSON = DATA_DIR / "image_finder_results.json"

STATUS_PENDING = "pending"
STATUS_SEARCHING = "searching…"
STATUS_URL_FOUND = "URL found"
STATUS_SAVED = "saved"
STATUS_NO_URL = "NO URL"
STATUS_NO_IMAGE = "no image"
STATUS_ERROR = "error"

BG = "#1a1a2e"
BG_DARK = "#16213e"
FG = "#e0e0e0"
YELLOW = "#f7d354"
GREEN = "#2ecc71"
RED = "#e74c3c"
ORANGE = "#f0ad4e"
BLUE = "#88bbff"

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

_file_lock = threading.Lock()
_shutdown = threading.Event()


def _load_results():
    if RESULTS_JSON.exists():
        try:
            return json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_results(data):
    with _file_lock:
        RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
        RESULTS_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Browser helpers
# ---------------------------------------------------------------------------

def _create_browser(worker_id):
    from playwright.sync_api import sync_playwright

    profile_dir = str(CACHE_DIR / f"pw-profile-{worker_id}")
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        profile_dir,
        headless=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-gpu",
            "--no-sandbox",
        ],
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )
    page = context.new_page()
    return pw, context, page


# ---------------------------------------------------------------------------
# Scraping logic
# ---------------------------------------------------------------------------

def _follow_search(page, rid):
    """On a theramenrater search results page, follow the best matching link.
    Returns (url, exact_match:bool) or (None, False)."""
    try:
        links = page.query_selector_all("h2.entry-title a, .entry-title a")
        prefix = f"#{rid}:"
        for link in links:
            text = (link.inner_text() or "").strip()
            if text.startswith(prefix):
                href = link.get_attribute("href") or ""
                if href:
                    page.goto(href, wait_until="domcontentloaded", timeout=15000)
                    return page.url, True
        if links:
            href = links[0].get_attribute("href") or ""
            if href:
                page.goto(href, wait_until="domcontentloaded", timeout=15000)
                return page.url, False
    except Exception:
        pass
    return None, False


def _find_review_url(page, rid, brand, variety, known_urls):
    """Try to find the theramenrater review page. Returns URL or None."""
    direct = known_urls.get(str(rid))
    if direct:
        try:
            page.goto(direct, wait_until="domcontentloaded", timeout=15000)
            return direct
        except Exception:
            pass

    id_search = f"https://www.theramenrater.com/?s={quote_plus(f'#{rid}:')}"
    try:
        page.goto(id_search, wait_until="commit", timeout=12000)
        url, _ = _follow_search(page, rid)
        if url:
            with _file_lock:
                save_url(rid, url)
            return url
    except Exception:
        pass

    name_query = f"{brand} {variety}".strip()
    name_search = f"https://www.theramenrater.com/?s={quote_plus(name_query)}"
    try:
        page.goto(name_search, wait_until="commit", timeout=12000)
        url, _ = _follow_search(page, rid)
        if url:
            with _file_lock:
                save_url(rid, url)
            return url
    except Exception:
        pass

    return None


def _extract_and_save_image(rid, page):
    """Extract the first content image from the loaded Playwright page and save as WebP.
    Returns True on success."""
    img_path = IMAGES_DIR / f"{rid}.webp"
    if img_path.exists():
        return True
    try:
        html = page.content()
    except Exception:
        return False

    match = re.search(
        r'<div[^>]*class="[^"]*entry-content[^"]*"[^>]*>.*?<img[^>]+src=["\']([^"\']+)',
        html, re.DOTALL)
    if not match:
        match = re.search(r'<article[^>]*>.*?<img[^>]+src=["\']([^"\']+)', html, re.DOTALL)
    if not match:
        return False

    src = match.group(1)
    if src.startswith("data:") or src.endswith(".svg"):
        return False

    try:
        resp = requests.get(src, headers=BROWSER_HEADERS, timeout=15)
        if resp.status_code != 200 or len(resp.content) < 1000:
            return False
        from PIL import Image as PILImage, ImageOps
        from io import BytesIO
        img = PILImage.open(BytesIO(resp.content))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        if img.width > MAX_WIDTH:
            ratio = MAX_WIDTH / img.width
            img = img.resize((MAX_WIDTH, int(img.height * ratio)), PILImage.LANCZOS)
        img.info.pop("exif", None)
        img_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(img_path, "WEBP", quality=WEBP_QUALITY)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Tkinter GUI
# ---------------------------------------------------------------------------

class ImageFinderApp:
    def __init__(self, num_workers=4):
        self._num_workers = num_workers
        self._results = _load_results()
        self._update_queue = queue.Queue()
        self._work_queue = queue.Queue()
        self._running = False
        self._total = 0
        self._processed = 0
        self._known_urls = {}

        self._root = tk.Tk()
        root = self._root
        root.title("Ramen Image Finder")
        root.geometry("920x700")
        root.minsize(750, 550)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_ui()
        self._load_data()
        self._poll_updates()
        root.mainloop()

    # ---- UI construction ----

    def _build_ui(self):
        root = self._root

        # Top bar: buttons + progress
        top = tk.Frame(root, bg=BG)
        top.pack(fill=tk.X, padx=10, pady=(10, 4))

        self._start_btn = tk.Button(
            top, text="▶  START", command=self._on_start,
            font=("Segoe UI", 10, "bold"), bg="#2a6041", fg=FG,
            activebackground="#1e8449", activeforeground="#fff", width=12)
        self._start_btn.pack(side=tk.LEFT, padx=(0, 6))

        self._retry_btn = tk.Button(
            top, text="↻  RETRY FAILED", command=self._on_retry,
            font=("Segoe UI", 10, "bold"), bg="#7d5a00", fg=FG,
            activebackground=ORANGE, activeforeground="#000", width=14,
            state=tk.DISABLED)
        self._retry_btn.pack(side=tk.LEFT, padx=(0, 6))

        self._stop_btn = tk.Button(
            top, text="■  STOP", command=self._on_stop,
            font=("Segoe UI", 10, "bold"), bg="#5a1a1a", fg=FG,
            activebackground=RED, activeforeground="#fff", width=10,
            state=tk.DISABLED)
        self._stop_btn.pack(side=tk.LEFT, padx=(0, 12))

        self._progress_var = tk.StringVar(value="Ready")
        tk.Label(top, textvariable=self._progress_var, font=("Segoe UI", 10),
                 fg=YELLOW, bg=BG, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Filter row
        filt = tk.Frame(root, bg=BG)
        filt.pack(fill=tk.X, padx=10, pady=(2, 4))
        tk.Label(filt, text="Show:", font=("Segoe UI", 9, "bold"),
                 fg=FG, bg=BG).pack(side=tk.LEFT, padx=(0, 6))

        self._filter_var = tk.StringVar(value="all")
        for val, label in [("all", "All"), ("no_url", "No URL"), ("no_image", "No Image"),
                           ("saved", "Saved"), ("pending", "Pending")]:
            tk.Radiobutton(filt, text=label, variable=self._filter_var, value=val,
                           font=("Segoe UI", 9), fg=FG, bg=BG, selectcolor=BG_DARK,
                           activebackground=BG, activeforeground=YELLOW,
                           command=self._apply_filter).pack(side=tk.LEFT, padx=4)

        # Stats row
        stats = tk.Frame(root, bg=BG)
        stats.pack(fill=tk.X, padx=10, pady=(0, 4))
        self._stats_var = tk.StringVar(value="")
        tk.Label(stats, textvariable=self._stats_var, font=("Segoe UI", 9),
                 fg="#aaa", bg=BG, anchor="w").pack(side=tk.LEFT)

        # Treeview
        tree_frame = tk.Frame(root, bg=BG)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 4))

        columns = ("id", "brand", "variety", "status", "url")
        self._tree = ttk.Treeview(tree_frame, columns=columns, show="headings",
                                  selectmode="browse")
        self._tree.heading("id", text="ID", anchor="w")
        self._tree.heading("brand", text="Brand", anchor="w")
        self._tree.heading("variety", text="Variety", anchor="w")
        self._tree.heading("status", text="Status", anchor="w")
        self._tree.heading("url", text="URL", anchor="w")

        self._tree.column("id", width=60, minwidth=50, stretch=False)
        self._tree.column("brand", width=140, minwidth=80)
        self._tree.column("variety", width=280, minwidth=120)
        self._tree.column("status", width=90, minwidth=70, stretch=False)
        self._tree.column("url", width=280, minwidth=100)

        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.bind("<Double-1>", self._on_double_click)

        # Style the treeview
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview",
                        background=BG_DARK, foreground=FG, fieldbackground=BG_DARK,
                        font=("Segoe UI", 9), rowheight=24)
        style.configure("Treeview.Heading",
                        background="#0f3460", foreground=FG,
                        font=("Segoe UI", 9, "bold"))
        style.map("Treeview",
                  background=[("selected", "#0f3460")],
                  foreground=[("selected", YELLOW)])

        self._tree.tag_configure("saved", foreground=GREEN)
        self._tree.tag_configure("no_url", foreground=RED)
        self._tree.tag_configure("no_image", foreground=ORANGE)
        self._tree.tag_configure("pending", foreground="#666")
        self._tree.tag_configure("searching", foreground=BLUE)
        self._tree.tag_configure("error", foreground=RED)

        # Detail bar
        detail = tk.Frame(root, bg=BG)
        detail.pack(fill=tk.X, padx=10, pady=(0, 10))

        self._detail_var = tk.StringVar(value="Double-click a row to open its URL in the browser")
        tk.Label(detail, textvariable=self._detail_var, font=("Segoe UI", 9),
                 fg="#aaa", bg=BG, anchor="w").pack(side=tk.LEFT, fill=tk.X, expand=True)

        tk.Button(detail, text="Open URL", command=self._open_selected_url,
                  font=("Segoe UI", 9), bg=BG_DARK, fg=BLUE,
                  activebackground="#0f3460", activeforeground=YELLOW).pack(side=tk.RIGHT, padx=(6, 0))

        tk.Button(detail, text="Retry Selected", command=self._retry_selected,
                  font=("Segoe UI", 9), bg=BG_DARK, fg=ORANGE,
                  activebackground="#0f3460", activeforeground=YELLOW).pack(side=tk.RIGHT, padx=(6, 0))

    # ---- Data loading ----

    def _load_data(self):
        try:
            _ensure_playwright_browser()
            _ensure_ublock()
        except Exception as e:
            self._progress_var.set(f"Setup error: {e}")

        ramen_list = load_ramen()
        has_image = {r["id"] for r in ramen_list if (IMAGES_DIR / f"{r['id']}.webp").exists()}
        self._known_urls = load_urls()
        pop = load_popularity()

        self._all_ramen = {}
        needs = []
        for r in ramen_list:
            rid = r["id"]
            if rid in has_image:
                continue
            self._all_ramen[rid] = r
            prev = self._results.get(str(rid), {})
            needs.append((rid, r, prev))

        needs.sort(key=lambda t: (-(pop.get(str(t[0]), 0)), t[0]))

        for rid, r, prev in needs:
            status = prev.get("status", STATUS_PENDING)
            url = prev.get("url", "")
            tag = self._tag_for_status(status)
            self._tree.insert("", tk.END, iid=str(rid),
                              values=(rid, r.get("brand", ""), r.get("variety", ""),
                                      status, url),
                              tags=(tag,))

        self._update_stats()
        self._progress_var.set(f"{len(needs)} ramen missing images")

    def _tag_for_status(self, status):
        if status == STATUS_SAVED:
            return "saved"
        if status == STATUS_NO_URL:
            return "no_url"
        if status == STATUS_NO_IMAGE:
            return "no_image"
        if status == STATUS_ERROR:
            return "error"
        if "search" in status:
            return "searching"
        return "pending"

    def _update_stats(self):
        counts = {STATUS_PENDING: 0, STATUS_SAVED: 0, STATUS_NO_URL: 0,
                  STATUS_NO_IMAGE: 0, STATUS_ERROR: 0, "other": 0}
        for iid in self._tree.get_children():
            st = self._tree.item(iid, "values")[3]
            if st in counts:
                counts[st] += 1
            else:
                counts["other"] += 1
        total = sum(counts.values())
        self._stats_var.set(
            f"Total: {total}  |  Saved: {counts[STATUS_SAVED]}  |  "
            f"No URL: {counts[STATUS_NO_URL]}  |  No Image: {counts[STATUS_NO_IMAGE]}  |  "
            f"Pending: {counts[STATUS_PENDING]}  |  Errors: {counts[STATUS_ERROR]}")

        has_failures = counts[STATUS_NO_URL] + counts[STATUS_NO_IMAGE] + counts[STATUS_ERROR] > 0
        self._retry_btn.config(state=tk.NORMAL if (has_failures and not self._running) else tk.DISABLED)

    # ---- Filter ----

    def _apply_filter(self):
        filt = self._filter_var.get()
        status_map = {
            "all": None,
            "no_url": STATUS_NO_URL,
            "no_image": STATUS_NO_IMAGE,
            "saved": STATUS_SAVED,
            "pending": STATUS_PENDING,
        }
        target = status_map[filt]
        for iid in self._tree.get_children():
            vals = self._tree.item(iid, "values")
            if target is None or vals[3] == target:
                self._tree.reattach(iid, "", tk.END)
            else:
                self._tree.detach(iid)

    # ---- Update loop ----

    def _poll_updates(self):
        try:
            while True:
                rid, status, url = self._update_queue.get_nowait()
                iid = str(rid)
                try:
                    old = self._tree.item(iid, "values")
                    self._tree.item(iid, values=(old[0], old[1], old[2], status, url or old[4]))
                    self._tree.item(iid, tags=(self._tag_for_status(status),))
                except tk.TclError:
                    pass

                self._results[str(rid)] = {"status": status, "url": url or ""}
                self._processed += 1
                self._progress_var.set(
                    f"Processing: {self._processed}/{self._total}  "
                    f"({self._processed * 100 // max(self._total, 1)}%)")

                if status in (STATUS_SAVED, STATUS_NO_URL, STATUS_NO_IMAGE, STATUS_ERROR):
                    self._update_stats()
                    filt = self._filter_var.get()
                    if filt != "all":
                        self._apply_filter()
        except queue.Empty:
            pass

        if self._running and self._processed >= self._total:
            self._on_done()

        self._root.after(100, self._poll_updates)

    def _on_done(self):
        self._running = False
        _save_results(self._results)
        self._start_btn.config(state=tk.NORMAL)
        self._stop_btn.config(state=tk.DISABLED)
        self._update_stats()
        self._apply_filter()
        self._progress_var.set(
            f"Done — {self._processed}/{self._total} processed. "
            f"Use filter or Retry Failed to revisit.")

    # ---- Actions ----

    def _on_start(self):
        items = []
        for iid in self._tree.get_children():
            vals = self._tree.item(iid, "values")
            status = vals[3]
            if status in (STATUS_PENDING, STATUS_ERROR):
                rid = int(vals[0])
                if rid in self._all_ramen:
                    items.append(rid)
        if not items:
            self._progress_var.set("Nothing to process — all items attempted already")
            return
        self._start_processing(items)

    def _on_retry(self):
        items = []
        for iid in self._tree.get_children():
            vals = self._tree.item(iid, "values")
            status = vals[3]
            if status in (STATUS_NO_URL, STATUS_NO_IMAGE, STATUS_ERROR):
                rid = int(vals[0])
                if rid in self._all_ramen:
                    items.append(rid)
                    self._tree.item(iid, values=(vals[0], vals[1], vals[2], STATUS_PENDING, vals[4]))
                    self._tree.item(iid, tags=("pending",))
        if not items:
            self._progress_var.set("No failed items to retry")
            return
        self._start_processing(items)

    def _retry_selected(self):
        sel = self._tree.selection()
        if not sel:
            return
        iid = sel[0]
        vals = self._tree.item(iid, "values")
        rid = int(vals[0])
        if rid not in self._all_ramen:
            return
        self._tree.item(iid, values=(vals[0], vals[1], vals[2], STATUS_PENDING, vals[4]))
        self._tree.item(iid, tags=("pending",))
        self._start_processing([rid])

    def _start_processing(self, rids):
        _shutdown.clear()
        self._running = True
        self._processed = 0
        self._total = len(rids)
        self._start_btn.config(state=tk.DISABLED)
        self._stop_btn.config(state=tk.NORMAL)
        self._retry_btn.config(state=tk.DISABLED)
        self._progress_var.set(f"Starting {self._total} items with {self._num_workers} workers…")

        self._known_urls = load_urls()

        for rid in rids:
            self._work_queue.put(rid)

        for i in range(self._num_workers):
            t = threading.Thread(target=self._worker, args=(i,), daemon=True)
            t.start()

    def _on_stop(self):
        _shutdown.set()
        self._progress_var.set("Stopping…")
        self._stop_btn.config(state=tk.DISABLED)

    def _on_close(self):
        _shutdown.set()
        _save_results(self._results)
        self._root.destroy()

    # ---- Worker ----

    def _worker(self, worker_id):
        pw, context, page = None, None, None
        try:
            pw, context, page = _create_browser(worker_id)
        except Exception:
            self._drain_queue_as_error()
            return

        while not _shutdown.is_set():
            try:
                rid = self._work_queue.get_nowait()
            except queue.Empty:
                break

            ramen = self._all_ramen.get(rid)
            if not ramen:
                self._update_queue.put((rid, STATUS_ERROR, ""))
                self._work_queue.task_done()
                continue

            img_path = IMAGES_DIR / f"{rid}.webp"
            if img_path.exists():
                self._update_queue.put((rid, STATUS_SAVED, self._known_urls.get(str(rid), "")))
                self._work_queue.task_done()
                continue

            brand = ramen.get("brand", "")
            variety = ramen.get("variety", "")

            self._update_queue.put((rid, STATUS_SEARCHING, ""))

            url = _find_review_url(page, rid, brand, variety, self._known_urls)

            if not url:
                self._update_queue.put((rid, STATUS_NO_URL, ""))
                self._work_queue.task_done()
                continue

            self._update_queue.put((rid, STATUS_URL_FOUND, url))

            if _extract_and_save_image(rid, page):
                self._update_queue.put((rid, STATUS_SAVED, url))
            else:
                self._update_queue.put((rid, STATUS_NO_IMAGE, url))

            self._work_queue.task_done()

        try:
            if context:
                context.close()
            if pw:
                pw.stop()
        except Exception:
            pass

    def _drain_queue_as_error(self):
        while True:
            try:
                rid = self._work_queue.get_nowait()
                self._update_queue.put((rid, STATUS_ERROR, ""))
                self._work_queue.task_done()
            except queue.Empty:
                break

    # ---- Tree interaction ----

    def _on_double_click(self, event):
        self._open_selected_url()

    def _open_selected_url(self):
        sel = self._tree.selection()
        if not sel:
            return
        vals = self._tree.item(sel[0], "values")
        url = vals[4]
        if url:
            import webbrowser
            webbrowser.open(url)
        else:
            rid = vals[0]
            import webbrowser
            webbrowser.open(f"https://www.theramenrater.com/?s={quote_plus(f'#{rid}:')}")

    # ---- Treeview selection tracking ----

    # Intentionally minimal — the double-click + buttons cover all actions.


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Ramen Image Finder GUI")
    parser.add_argument("-w", "--workers", type=int, default=4,
                        help="Number of parallel browser workers (default: 4)")
    args = parser.parse_args()
    ImageFinderApp(num_workers=max(1, args.workers))


if __name__ == "__main__":
    main()
