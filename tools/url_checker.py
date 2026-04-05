#!/usr/bin/env python3
"""
URL Checker — flags probable false URLs in urls.json using multiple signals:
  1. Does the ramen ID appear in the URL path?
  2. Does the URL slug fuzzy-match the ramen's brand + variety?
  3. Does the URL contain a *different* ramen ID (pointing to wrong review)?
"""

import json
import os
import re
import sys
from pathlib import Path
from difflib import SequenceMatcher
from urllib.parse import urlparse, unquote

if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RAMEN_JSON = DATA_DIR / "ramen.json"
URLS_JSON = DATA_DIR / "urls.json"

SLUG_THRESHOLD = 0.30


def slug_from_url(url):
    """Extract the meaningful slug from a theramenrater URL."""
    path = urlparse(url).path.strip("/")
    parts = path.split("/")
    if not parts:
        return ""
    slug = parts[-1]
    slug = unquote(slug).replace("-", " ").lower().strip()
    return slug


def normalize_name(brand, variety):
    name = f"{brand} {variety}".lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


def id_in_url(rid, url):
    """Check if the ramen ID appears as a distinct number in the URL path."""
    path = urlparse(url).path
    return bool(re.search(rf"(?<!\d){rid}(?!\d)", path))


def other_id_in_slug(rid, slug, all_ids):
    """Check if the slug's leading number is a different ramen ID."""
    m = re.match(r"^(\d+)", slug)
    if not m:
        return None
    slug_num = int(m.group(1))
    if slug_num != rid and slug_num in all_ids:
        return slug_num
    return None


def brand_in_slug(brand, slug):
    """Check if the brand name appears in the slug."""
    b = re.sub(r"[^a-z0-9\s]", "", brand.lower()).strip()
    return b in slug if b else False


def main():
    with open(RAMEN_JSON, "r", encoding="utf-8") as f:
        ramen_list = json.load(f)
    with open(URLS_JSON, "r", encoding="utf-8") as f:
        urls = json.load(f)

    ramen_by_id = {r["id"]: r for r in ramen_list}
    all_ids = set(ramen_by_id.keys())

    flagged = []
    checked = 0

    for rid_str, url in urls.items():
        rid = int(rid_str)
        ramen = ramen_by_id.get(rid)
        if not ramen:
            continue

        checked += 1
        slug = slug_from_url(url)
        name = normalize_name(ramen.get("brand", ""), ramen.get("variety", ""))
        ratio = SequenceMatcher(None, slug, name).ratio() if slug and name else 0

        has_id = id_in_url(rid, url)
        has_brand = brand_in_slug(ramen.get("brand", ""), slug)
        wrong_id = other_id_in_slug(rid, slug, all_ids)
        good_slug = ratio >= SLUG_THRESHOLD

        reasons = []

        if wrong_id:
            reasons.append(f"slug contains #{wrong_id} (different ramen)")
        if not has_id and not good_slug and not has_brand:
            reasons.append("no ID in URL, slug doesn't match name or brand")
        if "?s=" in url:
            reasons.append("search URL, not a review page")

        if not reasons:
            continue

        flagged.append({
            "id": rid,
            "brand": ramen.get("brand", ""),
            "variety": ramen.get("variety", ""),
            "url": url,
            "slug": slug,
            "score": round(ratio, 3),
            "has_id": has_id,
            "has_brand": has_brand,
            "wrong_id": wrong_id,
            "reasons": reasons,
        })

    flagged.sort(key=lambda x: (x["score"], x["id"]))

    print(f"\n  URL Checker")
    print(f"  Checked {checked} URLs, flagged {len(flagged)} probable mismatches\n")

    for item in flagged:
        print(f"  #{item['id']} (score: {item['score']})")
        print(f"    Ramen:   {item['brand']} — {item['variety']}")
        print(f"    URL:     {item['url']}")
        print(f"    Slug:    {item['slug']}")
        print(f"    Reasons: {'; '.join(item['reasons'])}")
        print()

    if flagged:
        out_path = DATA_DIR / "flagged_urls.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(flagged, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"  Saved to {out_path}")
    else:
        print("  All URLs look good!")


if __name__ == "__main__":
    main()
