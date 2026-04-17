#!/usr/bin/env python3
"""
IDVault — Discover YouTube videos via keyword search.

Primary:   YouTube Data API v3 `search.list` (requires $YOUTUBE_API_KEY).
Fallback:  yt-dlp `ytsearchN:"query"` (scrape-backed, no key).

Inputs:
    --seeds   ingest/seeds.yaml
    --index   known_faces/index.json
    --out     path to write candidates JSON
    --engine  auto|api|ytdlp  (default: auto)

Output is a JSON list of candidate dicts with keys:
    platform, platform_video_id, url, title, channel, published_at,
    subject_hint, discovery_source

Rate-limit / ToS posture is documented in docs/DISCOVERY_POLICY.md.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _discover_common import (  # noqa: E402
    load_seeds,
    load_subject_labels,
    write_candidates,
    ytdlp_date_to_iso,
    safe_getenv_path,
)


YT_API_URL = "https://www.googleapis.com/youtube/v3/search"


def build_queries(subjects: list[str], seeds: dict) -> list[dict]:
    modifiers: list[str] = seeds.get("keyword_modifiers") or ["{label}"]
    per_subject = seeds.get("subjects") or {}
    queries: list[dict] = []

    for label in subjects:
        cfg = per_subject.get(label) or {}
        if cfg.get("skip"):
            continue
        for m in modifiers:
            q = m.replace("{label}", label).strip()
            if not q:
                continue
            queries.append({"query": q, "subject_label": label, "modifier": m})
        for extra in cfg.get("extra_queries") or []:
            queries.append({
                "query": extra.strip(),
                "subject_label": label,
                "modifier": "per_subject_extra",
            })

    for kw in seeds.get("extra_keywords") or []:
        kw = (kw or "").strip()
        if not kw:
            continue
        queries.append({"query": kw, "subject_label": None, "modifier": "global_extra"})

    return queries


def youtube_api_search(query: str, api_key: str, max_results: int, published_after: str) -> list[dict]:
    params = {
        "part": "snippet",
        "type": "video",
        "maxResults": str(max_results),
        "q": query,
        "key": api_key,
        "publishedAfter": published_after,
        "order": "date",
    }
    url = YT_API_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "IDVault/1.0 discovery"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read())

    rows: list[dict] = []
    for item in data.get("items", []):
        vid = (item.get("id") or {}).get("videoId")
        if not vid:
            continue
        sn = item.get("snippet") or {}
        rows.append({
            "platform": "youtube",
            "platform_video_id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "title": sn.get("title"),
            "channel": sn.get("channelTitle"),
            "published_at": sn.get("publishedAt"),
        })
    return rows


def ytdlp_search(query: str, max_results: int, cookies: str | None = None) -> list[dict]:
    cmd = [
        "yt-dlp", "--flat-playlist", "--skip-download", "--quiet", "--no-warnings",
        "--playlist-end", str(max_results),
        "--print", "%(id)s\t%(title)s\t%(channel)s\t%(upload_date)s",
        f"ytsearch{max_results}:{query}",
    ]
    if cookies:
        cmd.extend(["--cookies", cookies])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  [ytdlp] error: {e}", file=sys.stderr)
        return []

    rows: list[dict] = []
    for line in (result.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 1 or not parts[0]:
            continue
        vid = parts[0]
        title = parts[1] if len(parts) > 1 else ""
        channel = parts[2] if len(parts) > 2 else ""
        upload_date = parts[3] if len(parts) > 3 else ""
        rows.append({
            "platform": "youtube",
            "platform_video_id": vid,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "title": title,
            "channel": channel,
            "published_at": ytdlp_date_to_iso(upload_date),
        })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="ingest/seeds.yaml")
    ap.add_argument("--index", default="known_faces/index.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--engine", choices=["auto", "api", "ytdlp"], default="auto")
    ap.add_argument("--sleep", type=float, default=0.4, help="Seconds between queries")
    args = ap.parse_args()

    seeds = load_seeds(args.seeds)
    subjects = load_subject_labels(args.index)
    queries = build_queries(subjects, seeds)

    api_key = os.environ.get("YOUTUBE_API_KEY")
    cookies = safe_getenv_path("YTDLP_COOKIES")
    engine = args.engine
    if engine == "auto":
        engine = "api" if api_key else "ytdlp"

    yt_cfg = seeds.get("youtube") or {}
    max_results = int(yt_cfg.get("max_results_per_query", 15))
    days = int(yt_cfg.get("published_within_days", 2))
    max_queries = int(yt_cfg.get("max_queries_per_run", 80))
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=days)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    if len(queries) > max_queries:
        print(f"[discover_youtube] capping queries {len(queries)} -> {max_queries} "
              f"(youtube.max_queries_per_run)", file=sys.stderr)
        queries = queries[:max_queries]

    print(f"[discover_youtube] engine={engine} queries={len(queries)} "
          f"subjects={len(subjects)} since={published_after}",
          file=sys.stderr)

    results: list[dict] = []
    quota_exhausted = False

    for q in queries:
        if quota_exhausted:
            break
        label = q["subject_label"] or ""
        tag = f"youtube_{engine}:{q['modifier']}:{label}"
        print(f"  [{tag}] q={q['query']!r}", file=sys.stderr)
        try:
            if engine == "api":
                rows = youtube_api_search(q["query"], api_key, max_results, published_after)
            else:
                rows = ytdlp_search(q["query"], max_results, cookies=cookies)
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            print(f"    http {e.code}: {body}", file=sys.stderr)
            if e.code in (403, 429):
                print("    quota / rate limit hit; stopping", file=sys.stderr)
                quota_exhausted = True
                break
            continue
        except Exception as e:
            print(f"    error: {e}", file=sys.stderr)
            continue

        for r in rows:
            r["discovery_source"] = tag
            r["subject_hint"] = q["subject_label"]
        results.extend(rows)
        time.sleep(args.sleep)

    write_candidates(args.out, results)
    print(f"[discover_youtube] wrote {len(results)} candidates -> {args.out}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
