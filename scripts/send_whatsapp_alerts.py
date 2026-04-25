#!/usr/bin/env python3
"""
IDVault — WhatsApp daily digest dispatcher via OpenClaw.

Reads reports/<DATE>/summary.json and alert_*.json files produced by
scripts/run-daily-idvault.sh, formats one chat-friendly summary, and sends it
through the existing OpenClaw WhatsApp channel:

    openclaw message send --channel whatsapp --target +1... --message "..." --json

Idempotency: writes reports/<DATE>/.sent/digest.whatsapp.json after a
successful send so reruns do not send duplicate daily notifications unless
--force is passed.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "pyyaml required: pip install -r scripts/requirements.txt") from exc


TIER_ORDER = {"low": 0, "medium": 1, "high": 2}


def _tier_rank(tier: str | None) -> int:
    return TIER_ORDER.get((tier or "low").lower(), 0)


def _alert_best_tier(alert: dict) -> str:
    best = "low"
    for m in alert.get("matched_subjects", []) or []:
        tier = (m.get("similarity_tier") or "low").lower()
        if _tier_rank(tier) > _tier_rank(best):
            best = tier
    return best


def _should_include(alert: dict, cfg: dict) -> tuple[bool, str]:
    reasons = cfg.get("include_reasons") or []
    reason = alert.get("alert_reason", "")
    if reasons and reason not in reasons:
        return False, f"reason {reason!r} not in include_reasons"
    min_tier = cfg.get("min_severity_tier") or "low"
    if _tier_rank(_alert_best_tier(alert)) < _tier_rank(min_tier):
        return False, f"tier below min_severity_tier={min_tier}"
    return True, ""


def _load_cfg(path: Path) -> dict:
    if not path.exists():
        return {}
    full = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return (full.get("whatsapp") or {}) if isinstance(full, dict) else {}


def _openclaw_bin(cfg: dict) -> str:
    cand = os.environ.get("OPENCLAW_CMD") or cfg.get("command") or "openclaw"
    if "/" not in cand and shutil.which(cand) is None:
        raise RuntimeError(
            f"openclaw CLI not found (looked for {cand!r} on PATH). "
            "Set OPENCLAW_CMD to the full binary path or fix cron PATH.")
    return cand


def _subject_line(match: dict) -> str:
    label = match.get("celebrity_label") or match.get("subject_id") or "unknown"
    license_status = match.get("license_status") or "unknown"
    tier = match.get("similarity_tier") or "low"
    sim = match.get("max_similarity")
    likeness = match.get("likeness_percentage")
    parts = [label, f"license={license_status}", f"tier={tier}"]
    if sim is not None:
        parts.append(f"sim={sim}")
    if likeness is not None:
        parts.append(f"likeness={likeness}%")
    return " | ".join(parts)


def _load_alerts(reports_dir: Path, cfg: dict) -> list[tuple[dict, Path]]:
    loaded: list[tuple[dict, Path]] = []
    for path in sorted(reports_dir.glob("alert_*.json")):
        try:
            alert = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[send_whatsapp_alerts] skip {path.name}: {exc}",
                  file=sys.stderr)
            continue
        ok, why = _should_include(alert, cfg)
        if not ok:
            print(f"[send_whatsapp_alerts] skip {path.name}: {why}",
                  file=sys.stderr)
            continue
        loaded.append((alert, path))
    loaded.sort(
        key=lambda ap: (
            -_tier_rank(_alert_best_tier(ap[0])),
            ap[0].get("alert_id") or "",
        )
    )
    return loaded


def build_digest_text(alerts: list[tuple[dict, Path]],
                      reports_dir: Path,
                      cfg: dict) -> str:
    run_date = reports_dir.name
    prefix = (cfg.get("subject_prefix") or "IDVault").strip()
    n = len(alerts)
    lines = [
        f"{prefix} WhatsApp digest · {run_date}",
        f"alerts: {n}",
    ]

    summary_path = reports_dir / "summary.json"
    if summary_path.exists():
        lines.append(f"summary: {summary_path}")
    else:
        lines.append(f"reports: {reports_dir}")

    if not alerts:
        lines.append("No matching face-license alerts today.")
        return "\n".join(lines)

    lines.append("Top alerts:")
    for alert, _ in alerts[:10]:
        video = alert.get("video") or {}
        title = (video.get("title") or "").strip()
        if len(title) > 90:
            title = title[:87] + "..."
        reason = alert.get("alert_reason") or "alert"
        platform = (alert.get("platform") or "?").upper()
        tier = _alert_best_tier(alert).upper()
        subject = _subject_line((alert.get("matched_subjects") or [{}])[0])
        lines.extend([
            f"- {platform} {reason} ({tier})",
            f"  {subject}",
        ])
        if title:
            lines.append(f"  {title}")
        if video.get("url"):
            lines.append(f"  {video['url']}")
    if len(alerts) > 10:
        lines.append(f"... +{len(alerts) - 10} more")
    return "\n".join(lines)


def send_whatsapp(text: str, to: str, cfg: dict, *,
                  dry_run: bool = False, verbose: bool = False) -> dict:
    if dry_run:
        print(f"--- DRY RUN -> WhatsApp {to} ---", file=sys.stderr)
        print(text)
        print("--------------------------------", file=sys.stderr)
        return {"ok": True, "dry_run": True}

    cmd = [
        _openclaw_bin(cfg),
        "message", "send",
        "--channel", "whatsapp",
        "--target", to,
        "--message", text,
        "--json",
    ]
    if verbose:
        cmd.append("--verbose")

    timeout = float(cfg.get("timeout_s") or 30)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"openclaw timed out after {timeout}s") from exc

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(
            f"openclaw exited {proc.returncode}: "
            f"{stderr or stdout or '<no output>'}")

    try:
        return json.loads(stdout) if stdout else {"ok": True}
    except json.JSONDecodeError:
        return {"ok": True, "raw": stdout, "stderr": stderr}


def main() -> int:
    ap = argparse.ArgumentParser(
        description="IDVault WhatsApp digest dispatcher via OpenClaw")
    ap.add_argument("--config", default="ingest/notifications.yaml")
    ap.add_argument("--reports-dir", required=True)
    ap.add_argument("--to", help="Override recipients, comma-separated E.164 numbers")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cfg = _load_cfg(Path(args.config))
    if args.to:
        cfg["to"] = [x.strip() for x in args.to.split(",") if x.strip()]

    if not cfg.get("enabled", False) and not args.to:
        print("[send_whatsapp_alerts] whatsapp disabled in "
              f"{args.config} (set whatsapp.enabled: true or pass --to).",
              file=sys.stderr)
        return 0

    recipients = [n for n in (cfg.get("to") or []) if n]
    if not recipients:
        print("[send_whatsapp_alerts] whatsapp.to is empty; nothing to do",
              file=sys.stderr)
        return 0

    reports_dir = Path(args.reports_dir)
    marker = reports_dir / ".sent" / "digest.whatsapp.json"
    if marker.exists() and not args.force and not args.dry_run:
        print(f"[send_whatsapp_alerts] digest already sent -> {marker}",
              file=sys.stderr)
        return 0

    alerts = _load_alerts(reports_dir, cfg)
    text = build_digest_text(alerts, reports_dir, cfg)

    sent_to: list[str] = []
    for to in recipients:
        try:
            send_whatsapp(text, to, cfg,
                          dry_run=args.dry_run, verbose=args.verbose)
        except Exception as exc:
            print(f"[send_whatsapp_alerts] digest -> {to} failed: {exc}",
                  file=sys.stderr)
            continue
        sent_to.append(to)
        verb = "previewed" if args.dry_run else "sent"
        print(f"[send_whatsapp_alerts] digest {verb} -> {to}",
              file=sys.stderr)

    if not args.dry_run and sent_to:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({
            "kind": "digest",
            "channel": "whatsapp",
            "sent_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "recipients": sent_to,
            "alert_count": len(alerts),
        }, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0 if sent_to or args.dry_run else 1


if __name__ == "__main__":
    raise SystemExit(main())
