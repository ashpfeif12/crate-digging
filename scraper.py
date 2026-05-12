"""
crate_digger/scraper.py

Scrapes 1001tracklists.com for:
  1. Artist pages — get tracklist URLs sorted by recent / most viewed / most liked
  2. Individual tracklists — parse track names, artists, timestamps, external links
  3. Track metadata — BPM, key, label, genre from the tracklist page itself

Uses BeautifulSoup + requests with fake user-agent rotation.
Designed to be polite: configurable delays, respects rate limits.

Usage:
    from scraper import CrateDigger

    digger = CrateDigger()
    
    # Get tracklist URLs for an artist
    urls = digger.get_artist_tracklists("peggy gou", mode="most_viewed", limit=5)
    
    # Parse a single tracklist
    tracks = digger.parse_tracklist(url)
    
    # Full pipeline: artist -> track pool
    pool = digger.dig(artist="peggy gou", mode="recent", num_sets=5)
"""

import re
import time
import json
import hashlib
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field, asdict
from urllib.parse import urlparse, urljoin, quote

import requests
from bs4 import BeautifulSoup, Tag
from fake_useragent import UserAgent

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
    timestamp: Optional[str] = None       # Position in the set (e.g. "1:23:00")
    set_position: Optional[str] = None     # "opener" / "warmup" / "peak" / "closer"
    play_count: int = 1                    # How many of the scraped sets this track appeared in
    tracklist_source: Optional[str] = None # Which tracklist URL it came from
    track_url: Optional[str] = None        # 1001tracklists track page
    spotify_id: Optional[str] = None
    beatport_url: Optional[str] = None
    buy_link: Optional[str] = None

    def fingerprint(self) -> str:
        """Dedup key: normalized artist + title."""
        raw = f"{self.artist.lower().strip()} - {self.title.lower().strip()}"
        # Remove feat/ft variations, remix credits for matching
        raw = re.sub(r'\s*\(.*?\)\s*', '', raw)
        raw = re.sub(r'\s*(feat\.?|ft\.?|featuring)\s*', ' ', raw, flags=re.IGNORECASE)
        raw = re.sub(r'\s+', ' ', raw).strip()
        return raw


@dataclass
class TracklistInfo:
    url: str
    title: str
    dj: str
    date: Optional[str] = None
    genre: Optional[str] = None
    duration: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    tracks: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------

BASE_URL = "https://www.1001tracklists.com"

class CrateDigger:
    """
    Main scraper class. Handles:
    - Artist search and page parsing
    - Tracklist URL extraction (sorted by recent / most_viewed / most_liked)
    - Individual tracklist parsing
    - Track pool building with deduplication
    """

    def __init__(
        self,
        delay: float = 2.0,          # Seconds between requests (be polite)
        cache_dir: Optional[str] = None,  # Cache HTML to avoid repeat fetches
        max_retries: int = 3,
    ):
        self.delay = delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self.ua = UserAgent(fallback="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")

        # Simple file-based cache
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        self._last_request_time = 0.0

    # ----- HTTP layer -----

    def _get(self, url: str) -> Optional[str]:
        """Fetch a URL with rate limiting, rotation, retries, and optional caching."""

        # Check cache first
        if self.cache_dir:
            cache_key = hashlib.md5(url.encode()).hexdigest()
            cache_file = self.cache_dir / f"{cache_key}.html"
            if cache_file.exists():
                log.debug(f"Cache hit: {url}")
                return cache_file.read_text(encoding="utf-8")

        # Rate limit
        elapsed = time.time() - self._last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

        headers = {
            "User-Agent": self.ua.random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "DNT": "1",
        }

        for attempt in range(self.max_retries):
            try:
                log.info(f"Fetching: {url} (attempt {attempt + 1})")
                resp = self.session.get(url, headers=headers, timeout=15)
                self._last_request_time = time.time()

                if resp.status_code == 200:
                    html = resp.text
                    # Cache it
                    if self.cache_dir:
                        cache_file.write_text(html, encoding="utf-8")
                    return html

                elif resp.status_code == 403:
                    log.warning(f"403 Forbidden — rotating user agent and retrying...")
                    headers["User-Agent"] = self.ua.random
                    time.sleep(self.delay * (attempt + 2))

                elif resp.status_code == 429:
                    wait = self.delay * (attempt + 3)
                    log.warning(f"429 Rate limited — waiting {wait}s...")
                    time.sleep(wait)

                else:
                    log.warning(f"HTTP {resp.status_code} for {url}")
                    time.sleep(self.delay)

            except requests.RequestException as e:
                log.error(f"Request error: {e}")
                time.sleep(self.delay * (attempt + 1))

        log.error(f"Failed to fetch {url} after {self.max_retries} attempts")
        return None

    def _soup(self, url: str) -> Optional[BeautifulSoup]:
        html = self._get(url)
        if html:
            return BeautifulSoup(html, "lxml")
        return None

    # ----- Artist search -----

    def search_artist(self, name: str) -> Optional[str]:
        """
        Search for an artist on 1001tracklists and return their DJ page URL.
        
        The search on 1001tracklists uses the URL pattern:
        https://www.1001tracklists.com/search/result.php?search_selection=2&search=QUERY
        (selection=2 means DJ search)
        """
        search_url = f"{BASE_URL}/search/result.php?search_selection=2&search={quote(name)}"
        soup = self._soup(search_url)
        if not soup:
            return None

        # Look for DJ links in search results
        # Pattern: /dj/{slug}/index.html
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/dj/" in href and "/index.html" in href:
                full_url = urljoin(BASE_URL, href)
                log.info(f"Found artist page: {full_url}")
                return full_url

        # Fallback: try to construct the URL directly from the name
        slug = re.sub(r'[^a-z0-9]+', '', name.lower())
        direct_url = f"{BASE_URL}/dj/{slug}/index.html"
        log.info(f"No search result, trying direct URL: {direct_url}")
        return direct_url

    # ----- Artist page parsing -----

    def get_artist_tracklists(
        self,
        artist_name: str,
        mode: str = "recent",  # "recent" | "most_viewed" | "most_liked"
        limit: int = 5,
    ) -> list[TracklistInfo]:
        """
        Get tracklist URLs from an artist's DJ page.
        
        The DJ page has sections:
        - Main list: recent tracklists (default chronological)
        - "Most Viewed Tracklists" info box
        - "Most Liked Tracklists" info box
        """
        artist_url = self.search_artist(artist_name)
        if not artist_url:
            log.error(f"Could not find artist: {artist_name}")
            return []

        soup = self._soup(artist_url)
        if not soup:
            return []

        tracklists = []

        if mode == "recent":
            tracklists = self._parse_recent_tracklists(soup, limit)
        elif mode == "most_viewed":
            tracklists = self._parse_info_box_tracklists(soup, "most viewed", limit)
        elif mode == "most_liked":
            tracklists = self._parse_info_box_tracklists(soup, "most liked", limit)

        # If a specific mode returned nothing, fall back to recent
        if not tracklists and mode != "recent":
            log.warning(f"No {mode} tracklists found, falling back to recent")
            tracklists = self._parse_recent_tracklists(soup, limit)

        return tracklists[:limit]

    def _parse_recent_tracklists(self, soup: BeautifulSoup, limit: int) -> list[TracklistInfo]:
        """Parse the main chronological tracklist listing on a DJ page."""
        results = []

        # 1001tracklists uses various div structures for tracklist entries
        # Look for links to /tracklist/ pages
        seen_urls = set()
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "/tracklist/" in href and href not in seen_urls:
                full_url = urljoin(BASE_URL, href)
                seen_urls.add(href)

                title = link.get_text(strip=True)
                if not title or len(title) < 3:
                    continue

                info = TracklistInfo(
                    url=full_url,
                    title=title,
                    dj="",  # Filled in later
                )

                # Try to find date near this link
                parent = link.parent
                if parent:
                    date_match = re.search(r'(\d{4}-\d{2}-\d{2})', parent.get_text())
                    if date_match:
                        info.date = date_match.group(1)

                results.append(info)
                if len(results) >= limit * 2:  # Get extras for dedup
                    break

        return results[:limit]

    def _parse_info_box_tracklists(
        self, soup: BeautifulSoup, box_type: str, limit: int
    ) -> list[TracklistInfo]:
        """
        Parse the 'Most Viewed Tracklists' or 'Most Liked Tracklists' info boxes
        on a DJ page. These are typically in sidebar/info sections.
        """
        results = []

        # Look for headings or sections containing the box_type text
        for element in soup.find_all(string=re.compile(box_type, re.IGNORECASE)):
            # Walk up to find the container
            container = element.parent
            for _ in range(5):  # Walk up max 5 levels
                if container is None:
                    break
                # Look for tracklist links within this container
                links = container.find_all("a", href=re.compile(r'/tracklist/'))
                if links:
                    for link in links:
                        href = link["href"]
                        full_url = urljoin(BASE_URL, href)
                        title = link.get_text(strip=True)
                        if title and len(title) > 3:
                            # Try to extract view/like count near the link
                            count = None
                            sibling_text = ""
                            for sib in link.next_siblings:
                                if isinstance(sib, Tag):
                                    sibling_text += sib.get_text()
                                elif isinstance(sib, str):
                                    sibling_text += sib
                            count_match = re.search(r'([\d,]+)', sibling_text)
                            if count_match:
                                count = int(count_match.group(1).replace(",", ""))

                            info = TracklistInfo(
                                url=full_url,
                                title=title,
                                dj="",
                                view_count=count if "viewed" in box_type else None,
                                like_count=count if "liked" in box_type else None,
                            )
                            results.append(info)

                    if results:
                        return results[:limit]
                container = container.parent

        return results[:limit]

    # ----- Individual tracklist parsing -----

    def parse_tracklist(self, url: str) -> list[Track]:
        """
        Parse a single tracklist page and extract all tracks with metadata.
        
        1001tracklists track entries use the class 'trackFormat' or 'tlpItem'
        with nested spans for artist/title, and various data attributes for
        timestamps, external links, etc.
        """
        soup = self._soup(url)
        if not soup:
            return []

        tracks = []

        # Get the tracklist name for context
        tracklist_title = ""
        title_el = soup.find("meta", property="og:title")
        if title_el:
            tracklist_title = title_el.get("content", "")

        # Method 1: Look for trackFormat spans (older layout)
        track_elements = soup.find_all("span", class_="trackFormat")
        
        # Method 2: Look for track value divs (newer layout)
        if not track_elements:
            track_elements = soup.find_all("div", class_="tlpItem")

        # Method 3: Look for track containers with data attributes
        if not track_elements:
            track_elements = soup.find_all("div", attrs={"data-trk": True})

        for i, el in enumerate(track_elements):
            track = self._parse_track_element(el, url)
            if track:
                track.tracklist_source = url
                tracks.append(track)

        # Assign set positions based on track index
        total = len(tracks)
        for i, track in enumerate(tracks):
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

        log.info(f"Parsed {len(tracks)} tracks from {url}")
        return tracks

    def _parse_track_element(self, el: Tag, source_url: str) -> Optional[Track]:
        """Extract track data from a single track DOM element."""

        # --- Artist and Title ---
        # Pattern 1: "Artist - Title" in trackFormat span
        full_text = el.get_text(separator=" ", strip=True)
        
        # Clean up the text
        full_text = re.sub(r'\s+', ' ', full_text)
        
        # Try to split on " - " (standard 1001tracklists format)
        parts = full_text.split(" - ", 1)
        if len(parts) == 2:
            artist = parts[0].strip()
            title = parts[1].strip()
        else:
            # Try to find artist/title in child spans
            artist_el = el.find("span", class_=re.compile(r'blue|artist', re.IGNORECASE))
            title_el = el.find("span", class_=re.compile(r'track|title', re.IGNORECASE))
            
            if artist_el and title_el:
                artist = artist_el.get_text(strip=True)
                title = title_el.get_text(strip=True)
            else:
                # Last resort: use the full text
                artist = "Unknown"
                title = full_text

        # Skip ID tracks
        if artist == "ID" and title == "ID":
            return None
        if not title or title == "ID":
            return None

        # Clean up trailing icons/links text
        artist = re.sub(r'\s*$', '', artist)
        title = re.sub(r'\s*$', '', title)

        track = Track(title=title, artist=artist, tracklist_source=source_url)

        # --- Timestamp ---
        # Look for cue/time data in nearby elements or data attributes
        parent = el.parent
        if parent:
            time_el = parent.find("span", class_=re.compile(r'cueValue|time', re.IGNORECASE))
            if time_el:
                track.timestamp = time_el.get_text(strip=True)

            # Check data attributes
            for attr in ["data-cue", "data-time"]:
                val = parent.get(attr) or el.get(attr)
                if val:
                    track.timestamp = val
                    break

        # --- External links (Spotify, Beatport, etc.) ---
        for link in el.find_all("a", href=True):
            href = link["href"]
            if "spotify.com" in href or "spotify" in href.lower():
                # Extract Spotify ID
                sp_match = re.search(r'track[/:]([a-zA-Z0-9]+)', href)
                if sp_match:
                    track.spotify_id = sp_match.group(1)
            elif "beatport.com" in href:
                track.beatport_url = href
                track.buy_link = href
            elif "junodownload.com" in href or "juno.co.uk" in href:
                if not track.buy_link:
                    track.buy_link = href

        # Also check parent/sibling elements for external media links
        if parent:
            for link in parent.find_all("a", href=True):
                href = link["href"]
                if "spotify" in href and not track.spotify_id:
                    sp_match = re.search(r'track[/:]([a-zA-Z0-9]+)', href)
                    if sp_match:
                        track.spotify_id = sp_match.group(1)
                if "beatport" in href and not track.beatport_url:
                    track.beatport_url = href
                    if not track.buy_link:
                        track.buy_link = href

        # --- Track page link (for additional metadata) ---
        track_page_link = el.find("a", href=re.compile(r'/track/'))
        if not track_page_link and parent:
            track_page_link = parent.find("a", href=re.compile(r'/track/'))
        if track_page_link:
            track.track_url = urljoin(BASE_URL, track_page_link["href"])

        # --- BPM / Key / Label from track page or inline data ---
        # Some tracklist pages show BPM inline
        bpm_match = re.search(r'(\d{2,3})\s*(?:BPM|bpm)', full_text)
        if bpm_match:
            track.bpm = int(bpm_match.group(1))

        # Key detection
        key_match = re.search(
            r'\b([A-G][#b]?)\s*(min(?:or)?|maj(?:or)?|m)\b',
            full_text, re.IGNORECASE
        )
        if key_match:
            track.key = key_match.group(1) + key_match.group(2)[0].lower()

        # Genre from parent/container data attributes
        if parent:
            genre_el = parent.find("span", class_=re.compile(r'genre', re.IGNORECASE))
            if genre_el:
                track.genre = genre_el.get_text(strip=True)

        return track

    # ----- Track page enrichment -----

    def enrich_track(self, track: Track) -> Track:
        """
        Fetch the track's detail page on 1001tracklists for additional metadata
        like BPM, key, label, genre, year, and buy links.
        
        Only call this if track.track_url is set and you need more data.
        """
        if not track.track_url:
            return track

        soup = self._soup(track.track_url)
        if not soup:
            return track

        page_text = soup.get_text()

        # BPM
        if not track.bpm:
            bpm_match = re.search(r'(\d{2,3})\s*(?:BPM|bpm)', page_text)
            if bpm_match:
                track.bpm = int(bpm_match.group(1))

        # Key
        if not track.key:
            key_match = re.search(
                r'Key:\s*([A-G][#b]?\s*(?:min|maj|m)\w*)',
                page_text, re.IGNORECASE
            )
            if key_match:
                track.key = key_match.group(1).strip()

        # Label
        if not track.label:
            label_match = re.search(r'Label:\s*(.+?)(?:\n|$)', page_text)
            if not label_match:
                label_el = soup.find("a", href=re.compile(r'/label/'))
                if label_el:
                    track.label = label_el.get_text(strip=True)
            else:
                track.label = label_match.group(1).strip()

        # Genre
        if not track.genre:
            genre_el = soup.find("a", href=re.compile(r'/style/'))
            if genre_el:
                track.genre = genre_el.get_text(strip=True)

        # Year (from release date)
        if not track.year:
            year_match = re.search(r'(\d{4})', page_text[:3000])
            if year_match:
                y = int(year_match.group(1))
                if 1990 <= y <= 2027:
                    track.year = y

        # Buy links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if "beatport.com" in href and not track.beatport_url:
                track.beatport_url = href
                if not track.buy_link:
                    track.buy_link = href
            if "spotify" in href and not track.spotify_id:
                sp_match = re.search(r'track[/:]([a-zA-Z0-9]+)', href)
                if sp_match:
                    track.spotify_id = sp_match.group(1)

        return track

    # ----- Full pipeline -----

    def dig(
        self,
        artist: str,
        mode: str = "recent",
        num_sets: int = 5,
        enrich: bool = False,       # Fetch individual track pages (slow but thorough)
        enrich_limit: int = 50,     # Max tracks to enrich (rate limit protection)
    ) -> dict:
        """
        Full crate-digging pipeline:
        1. Find artist on 1001tracklists
        2. Get their tracklists (sorted by mode)
        3. Parse each tracklist for tracks
        4. Deduplicate and count plays across sets
        5. Optionally enrich tracks with detail page metadata
        6. Return structured track pool
        
        Returns dict with:
        - artist: str
        - mode: str
        - tracklists: list of TracklistInfo (with track counts)
        - track_pool: list of Track (deduplicated, sorted by play count)
        - stats: summary statistics
        """
        log.info(f"=== DIGGING: {artist} | mode={mode} | sets={num_sets} ===")

        # Step 1: Get tracklist URLs
        tracklists = self.get_artist_tracklists(artist, mode=mode, limit=num_sets)
        if not tracklists:
            log.error("No tracklists found")
            return {"artist": artist, "mode": mode, "tracklists": [], "track_pool": [], "stats": {}}

        log.info(f"Found {len(tracklists)} tracklists")

        # Step 2: Parse each tracklist
        all_tracks = []
        for tl_info in tracklists:
            tracks = self.parse_tracklist(tl_info.url)
            tl_info.tracks = tracks
            all_tracks.extend(tracks)
            log.info(f"  {tl_info.title}: {len(tracks)} tracks")

        # Step 3: Deduplicate and count
        pool = self._deduplicate_tracks(all_tracks)
        log.info(f"Deduplicated: {len(all_tracks)} raw -> {len(pool)} unique tracks")

        # Step 4: Optional enrichment
        if enrich:
            enrichable = [t for t in pool if t.track_url][:enrich_limit]
            log.info(f"Enriching {len(enrichable)} tracks with detail pages...")
            for i, track in enumerate(enrichable):
                self.enrich_track(track)
                if (i + 1) % 10 == 0:
                    log.info(f"  Enriched {i + 1}/{len(enrichable)}")

        # Sort by play count (most played across sets first), then alphabetically
        pool.sort(key=lambda t: (-t.play_count, t.artist.lower(), t.title.lower()))

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
            "tracks_with_key": len([t for t in pool if t.key]),
            "tracks_with_buy_link": len([t for t in pool if t.buy_link]),
        }

        return {
            "artist": artist,
            "mode": mode,
            "tracklists": [
                {"url": tl.url, "title": tl.title, "date": tl.date, "track_count": len(tl.tracks)}
                for tl in tracklists
            ],
            "track_pool": [asdict(t) for t in pool],
            "stats": stats,
        }

    def _deduplicate_tracks(self, tracks: list[Track]) -> list[Track]:
        """Merge duplicate tracks, accumulating play counts and metadata."""
        seen = {}
        for track in tracks:
            fp = track.fingerprint()
            if fp in seen:
                existing = seen[fp]
                existing.play_count += 1
                # Fill in missing metadata from this copy
                if not existing.bpm and track.bpm:
                    existing.bpm = track.bpm
                if not existing.key and track.key:
                    existing.key = track.key
                if not existing.label and track.label:
                    existing.label = track.label
                if not existing.genre and track.genre:
                    existing.genre = track.genre
                if not existing.year and track.year:
                    existing.year = track.year
                if not existing.buy_link and track.buy_link:
                    existing.buy_link = track.buy_link
                if not existing.spotify_id and track.spotify_id:
                    existing.spotify_id = track.spotify_id
                if not existing.track_url and track.track_url:
                    existing.track_url = track.track_url
            else:
                seen[fp] = track
        return list(seen.values())

    @staticmethod
    def _top_n(items: list, n: int) -> list:
        """Return top N most common items."""
        counts = {}
        for item in items:
            counts[item] = counts.get(item, 0) + 1
        return sorted(counts, key=counts.get, reverse=True)[:n]

    # ----- Export helpers -----

    def to_json(self, result: dict, path: str) -> str:
        """Save dig results to JSON."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        log.info(f"Saved to {path}")
        return path

    def to_csv(self, result: dict, path: str) -> str:
        """Save track pool to CSV (for Rekordbox import, etc.)."""
        import csv
        tracks = result.get("track_pool", [])
        if not tracks:
            return path
        
        fields = ["title", "artist", "bpm", "key", "label", "genre", "year",
                   "set_position", "play_count", "buy_link", "beatport_url"]
        
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            for track in tracks:
                writer.writerow(track)
        
        log.info(f"Saved {len(tracks)} tracks to {path}")
        return path


# ---------------------------------------------------------------------------
# CLI interface
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Crate Digger — scrape DJ sets from 1001tracklists",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scraper.py "Peggy Gou" --mode recent --sets 5
  python scraper.py "Keinemusik" --mode most_viewed --sets 3 --enrich
  python scraper.py "Dixon" --mode most_liked --output dixon_pool.json
        """
    )
    parser.add_argument("artist", help="Artist/DJ name to search for")
    parser.add_argument("--mode", choices=["recent", "most_viewed", "most_liked"],
                        default="recent", help="How to select tracklists (default: recent)")
    parser.add_argument("--sets", type=int, default=5,
                        help="Number of sets to scrape (default: 5)")
    parser.add_argument("--enrich", action="store_true",
                        help="Fetch individual track pages for extra metadata (slower)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output JSON file path")
    parser.add_argument("--csv", default=None,
                        help="Also export track pool as CSV")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Delay between requests in seconds (default: 2.0)")
    parser.add_argument("--cache", default=".crate_cache",
                        help="Cache directory (default: .crate_cache)")

    args = parser.parse_args()

    digger = CrateDigger(delay=args.delay, cache_dir=args.cache)
    result = digger.dig(
        artist=args.artist,
        mode=args.mode,
        num_sets=args.sets,
        enrich=args.enrich,
    )

    # Print summary
    stats = result["stats"]
    print(f"\n{'='*60}")
    print(f"  CRATE DIG RESULTS: {result['artist']}")
    print(f"  Mode: {result['mode']} | Sets parsed: {stats['tracklists_parsed']}")
    print(f"{'='*60}")
    print(f"  Total unique tracks: {stats['total_tracks']}")
    print(f"  BPM range: {stats['bpm_range']}")
    if stats['top_genres']:
        print(f"  Top genres: {', '.join(stats['top_genres'])}")
    if stats['top_labels']:
        print(f"  Top labels: {', '.join(stats['top_labels'])}")
    print(f"  Tracks with BPM: {stats['tracks_with_bpm']}")
    print(f"  Tracks with buy link: {stats['tracks_with_buy_link']}")
    print(f"{'='*60}\n")

    # Top tracks by play count
    pool = result["track_pool"]
    if pool:
        print("  TOP TRACKS (by play frequency across sets):\n")
        for i, t in enumerate(pool[:15]):
            bpm_str = f"{t['bpm']}bpm" if t.get('bpm') else "???bpm"
            key_str = t.get('key') or '?'
            label_str = t.get('label') or ''
            print(f"  {i+1:2d}. [{t['play_count']}x] {t['artist']} - {t['title']}")
            print(f"      {bpm_str} | {key_str} | {label_str}")
        print()

    # Save
    output_path = args.output or f"{result['artist'].lower().replace(' ', '_')}_{result['mode']}.json"
    digger.to_json(result, output_path)

    if args.csv:
        digger.to_csv(result, args.csv)
