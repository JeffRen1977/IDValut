#!/usr/bin/env python3
"""
IDVault — Discover YouTube videos via per-channel RSS feeds.

For every channel listed under `youtube.channels` in ingest/seeds.yaml,
pull its public Atom feed (no auth, no API quota) and emit candidates.

Output shape matches discover_youtube.py so _merge_candidates.py can merge
them side by side.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _discover_common import load_seeds, write_candidates  # noqa: E402


NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}

FEED_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def fetch_channel(channel_id: str, limit: int = 25, timeout: int = 30) -> list[dict]:
    url = FEED_URL.format(channel_id=channel_id)
    req = Request(url, headers={"User-Agent": "IDVault/1.0 discovery-rss"})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)

    rows: list[dict] = []
    for entry in root.findall("atom:entry", NS)[:limit]:
        vid = entry.findtext("yt:videoId", default="", namespaces=NS)
        if not vid:
            continue
        title = entry.findtext("atom:title", default="", namespaces=NS)
        author = entry.findtext("atom:author/atom:name", default="", namespaces=NS)
        published = entry.findtext("atom:published", default="", namespaces=NS) or None
        rows.append({
            "platform": "youtube",
            "platform_video_id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "title": title,
            "channel": author,
            "published_at": published,
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="ingest/seeds.yaml")
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=25, help="Max entries per channel feed")
    ap.add_argument("--sleep", type=float, default=0.5)
    args = ap.parse_args()

    seeds = load_seeds(args.seeds)
    channels = (seeds.get("youtube") or {}).get("channels") or []

    results: list[dict] = []
    print(f"[discover_rss] channels={len(channels)}", file=sys.stderr)

    for c in channels:
        if isinstance(c, dict):
            cid = c.get("id")
            note = c.get("note", "")
        else:
            cid = str(c)
            note = ""
        if not cid:
            continue
        tag = f"youtube_rss:channel:{cid}"
        print(f"  [{tag}] {note}", file=sys.stderr)
        try:
            rows = fetch_channel(cid, limit=args.limit)
        except Exception as e:
            print(f"    error: {e}", file=sys.stderr)
            continue
        for r in rows:
            r["discovery_source"] = tag
            r["subject_hint"] = None  # RSS is channel-scoped; FR decides matches
        results.extend(rows)
        time.sleep(args.sleep)

    write_candidates(args.out, results)
    print(f"[discover_rss] wrote {len(results)} candidates -> {args.out}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
