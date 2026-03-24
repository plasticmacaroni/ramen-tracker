# Ramen Rater Fan App

A personal ramen tracking and ranking app powered by [The Ramen Rater](https://www.theramenrater.com/)'s Big List (~5,400 instant ramen reviews). Rate ramen you've tried, build your personal rankings through head-to-head comparisons, and discover new ones to try.

**Live at:** `https://<username>.github.io/ramen-rater/` (GitHub Pages)

## Tech Stack

- Single `index.html` + `style.css` + vanilla JS (ES modules, no bundler)
- Data: static `data/ramen.json` generated from The Big List xlsx
- Images: compressed WebP thumbnails fetched via Bing image search
- Storage: localStorage with JSON backup/restore
- Style: Tee KO (Jackbox) inspired dark theme

## Data Source

The Ramen Rater publishes The Big List as an xlsx:
`https://www.theramenrater.com/wp-content/uploads/2025/11/11212025The-Ramen-Rater.xlsx`

Fields: Review #, Brand, Variety, Style, Country, Stars (0-5 in 0.25 increments).
Updated roughly once a year.

A Python script (`tools/fetch_ramen_data.py`) handles the full pipeline:

1. Downloads the xlsx (conditional: skips if unchanged via ETag/If-Modified-Since)
2. Parses to JSON, corrects known typos (e.g. "boowl" -> "Bowl")
3. Fetches product images via Bing image search (scraping, no API key), compresses to 400px WebP with Pillow

Run it locally, then push the updated `data/` and `images/` to GitHub.

Dependencies (`tools/requirements.txt`): openpyxl, requests, Pillow

## Views

### 1. Rate (Home)

Search for a ramen (searches both the database and user-created custom ramen), then rate it:

- **Flavor** (5-tier: Bland, Flat, Tasty, Delicious, Incredible)
- **Noodles** (5-tier: Forgettable, Passable, Satisfying, Excellent, Heavenly)
- **Binary insertion ranking**: "Which did you enjoy more?" comparisons to slot the new ramen into your personal ranked list (~log2(N) comparisons)

A "Can't find it? Add custom ramen" link appears below search results for adding ramen not in the database.

A settings toggle allows hiding The Ramen Rater's letter grades from Rate tab search results so users aren't biased.

### 2. My Ramen (Collection)

Browse your rated ramen. Each card shows rank, score (a derived letter grade), flavor/noodle badges, and dates tried. Custom ramen display a "Custom" badge.
Sort by: Rank, Newest, Oldest, Best Flavor, Best Noodles.
Filter by country, style, or text search.

### 3. Discover

Browse the full Big List (custom ramen do NOT appear here). Sort by Ramen Rater score, brand, country, newest.
Filter by country, style, and hide-already-rated toggle. Infinite scroll for performance.

### 4. Ramen Fight

Two random ramen from your collection go head to head. Pick the winner -- rankings update. Track your fight streak and total fights.

## Ranking System

Maintains an ordered array (ranked list). Score is derived by linear interpolation:
`score = ((N - 1 - position) / (N - 1)) * 10`

New ramen are inserted via binary search comparisons. Ramen Fight swaps positions when the winner is ranked below the loser.

## Letter Grade System

Both Ramen Rater stars (0-5) and personal scores (0-10) are converted to letter grades:
A+ (97%+), A (93%), A- (90%), B+ (87%), B (83%), B- (80%), C+ (77%), C (73%), C- (70%), D+ (67%), D (63%), D- (60%), F (<60%).

Grade colors use an intuitive green-to-red gradient:

- **A range**: teal-green (#00d4aa)
- **B range**: lime green (#7bc74d)
- **C range**: yellow (#ffd803)
- **D range**: orange (#e8833a)
- **F**: hot pink/red (#ff3366)

## Ramen Rater Credit

Each ramen's rating modal links to The Ramen Rater's review page via a search URL (`theramenrater.com/?s=<review_id>`). A credit line appears in the Settings modal.

## Custom Ramen

Users can add ramen not in the database via a "Add Custom Ramen" modal accessible from the Rate tab:

- Required: variety name, brand
- Optional: style (Pack/Cup/Bowl/Tray/Other), country, photo
- Photos are compressed client-side to 300px JPEG at 60% quality, stored as base64 in localStorage
- Custom ramen IDs are prefixed with `c-` followed by a timestamp
- Custom ramen show a "Custom" badge instead of Ramen Rater grades
- Custom ramen can be deleted from the rating modal (removes ramen, rating, and ranking)
- Custom ramen appear in Rate tab search and My Ramen collection, but NOT in Discover

Storage footprint: ~15-30KB per custom ramen with image, ~100 entries = ~3MB within localStorage limits.

## Storage & Backup

All user data lives in localStorage:

- `ratings`: flavor/noodle tier per ramen
- `rankedList`: ordered array of ramen IDs
- `stats`: fight count, streak
- `settings`: backup reminder timing, `hideRaterScore` toggle, `cardSize` (compact/large)
- `customRamen`: user-created ramen entries with base64 images

Backup reminders appear after every 5 new ratings or 14 days. Users can download/restore JSON backups.

## Share Rankings

Users can share their ranked ramen list with friends via a compact URL.

### Generating a share link

A **"SHARE MY RANKINGS"** button in Settings opens a modal. The user enters a display name, then clicks "Generate Link" to produce a shareable URL. The link can be copied to clipboard or shared via the native Web Share API on mobile.

### URL encoding scheme

The ranked list is encoded as a compact binary format, compressed with `deflate-raw` via the browser's native `CompressionStream` API, and base64url-encoded into the URL hash:

```
#share=<base64url-encoded deflated binary>
```

Binary format: `[version:1][nameLen:1][name:N][dbCount:2][entries:3*N][customCount:1][customEntries:var]`

Each database ramen entry is 3 bytes: 2-byte big-endian ID + 1 byte packing flavor (1-5) and noodle (1-5) ratings. Position in the list encodes rank. Custom ramen include length-prefixed strings for variety, brand, style, and country (no images). Typical URLs are 150-500 characters for 50-200 rated ramen.

### Viewing a shared link

When the app detects `share=` in the URL hash, it decodes the data and displays a dynamic 5th tab labeled "{Name}'s Ramen" (teal accent). This view is identical to "My Ramen" in layout: search, sort/filter controls, card grid with derived grades and rank. Clicking a card opens a read-only detail popup. A "Remove shared view" button dismisses the tab.

Shared data is ephemeral -- it lives only in the URL, not in localStorage. Custom ramen appear with a "Custom" badge and placeholder images. The `share=` parameter is preserved across tab switches and filter changes.

Implementation: `js/share.js` handles encoding/decoding; `js/ui.js` has the share modal and shared view rendering; `js/app.js` detects the parameter and manages the dynamic tab.

## Visual Design

Tee KO (Jackbox) inspired: dark background (#0d0d0d), bright yellow (#ffd803) / teal (#00d4aa) / hot pink (#ff3366) accents, Bangers font for headings, subtle noise texture, bold high-contrast cards.

### Card Size Setting

A **Card Size** toggle in Settings (Compact / Large) controls ramen card density on desktop. Large mode (the default) shows bigger images (140px), larger text, and wider badges for accessibility. On 1024px screens, large mode shows 2 columns instead of 3, expanding to 3 columns at 1400px+. Mobile is unaffected -- cards always use the compact mobile-optimized layout regardless of the setting.

## File Structure

```
index.html
style.css
js/
  app.js           -- Entry point, tab switching
  data.js          -- Ramen data loading, search, filter/sort
  storage.js       -- localStorage CRUD, backup, custom ramen
  ranking.js       -- Binary insertion sort, fight logic
  share.js         -- Share URL encoding/decoding (binary + deflate + base64url)
  ui.js            -- All UI rendering and event handling
data/
  ramen.json       -- Full ramen database (generated; app loads only this)
images/
  ramen/*.webp     -- Product thumbnails (generated)
  brand/*.png      -- Brand logos (manually added, lowercase name e.g. nissin.png)
tools/
  fetch_ramen_data.py  -- Data pipeline script
  requirements.txt     -- Python dependencies
```
