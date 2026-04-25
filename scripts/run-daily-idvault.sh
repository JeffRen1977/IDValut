#!/usr/bin/env bash
# =============================================================================
# IDVault — Daily monitoring pipeline
#
# Pulls today's video URLs from ingest/, downloads each via yt-dlp, runs the
# local face-recognition scanner against known_faces/index.json, cross-checks
# licenses/, and writes structured alerts into reports/<DATE>/.
#
# Sources of face-recognition logic:
#   scripts/face_utils.py    - DeepFace detect + Facenet embedding + cosine
#                               (extracted from faceIdentity-main/backend)
#   scripts/analyze_video.py - frame loop + matching + alert JSON emitter
#                               (adapted from faceIdentity-main/backend/video_utils.py,
#                                Firebase / SQL removed)
#
# Usage:
#   scripts/run-daily-idvault.sh [YYYY-MM-DD] [--discover] [--send-warnings] [--send-whatsapp]
#
# Flags:
#   --discover        Run scripts/run-discover.sh first to populate
#                     ingest/<DATE>/sources.json from YouTube / TikTok seeds.
#                     Equivalent to IDVAULT_DISCOVER=1.
#   --send-warnings   After scanning, email alert_*.json via
#                     scripts/send-warnings.sh. Equivalent to
#                     IDVAULT_SEND_WARNINGS=1.
#   --send-whatsapp   After scanning, send one WhatsApp digest via
#                     scripts/send-whatsapp-alerts.sh. Equivalent to
#                     IDVAULT_SEND_WHATSAPP=1.
#
# Ingest sources (first one found wins):
#   ingest/<DATE>/sources.json      — {"urls": [{"url": "...", "platform": "..."}, ...]}
#   ingest/daily_urls.txt           — one URL per line (# comments allowed)
#
# Environment knobs (optional, e.g. export in ~/.idvault-env):
#   FRAME_INTERVAL=30     # process every Nth frame
#   MATCH_THRESHOLD=0.6   # cosine similarity threshold
#   MAX_FRAMES=0          # cap processed frames per video (0 = no cap)
#   YTDLP_FORMAT='mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]'
#   KEEP_MEDIA=0          # 1 to keep downloaded media after scan
#   IDVAULT_DISCOVER=1    # run discovery orchestrator before scanning
#   IDVAULT_SEND_WHATSAPP=1 # send one WhatsApp digest after scanning
#   LOG=/tmp/idvault-daily.log
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

DATE=""
RUN_DISCOVER="${IDVAULT_DISCOVER:-0}"
SEND_WARNINGS="${IDVAULT_SEND_WARNINGS:-0}"
SEND_WHATSAPP="${IDVAULT_SEND_WHATSAPP:-0}"
for arg in "$@"; do
  case "$arg" in
    --discover)        RUN_DISCOVER=1 ;;
    --no-discover)     RUN_DISCOVER=0 ;;
    --send-warnings)   SEND_WARNINGS=1 ;;
    --no-send-warnings) SEND_WARNINGS=0 ;;
    --send-whatsapp)   SEND_WHATSAPP=1 ;;
    --no-send-whatsapp) SEND_WHATSAPP=0 ;;
    -*)                echo "unknown flag: $arg" >&2; exit 2 ;;
    *)                 [[ -z "$DATE" ]] && DATE="$arg" ;;
  esac
done
DATE="${DATE:-$(date +%Y-%m-%d)}"
COMPACT_DATE="${DATE//-/}"

LOG="${LOG:-/tmp/idvault-daily.log}"
FRAME_INTERVAL="${FRAME_INTERVAL:-30}"
MATCH_THRESHOLD="${MATCH_THRESHOLD:-0.6}"
MAX_FRAMES="${MAX_FRAMES:-0}"
YTDLP_FORMAT="${YTDLP_FORMAT:-mp4/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best}"
KEEP_MEDIA="${KEEP_MEDIA:-0}"

# DeepFace relies on Keras 2 semantics; TF >= 2.16 defaults to Keras 3, so we
# force the legacy path. The Python modules set the same default, but exporting
# here also covers any subprocess (e.g. pure `python3 -c "import deepface"`).
export TF_USE_LEGACY_KERAS="${TF_USE_LEGACY_KERAS:-1}"
export TF_CPP_MIN_LOG_LEVEL="${TF_CPP_MIN_LOG_LEVEL:-2}"

INDEX="$ROOT/known_faces/index.json"
IMAGES_DIR="$ROOT/known_faces/images"
SRC_JSON="$ROOT/ingest/$DATE/sources.json"
SRC_TXT="$ROOT/ingest/daily_urls.txt"
CACHE="$ROOT/ingest/cache/$DATE"
REPORTS="$ROOT/reports/$DATE"

mkdir -p "$CACHE" "$REPORTS"

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG" >&2; }

# Optional: per-user env (API keys, webhook URLs, etc.)
if [[ -f "$HOME/.idvault-env" ]]; then
  # shellcheck disable=SC1090
  source "$HOME/.idvault-env"
fi

# Prefer the project venv so cron (which has a stripped PATH) picks up
# deepface/opencv/numpy. Falls back to system python3 for interactive
# installs that haven't built a venv yet.
if [[ -z "${PYTHON:-}" ]]; then
  if [[ -x "$ROOT/.venv/bin/python3" ]]; then
    PYTHON="$ROOT/.venv/bin/python3"
  elif [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON="$ROOT/.venv/bin/python"
  else
    PYTHON="python3"
  fi
fi
export PYTHON

# -----------------------------------------------------------------------------
# 0. Preflight
# -----------------------------------------------------------------------------

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    log "ERROR: required tool not found: $1"
    exit 127
  fi
}

need "$PYTHON"
need yt-dlp
need jq

if ! "$PYTHON" -c "import cv2, numpy, deepface" >/dev/null 2>&1; then
  log "ERROR: python deps missing in $PYTHON. Run:  $PYTHON -m pip install -r $SCRIPT_DIR/requirements.txt"
  exit 1
fi

log "IDVault daily run start, DATE=$DATE frame_interval=$FRAME_INTERVAL threshold=$MATCH_THRESHOLD"

# -----------------------------------------------------------------------------
# 1. Ensure known_faces index exists (build from images if needed)
# -----------------------------------------------------------------------------

if [[ ! -f "$INDEX" ]]; then
  if [[ -d "$IMAGES_DIR" ]] && compgen -G "$IMAGES_DIR/*/*" >/dev/null; then
    log "index.json missing, building from $IMAGES_DIR"
    "$PYTHON" "$SCRIPT_DIR/build_known_faces.py" "$IMAGES_DIR" "$INDEX" 2>&1 | tee -a "$LOG"
  else
    log "ERROR: no known_faces index and no reference images under $IMAGES_DIR"
    log "  Put reference photos under known_faces/images/<subject_id>/*.jpg and rerun."
    exit 2
  fi
fi

# -----------------------------------------------------------------------------
# 1b. (Optional) Discovery: refresh ingest/<DATE>/sources.json from seeds.yaml
# -----------------------------------------------------------------------------

if [[ "$RUN_DISCOVER" == "1" ]]; then
  if [[ -x "$SCRIPT_DIR/run-discover.sh" ]]; then
    log "running discovery before scan"
    "$SCRIPT_DIR/run-discover.sh" "$DATE" || log "discovery exited non-zero (continuing with whatever sources exist)"
  else
    log "WARN: run-discover.sh not found or not executable; skipping discovery"
  fi
fi

# -----------------------------------------------------------------------------
# 2. Load today's URL list
# -----------------------------------------------------------------------------

urls_file="$(mktemp)"
trap 'rm -f "$urls_file"' EXIT

if [[ -f "$SRC_JSON" ]]; then
  log "ingest source: $SRC_JSON"
  # Each line: "<url>\t<platform>\t<title>\t<discovery_source>" (tabs, any trailing field optional)
  jq -r '.urls[] | [ .url, (.platform // ""), (.title // ""), (.discovery_source // "") ] | @tsv' "$SRC_JSON" > "$urls_file"
elif [[ -f "$SRC_TXT" ]]; then
  log "ingest source: $SRC_TXT"
  grep -E -v '^\s*(#|$)' "$SRC_TXT" | awk -F'\t' '{printf "%s\t\t\t\n", $1}' > "$urls_file"
else
  log "no ingest source at $SRC_JSON or $SRC_TXT; nothing to do"
  exit 0
fi

url_count=$(wc -l < "$urls_file" | tr -d ' ')
log "URLs to process: $url_count"

# -----------------------------------------------------------------------------
# 3. Per-URL: download -> analyze -> alert
# -----------------------------------------------------------------------------

infer_platform() {
  local url="$1"
  case "$url" in
    *youtube.com*|*youtu.be*) echo "youtube" ;;
    *tiktok.com*)             echo "tiktok" ;;
    *)                        echo "other" ;;
  esac
}

next_alert_id() {
  local n
  n=$(find "$REPORTS" -maxdepth 1 -name 'alert_*.json' 2>/dev/null | wc -l | tr -d ' ')
  printf "IDV-%s-%03d" "$COMPACT_DATE" $((n + 1))
}

next_case_id() {
  local n="$1"
  printf "CASE-%s-%03d" "$DATE" "$n"
}

seq_no=0

while IFS=$'\t' read -r url platform hint_title hint_source; do
  [[ -z "$url" ]] && continue
  seq_no=$((seq_no + 1))
  platform="${platform:-$(infer_platform "$url")}"
  [[ -n "$hint_source" ]] && log "---- [$seq_no/$url_count] $platform :: $url (from: $hint_source)" \
                         ||  log "---- [$seq_no/$url_count] $platform :: $url"

  vid="$(yt-dlp --get-id "$url" 2>>"$LOG" || true)"
  if [[ -z "$vid" ]]; then
    log "  skip: cannot resolve video id"
    continue
  fi
  title="$(yt-dlp --get-title "$url" 2>>"$LOG" || true)"
  [[ -z "$title" && -n "$hint_title" ]] && title="$hint_title"

  media="$CACHE/${platform}_${vid}.mp4"
  if [[ ! -s "$media" ]]; then
    log "  downloading to $media"
    if ! yt-dlp -q --no-warnings \
         -f "$YTDLP_FORMAT" \
         --merge-output-format mp4 \
         -o "$media" "$url" >>"$LOG" 2>&1; then
      log "  skip: yt-dlp download failed"
      continue
    fi
  else
    log "  using cached media"
  fi

  scan_out="$REPORTS/scan_${platform}_${vid}.json"
  alert_id="$(next_alert_id)"
  case_id="$(next_case_id "$seq_no")"
  alert_out="$REPORTS/alert_${alert_id}.json"

  if ! "$PYTHON" "$SCRIPT_DIR/analyze_video.py" \
      --video "$media" \
      --index "$INDEX" \
      --scan-out "$scan_out" \
      --alert-out "$alert_out" \
      --licenses-dir "$ROOT/licenses" \
      --threshold "$MATCH_THRESHOLD" \
      --frame-interval "$FRAME_INTERVAL" \
      --max-frames "$MAX_FRAMES" \
      --alert-id "$alert_id" \
      --case-id "$case_id" \
      --platform "$platform" \
      --video-url "$url" \
      --video-title "${title:-}" \
      --video-id "$vid" \
      --llm-summary-sources "title" \
      >> "$LOG" 2>&1; then
    log "  skip: analyze failed (see $LOG)"
    [[ "$KEEP_MEDIA" == "1" ]] || rm -f "$media"
    continue
  fi

  if [[ -f "$alert_out" ]]; then
    n_match="$(jq '.matched_subjects | length' "$alert_out")"
    reason="$(jq -r '.alert_reason' "$alert_out")"
    log "  ALERT $alert_id: reason=$reason subjects=$n_match -> $alert_out"
  else
    log "  no match"
  fi

  [[ "$KEEP_MEDIA" == "1" ]] || rm -f "$media"
done < "$urls_file"

# -----------------------------------------------------------------------------
# 4. Per-day summary (list alert files + top-line counts)
# -----------------------------------------------------------------------------

summary_path="$REPORTS/summary.json"
"$PYTHON" - "$REPORTS" "$DATE" "$summary_path" <<'PY'
import json, sys, glob, os
reports_dir, date, out = sys.argv[1], sys.argv[2], sys.argv[3]
alerts = []
for p in sorted(glob.glob(os.path.join(reports_dir, "alert_*.json"))):
    try:
        a = json.load(open(p, encoding="utf-8"))
        alerts.append({
            "alert_id": a.get("alert_id"),
            "case_id":  a.get("case_id"),
            "platform": a.get("platform"),
            "url":      (a.get("video") or {}).get("url"),
            "title":    (a.get("video") or {}).get("title"),
            "reason":   a.get("alert_reason"),
            "subjects": [m.get("celebrity_label") for m in a.get("matched_subjects", [])],
            "file":     os.path.relpath(p, reports_dir),
        })
    except Exception as e:
        print(f"[summary] skip {p}: {e}", file=sys.stderr)
summary = {
    "date": date,
    "alert_count": len(alerts),
    "alerts": alerts,
}
with open(out, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2, ensure_ascii=False)
print(f"[summary] wrote {out} ({len(alerts)} alerts)")
PY

log "IDVault daily run done. Reports at $REPORTS"

# -----------------------------------------------------------------------------
# 5. Optional: email alerts
# -----------------------------------------------------------------------------

if [[ "$SEND_WARNINGS" == "1" ]]; then
  n_alerts=$(find "$REPORTS" -maxdepth 1 -name 'alert_*.json' 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$n_alerts" -gt 0 ]]; then
    log "dispatching $n_alerts alert(s) via send-warnings.sh"
    "$SCRIPT_DIR/send-warnings.sh" "$DATE" >>"$LOG" 2>&1 || log "send-warnings.sh failed (see $LOG)"
  else
    log "no alerts to send"
  fi
fi

# -----------------------------------------------------------------------------
# 6. Optional: WhatsApp daily digest
# -----------------------------------------------------------------------------

if [[ "$SEND_WHATSAPP" == "1" ]]; then
  if [[ -x "$SCRIPT_DIR/send-whatsapp-alerts.sh" ]]; then
    log "dispatching WhatsApp digest via send-whatsapp-alerts.sh"
    "$SCRIPT_DIR/send-whatsapp-alerts.sh" "$DATE" >>"$LOG" 2>&1 || log "send-whatsapp-alerts.sh failed (see $LOG)"
  else
    log "WARN: send-whatsapp-alerts.sh not found or not executable; skipping WhatsApp digest"
  fi
fi

# Dispatch credentials live in ~/.idvault-env (SMTP_HOST/USER/PASSWORD/FROM).
# Recipient list is in ingest/notifications.yaml. Never commit credentials.
