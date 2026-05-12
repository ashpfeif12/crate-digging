# 🎧 Crate Digger

AI-powered setlist builder that scrapes DJ sets from 1001tracklists.com and builds ordered, buyable setlists based on your vibe description.

## How it works

```
You: "Peggy Gou" + "dark minimal, 126-130bpm, late night" + most_viewed

Stage 1 — SCRAPE
  → Finds Peggy Gou on 1001tracklists
  → Pulls her 5 most viewed sets
  → Parses every track: artist, title, timestamp, external links

Stage 2 — CHARACTERIZE
  → Deduplicates across sets (tracks played 3x = DJ favorites)
  → Extracts BPM, key, label, genre from tracklist pages
  → Optionally enriches from individual track pages (Beatport links, etc.)
  → Tags set position: opener / warmup / peak / closer

Stage 3 — BUILD SETLIST
  → Pre-filters pool by your BPM range and genre keywords
  → Claude API sequences tracks for smooth transitions:
      - Camelot wheel key compatibility
      - Gradual BPM progression
      - Natural energy arc (build → peak → release)
  → Falls back to rule-based sequencing if API unavailable
  → Outputs ordered tracklist with buy links
```

## Quick start

```bash
pip install -r requirements.txt

# Full pipeline
python dig.py "Peggy Gou" "dark minimal, 126-130bpm, late night"

# With options
python dig.py "Keinemusik" "groovy disco house, sunset" \
  --mode most_liked --sets 3 --max-tracks 10 --output keinemusik_set.json

# Just scrape (no setlist building)
python dig.py "Dixon" "placeholder" --pool-only --csv dixon_pool.csv

# Rule-based only (no Claude API needed)
python dig.py "Ben UFO" "eclectic, mixed bpm" --no-ai
```

## Selection modes

| Mode | What it pulls | Best for |
|------|--------------|----------|
| `recent` | Last N sets chronologically | Current rotation, new IDs being tested |
| `most_viewed` | Highest traffic sets | Festival bangers, mainstream picks |
| `most_liked` | Community favorite sets | Deeper cuts, curated radio mixes |

## Architecture

```
crate_digger/
├── scraper.py      # 1001tracklists scraper (artist search, tracklist parsing)
├── builder.py      # AI setlist builder (pre-filter, Claude API, rule-based fallback)
├── dig.py          # CLI entry point (full pipeline)
├── requirements.txt
└── README.md
```

### scraper.py — `CrateDigger` class

- `search_artist(name)` → finds DJ page URL
- `get_artist_tracklists(name, mode, limit)` → returns tracklist URLs sorted by mode
- `parse_tracklist(url)` → extracts all tracks with metadata from a single set
- `enrich_track(track)` → fetches individual track page for BPM/key/label
- `dig(artist, mode, num_sets)` → full pipeline, returns deduplicated track pool

### builder.py — `SetlistBuilder` class

- `build(pool, vibe, max_tracks)` → filtered + sequenced setlist
- Pre-filters by BPM range and genre keywords from vibe text
- AI mode: sends pool + vibe to Claude API for intelligent sequencing
- Rule-based fallback: BPM sort + Camelot key greedy reordering
- Validates AI output against pool (no hallucinated tracks)

## Vibe examples

```
"dark minimal, 126-130bpm, late night"
"groovy disco house, 120-124bpm, sunset"
"high energy techno, 132+bpm, peak time"
"melodic & emotional, 122-128bpm, sunrise"
"eclectic & weird, mixed bpm, afterhours"
```

## Environment variables

- `ANTHROPIC_API_KEY` — Claude API key (optional, falls back to rule-based)

## Caching

HTML pages are cached in `.crate_cache/` by default. This avoids hammering 1001tracklists on repeated runs for the same artist. Delete the directory to force fresh fetches.

## Rate limiting

Default: 2 seconds between requests. Adjust with `--delay`. The scraper rotates user agents and handles 403/429 responses with exponential backoff. Be respectful.

## Next steps

- [ ] Discogs API enrichment (label rosters, artist aliases)
- [ ] Beatport API for BPM/key when not on tracklist page
- [ ] Web UI (React frontend from `crate-digger.jsx`)
- [ ] Periodic "watch" mode for new sets / newly-IDed tracks
- [ ] Rekordbox XML export
