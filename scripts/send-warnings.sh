#!/usr/bin/env bash
# =============================================================================
# IDVault — email the day's alert_*.json files to recipients in
# ingest/notifications.yaml.
#
# Usage:
#   scripts/send-warnings.sh                 # today
#   scripts/send-warnings.sh 2026-04-16      # specific date
#   scripts/send-warnings.sh 2026-04-16 --dry-run
#   scripts/send-warnings.sh --to someone@example.com reports/2026-04-16
#
# Any trailing argument that starts with "reports/" is passed as the reports
# directory. Otherwise the first positional arg is treated as YYYY-MM-DD.
# All unrecognized args are forwarded to scripts/send_warnings.py.
#
# Credentials (export in ~/.idvault-env):
#   SMTP_HOST=smtp.gmail.com
#   SMTP_PORT=587
#   SMTP_USER=you@example.com
#   SMTP_PASSWORD=<app password>
#   SMTP_FROM='IDVault <you@example.com>'   # optional, defaults to SMTP_USER
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

date_or_dir=""
pass_through=()
skip_next=0
prev=""
for arg in "$@"; do
  if [[ $skip_next -eq 1 ]]; then
    pass_through+=("$arg")
    skip_next=0
    prev="$arg"
    continue
  fi
  # If the previous token was a flag that takes a value, keep this one with it.
  case "$prev" in
    --alert|--to|--config|--reports-dir) pass_through+=("$arg"); prev="$arg"; continue ;;
  esac
  case "$arg" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9])
                                   date_or_dir="--reports-dir reports/$arg" ;;
    reports/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]|reports/[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]/)
                                   date_or_dir="--reports-dir ${arg%/}" ;;
    *)                             pass_through+=("$arg") ;;
  esac
  prev="$arg"
done

if [[ -z "$date_or_dir" ]]; then
  # Only default the reports-dir if the caller did not pass --reports-dir or --alert.
  has_explicit=0
  for a in "${pass_through[@]}"; do
    case "$a" in
      --reports-dir|--alert) has_explicit=1 ;;
    esac
  done
  [[ $has_explicit -eq 0 ]] && date_or_dir="--reports-dir reports/$(date +%Y-%m-%d)"
fi

# shellcheck disable=SC2086
exec "$PY" "$SCRIPT_DIR/send_warnings.py" \
     --config "$ROOT/ingest/notifications.yaml" \
     $date_or_dir \
     "${pass_through[@]}"
