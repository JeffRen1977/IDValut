#!/usr/bin/env bash
# =============================================================================
# IDVault — Discovery orchestrator
#
# Runs all three discovery engines, merges their outputs into today's
# ingest/<DATE>/sources.json, and updates ingest/cache/seen.json so previously
# scanned videos are never re-processed.
#
# Usage:
#   scripts/run-discover.sh [YYYY-MM-DD]
#
# Env:
#   YOUTUBE_API_KEY   # if set, discover_youtube.py uses the API (preferred)
#   YTDLP_COOKIES     # optional path to cookies.txt for TikTok
#   LOG               # override log path (default /tmp/idvault-discover.log)
#   IDVAULT_SKIP_YT=1       # skip discover_youtube.py
#   IDVAULT_SKIP_RSS=1      # skip discover_rss.py
#   IDVAULT_SKIP_TIKTOK=1   # skip discover_tiktok.py
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

DATE="${1:-$(date +%Y-%m-%d)}"
DAY_DIR="$ROOT/ingest/$DATE"
CACHE_DIR="$ROOT/ingest/cache"
LOG="${LOG:-/tmp/idvault-discover.log}"

mkdir -p "$DAY_DIR" "$CACHE_DIR"

if [[ -f "$HOME/.idvault-env" ]]; then
  # shellcheck disable=SC1090
  source "$HOME/.idvault-env"
fi

PY="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PY" ]]; then
  PY="python3"
fi

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG" >&2; }

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: required tool not found: $1"
    exit 127
  fi
}
need yt-dlp

if ! "$PY" -c "import yaml" >/dev/null 2>&1; then
  log "ERROR: PyYAML missing in $PY; run: pip install -r $SCRIPT_DIR/requirements.txt"
  exit 1
fi

log "discover start date=$DATE"

yt_json="$DAY_DIR/_discover_youtube.json"
rss_json="$DAY_DIR/_discover_rss.json"
tk_json="$DAY_DIR/_discover_tiktok.json"

# Default to empty arrays so the merger can always run, even if an engine is
# skipped or fails.
echo "[]" > "$yt_json"
echo "[]" > "$rss_json"
echo "[]" > "$tk_json"

if [[ "${IDVAULT_SKIP_YT:-0}" != "1" ]]; then
  log "  discover_youtube.py"
  "$PY" "$SCRIPT_DIR/discover_youtube.py" \
       --seeds "$ROOT/ingest/seeds.yaml" \
       --index "$ROOT/known_faces/index.json" \
       --out   "$yt_json" \
       2>>"$LOG" || log "    discover_youtube.py failed (continuing)"
fi

if [[ "${IDVAULT_SKIP_RSS:-0}" != "1" ]]; then
  log "  discover_rss.py"
  "$PY" "$SCRIPT_DIR/discover_rss.py" \
       --seeds "$ROOT/ingest/seeds.yaml" \
       --out   "$rss_json" \
       2>>"$LOG" || log "    discover_rss.py failed (continuing)"
fi

if [[ "${IDVAULT_SKIP_TIKTOK:-0}" != "1" ]]; then
  log "  discover_tiktok.py"
  "$PY" "$SCRIPT_DIR/discover_tiktok.py" \
       --seeds "$ROOT/ingest/seeds.yaml" \
       --out   "$tk_json" \
       2>>"$LOG" || log "    discover_tiktok.py failed (continuing)"
fi

merged="$DAY_DIR/sources.json"
log "  merge -> $merged"
"$PY" "$SCRIPT_DIR/_merge_candidates.py" \
     --inputs "$yt_json" "$rss_json" "$tk_json" \
     --seen   "$CACHE_DIR/seen.json" \
     --out    "$merged" \
     --date   "$DATE" \
     2>>"$LOG"

count=$(python3 -c "import json,sys; print(len(json.load(open('$merged')).get('urls',[])))" 2>/dev/null || echo "?")
log "discover done: $count candidate URLs -> $merged"
