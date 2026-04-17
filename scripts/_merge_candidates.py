#!/usr/bin/env python3
"""
IDVault — Merge per-engine discovery outputs into ingest/<DATE>/sources.json.

- Deduplicates against ingest/cache/seen.json (platform:video_id keys).
- Coalesces same-video hits from multiple engines into one row whose
  `discovery_source` becomes a "|"-joined list.
- Writes the merged sources.json in the format consumed by
  scripts/run-daily-idvault.sh (top-level { urls: [...] }).
- Updates seen.json so future runs skip these IDs.

Usage:
  python3 scripts/_merge_candidates.py \
      --date 2026-04-16 \
      --inputs ingest/2026-04-16/_discover_youtube.json \
               ingest/2026-04-16/_discover_rss.json \
               ingest/2026-04-16/_discover_tiktok.json \
      --seen   ingest/cache/seen.json \
      --out    ingest/2026-04-16/sources.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _load_json(p: Path, default):
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[merge] could not read {p}: {exc}", file=sys.stderr)
        return default


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", nargs="+", required=True, help="Per-engine candidate JSONs")
    ap.add_argument("--seen", required=True, help="Dedup cache path (created if missing)")
    ap.add_argument("--out", required=True, help="Merged sources.json output")
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = ap.parse_args()

    seen_path = Path(args.seen)
    seen = _load_json(seen_path, {}) or {}

    merged: list[dict] = []
    index_of: dict[str, int] = {}
    input_counts: dict[str, int] = {}

    for raw in args.inputs:
        p = Path(raw)
        rows = _load_json(p, [])
        input_counts[p.name] = len(rows) if isinstance(rows, list) else 0
        if not isinstance(rows, list):
            continue
        for r in rows:
            platform = r.get("platform")
            vid = r.get("platform_video_id")
            if not platform or not vid:
                continue
            key = f"{platform}:{vid}"
            if key in seen:
                continue
            if key in index_of:
                existing = merged[index_of[key]]
                src_new = r.get("discovery_source")
                if src_new and src_new != existing.get("discovery_source"):
                    existing["discovery_source"] = (
                        f"{existing['discovery_source']}|{src_new}"
                        if existing.get("discovery_source") else src_new
                    )
                if not existing.get("subject_hint") and r.get("subject_hint"):
                    existing["subject_hint"] = r["subject_hint"]
                continue

            index_of[key] = len(merged)
            merged.append({
                "url": r.get("url"),
                "platform": platform,
                "platform_video_id": vid,
                "title": r.get("title"),
                "channel": r.get("channel"),
                "published_at": r.get("published_at"),
                "subject_hint": r.get("subject_hint"),
                "discovery_source": r.get("discovery_source"),
            })

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "date": args.date,
        "generated_at": now,
        "input_counts": input_counts,
        "candidate_count": len(merged),
        "urls": merged,
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    for m in merged:
        key = f"{m['platform']}:{m['platform_video_id']}"
        seen[key] = {
            "first_seen": now,
            "discovery_source": m.get("discovery_source"),
            "title": m.get("title"),
        }
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    seen_path.write_text(json.dumps(seen, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"[merge] date={args.date} inputs={input_counts} new={len(merged)} -> {out_path}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
