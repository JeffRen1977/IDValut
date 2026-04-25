#!/usr/bin/env bash
# =============================================================================
# IDVault — send one daily WhatsApp digest for reports/<DATE>/ via OpenClaw.
#
# Usage:
#   scripts/send-whatsapp-alerts.sh                  # today
#   scripts/send-whatsapp-alerts.sh 2026-04-25       # specific date
#   scripts/send-whatsapp-alerts.sh 2026-04-25 --dry-run
#   scripts/send-whatsapp-alerts.sh --to +18586039367 reports/2026-04-25
#
# Recipients live in ingest/notifications.yaml (whatsapp.to). OpenClaw session
# credentials remain in ~/.openclaw/openclaw.json.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-$ROOT/.venv/bin/python}"
[[ -x "$PY" ]] || PY="python3"

if [[ -f "$HOME/.idvault-env" ]]; then
  # shellcheck disable=SC1090
  source "$HOME/.idvault-env"
fi

if ! command -v "${OPENCLAW_CMD:-openclaw}" >/dev/null 2>&1; then
  echo "ERROR: openclaw CLI not found on PATH. Install OpenClaw or set OPENCLAW_CMD." >&2
  exit 127
fi

date_or_dir=""
pass_through=()
prev=""
for arg in "$@"; do
  case "$prev" in
    --to|--config|--reports-dir)
      pass_through+=("$arg"); prev="$arg"; continue ;;
  esac
  case "$arg" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
      date_or_dir="--reports-dir reports/$arg" ;;
    reports/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]|reports/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]/)
      date_or_dir="--reports-dir ${arg%/}" ;;
    *)
      pass_through+=("$arg") ;;
  esac
  prev="$arg"
done

if [[ -z "$date_or_dir" ]]; then
  has_explicit=0
  for a in "${pass_through[@]}"; do
    [[ "$a" == "--reports-dir" ]] && has_explicit=1
  done
  [[ $has_explicit -eq 0 ]] && date_or_dir="--reports-dir reports/$(date +%Y-%m-%d)"
fi

# shellcheck disable=SC2086
exec "$PY" "$SCRIPT_DIR/send_whatsapp_alerts.py" \
     --config "$ROOT/ingest/notifications.yaml" \
     $date_or_dir \
     "${pass_through[@]}"
