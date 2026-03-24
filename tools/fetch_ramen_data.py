#!/usr/bin/env python3
"""
Ramen Rater Data Pipeline

Downloads The Big List xlsx from theramenrater.com, converts it to JSON,
and fetches product images via Bing image search.
Each step skips work already done.

Usage:
    python fetch_ramen_data.py            # Process all ramen
    python fetch_ramen_data.py --limit 10 # Process up to 10 ramen that still need images
"""

import json
import os
import random
import re
import sys
import time
import argparse
from pathlib import Path
from io import BytesIO

import requests
from openpyxl import load_workbook

import threading
import tkinter as tk

XLSX_URL = "https://www.theramenrater.com/wp-content/uploads/2025/11/11212025The-Ramen-Rater.xlsx"
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
IMAGES_DIR = ROOT_DIR / "images" / "ramen"
BRAND_DIR = ROOT_DIR / "images" / "brand"
CACHE_DIR = ROOT_DIR / "tools" / ".cache"
XLSX_PATH = CACHE_DIR / "big-list.xlsx"
XLSX_ETAG_PATH = CACHE_DIR / ".big-list-etag"

HEADERS = {"User-Agent": "RamenRaterFanApp/1.0 (personal project; respectful scraping)"}

def _load_typos():
    typo_path = Path(__file__).resolve().parent / "typos.json"
    if typo_path.exists():
        with open(typo_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

_TYPOS = _load_typos()
STYLE_TYPOS = _TYPOS.get('style', {})
BRAND_TYPOS = _TYPOS.get('brand', {})
TEXT_TYPOS = _TYPOS.get('text', {})


def download_xlsx():
    """Download the xlsx, skipping if the server copy hasn't changed.
    Returns True if the file was updated, False if unchanged."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    headers = dict(HEADERS)

    if XLSX_PATH.exists() and XLSX_ETAG_PATH.exists():
        saved_etag = XLSX_ETAG_PATH.read_text().strip()
        headers['If-None-Match'] = saved_etag

    if XLSX_PATH.exists():
        from email.utils import formatdate
        mtime = os.path.getmtime(XLSX_PATH)
        headers['If-Modified-Since'] = formatdate(mtime, usegmt=True)

    print(f"Checking xlsx at {XLSX_URL}...")
    resp = requests.get(XLSX_URL, headers=headers, timeout=60)

    if resp.status_code == 304:
        print("  xlsx unchanged, skipping download.")
        return False

    resp.raise_for_status()
    XLSX_PATH.write_bytes(resp.content)
    print(f"  Downloaded ({len(resp.content) / 1024:.0f} KB)")

    etag = resp.headers.get('ETag')
    if etag:
        XLSX_ETAG_PATH.write_text(etag)

    return True


def parse_xlsx():
    print(f"Parsing {XLSX_PATH}...")
    wb = load_workbook(XLSX_PATH, read_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        print("  ERROR: Spreadsheet is empty")
        return []

    header_idx = 0
    for i, row in enumerate(rows[:5]):
        cells = [str(c).strip().lower() if c else '' for c in row]
        if any('review' in c for c in cells):
            header_idx = i
            break

    headers_raw = [str(c).strip() if c else '' for c in rows[header_idx]]
    print(f"  Headers (row {header_idx}): {headers_raw}")

    col_map = {}
    for i, h in enumerate(headers_raw):
        hl = h.lower()
        if 'review' in hl and '#' in hl:
            col_map['id'] = i
        elif hl == 'brand':
            col_map['brand'] = i
        elif hl == 'variety':
            col_map['variety'] = i
        elif hl == 'style':
            col_map['style'] = i
        elif hl == 'country':
            col_map['country'] = i
        elif hl == 'stars':
            col_map['stars'] = i

    required = ['id', 'brand', 'variety']
    missing = [k for k in required if k not in col_map]
    if missing:
        print(f"  ERROR: Missing columns: {missing}")
        return []

    ramen_list = []
    for row in rows[header_idx + 1:]:
        try:
            raw_id = row[col_map['id']]
            if raw_id is None:
                continue
            review_id = int(float(str(raw_id)))
        except (ValueError, TypeError):
            continue

        brand = str(row[col_map.get('brand', 0)] or '').strip()
        brand = BRAND_TYPOS.get(brand, brand)
        variety = str(row[col_map.get('variety', 0)] or '').strip()
        for typo, fix in TEXT_TYPOS.items():
            variety = variety.replace(typo, fix)
        if not variety:
            continue

        style = str(row[col_map.get('style', 0)] or '').strip() if 'style' in col_map else ''
        style = STYLE_TYPOS.get(style.lower(), style)
        country = str(row[col_map.get('country', 0)] or '').strip() if 'country' in col_map else ''

        stars = None
        if 'stars' in col_map:
            raw_stars = row[col_map['stars']]
            if raw_stars is not None:
                try:
                    stars = float(raw_stars)
                except (ValueError, TypeError):
                    pass

        ramen_list.append({
            'id': review_id,
            'brand': brand,
            'variety': variety,
            'style': style,
            'country': country,
            'stars': stars,
            'url': f"https://www.theramenrater.com/?s={review_id}",
            'image': False,
        })

    wb.close()
    print(f"  Parsed {len(ramen_list)} ramen entries")
    return ramen_list


def update_image_flags(ramen_list):
    """Set the image flag for any ramen that already has a downloaded .webp."""
    existing = set()
    if IMAGES_DIR.exists():
        for f in IMAGES_DIR.glob("*.webp"):
            if f.stem.isdigit():
                existing.add(int(f.stem))
    count = 0
    for r in ramen_list:
        has = r['id'] in existing
        r['image'] = has
        if has:
            count += 1
    return count


def save_json(ramen_list):
    DATA_DIR.mkdir(exist_ok=True)
    out_path = DATA_DIR / "ramen.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(ramen_list, f, ensure_ascii=False)
    print(f"  Saved {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")


BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def _search_bing(query):
    """Scrape Bing image search results. Returns list of image URLs."""
    from urllib.parse import quote_plus
    url = f"https://www.bing.com/images/search?q={quote_plus(query)}&form=HDRSC2&first=1"
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
        resp.raise_for_status()
        urls = re.findall(r'murl&quot;:&quot;(https?://[^&]+?)&quot;', resp.text)
        urls = [u for u in urls if not u.endswith('.svg')]
        return urls[:5]
    except Exception as e:
        print(f"      Bing: {type(e).__name__}: {e}")
        return []


UBLOCK_ID = "ddkjiahejlhfcafbddmgiahcphecmpfh"
UBLOCK_DIR = CACHE_DIR / "ublock"
UBLOCK_VERSION_FILE = CACHE_DIR / "ublock-version"
PW_VERSION_FILE = CACHE_DIR / "playwright-version"


def _ensure_ublock():
    """Download/update uBlock Origin Lite if needed. Returns path to unpacked extension."""
    import zipfile

    crx_url = (
        f"https://clients2.google.com/service/update2/crx"
        f"?response=redirect&prodversion=130.0&acceptformat=crx2,crx3"
        f"&x=id%3D{UBLOCK_ID}%26uc"
    )

    manifest_path = UBLOCK_DIR / "manifest.json"
    local_ver = ""
    if UBLOCK_VERSION_FILE.exists():
        local_ver = UBLOCK_VERSION_FILE.read_text().strip()

    # Check for update via HEAD request ETag
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

    # CRX3 format: magic(4) + version(4) + header_len(4) + header + ZIP
    # Find the ZIP start (PK signature)
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

    # Read actual extension version from manifest
    if manifest_path.exists():
        import json as _json
        mf = _json.loads(manifest_path.read_text(encoding="utf-8"))
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


class ScraperControlPanel:
    """Floating tkinter window for live control during scraping.
    
    Tkinter must own the main thread, so the scraping work runs in a
    background thread while this panel runs mainloop() on main.
    """

    def __init__(self):
        self.engine = "google"
        self._root = tk.Tk()
        root = self._root
        root.title("Ramen Scraper")
        root.attributes("-topmost", True)
        root.resizable(False, False)
        root.geometry("280x170")
        root.configure(bg="#1a1a2e")

        tk.Label(root, text="Search Engine", font=("Segoe UI", 10, "bold"),
                 fg="#e0e0e0", bg="#1a1a2e").pack(pady=(10, 2))

        self._engine_var = tk.StringVar(value="google")
        frame = tk.Frame(root, bg="#1a1a2e")
        frame.pack()
        for val, label in [("google", "Google"), ("bing", "Bing")]:
            tk.Radiobutton(frame, text=label, variable=self._engine_var, value=val,
                           command=self._on_engine_change,
                           fg="#e0e0e0", bg="#1a1a2e", selectcolor="#16213e",
                           activebackground="#1a1a2e", activeforeground="#f7d354",
                           font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=10)

        self._progress_var = tk.StringVar(value="Starting...")
        tk.Label(root, textvariable=self._progress_var, font=("Segoe UI", 9),
                 fg="#a0a0a0", bg="#1a1a2e").pack(pady=(8, 2))

        self._status_var = tk.StringVar(value="")
        tk.Label(root, textvariable=self._status_var, font=("Segoe UI", 8),
                 fg="#666", bg="#1a1a2e", wraplength=260).pack(pady=(0, 8))

        root.protocol("WM_DELETE_WINDOW", lambda: None)

    def _on_engine_change(self):
        self.engine = self._engine_var.get()

    def set_progress(self, text):
        if self._root:
            self._root.after(0, lambda: self._progress_var.set(text))

    def set_status(self, text):
        if self._root:
            self._root.after(0, lambda: self._status_var.set(text))

    def run_with_panel(self, fn, *args, **kwargs):
        """Run fn in a background thread while tkinter mainloop owns the main thread."""
        result = [None]
        error = [None]

        def _worker():
            try:
                result[0] = fn(*args, **kwargs)
            except Exception as e:
                error[0] = e
            finally:
                self._root.after(0, self._root.destroy)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        self._root.mainloop()
        t.join()
        if error[0]:
            raise error[0]
        return result[0]

    def destroy(self):
        if self._root:
            try:
                self._root.destroy()
            except Exception:
                pass


def _create_popularity_browser():
    """Launch a Playwright browser with uBlock Origin Lite. Returns (playwright, context, page)."""
    from playwright.sync_api import sync_playwright

    _ensure_playwright_browser()
    ext_path = _ensure_ublock()

    pw = sync_playwright().start()
    user_data = str(CACHE_DIR / "pw-profile")
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


DEBUG_LOG = CACHE_DIR / "popularity-debug.log"


def _debug(msg):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(DEBUG_LOG, 'a', encoding='utf-8') as f:
        f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")


def _bing_web_result_count(page, query, brand):
    """Get estimated result count from Bing web search via Playwright. Returns int."""
    from urllib.parse import quote_plus
    url = f"https://www.bing.com/search?q={quote_plus(query)}"
    _debug(f"QUERY: {query}")
    _debug(f"  URL: {url}")
    _debug(f"  BRAND: {brand}")
    try:
        page.goto(url, wait_until="load", timeout=20000)

        el = page.wait_for_selector(".sb_count", timeout=5000)
        if not el:
            raise TimeoutError()
    except Exception:
        print(f"      Waiting for CAPTCHA — solve it in the browser, will resume automatically...")
        _debug(f"  .sb_count not found in 5s, waiting indefinitely (CAPTCHA?)")
        try:
            page.wait_for_selector(".sb_count", timeout=0)
        except Exception as e:
            _debug(f"  FAILED: {type(e).__name__}: {e}")
            _debug(f"  PAGE TITLE: {page.title()}")
            _debug(f"  PAGE URL: {page.url}")
            body_text = page.inner_text("body")[:500]
            _debug(f"  BODY START: {body_text}")
            return 0

    # Validate: the brand name must appear in the search results
    try:
        results_text = page.inner_text("#b_results")
    except Exception:
        results_text = ""
    brand_lower = brand.lower()
    if brand_lower not in results_text.lower():
        _debug(f"  BOGUS PAGE: brand '{brand}' not found in results, skipping")
        print(f"      Bogus results (brand not found on page), skipping")
        return 0

    try:
        text = page.inner_text(".sb_count")
        _debug(f"  .sb_count raw text: {repr(text)}")
        match = re.search(r'([\d,\.]+)', text)
        if match:
            count = int(match.group(1).replace(',', '').replace('.', ''))
            _debug(f"  PARSED: {count}")
            _maybe_click_result(page, "bing")
            return count
        else:
            _debug(f"  NO MATCH in: {repr(text)}")
    except Exception as e:
        _debug(f"  ERROR reading .sb_count: {type(e).__name__}: {e}")
    return 0


def _maybe_click_result(page, engine):
    """40% chance to click a random organic result, dwell 3-12s, then go back.
    Prefers The Ramen Rater links if present."""
    if random.random() > 0.4:
        return
    try:
        if engine == "google":
            links = page.query_selector_all("#search a h3")
        else:
            links = page.query_selector_all("#b_results h2 a")
        if not links:
            return
        # Prefer The Ramen Rater links
        rr_links = []
        for link in links:
            href = link.evaluate('el => el.closest("a")?.href || ""')
            if 'theramenrater' in href.lower():
                rr_links.append(link)
        pick = random.choice(rr_links) if rr_links else random.choice(links)
        pick.scroll_into_view_if_needed()
        time.sleep(random.uniform(0.3, 1.0))
        pick.click()
        dwell = random.uniform(3, 12)
        _debug(f"  DWELL: clicked random result, staying {dwell:.1f}s")
        time.sleep(dwell)
        page.go_back(wait_until="load", timeout=10000)
    except Exception as e:
        _debug(f"  DWELL error: {type(e).__name__}: {e}")


def _google_web_result_count(page, query, brand):
    """Get estimated result count from Google web search via Playwright. Returns int."""
    from urllib.parse import quote_plus
    url = f"https://www.google.com/search?q={quote_plus(query)}"
    _debug(f"GOOGLE QUERY: {query}")
    _debug(f"  URL: {url}")
    _debug(f"  BRAND: {brand}")
    try:
        page.goto(url, wait_until="load", timeout=20000)
        page.wait_for_selector("#search", timeout=5000)
    except Exception:
        print(f"      Waiting for CAPTCHA — solve it in the browser, will resume automatically...")
        _debug(f"  #search not found in 5s, waiting indefinitely (CAPTCHA?)")
        try:
            page.wait_for_selector("#search", timeout=0)
        except Exception as e:
            _debug(f"  FAILED: {type(e).__name__}: {e}")
            _debug(f"  PAGE TITLE: {page.title()}")
            _debug(f"  PAGE URL: {page.url}")
            body_text = page.inner_text("body")[:500]
            _debug(f"  BODY START: {body_text}")
            return 0

    # Click "Tools" to reveal the result count
    try:
        # sleep for 1-3 seconds
        time.sleep(random.uniform(1, 3))
        tools_btn = page.query_selector("#hdtb-tls") or page.query_selector("div.hdtb-mitem >> text=Tools")
        if tools_btn:
            tools_btn.click()
            page.wait_for_selector("#result-stats", timeout=3000)
            _debug(f"  Clicked Tools button to reveal result stats")
        else:
            _debug(f"  Tools button not found, trying #result-stats directly")
    except Exception as e:
        _debug(f"  Tools click issue: {type(e).__name__}: {e}")

    try:
        results_text = page.inner_text("#search")
    except Exception:
        results_text = ""
    brand_lower = brand.lower()
    if brand_lower not in results_text.lower():
        _debug(f"  BOGUS PAGE: brand '{brand}' not found in results, skipping")
        print(f"      Bogus results (brand not found on page), skipping")
        return 0

    try:
        text = page.inner_text("#result-stats")
        _debug(f"  #result-stats raw text: {repr(text)}")
        match = re.search(r'([\d,\.]+)\s+result', text)
        if match:
            count = int(match.group(1).replace(',', '').replace('.', ''))
            _debug(f"  PARSED: {count}")
            _maybe_click_result(page, "google")
            return count
        else:
            _debug(f"  NO MATCH in: {repr(text)}")
    except Exception as e:
        _debug(f"  ERROR reading #result-stats: {type(e).__name__}: {e}")
    return 0


def _download_image(img_url, out_path, has_pillow, Image):
    """Download a single image URL and save as compressed WebP. Returns True on success."""
    try:
        resp = requests.get(img_url, headers={**BROWSER_HEADERS, "Accept": "image/webp,image/*,*/*;q=0.8"}, timeout=15)
        resp.raise_for_status()

        content_type = resp.headers.get('Content-Type', '')
        if 'html' in content_type:
            print(f"      Skipped (got HTML instead of image)")
            return False

        if len(resp.content) < 1000:
            print(f"      Skipped (only {len(resp.content)} bytes)")
            return False

        if has_pillow:
            from PIL import ImageOps
            img = Image.open(BytesIO(resp.content))
            img = ImageOps.exif_transpose(img)
            img = img.convert('RGB')
            if img.width > MAX_WIDTH:
                ratio = MAX_WIDTH / img.width
                img = img.resize((MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)
            img.save(out_path, 'WEBP', quality=WEBP_QUALITY)
        else:
            out_path.write_bytes(resp.content)

        return True

    except requests.RequestException as e:
        print(f"      Download failed: {type(e).__name__}: {e}")
    except Exception as e:
        print(f"      Image processing failed: {type(e).__name__}: {e}")
    return False


MAX_WIDTH = 400
WEBP_QUALITY = 75
MAX_FILE_SIZE = 80_000  # 80KB threshold for recompression


def _recompress_dir(directory, patterns, fmt, quality, Image):
    """Recompress images in a directory that exceed size/width limits. Returns count."""
    if not directory.exists():
        return 0

    files = []
    for pat in patterns:
        files.extend(directory.glob(pat))
    if not files:
        return 0

    from PIL import ImageOps

    recompressed = 0
    for f in files:
        try:
            file_size = f.stat().st_size
            img = Image.open(f)
            reasons = []

            # Check EXIF orientation (tag 0x0112; value 1 = normal)
            exif_orientation = None
            try:
                exif = img.getexif()
                exif_orientation = exif.get(0x0112, 1)
            except Exception:
                pass
            if exif_orientation and exif_orientation != 1:
                img = ImageOps.exif_transpose(img)
                reasons.append(f"EXIF rotated (tag={exif_orientation})")

            if file_size > MAX_FILE_SIZE:
                reasons.append(f"too large ({file_size//1024}KB)")
            if img.width > MAX_WIDTH:
                reasons.append(f"too wide ({img.width}px)")

            if not reasons:
                continue

            if fmt == 'PNG':
                img = img.convert('RGBA')
            else:
                img = img.convert('RGB')

            if img.width > MAX_WIDTH:
                ratio = MAX_WIDTH / img.width
                img = img.resize((MAX_WIDTH, int(img.height * ratio)), Image.LANCZOS)

            save_kwargs = {'optimize': True} if fmt == 'PNG' else {'quality': quality}
            img.save(f, fmt, **save_kwargs)
            new_size = f.stat().st_size
            recompressed += 1
            print(f"    {f.name}: {', '.join(reasons)} -> {new_size//1024}KB ({img.width}x{img.height})")
        except Exception as e:
            print(f"    Error checking {f.name}: {e}")

    return recompressed


TOOLS_DIR = ROOT_DIR / "tools"


class OrientationChecker:
    """Long-running Node.js process for checking image orientation via tesseract.js OSD."""

    def __init__(self):
        import subprocess as sp
        script = TOOLS_DIR / "fix-orientation.js"
        node_modules = CACHE_DIR / "node_modules"

        if not script.exists() or not node_modules.exists():
            raise FileNotFoundError("fix-orientation.js or node_modules not found")

        self._proc = sp.Popen(
            ["node", str(script), "--server"],
            stdin=sp.PIPE, stdout=sp.PIPE, stderr=None,
            text=True, bufsize=1,
        )

    def check(self, image_path):
        """Check/fix orientation of a single image. Returns dict with status."""
        if self._proc.poll() is not None:
            return {"status": "error", "reason": "worker exited"}
        try:
            print(f"      OSD: sending {Path(image_path).name}...", end="", flush=True)
            self._proc.stdin.write(str(image_path) + "\n")
            self._proc.stdin.flush()
            line = self._proc.stdout.readline().strip()
            if line:
                result = json.loads(line)
                print(f" {result.get('status', '?')}")
                return result
            print(" no response")
            return {"status": "error", "reason": "no response"}
        except Exception as e:
            print(f" error: {e}")
            return {"status": "error", "reason": str(e)}

    def close(self):
        if self._proc and self._proc.poll() is None:
            self._proc.stdin.close()
            self._proc.wait(timeout=10)


def recompress_existing():
    """Check all existing ramen and brand images, recompress any that are too large."""
    try:
        from PIL import Image
    except ImportError:
        print("  Pillow not installed, skipping recompression check.")
        return

    # Lowercase all brand logo filenames for consistent matching
    if BRAND_DIR.exists():
        for f in BRAND_DIR.iterdir():
            lower_name = f.name.lower()
            if f.name != lower_name:
                dest = f.with_name(lower_name)
                if not dest.exists():
                    f.rename(dest)
                    print(f"    Renamed {f.name} -> {lower_name}")

    ramen_count = _recompress_dir(IMAGES_DIR, ['*.webp'], 'WEBP', WEBP_QUALITY, Image)
    brand_count = _recompress_dir(BRAND_DIR, ['*.png'], 'PNG', None, Image)

    total = ramen_count + brand_count
    if total:
        print(f"  Recompressed {total} images ({ramen_count} ramen, {brand_count} brand logos)")
    else:
        ramen_files = len(list(IMAGES_DIR.glob('*.webp'))) if IMAGES_DIR.exists() else 0
        brand_files = len(list(BRAND_DIR.glob('*.png')) + list(BRAND_DIR.glob('*.PNG'))) if BRAND_DIR.exists() else 0
        print(f"  All {ramen_files + brand_files} images are properly compressed")



def fetch_images_and_popularity(ramen_list, limit=None, panel=None):
    """Fetch product images and popularity scores together. Saves JSON after each update."""
    IMAGES_DIR.mkdir(exist_ok=True)

    try:
        from PIL import Image
        has_pillow = True
    except ImportError:
        print("  WARNING: Pillow not installed. Saving raw images.")
        has_pillow = False
        Image = None

    existing = set()
    for f in IMAGES_DIR.glob("*.webp"):
        if f.stem.isdigit():
            existing.add(int(f.stem))

    needed = [r for r in ramen_list
              if r['id'] not in existing
              or not r.get('popularity')
              or (r['id'] in existing and not r.get('orientation_checked'))]

    if not needed:
        print(f"Images & popularity: everything up to date ({len(existing)} images).")
        return

    any_need_popularity = any(not r.get('popularity') for r in needed)

    if limit is not None:
        batch = needed[:limit]
        print(f"Processing: {len(needed)} need work -- doing {len(batch)} this run")
    else:
        batch = needed
        print(f"Processing: {len(batch)} ramen need images and/or popularity")

    pw, context, page = None, None, None
    if any_need_popularity:
        try:
            pw, context, page = _create_popularity_browser()
            print("  Launched browser for popularity lookups")
        except Exception as e:
            print(f"  WARNING: Could not launch browser ({e}). Skipping popularity.")
            print("  Run: bash tools/setup.sh")

    # Start orientation checker (long-running Node process)
    osd = None
    try:
        osd = OrientationChecker()
        print("  Started orientation checker (tesseract.js)")
    except FileNotFoundError:
        print("  Orientation checker not available (run: cd tools/.cache && npm install)")
    except Exception as e:
        print(f"  Orientation checker failed to start: {e}")

    downloaded = 0
    scored = 0
    oriented = 0
    errors = 0
    no_results = 0

    def _get_engine():
        return panel.engine if panel else "google"

    try:
        for i, r in enumerate(batch):
            out_path = IMAGES_DIR / f"{r['id']}.webp"
            needs_image = not out_path.exists()
            has_image = out_path.exists()
            existing_pop = r.get('popularity')
            needs_popularity = not existing_pop
            changed = False

            _debug(f"--- #{r['id']} {r['brand']} - {r['variety']}")
            _debug(f"  existing popularity value: {repr(existing_pop)} -> needs_popularity={needs_popularity}")

            if panel:
                panel.set_progress(f"[{i+1}/{len(batch)}] {r['variety'][:30]}")
                panel.set_status(f"Engine: {_get_engine().title()}")

            print(f"    [{i+1}/{len(batch)}] #{r['id']} {r['brand']} - {r['variety']}")

            # --- Image ---
            if needs_image:
                query = f'{r["brand"]} {r["variety"]} packaging the ramen rater'
                candidates = _search_bing(query)

                if not candidates:
                    no_results += 1
                    print(f"      Image: no candidates found")
                else:
                    saved = False
                    for j, img_url in enumerate(candidates):
                        print(f"      Image: trying {j+1}/{len(candidates)}: {img_url[:100]}")
                        if _download_image(img_url, out_path, has_pillow, Image):
                            saved = True
                            downloaded += 1
                            r['image'] = True
                            has_image = True
                            changed = True
                            print(f"      Image: downloaded")
                            break
                    if not saved:
                        errors += 1
                        print(f"      Image: FAILED (all {len(candidates)} candidates failed)")

                time.sleep(0.3)
            else:
                print(f"      Image: ok")

            # --- Orientation ---
            needs_orient = has_image and not r.get('orientation_checked')
            if needs_orient and has_pillow:
                # EXIF pass first (free, no OCR needed)
                from PIL import ImageOps
                try:
                    pil_img = Image.open(out_path)
                    exif_orient = None
                    try:
                        exif_orient = pil_img.getexif().get(0x0112, 1)
                    except Exception:
                        pass
                    if exif_orient and exif_orient != 1:
                        pil_img = ImageOps.exif_transpose(pil_img)
                        pil_img = pil_img.convert('RGB')
                        pil_img.save(out_path, 'WEBP', quality=WEBP_QUALITY)
                        print(f"      Orientation (EXIF): FIXED (tag={exif_orient})")
                        oriented += 1
                    else:
                        print(f"      Orientation (EXIF): ok")
                except Exception as e:
                    _debug(f"  EXIF error for {out_path.name}: {e}")
                    print(f"      Orientation (EXIF): error ({e})")

                # OCR/OSD pass
                if osd:
                    osd_result = osd.check(out_path)
                    status = osd_result.get("status", "error")
                    if status == "fixed":
                        rot = osd_result.get("rotation", "?")
                        conf = osd_result.get("confidence", "?")
                        print(f"      Orientation (OSD): FIXED — rotated {rot}° (confidence: {conf})")
                        oriented += 1
                    elif status == "ok":
                        print(f"      Orientation (OSD): ok")
                    elif status == "skip":
                        print(f"      Orientation (OSD): skipped ({osd_result.get('reason', '')})")
                    else:
                        reason = osd_result.get("reason", "unknown")
                        _debug(f"  OSD error for {out_path.name}: {reason}")
                        print(f"      Orientation (OSD): error ({reason})")
                else:
                    print(f"      Orientation (OSD): —")

                r['orientation_checked'] = True
                changed = True
            elif has_image:
                print(f"      Orientation: already checked")
            else:
                print(f"      Orientation: no image")

            # --- Popularity ---
            if needs_popularity and page:
                pop_query = f'"{r["brand"]}" {r["variety"]}'
                engine = _get_engine()
                time.sleep(random.uniform(3, 12))
                if engine == "google":
                    count = _google_web_result_count(page, pop_query, r["brand"])
                else:
                    count = _bing_web_result_count(page, pop_query, r["brand"])
                if count > 0:
                    r['popularity'] = count
                    scored += 1
                    changed = True
                    print(f"      Popularity: {count:,} ({engine})")
                    if panel:
                        panel.set_status(f"{r['variety'][:25]}: {count:,}")
                else:
                    print(f"      Popularity: no results ({engine})")
            elif existing_pop:
                print(f"      Popularity: {existing_pop:,}")
            else:
                print(f"      Popularity: —")

            if changed:
                save_json(ramen_list)
    finally:
        if osd:
            try:
                osd.close()
            except Exception:
                pass
        if context:
            context.close()
        if pw:
            pw.stop()

    parts = []
    if downloaded: parts.append(f"{downloaded} images downloaded")
    if oriented: parts.append(f"{oriented} orientations fixed")
    if scored: parts.append(f"{scored} popularity scores")
    if no_results: parts.append(f"{no_results} no image results")
    if errors: parts.append(f"{errors} image errors")
    print(f"  Done: {', '.join(parts) if parts else 'nothing to do'}")


def main():
    parser = argparse.ArgumentParser(description="Ramen Rater Data Pipeline")
    parser.add_argument('--limit', type=int, default=None, metavar='N',
                        help='Process up to N ramen that still need images/popularity (omit to do all)')
    args = parser.parse_args()

    xlsx_changed = download_xlsx()

    json_path = DATA_DIR / "ramen.json"
    if not xlsx_changed and json_path.exists():
        print("XLSX unchanged -- loading existing ramen.json")
        with open(json_path, 'r', encoding='utf-8') as f:
            ramen_list = json.load(f)
    else:
        ramen_list = parse_xlsx()
        if not ramen_list:
            print("No data parsed. Exiting.")
            sys.exit(1)

        # Carry forward popularity scores from previous JSON after a fresh parse
        if json_path.exists():
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    old_data = json.load(f)
                pop_map = {r['id']: r['popularity'] for r in old_data if r.get('popularity')}
                merged = 0
                for r in ramen_list:
                    if r['id'] in pop_map:
                        r['popularity'] = pop_map[r['id']]
                        merged += 1
                if merged:
                    print(f"  Carried forward {merged} popularity scores from previous run")
            except Exception:
                pass

    has_images = update_image_flags(ramen_list)
    print(f"  {has_images} ramen already have images")

    print("Checking existing images...")
    recompress_existing()

    # Run scraping with the floating control panel (tkinter needs main thread)
    panel = None
    try:
        panel = ScraperControlPanel()
        print("  Opened scraper control panel (switch engines live)")
        panel.run_with_panel(
            _main_scrape_and_finish, ramen_list, args.limit, panel
        )
    except Exception as e:
        print(f"  Control panel unavailable ({e}), running without GUI")
        _main_scrape_and_finish(ramen_list, args.limit, None)


def _main_scrape_and_finish(ramen_list, limit, panel):
    fetch_images_and_popularity(ramen_list, limit=limit, panel=panel)
    update_image_flags(ramen_list)
    save_json(ramen_list)
    print(f"\nDone! {len(ramen_list)} ramen in database.")


if __name__ == '__main__':
    main()
