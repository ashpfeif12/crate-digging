# 🎧 Crate Digger

AI-powered setlist builder. Scrapes DJ sets from [1001tracklists.com](https://www.1001tracklists.com), then builds ordered, buyable setlists from a natural language vibe description.

```
You: "Peggy Gou" + "dark minimal, 126-130bpm, late night" + most_viewed
 ↓
Stage 1 — Scrape her 5 most viewed sets from 1001tracklists
Stage 2 — Deduplicate, extract BPM/key/label/genre, tag set positions
Stage 3 — Claude filters + sequences tracks by Camelot key, BPM arc, energy flow
 ↓
Out: 12-track ordered setlist with buy links
```

## Project structure

```
crate-digging/
├── backend/              # Python scraper + AI builder
│   ├── scraper.py        # 1001tracklists scraper
│   ├── builder.py        # AI setlist sequencer (Claude API + rule-based fallback)
│   ├── dig.py            # CLI entry point
│   └── requirements.txt
├── frontend/             # React UI (Vite)
│   ├── src/
│   │   ├── App.jsx       # Main crate digger component
│   │   ├── main.jsx      # Entry point
│   │   └── index.css     # Global styles
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
└── README.md
```

## Quick start

### Backend (CLI)

```bash
cd backend
pip install -r requirements.txt

# Full pipeline
python dig.py "Peggy Gou" "dark minimal, 126-130bpm, late night"

# With options
python dig.py "Keinemusik" "groovy disco house, sunset" --mode most_liked --sets 3

# Rule-based only (no API key needed)
python dig.py "Ben UFO" "eclectic, mixed bpm" --no-ai
```

### Frontend (Web UI)

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

The frontend currently runs with demo data and calls the Claude API directly from the browser for setlist sequencing. To connect it to the Python backend, we'll add a Flask/FastAPI server next.

## Selection modes

| Mode | What it pulls | Best for |
|------|--------------|----------|
| `recent` | Last N sets chronologically | Current rotation, new IDs |
| `most_viewed` | Highest traffic sets | Festival bangers |
| `most_liked` | Community favorites | Deeper cuts, curated mixes |

## Vibe examples

```
"dark minimal, 126-130bpm, late night"
"groovy disco house, 120-124bpm, sunset"
"high energy techno, 132+bpm, peak time"
"melodic & emotional, 122-128bpm, sunrise"
"eclectic & weird, mixed bpm, afterhours"
```

## Environment variables

- `ANTHROPIC_API_KEY` — for Claude API setlist building (optional, falls back to rule-based)

## Roadmap

- [ ] Flask/FastAPI bridge between frontend and Python scraper
- [ ] Discogs API enrichment (label rosters, artist aliases)
- [ ] Beatport metadata for BPM/key
- [ ] "Watch" mode for new sets / newly-IDed tracks
- [ ] Rekordbox XML export
- [ ] Playlist sharing
