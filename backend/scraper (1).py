"""
crate_digger/scraper.py  (v2 — search-based)

Instead of direct HTTP scraping (blocked by Cloudflare + robots.txt),
this version uses web search as its data API:

  1. Search for artist tracklists on 1001tracklists → get URLs + snippet metadata
  2. Search for each tracklist URL → get track names from snippets  
  3. Cross-reference with Ticketmaster/setlist.fm for ordered track lists
  4. Enrich tracks via search (BPM, key, label, buy links)

This approach is MORE reliable than HTML scraping because:
  - Doesn't break when 1001tracklists changes their DOM
  - Google has already indexed and structured the data
  - Works without Cloudflare bypass, proxy rotation, or browser automation
  - Ticketmaster provides complete numbered setlists

Usage:
    python scraper.py "Peggy Gou" --mode recent --sets 5
    
    # Or as a library (designed for Claude API tool use):
    from scraper import CrateDigger
    digger = CrateDigger(search_fn=your_search_function)
    result = digger.dig("Peggy Gou", mode="recent", num_sets=5)
"""

import re
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional, Callable
from urllib.parse import quote

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("crate_digger")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Track:
    title: str
    artist: str
    bpm: Optional[int] = None
    key: Optional[str] = None
    label: Optional[str] = None
    genre: Optional[str] = None
    year: Optional[int] = None
    position: Optional[int] = None         # Track number in the set
    set_position: Optional[str] = None     # "opener" / "warmup" / "peak" / "closer"
    play_count: int = 1                    # How many sets this track appeared in
    tracklist_source: Optional[str] = None # Which set it came from
    buy_link: Optional[str] = None
    beatport_url: Optional[str] = None

    def fingerprint(self) -> str:
        """Dedup key: normalized artist + title."""
        raw = f"{self.artist.lower().strip()} - {self.title.lower().strip()}"
        raw = re.sub(r'\s*\(.*?(remix|edit|mix|version|dub).*?\)\s*', '', raw, flags=re.IGNORECASE)
        raw = re.sub(r'\s*(feat\.?|ft\.?|featuring|pres\.?|presents?)\s*', ' ', raw, flags=re.IGNORECASE)
        raw = re.sub(r'\s+', ' ', raw).strip()
        return raw


@dataclass
class TracklistInfo:
    url: str
    title: str
    dj: str
    date: Optional[str] = None
    venue: Optional[str] = None
    genre: Optional[str] = None
    duration: Optional[str] = None
    track_count: Optional[int] = None
    views: Optional[int] = None
    likes: Optional[int] = None
    tracks: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Search result parsers
# ---------------------------------------------------------------------------

def parse_tracklist_url_from_search(url: str, snippet: str, title: str) -> Optional[TracklistInfo]:
    """Parse a 1001tracklists URL + search snippet into TracklistInfo."""
    if "/tracklist/" not in url:
        return None

    info = TracklistInfo(url=url, title=title, dj="")

    # Extract DJ name and venue from URL slug
    # Pattern: /tracklist/{id}/{dj-name}-{venue}-{date}.html
    slug_match = re.search(r'/tracklist/[^/]+/(.+)\.html', url)
    if slug_match:
        slug = slug_match.group(1)
        # Date is usually at the end: YYYY-MM-DD
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})$', slug)
        if date_match:
            info.date = date_match.group(1)

    # Extract from snippet text
    combined = f"{title} {snippet}"

    # Track count: "18 House Tech House tracks" or "27 tracks"
    tc_match = re.search(r'(\d+)\s+(?:\w+\s+)*tracks', combined)
    if tc_match:
        info.track_count = int(tc_match.group(1))

    # Duration: "1 hour 15 minutes" or "2h 24m"
    dur_match = re.search(r'(\d+\s*h(?:our)?s?\s*\d*\s*m(?:in(?:ute)?s?)?)', combined) or \
                re.search(r'(\d+\s+hours?\s+\d+\s+minutes?)', combined)
    if dur_match:
        info.duration = dur_match.group(1)

    # Genre
    genre_match = re.search(r'Genre(?:s)?\s+(.+?)(?:\s*·|\s*$)', combined)
    if genre_match:
        info.genre = genre_match.group(1).strip()
    else:
        # Try from "X tracks, Y hours, Genre1, Genre2"
        genre_match2 = re.search(r'\d+\s+tracks.*?,.*?,\s*(.+?)(?:\s*\.|\s*$)', combined)
        if genre_match2:
            info.genre = genre_match2.group(1).strip()

    # Views
    views_match = re.search(r'Views\s*·?\s*([\d,]+)', combined)
    if views_match:
        info.views = int(views_match.group(1).replace(",", ""))

    # Likes  
    likes_match = re.search(r'Likes\s*·?\s*(\d+)\s*users?', combined)
    if likes_match:
        info.likes = int(likes_match.group(1))

    # IDed count
    ided_match = re.search(r'IDed\s*·?\s*(\d+)\s*/\s*(\d+)', combined)
    if ided_match:
        if not info.track_count:
            info.track_count = int(ided_match.group(2))

    return info


def parse_tracks_from_snippet(snippet: str, source_url: str = "") -> list[Track]:
    """
    Extract track names from search result snippets.
    
    Handles patterns like:
    - "Artist - Title LABEL" (1001tracklists format)
    - "Artist - Title [LABEL]" (common in snippets)
    - "1.Track Title · 2.Track Title" (Ticketmaster numbered format)
    - "Title (Artist cover)" (setlist.fm format)
    """
    tracks = []

    # Pattern 1: Ticketmaster numbered format "1.Title · 2.Title (Artist cover)"
    # Split on "N." where N is a number — handles both "·" and no delimiter
    tm_parts = re.split(r'(?:·\s*)?(\d+)\.', snippet)
    # tm_parts alternates: [prefix, num, content, num, content, ...]
    tm_matches = []
    for i in range(1, len(tm_parts) - 1, 2):
        pos = tm_parts[i]
        content = tm_parts[i + 1].strip().rstrip('·').strip()
        if content:
            tm_matches.append((pos, content))

    if len(tm_matches) >= 3:  # At least 3 numbered tracks = likely a setlist
        for pos, raw in tm_matches:
            title, artist = _parse_tm_track(raw.strip())
            if title and title != "ID" and len(title) > 1:
                tracks.append(Track(
                    title=title,
                    artist=artist,
                    position=int(pos),
                    tracklist_source=source_url,
                ))
        return tracks

    # Pattern 2: 1001tracklists format "Artist - Title LABEL · contributor(Xk)"
    # First aggressively clean out contributor noise
    cleaned = snippet
    cleaned = re.sub(r'\w+\s*\([\d.]+k\)', '', cleaned)  # "user (245.8k)"
    cleaned = re.sub(r'\b(?:Save|Pre-Save)\s*\d*', '', cleaned)
    cleaned = re.sub(r'\b\d+\s*·', '·', cleaned)  # Standalone numbers before ·
    cleaned = re.sub(r'\d+:\d+:\d+', '', cleaned)  # Timestamps
    cleaned = re.sub(r'·\s*·', '·', cleaned)  # Double separators
    cleaned = re.sub(r'·\s*$', '', cleaned)  # Trailing separator
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()  # Collapse whitespace

    # Split on · and look for "Artist - Title" in each segment
    segments = [s.strip() for s in cleaned.split('·') if s.strip()]
    for seg in segments:
        m = re.match(
            r'^([A-Z][A-Za-z0-9\s.&\',]+?)\s+-\s+(.+?)(?:\s+([A-Z][A-Z\s/&()!]+?))?$',
            seg.strip()
        )
        if m:
            artist = m.group(1).strip()
            title = m.group(2).strip()
            label = m.group(3).strip() if m.group(3) else None

            if not title or title == "ID" or len(title) < 2:
                continue
            if any(x in artist.lower() for x in ["google search", "songstats", "share", "short link"]):
                continue
            if label and len(label) < 3:
                label = None

            tracks.append(Track(
                title=title,
                artist=artist,
                label=label,
                tracklist_source=source_url,
            ))

    return tracks


def _parse_tm_track(raw: str) -> tuple[str, str]:
    """Parse a Ticketmaster track entry like 'Murder On The Dancefloor (Hannah Laing cover)'."""
    # Check for "(Artist cover)" or "(Artist remix)"
    cover_match = re.search(r'\((.+?)\s+(?:cover|remix)\)\s*$', raw, re.IGNORECASE)
    if cover_match:
        artist = cover_match.group(1).strip()
        title = raw[:cover_match.start()].strip()
        return title, artist

    # Check for "Title - Remix Info (Artist remix)"
    remix_match = re.search(r'^(.+?)\s*-\s*(.+?)$', raw)
    if remix_match:
        return remix_match.group(1).strip() + " - " + remix_match.group(2).strip(), ""

    return raw.strip(), ""


def parse_track_metadata_from_search(snippet: str, track_title: str) -> dict:
    """Extract BPM, key, label, genre from a track search result."""
    meta = {}

    # BPM: "124 BPM" or "with 124 BPM"
    bpm_match = re.search(r'(\d{2,3})\s*BPM', snippet, re.IGNORECASE)
    if bpm_match:
        bpm = int(bpm_match.group(1))
        if 70 <= bpm <= 200:
            meta["bpm"] = bpm

    # Label: "Label · LABEL_NAME" or "[LABEL_NAME]" or "on LABEL_NAME"
    label_match = re.search(r'Label\s*·?\s*([A-Z][A-Z\s/&()]+?)(?:\s*·|\s*$)', snippet)
    if label_match:
        meta["label"] = label_match.group(1).strip()
    else:
        bracket_match = re.search(r'\[([A-Z][A-Z\s/&()]+?)\]', snippet)
        if bracket_match:
            meta["label"] = bracket_match.group(1).strip()

    # Genre
    genre_match = re.search(r'Genre\s*·?\s*([A-Za-z\s/&,]+?)(?:\s*·|\s*$)', snippet)
    if genre_match:
        meta["genre"] = genre_match.group(1).strip()

    # Total plays: "Total Tracklist Plays: 58x"
    plays_match = re.search(r'Total Tracklist Plays:\s*(\d+)x', snippet)
    if plays_match:
        meta["total_plays"] = int(plays_match.group(1))

    # Year from release date
    year_match = re.search(r'released\s+(\d{4})', snippet, re.IGNORECASE)
    if year_match:
        meta["year"] = int(year_match.group(1))

    return meta


# ---------------------------------------------------------------------------
# Main scraper class
# ---------------------------------------------------------------------------

class CrateDigger:
    """
    Search-based crate digger.
    
    Requires a search_fn callback that takes a query string and returns
    a list of dicts with keys: url, title, snippet.
    
    For Claude API usage, wrap web_search tool results into this format.
    For CLI usage, a default Google search implementation is provided.
    """

    def __init__(self, search_fn: Optional[Callable] = None):
        self.search_fn = search_fn

    def find_tracklists(
        self,
        artist: str,
        mode: str = "recent",
        limit: int = 5,
    ) -> list[TracklistInfo]:
        """Find tracklist URLs for an artist via search."""

        # Build targeted search queries based on mode
        queries = []
        if mode == "recent":
            queries = [
                f'site:1001tracklists.com "{artist}" tracklist 2025',
                f'site:1001tracklists.com "{artist}" tracklist 2024',
            ]
        elif mode == "most_viewed":
            queries = [
                f'site:1001tracklists.com "{artist}" tracklist festival',
                f'site:1001tracklists.com "{artist}" tracklist 2024 2025',
            ]
        elif mode == "most_liked":
            queries = [
                f'site:1001tracklists.com "{artist}" tracklist essential mix OR radio',
                f'site:1001tracklists.com "{artist}" tracklist 2024',
            ]

        tracklists = []
        seen_urls = set()

        for query in queries:
            results = self._search(query)
            for r in results:
                url = r.get("url", "")
                if "/tracklist/" not in url:
                    continue
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                info = parse_tracklist_url_from_search(
                    url, r.get("snippet", ""), r.get("title", "")
                )
                if info:
                    info.dj = artist
                    tracklists.append(info)

            if len(tracklists) >= limit:
                break

        # Sort by date (most recent first) for "recent" mode
        if mode == "recent":
            tracklists.sort(key=lambda t: t.date or "", reverse=True)

        return tracklists[:limit]

    def get_tracks_for_tracklist(self, tl: TracklistInfo) -> list[Track]:
        """Get tracks for a specific tracklist by searching for its content."""
        all_tracks = []

        # Strategy 1: Search for the tracklist URL + track content
        # This sometimes returns snippets with track names from 1001tracklists
        results = self._search(f'"{tl.title}" tracklist tracks')
        for r in results:
            snippet = r.get("snippet", "")
            tracks = parse_tracks_from_snippet(snippet, tl.url)
            all_tracks.extend(tracks)

        # Strategy 2: Search Ticketmaster (they have complete numbered setlists)
        if len(all_tracks) < 5:
            dj_name = tl.dj or ""
            venue = ""
            if tl.date:
                venue = tl.title.replace(dj_name, "").strip(" -@,")

            tm_results = self._search(
                f'ticketmaster "{dj_name}" setlist {tl.date or ""} {venue}'
            )
            for r in tm_results:
                snippet = r.get("snippet", "")
                tracks = parse_tracks_from_snippet(snippet, tl.url)
                if tracks:
                    all_tracks.extend(tracks)
                    break

        # Assign set positions based on track order
        total = len(all_tracks)
        for i, track in enumerate(all_tracks):
            if track.position:
                i = track.position - 1
            if total <= 1:
                track.set_position = "peak"
            elif i < total * 0.15:
                track.set_position = "opener"
            elif i < total * 0.35:
                track.set_position = "warmup"
            elif i < total * 0.8:
                track.set_position = "peak"
            else:
                track.set_position = "closer"

        tl.tracks = all_tracks
        log.info(f"  Found {len(all_tracks)} tracks for: {tl.title}")
        return all_tracks

    def enrich_tracks(self, tracks: list[Track], limit: int = 20) -> list[Track]:
        """Enrich tracks with BPM, key, label via search."""
        enriched_count = 0

        for track in tracks[:limit]:
            if track.bpm and track.label:
                continue  # Already enriched

            query = f'"{track.artist}" "{track.title}" BPM label'
            results = self._search(query)

            for r in results:
                meta = parse_track_metadata_from_search(
                    r.get("snippet", ""), track.title
                )
                if meta.get("bpm") and not track.bpm:
                    track.bpm = meta["bpm"]
                if meta.get("label") and not track.label:
                    track.label = meta["label"]
                if meta.get("genre") and not track.genre:
                    track.genre = meta["genre"]
                if meta.get("year") and not track.year:
                    track.year = meta["year"]

                if track.bpm and track.label:
                    break

            # Try Beatport for buy link
            if not track.buy_link:
                bp_results = self._search(
                    f'beatport "{track.artist}" "{track.title}"'
                )
                for r in bp_results:
                    if "beatport.com" in r.get("url", ""):
                        track.buy_link = r["url"]
                        track.beatport_url = r["url"]
                        break

            enriched_count += 1

        log.info(f"Enriched {enriched_count} tracks")
        return tracks

    def dig(
        self,
        artist: str,
        mode: str = "recent",
        num_sets: int = 5,
        enrich: bool = True,
        enrich_limit: int = 20,
    ) -> dict:
        """
        Full crate-digging pipeline.
        
        Returns:
        {
            "artist": str,
            "mode": str,
            "tracklists": [...],
            "track_pool": [...],
            "stats": {...}
        }
        """
        log.info(f"=== DIGGING: {artist} | mode={mode} | sets={num_sets} ===")

        # Step 1: Find tracklists
        tracklists = self.find_tracklists(artist, mode=mode, limit=num_sets)
        if not tracklists:
            log.error("No tracklists found")
            return {"artist": artist, "mode": mode, "tracklists": [], "track_pool": [], "stats": {}}

        log.info(f"Found {len(tracklists)} tracklists")

        # Step 2: Get tracks for each tracklist
        all_tracks = []
        for tl in tracklists:
            tracks = self.get_tracks_for_tracklist(tl)
            all_tracks.extend(tracks)

        # Step 3: Deduplicate
        pool = self._deduplicate(all_tracks)
        log.info(f"Deduplicated: {len(all_tracks)} raw -> {len(pool)} unique")

        # Step 4: Enrich
        if enrich and pool:
            pool = self.enrich_tracks(pool, limit=enrich_limit)

        # Sort by play count
        pool.sort(key=lambda t: (-t.play_count, t.artist.lower()))

        # Stats
        bpms = [t.bpm for t in pool if t.bpm]
        genres = [t.genre for t in pool if t.genre]
        labels = [t.label for t in pool if t.label]

        stats = {
            "total_tracks": len(pool),
            "total_raw_tracks": len(all_tracks),
            "tracklists_parsed": len(tracklists),
            "bpm_range": f"{min(bpms)}-{max(bpms)}" if bpms else "unknown",
            "bpm_avg": round(sum(bpms) / len(bpms), 1) if bpms else None,
            "top_genres": self._top_n(genres, 5),
            "top_labels": self._top_n(labels, 5),
            "tracks_with_bpm": len(bpms),
            "tracks_with_buy_link": len([t for t in pool if t.buy_link]),
        }

        return {
            "artist": artist,
            "mode": mode,
            "tracklists": [
                {
                    "url": tl.url, "title": tl.title, "date": tl.date,
                    "genre": tl.genre, "track_count": len(tl.tracks),
                    "views": tl.views, "likes": tl.likes,
                }
                for tl in tracklists
            ],
            "track_pool": [asdict(t) for t in pool],
            "stats": stats,
        }

    def _search(self, query: str) -> list[dict]:
        """Execute a search query. Returns list of {url, title, snippet}."""
        if self.search_fn:
            return self.search_fn(query)
        log.warning(f"No search function configured. Query: {query}")
        return []

    def _deduplicate(self, tracks: list[Track]) -> list[Track]:
        """Merge duplicate tracks, accumulating play counts and metadata."""
        seen = {}
        for track in tracks:
            fp = track.fingerprint()
            if fp in seen:
                existing = seen[fp]
                existing.play_count += 1
                # Fill in missing metadata
                for attr in ["bpm", "key", "label", "genre", "year", "buy_link", "beatport_url"]:
                    if not getattr(existing, attr) and getattr(track, attr):
                        setattr(existing, attr, getattr(track, attr))
            else:
                seen[fp] = track
        return list(seen.values())

    @staticmethod
    def _top_n(items: list, n: int) -> list:
        counts = {}
        for item in items:
            counts[item] = counts.get(item, 0) + 1
        return sorted(counts, key=counts.get, reverse=True)[:n]

    def to_json(self, result: dict, path: str) -> str:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        return path

    def to_csv(self, result: dict, path: str) -> str:
        import csv
        tracks = result.get("track_pool", [])
        if not tracks:
            return path
        fields = ["title", "artist", "bpm", "key", "label", "genre", "year",
                   "set_position", "play_count", "buy_link"]
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for track in tracks:
                writer.writerow(track)
        return path


# ---------------------------------------------------------------------------
# CLI with built-in Google search (for local testing)
# ---------------------------------------------------------------------------

def google_search_cli(query: str) -> list[dict]:
    """Basic Google search via requests (for CLI testing only)."""
    import requests
    from bs4 import BeautifulSoup

    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    url = f"https://www.google.com/search?q={quote(query)}&num=10"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results = []

        for div in soup.find_all("div", class_="g"):
            link = div.find("a", href=True)
            snippet_el = div.find("span", class_=re.compile(".*"))
            if link:
                results.append({
                    "url": link["href"],
                    "title": link.get_text(strip=True),
                    "snippet": div.get_text(separator=" ", strip=True),
                })

        return results[:10]
    except Exception as e:
        log.error(f"Search failed: {e}")
        return []


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crate Digger v2 — search-based")
    parser.add_argument("artist", help="DJ name")
    parser.add_argument("--mode", choices=["recent", "most_viewed", "most_liked"], default="recent")
    parser.add_argument("--sets", type=int, default=5)
    parser.add_argument("--no-enrich", action="store_true")
    parser.add_argument("--output", "-o", default=None)
    parser.add_argument("--csv", default=None)

    args = parser.parse_args()

    digger = CrateDigger(search_fn=google_search_cli)
    result = digger.dig(
        artist=args.artist,
        mode=args.mode,
        num_sets=args.sets,
        enrich=not args.no_enrich,
    )

    stats = result["stats"]
    print(f"\n{'='*60}")
    print(f"  CRATE DIG: {result['artist']} ({result['mode']})")
    print(f"  {stats['tracklists_parsed']} sets → {stats['total_tracks']} unique tracks")
    print(f"  BPM: {stats['bpm_range']}")
    print(f"{'='*60}\n")

    for i, t in enumerate(result["track_pool"][:20]):
        bpm = t.get("bpm", "???")
        label = t.get("label", "")
        plays = t.get("play_count", 1)
        print(f"  {i+1:2d}. [{plays}x] {t['artist']} - {t['title']}")
        if bpm != "???" or label:
            print(f"      {bpm}bpm | {label}")

    if args.output:
        digger.to_json(result, args.output)
    if args.csv:
        digger.to_csv(result, args.csv)
