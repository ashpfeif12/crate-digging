#!/usr/bin/env python3
"""
crate_digger/dig.py

Full pipeline: Artist name + vibe -> ordered, buyable setlist.

Usage:
    python dig.py "Peggy Gou" "dark minimal, 126-130bpm, late night"
    python dig.py "Keinemusik" "groovy disco, 120-124bpm, sunset" --mode most_liked --sets 3
    python dig.py "Dixon" "melodic techno, 128-134bpm" --mode most_viewed --output dixon_set.json
"""

import argparse
import json
import sys
import os

from scraper import CrateDigger
from builder import SetlistBuilder


def main():
    parser = argparse.ArgumentParser(
        description="🎧 Crate Digger — AI-powered setlist builder from 1001tracklists",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "Peggy Gou" "dark minimal, 126-130bpm, late night"
  %(prog)s "Keinemusik" "groovy disco house, 120-124bpm, sunset" --mode most_liked
  %(prog)s "Dixon" "melodic techno, 128-134bpm" --mode most_viewed --sets 3 --enrich
  %(prog)s "Ben UFO" "eclectic, mixed bpm, afterhours" --no-ai --max-tracks 15
        """
    )
    parser.add_argument("artist", help="DJ/artist name to search on 1001tracklists")
    parser.add_argument("vibe", help="Natural language vibe description (in quotes)")

    # Scraping options
    scrape = parser.add_argument_group("scraping options")
    scrape.add_argument("--mode", choices=["recent", "most_viewed", "most_liked"],
                        default="recent",
                        help="How to select sets: recent (chronological), "
                             "most_viewed (highest traffic), most_liked (community favorites)")
    scrape.add_argument("--sets", type=int, default=5,
                        help="Number of sets to scrape (default: 5)")
    scrape.add_argument("--enrich", action="store_true",
                        help="Fetch individual track pages for BPM/key/label (slower, more metadata)")
    scrape.add_argument("--delay", type=float, default=2.0,
                        help="Seconds between HTTP requests (default: 2.0, be polite)")
    scrape.add_argument("--cache", default=".crate_cache",
                        help="Cache directory for HTML (default: .crate_cache)")

    # Builder options
    build = parser.add_argument_group("setlist builder options")
    build.add_argument("--max-tracks", type=int, default=12,
                       help="Max tracks in the final setlist (default: 12)")
    build.add_argument("--no-ai", action="store_true",
                       help="Skip Claude API, use rule-based sequencing only")

    # Output options
    output = parser.add_argument_group("output options")
    output.add_argument("--output", "-o", default=None,
                        help="Save full results as JSON")
    output.add_argument("--csv", default=None,
                        help="Export track pool as CSV (for Rekordbox, etc.)")
    output.add_argument("--pool-only", action="store_true",
                        help="Only scrape and output the pool, skip setlist building")
    output.add_argument("--quiet", "-q", action="store_true",
                        help="Minimal output")

    args = parser.parse_args()

    # ---- Banner ----
    if not args.quiet:
        print("""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║   ██████╗██████╗  █████╗ ████████╗███████╗               ║
║  ██╔════╝██╔══██╗██╔══██╗╚══██╔══╝██╔════╝               ║
║  ██║     ██████╔╝███████║   ██║   █████╗                  ║
║  ██║     ██╔══██╗██╔══██║   ██║   ██╔══╝                  ║
║  ╚██████╗██║  ██║██║  ██║   ██║   ███████╗                ║
║   ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝   ╚═╝   ╚══════╝                ║
║                                                          ║
║  ██████╗ ██╗ ██████╗  ██████╗ ███████╗██████╗            ║
║  ██╔══██╗██║██╔════╝ ██╔════╝ ██╔════╝██╔══██╗           ║
║  ██║  ██║██║██║  ███╗██║  ███╗█████╗  ██████╔╝           ║
║  ██║  ██║██║██║   ██║██║   ██║██╔══╝  ██╔══██╗           ║
║  ██████╔╝██║╚██████╔╝╚██████╔╝███████╗██║  ██║           ║
║  ╚═════╝ ╚═╝ ╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝           ║
║                                                          ║
║  AI-powered setlist builder from 1001tracklists          ║
╚══════════════════════════════════════════════════════════╝
        """)

    # ---- Stage 1: Scrape ----
    if not args.quiet:
        print(f"  ⏺ SCRAPING: {args.artist}")
        print(f"    Mode: {args.mode} | Sets: {args.sets}")
        print(f"    Delay: {args.delay}s | Cache: {args.cache}")
        print()

    digger = CrateDigger(delay=args.delay, cache_dir=args.cache)
    dig_result = digger.dig(
        artist=args.artist,
        mode=args.mode,
        num_sets=args.sets,
        enrich=args.enrich,
    )

    pool = dig_result.get("track_pool", [])
    stats = dig_result.get("stats", {})

    if not pool:
        print("  ✗ No tracks found. Check the artist name or try a different mode.")
        sys.exit(1)

    if not args.quiet:
        print(f"\n  ✓ TRACK POOL: {stats.get('total_tracks', 0)} unique tracks")
        print(f"    From {stats.get('tracklists_parsed', 0)} sets "
              f"({stats.get('total_raw_tracks', 0)} raw → {stats.get('total_tracks', 0)} deduplicated)")
        print(f"    BPM range: {stats.get('bpm_range', '?')}")
        if stats.get('top_genres'):
            print(f"    Genres: {', '.join(stats['top_genres'])}")
        if stats.get('top_labels'):
            print(f"    Labels: {', '.join(stats['top_labels'])}")
        print()

    # Save pool if requested
    if args.csv:
        digger.to_csv(dig_result, args.csv)
        print(f"  → Pool exported to {args.csv}")

    if args.pool_only:
        if args.output:
            digger.to_json(dig_result, args.output)
            print(f"  → Pool saved to {args.output}")
        sys.exit(0)

    # ---- Stage 2: Build Setlist ----
    if not args.quiet:
        print(f"  ⏺ BUILDING SETLIST")
        print(f"    Vibe: \"{args.vibe}\"")
        print(f"    Max tracks: {args.max_tracks}")
        print(f"    AI: {'off (rule-based)' if args.no_ai else 'Claude API'}")
        print()

    builder = SetlistBuilder()
    build_result = builder.build(
        track_pool=pool,
        vibe=args.vibe,
        max_tracks=args.max_tracks,
        use_ai=not args.no_ai,
    )

    setlist = build_result.get("setlist", [])
    set_stats = build_result.get("stats", {})

    if not setlist:
        print("  ✗ Could not build a setlist. Try broadening your vibe description.")
        sys.exit(1)

    # ---- Output ----
    print(f"""
{'═'*60}
  YOUR SETLIST
  Vibe: "{args.vibe}"
  {set_stats.get('track_count', 0)} tracks | BPM: {set_stats.get('bpm_range', '?')} | Key compat: {set_stats.get('key_compatibility', '?')}
{'═'*60}
""")

    if build_result.get("reasoning"):
        print(f"  💭 {build_result['reasoning']}\n")

    for i, t in enumerate(setlist):
        bpm = t.get("bpm", "???")
        key = t.get("key", "?")
        label = t.get("label", "")
        plays = t.get("play_count", 1)
        buy = t.get("buy_link", "")

        # Position indicator
        total = len(setlist)
        if i < total * 0.2:
            phase = "░"  # opener
        elif i < total * 0.4:
            phase = "▒"  # warmup
        elif i < total * 0.8:
            phase = "▓"  # peak
        else:
            phase = "░"  # closer

        print(f"  {phase} {i+1:2d}. {t['artist']} — {t['title']}")
        info_parts = [f"{bpm}bpm", key]
        if label:
            info_parts.append(label)
        if plays > 1:
            info_parts.append(f"played {plays}x")
        print(f"       {' · '.join(info_parts)}")
        if buy:
            print(f"       → {buy}")
        print()

    print(f"{'═'*60}")

    # Save full results
    if args.output:
        full_result = {
            "artist": args.artist,
            "vibe": args.vibe,
            "mode": args.mode,
            "scrape_stats": stats,
            "setlist_stats": set_stats,
            "reasoning": build_result.get("reasoning", ""),
            "setlist": setlist,
            "full_track_pool": pool,
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(full_result, f, indent=2, ensure_ascii=False)
        print(f"\n  → Full results saved to {args.output}")


if __name__ == "__main__":
    main()
