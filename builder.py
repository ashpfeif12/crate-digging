"""
crate_digger/builder.py

Takes a track pool (from scraper.py) and a natural language vibe description,
then uses Claude to build an ordered, buyable setlist.

The LLM's job is ONLY filtering and sequencing — it works from real scraped data
and cannot hallucinate tracks that don't exist in the pool.

Usage:
    from builder import SetlistBuilder

    builder = SetlistBuilder(api_key="sk-ant-...")
    result = builder.build(
        track_pool=pool,       # list of track dicts from scraper
        vibe="dark minimal, 126-130bpm, late night",
        max_tracks=12,
    )
"""

import json
import os
import logging
from typing import Optional

import requests

log = logging.getLogger("crate_digger.builder")

# Camelot wheel for harmonic mixing compatibility
CAMELOT_WHEEL = {
    # (pitch_class, mode) -> camelot_code
    # Major keys (mode=1)
    (0, 1): "8B", (1, 1): "3B", (2, 1): "10B", (3, 1): "5B",
    (4, 1): "12B", (5, 1): "7B", (6, 1): "2B", (7, 1): "9B",
    (8, 1): "4B", (9, 1): "11B", (10, 1): "6B", (11, 1): "1B",
    # Minor keys (mode=0)
    (0, 0): "5A", (1, 0): "12A", (2, 0): "7A", (3, 0): "2A",
    (4, 0): "9A", (5, 0): "4A", (6, 0): "11A", (7, 0): "6A",
    (8, 0): "1A", (9, 0): "8A", (10, 0): "3A", (11, 0): "10A",
}

# Key string -> Camelot code mapping
KEY_TO_CAMELOT = {
    "C": "8B", "Cm": "5A", "C#": "3B", "C#m": "12A", "Db": "3B", "Dbm": "12A",
    "D": "10B", "Dm": "7A", "D#": "5B", "D#m": "2A", "Eb": "5B", "Ebm": "2A",
    "E": "12B", "Em": "9A",
    "F": "7B", "Fm": "4A", "F#": "2B", "F#m": "11A", "Gb": "2B", "Gbm": "11A",
    "G": "9B", "Gm": "6A", "G#": "4B", "G#m": "1A", "Ab": "4B", "Abm": "1A",
    "A": "11B", "Am": "8A", "A#": "6B", "A#m": "3A", "Bb": "6B", "Bbm": "3A",
    "B": "1B", "Bm": "10A",
}


def camelot_compatible(key1: str, key2: str) -> bool:
    """Check if two keys are harmonically compatible on the Camelot wheel."""
    c1 = KEY_TO_CAMELOT.get(key1)
    c2 = KEY_TO_CAMELOT.get(key2)
    if not c1 or not c2:
        return True  # Unknown keys = assume compatible

    num1, letter1 = int(c1[:-1]), c1[-1]
    num2, letter2 = int(c2[:-1]), c2[-1]

    # Same position
    if c1 == c2:
        return True
    # Same number, different letter (relative major/minor)
    if num1 == num2:
        return True
    # Adjacent numbers, same letter (+1 or -1 on the wheel, wrapping at 12)
    if letter1 == letter2 and ((num1 - num2) % 12 in (1, 11)):
        return True

    return False


class SetlistBuilder:
    """
    Builds an ordered setlist from a track pool using Claude API.
    
    The builder:
    1. Pre-filters the pool based on explicit vibe constraints (BPM range, genre keywords)
    2. Sends the filtered pool + vibe to Claude for intelligent sequencing
    3. Validates the response against the actual pool (no hallucinations)
    4. Falls back to rule-based sequencing if the API is unavailable
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.api_url = "https://api.anthropic.com/v1/messages"

    def build(
        self,
        track_pool: list[dict],
        vibe: str,
        max_tracks: int = 12,
        use_ai: bool = True,
    ) -> dict:
        """
        Build a setlist from a track pool.
        
        Args:
            track_pool: List of track dicts (from scraper.dig()["track_pool"])
            vibe: Natural language vibe description
            max_tracks: Maximum tracks in the setlist
            use_ai: Whether to use Claude API (falls back to rules if False/unavailable)
        
        Returns:
            {
                "setlist": [ordered list of track dicts],
                "reasoning": str,
                "vibe": str,
                "stats": {...}
            }
        """
        if not track_pool:
            return {"setlist": [], "reasoning": "Empty track pool.", "vibe": vibe, "stats": {}}

        # Step 1: Pre-filter by explicit constraints in the vibe
        filtered = self._prefilter(track_pool, vibe)
        log.info(f"Pre-filtered: {len(track_pool)} -> {len(filtered)} tracks")

        # If filtering was too aggressive, relax progressively
        if len(filtered) < 3:
            log.warning("Pre-filter too aggressive, trying BPM-only filter")
            # Retry with just BPM filtering (no genre)
            filtered = self._prefilter_bpm_only(track_pool, vibe)
        if len(filtered) < 3:
            log.warning("Still too few tracks, using full pool")
            filtered = track_pool

        # Step 2: Try AI sequencing
        if use_ai and self.api_key:
            ai_result = self._ai_sequence(filtered, vibe, max_tracks)
            if ai_result and ai_result["setlist"]:
                return ai_result

        # Step 3: Fallback to rule-based sequencing
        log.info("Using rule-based sequencing")
        return self._rule_based_sequence(filtered, vibe, max_tracks)

    def _prefilter_bpm_only(self, pool: list[dict], vibe: str) -> list[dict]:
        """Lighter pre-filter: only BPM range, no genre matching."""
        import re as _re
        vibe_lower = vibe.lower()
        filtered = list(pool)

        patterns = [
            r'(\d{2,3})\s*[-–to]+\s*(\d{2,3})\s*bpm',
            r'(\d{2,3})\s*bpm',
            r'(\d{2,3})\+\s*bpm',
        ]
        for pattern in patterns:
            m = _re.search(pattern, vibe_lower)
            if m:
                groups = m.groups()
                if len(groups) == 2:
                    bpm_low, bpm_high = int(groups[0]), int(groups[1])
                elif "+" in m.group():
                    bpm_low, bpm_high = int(groups[0]), 200
                else:
                    bpm_low, bpm_high = int(groups[0]) - 6, int(groups[0]) + 6

                filtered = [
                    t for t in filtered
                    if not t.get("bpm") or (bpm_low - 5 <= t["bpm"] <= bpm_high + 5)
                ]
                break

        return filtered

    def _prefilter(self, pool: list[dict], vibe: str) -> list[dict]:
        """Extract explicit constraints from the vibe and filter the pool."""
        vibe_lower = vibe.lower()
        filtered = list(pool)

        # Extract BPM range if mentioned
        bpm_match = None
        # "126-130bpm" or "126-130 bpm" or "126 to 130 bpm"
        patterns = [
            r'(\d{2,3})\s*[-–to]+\s*(\d{2,3})\s*bpm',
            r'(\d{2,3})\s*bpm',
            r'(\d{2,3})\+\s*bpm',
        ]
        for pattern in patterns:
            m = __import__("re").search(pattern, vibe_lower)
            if m:
                bpm_match = m
                break

        if bpm_match:
            groups = bpm_match.groups()
            if len(groups) == 2:
                bpm_low, bpm_high = int(groups[0]), int(groups[1])
            elif "+" in bpm_match.group():
                bpm_low, bpm_high = int(groups[0]), 200
            else:
                bpm_low, bpm_high = int(groups[0]) - 4, int(groups[0]) + 4

            # Allow ±3 BPM tolerance
            filtered = [
                t for t in filtered
                if not t.get("bpm") or (bpm_low - 3 <= t["bpm"] <= bpm_high + 3)
            ]

        # Genre keyword matching
        genre_keywords = []
        genre_terms = [
            "techno", "house", "minimal", "disco", "trance", "breaks",
            "electro", "ambient", "acid", "garage", "dubstep", "dnb",
            "drum and bass", "melodic", "progressive", "deep", "tech house",
            "afro", "tribal", "industrial", "dub",
        ]
        for term in genre_terms:
            if term in vibe_lower:
                genre_keywords.append(term)

        if genre_keywords:
            def genre_match(track):
                g = (track.get("genre") or "").lower()
                t = (track.get("title") or "").lower()
                a = (track.get("artist") or "").lower()
                combined = f"{g} {t} {a}"
                return any(kw in combined for kw in genre_keywords) or not g
            filtered = [t for t in filtered if genre_match(t)]

        return filtered

    def _ai_sequence(
        self, pool: list[dict], vibe: str, max_tracks: int
    ) -> Optional[dict]:
        """Use Claude to sequence the tracks."""

        # Prepare a compact track list for the prompt
        compact_pool = []
        for t in pool:
            compact_pool.append({
                "title": t["title"],
                "artist": t["artist"],
                "bpm": t.get("bpm"),
                "key": t.get("key"),
                "genre": t.get("genre"),
                "label": t.get("label"),
                "set_position": t.get("set_position"),
                "play_count": t.get("play_count", 1),
            })

        system_prompt = """You are a professional DJ and crate digger building a setlist.

RULES:
1. Select up to {max_tracks} tracks from the provided pool.
2. Only use tracks that EXIST in the pool. Never invent track names.
3. Sequence for smooth transitions: compatible keys (Camelot wheel), gradual BPM changes (max ±4 between adjacent tracks), and a natural energy arc.
4. Match the user's vibe description in genre feel and energy.
5. Prefer tracks with higher play_count (DJ favorites).
6. Build an energy arc: start mellow, build to peak, then bring it down.

Return ONLY valid JSON with no markdown formatting:
{{"reasoning": "2-3 sentences explaining your selection and sequencing logic", "setlist": ["Track Title 1", "Track Title 2", ...]}}

Track titles must match EXACTLY as they appear in the pool.""".replace("{max_tracks}", str(max_tracks))

        user_message = f"""Track pool ({len(compact_pool)} tracks):
{json.dumps(compact_pool, indent=1)}

Vibe: "{vibe}"

Build me an ordered setlist of up to {max_tracks} tracks. Return only JSON."""

        try:
            headers = {
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            }

            payload = {
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            }

            log.info("Calling Claude API for setlist sequencing...")
            resp = requests.post(self.api_url, headers=headers, json=payload, timeout=30)

            if resp.status_code != 200:
                log.warning(f"Claude API returned {resp.status_code}: {resp.text[:200]}")
                return None

            data = resp.json()
            text = "".join(block.get("text", "") for block in data.get("content", []))
            text = text.strip().strip("`").strip()
            if text.startswith("json"):
                text = text[4:].strip()

            parsed = json.loads(text)
            ordered_titles = parsed.get("setlist", [])
            reasoning = parsed.get("reasoning", "")

            # Validate against pool — only keep tracks that actually exist
            title_to_track = {t["title"].lower(): t for t in pool}
            setlist = []
            for title in ordered_titles:
                match = title_to_track.get(title.lower())
                if match:
                    setlist.append(match)

            if not setlist:
                log.warning("AI returned no valid track matches")
                return None

            log.info(f"AI built setlist: {len(setlist)} tracks")
            return {
                "setlist": setlist,
                "reasoning": reasoning,
                "vibe": vibe,
                "stats": self._setlist_stats(setlist),
            }

        except Exception as e:
            log.error(f"AI sequencing failed: {e}")
            return None

    def _rule_based_sequence(
        self, pool: list[dict], vibe: str, max_tracks: int
    ) -> dict:
        """
        Fallback: sequence tracks using rules.
        
        Strategy:
        1. Sort by BPM
        2. Build energy arc (start low, peak in middle, come down)
        3. Prefer key-compatible adjacent tracks
        4. Prefer tracks with higher play count
        """
        if not pool:
            return {"setlist": [], "reasoning": "No tracks in pool.", "vibe": vibe, "stats": {}}

        # Score each track
        scored = []
        for t in pool:
            score = t.get("play_count", 1) * 2
            if t.get("bpm"):
                score += 1
            if t.get("key"):
                score += 1
            if t.get("genre"):
                score += 1
            scored.append((score, t))

        # Sort by score, take top candidates
        scored.sort(key=lambda x: -x[0])
        candidates = [t for _, t in scored[:max_tracks * 2]]

        # Sort candidates by BPM for the energy arc
        with_bpm = [t for t in candidates if t.get("bpm")]
        without_bpm = [t for t in candidates if not t.get("bpm")]
        with_bpm.sort(key=lambda t: t["bpm"])

        # Build the arc: slow start -> peak -> slight cooldown
        n = min(max_tracks, len(with_bpm) + len(without_bpm))
        if not with_bpm:
            setlist = candidates[:n]
        else:
            # Split into thirds
            third = max(1, len(with_bpm) // 3)
            openers = with_bpm[:third]
            peak = with_bpm[third:]
            # Interleave unknown-BPM tracks into the middle
            mid_section = peak[:len(peak)//2] + without_bpm + peak[len(peak)//2:]
            
            ordered = openers + mid_section
            setlist = ordered[:n]

        # Greedy key-compatibility reordering
        if len(setlist) > 2:
            setlist = self._reorder_by_key(setlist)

        return {
            "setlist": setlist,
            "reasoning": f"Rule-based sequencing: {len(setlist)} tracks ordered by BPM progression with key-compatible transitions. Tracks with higher play frequency across sets were preferred.",
            "vibe": vibe,
            "stats": self._setlist_stats(setlist),
        }

    def _reorder_by_key(self, tracks: list[dict]) -> list[dict]:
        """Greedy nearest-neighbor reordering for key compatibility."""
        if len(tracks) <= 2:
            return tracks

        remaining = list(tracks)
        ordered = [remaining.pop(0)]

        while remaining:
            last_key = ordered[-1].get("key", "")
            last_bpm = ordered[-1].get("bpm", 128)

            # Score each candidate
            best_idx = 0
            best_score = -999

            for i, t in enumerate(remaining):
                score = 0
                # Key compatibility bonus
                t_key = t.get("key", "")
                if last_key and t_key and camelot_compatible(last_key, t_key):
                    score += 10
                # BPM proximity bonus (prefer small jumps)
                t_bpm = t.get("bpm")
                if t_bpm and last_bpm:
                    diff = abs(t_bpm - last_bpm)
                    if diff <= 2:
                        score += 5
                    elif diff <= 4:
                        score += 3
                    elif diff <= 6:
                        score += 1
                    else:
                        score -= 2
                # Play count bonus
                score += t.get("play_count", 1) * 0.5

                if score > best_score:
                    best_score = score
                    best_idx = i

            ordered.append(remaining.pop(best_idx))

        return ordered

    @staticmethod
    def _setlist_stats(setlist: list[dict]) -> dict:
        bpms = [t["bpm"] for t in setlist if t.get("bpm")]
        keys = [t["key"] for t in setlist if t.get("key")]
        genres = [t["genre"] for t in setlist if t.get("genre")]

        # Check key compatibility chain
        compatible_transitions = 0
        total_transitions = max(len(keys) - 1, 1)
        for i in range(len(keys) - 1):
            if camelot_compatible(keys[i], keys[i + 1]):
                compatible_transitions += 1

        return {
            "track_count": len(setlist),
            "bpm_range": f"{min(bpms)}-{max(bpms)}" if bpms else "unknown",
            "bpm_avg": round(sum(bpms) / len(bpms), 1) if bpms else None,
            "key_compatibility": f"{compatible_transitions}/{total_transitions} transitions",
            "genres": list(set(genres)),
        }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build a setlist from a track pool JSON")
    parser.add_argument("pool_file", help="JSON file from scraper.py output")
    parser.add_argument("vibe", help="Vibe description in quotes")
    parser.add_argument("--max-tracks", type=int, default=12)
    parser.add_argument("--no-ai", action="store_true", help="Use rule-based sequencing only")
    parser.add_argument("--output", "-o", default=None)

    args = parser.parse_args()

    with open(args.pool_file) as f:
        data = json.load(f)

    pool = data.get("track_pool", [])
    if not pool:
        print("No tracks in pool file")
        exit(1)

    builder = SetlistBuilder()
    result = builder.build(
        track_pool=pool,
        vibe=args.vibe,
        max_tracks=args.max_tracks,
        use_ai=not args.no_ai,
    )

    print(f"\n{'='*60}")
    print(f"  SETLIST — Vibe: \"{args.vibe}\"")
    print(f"  {result['stats'].get('track_count', 0)} tracks | "
          f"BPM: {result['stats'].get('bpm_range', '?')} | "
          f"Key compat: {result['stats'].get('key_compatibility', '?')}")
    print(f"{'='*60}")
    print(f"\n  {result['reasoning']}\n")

    for i, t in enumerate(result["setlist"]):
        bpm = t.get("bpm", "???")
        key = t.get("key", "?")
        label = t.get("label", "")
        buy = t.get("buy_link", "")
        print(f"  {i+1:2d}. {t['artist']} - {t['title']}")
        print(f"      {bpm}bpm | {key} | {label}" + (f" | {buy}" if buy else ""))

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2)
        print(f"\nSaved to {args.output}")
