#!/usr/bin/env python3
"""
IDVault — Discover TikTok videos from seeded users / hashtags.

TikTok does not provide a free public search API. To keep discovery auditable
and within reason, we only scan sources that a human operator has explicitly
added to `ingest/seeds.yaml`:

    tiktok:
      users:
        - { handle: "some_handle" }
      hashtags:
        - { tag: "aiface" }

We use `yt-dlp --flat-playlist` on the user profile and hashtag pages; yt-dlp
handles TikTok's web endpoints and returns per-video metadata.

If your region or account requires cookies (common), export YTDLP_COOKIES in
~/.idvault-env pointing to a Netscape-format cookies file. The script forwards
it via --cookies.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _discover_common import (  # noqa: E402
    load_seeds,
    write_candidates,
    ytdlp_date_to_iso,
    safe_getenv_path,
)


def ytdlp_list(url: str, limit: int, cookies: str | None) -> list[dict]:
    cmd = [
        "yt-dlp", "--flat-playlist", "--skip-download", "--quiet", "--no-warnings",
        "--playlist-end", str(limit),
        "--print", "%(id)s\t%(title)s\t%(uploader)s\t%(upload_date)s\t%(webpage_url)s",
        url,
    ]
    if cookies:
        cmd.extend(["--cookies", cookies])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  [ytdlp] error: {e}", file=sys.stderr)
        return []

    rows: list[dict] = []
    for line in (result.stdout or "").splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        vid = parts[0]
        title = parts[1] if len(parts) > 1 else ""
        uploader = parts[2] if len(parts) > 2 and parts[2] != "NA" else ""
        upload_date = parts[3] if len(parts) > 3 else ""
        webpage_url = parts[4] if len(parts) > 4 and parts[4] and parts[4] != "NA" else ""

        canonical = webpage_url
        if not canonical:
            if uploader:
                canonical = f"https://www.tiktok.com/@{uploader}/video/{vid}"
            else:
                canonical = f"https://www.tiktok.com/video/{vid}"

        rows.append({
            "platform": "tiktok",
            "platform_video_id": vid,
            "url": canonical,
            "title": title,
            "channel": uploader,
            "published_at": ytdlp_date_to_iso(upload_date),
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="ingest/seeds.yaml")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sleep", type=float, default=1.0)
    args = ap.parse_args()

    seeds = load_seeds(args.seeds)
    cfg = seeds.get("tiktok") or {}
    limit = int(cfg.get("max_results_per_source", 15))
    cookies = safe_getenv_path("YTDLP_COOKIES")

    users = cfg.get("users") or []
    hashtags = cfg.get("hashtags") or []
    print(f"[discover_tiktok] users={len(users)} hashtags={len(hashtags)} "
          f"limit_per_source={limit}",
          file=sys.stderr)

    results: list[dict] = []

    for u in users:
        handle = (u.get("handle") if isinstance(u, dict) else str(u or "")).lstrip("@")
        if not handle:
            continue
        url = f"https://www.tiktok.com/@{handle}"
        tag = f"tiktok_ytdlp:user:{handle}"
        print(f"  [{tag}]", file=sys.stderr)
        rows = ytdlp_list(url, limit, cookies)
        for r in rows:
            r["discovery_source"] = tag
            r["subject_hint"] = None
        results.extend(rows)
        time.sleep(args.sleep)

    for h in hashtags:
        tag_name = (h.get("tag") if isinstance(h, dict) else str(h or "")).lstrip("#")
        if not tag_name:
            continue
        url = f"https://www.tiktok.com/tag/{tag_name}"
        tag = f"tiktok_ytdlp:hashtag:{tag_name}"
        print(f"  [{tag}]", file=sys.stderr)
        rows = ytdlp_list(url, limit, cookies)
        for r in rows:
            r["discovery_source"] = tag
            r["subject_hint"] = None
        results.extend(rows)
        time.sleep(args.sleep)

    write_candidates(args.out, results)
    print(f"[discover_tiktok] wrote {len(results)} candidates -> {args.out}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
