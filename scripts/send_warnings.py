#!/usr/bin/env python3
"""
IDVault — Alert dispatcher (email / SMTP).

Reads alert JSON files produced by scripts/analyze_video.py and emails each
one to the recipients listed in ingest/notifications.yaml. Credentials stay
in environment variables (expected to be set in ~/.idvault-env):

    SMTP_HOST       e.g. smtp.gmail.com
    SMTP_PORT       e.g. 587
    SMTP_USER       SMTP login username
    SMTP_PASSWORD   password / Gmail App Password
    SMTP_FROM       (optional) "IDVault <id@example>"; falls back to SMTP_USER
    SMTP_STARTTLS   "1" (default) | "0"
    SMTP_USE_SSL    "1" to use SMTPS on port 465; default "0"

Idempotency: for each alert we write reports/<DATE>/.sent/<alert_id>.json
once the email has been accepted by the SMTP server, so reruns skip it.

Usage:
    scripts/send_warnings.py --reports-dir reports/2026-04-16
    scripts/send_warnings.py --alert reports/2026-04-16/alert_IDV-...json
    scripts/send_warnings.py --reports-dir reports/2026-04-16 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html import escape
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _discover_common import load_seeds  # reuses the YAML loader  # noqa: E402


TIER_ORDER = {"low": 0, "medium": 1, "high": 2}


def _tier_at_least(alert: dict, min_tier: str) -> bool:
    min_rank = TIER_ORDER.get((min_tier or "low").lower(), 0)
    best = 0
    for m in alert.get("matched_subjects", []) or []:
        t = TIER_ORDER.get((m.get("similarity_tier") or "low").lower(), 0)
        if t > best:
            best = t
    return best >= min_rank


def _should_send(alert: dict, cfg: dict) -> tuple[bool, str]:
    reasons = cfg.get("include_reasons") or []
    reason = alert.get("alert_reason", "")
    if reasons and reason not in reasons:
        return False, f"reason {reason!r} not in include_reasons"
    if not _tier_at_least(alert, cfg.get("min_severity_tier") or "low"):
        return False, f"max tier below min_severity_tier={cfg.get('min_severity_tier')}"
    return True, ""


def _format_subjects_html(alert: dict) -> str:
    rows: list[str] = []
    for m in alert.get("matched_subjects", []) or []:
        rows.append(
            "<tr>"
            f"<td>{escape(str(m.get('celebrity_label') or m.get('subject_id') or ''))}</td>"
            f"<td>{escape(str(m.get('license_status') or ''))}</td>"
            f"<td>{escape(str(m.get('similarity_tier') or ''))}</td>"
            f"<td>{escape(str(m.get('max_similarity') or ''))}</td>"
            f"<td>{escape(str(m.get('likeness_percentage') or ''))}%</td>"
            f"<td>{escape(str(m.get('votes') or ''))}</td>"
            "</tr>"
        )
    table = (
        "<table border='1' cellpadding='6' cellspacing='0' "
        "style='border-collapse:collapse;font-family:-apple-system,Segoe UI,Roboto,sans-serif;font-size:13px'>"
        "<thead><tr style='background:#f6f6f6'>"
        "<th>Celebrity</th><th>License</th><th>Tier</th>"
        "<th>Max sim</th><th>Likeness</th><th>Votes</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    return table


def _format_subjects_text(alert: dict) -> str:
    lines: list[str] = []
    for m in alert.get("matched_subjects", []) or []:
        lines.append(
            f"  - {m.get('celebrity_label') or m.get('subject_id')}"
            f" | license={m.get('license_status')}"
            f" | tier={m.get('similarity_tier')}"
            f" | max_sim={m.get('max_similarity')}"
            f" | likeness={m.get('likeness_percentage')}%"
            f" | votes={m.get('votes')}"
        )
    return "\n".join(lines) or "  (none)"


def build_email(alert: dict, cfg: dict, alert_path: Path) -> EmailMessage:
    video = alert.get("video") or {}
    subjects_text = _format_subjects_text(alert)
    subjects_html = _format_subjects_html(alert)

    primary_label = ""
    for m in alert.get("matched_subjects", []) or []:
        primary_label = m.get("celebrity_label") or m.get("subject_id") or ""
        if primary_label:
            break

    prefix = (cfg.get("subject_prefix") or "[IDVault]").strip()
    subject_parts = [
        prefix,
        alert.get("platform", "").upper() or "?",
        alert.get("alert_reason") or "alert",
    ]
    if primary_label:
        subject_parts.append(primary_label)
    title_snip = (video.get("title") or "").strip()
    if title_snip:
        subject_parts.append(title_snip[:80])
    subject = " · ".join(p for p in subject_parts if p)

    scanned_at = alert.get("scanned_at") or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    text_body = "\n".join([
        f"IDVault alert  {alert.get('alert_id','?')}  (case {alert.get('case_id','?')})",
        f"reason       : {alert.get('alert_reason')}",
        f"platform     : {alert.get('platform')}",
        f"video title  : {video.get('title','')}",
        f"video url    : {video.get('url','')}",
        f"video id     : {video.get('platform_video_id','')}",
        f"scanned_at   : {scanned_at}",
        "",
        "matched subjects:",
        subjects_text,
        "",
        "LLM summary:",
        (alert.get("llm_summary") or "(none)"),
        f"  sources: {', '.join(alert.get('llm_summary_sources') or [])}",
        "",
        f"disclaimer: {alert.get('disclaimer','')}",
        "",
        f"source file: {alert_path}",
    ])

    html_body = f"""
<html><body style="font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#222">
<h2 style="margin:0 0 8px 0">IDVault alert &middot; {escape(alert.get('alert_id','?'))}</h2>
<p style="margin:0 0 14px 0;color:#555">case <code>{escape(alert.get('case_id','?'))}</code>
 &middot; reason <b>{escape(alert.get('alert_reason',''))}</b>
 &middot; scanned {escape(scanned_at)}</p>

<table cellpadding="6" cellspacing="0" style="border-collapse:collapse;margin-bottom:16px">
<tr><td><b>Platform</b></td><td>{escape(alert.get('platform',''))}</td></tr>
<tr><td><b>Title</b></td><td>{escape(video.get('title',''))}</td></tr>
<tr><td><b>URL</b></td><td><a href="{escape(video.get('url',''))}">{escape(video.get('url',''))}</a></td></tr>
<tr><td><b>Video ID</b></td><td>{escape(video.get('platform_video_id',''))}</td></tr>
</table>

<h3 style="margin:0 0 6px 0">Matched subjects</h3>
{subjects_html}

<h3 style="margin:16px 0 6px 0">LLM summary</h3>
<p style="margin:0 0 6px 0">{escape(alert.get('llm_summary','(none)'))}</p>
<p style="margin:0;color:#888;font-size:12px">sources: {escape(', '.join(alert.get('llm_summary_sources') or []))}</p>

<p style="margin-top:20px;color:#888;font-size:12px">
{escape(alert.get('disclaimer',''))}<br/>
source file: <code>{escape(str(alert_path))}</code>
</p>
</body></html>
"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    frm = cfg.get("from") or os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER")
    if not frm:
        raise RuntimeError("no From: set (configure email.from or SMTP_FROM / SMTP_USER)")
    msg["From"] = frm

    to_list = [a for a in (cfg.get("to") or []) if a]
    if not to_list:
        raise RuntimeError("notifications.yaml email.to is empty; nothing to do")
    msg["To"] = ", ".join(to_list)
    if cfg.get("cc"):
        msg["Cc"] = ", ".join(cfg["cc"])

    msg["Message-ID"] = make_msgid(domain="idvault.local")
    msg["X-IDVault-Alert-Id"] = alert.get("alert_id", "")
    msg["X-IDVault-Case-Id"] = alert.get("case_id", "")

    msg.set_content(text_body)
    msg.add_alternative(html_body, subtype="html")

    if cfg.get("attach_json", True):
        raw = json.dumps(alert, indent=2, ensure_ascii=False).encode("utf-8")
        msg.add_attachment(
            raw,
            maintype="application",
            subtype="json",
            filename=alert_path.name,
        )
    return msg


def send_smtp(msg: EmailMessage, to_list: list[str]) -> None:
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587") or 587)
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASSWORD")
    use_ssl = os.environ.get("SMTP_USE_SSL", "0") == "1"
    use_starttls = os.environ.get("SMTP_STARTTLS", "1") == "1" and not use_ssl

    if not host:
        raise RuntimeError("SMTP_HOST not set; export SMTP_* in ~/.idvault-env")

    if use_ssl:
        smtp_cls = smtplib.SMTP_SSL
    else:
        smtp_cls = smtplib.SMTP

    with smtp_cls(host, port, timeout=30) as srv:
        srv.ehlo()
        if use_starttls:
            srv.starttls()
            srv.ehlo()
        if user and password:
            srv.login(user, password)
        srv.send_message(msg, to_addrs=to_list)


def iter_alerts(args) -> list[Path]:
    paths: list[Path] = []
    if args.alert:
        paths.extend(Path(p) for p in args.alert)
    if args.reports_dir:
        root = Path(args.reports_dir)
        paths.extend(sorted(root.glob("alert_*.json")))
    return paths


def sent_marker_path(alert_path: Path) -> Path:
    return alert_path.parent / ".sent" / (alert_path.stem + ".json")


def main() -> int:
    ap = argparse.ArgumentParser(description="IDVault email dispatcher")
    ap.add_argument("--config", default="ingest/notifications.yaml")
    ap.add_argument("--reports-dir", help="Directory whose alert_*.json to send")
    ap.add_argument("--alert", action="append", default=[], help="Explicit alert JSON path (repeatable)")
    ap.add_argument("--to", help="Override recipient(s), comma-separated")
    ap.add_argument("--dry-run", action="store_true", help="Compose only, do not open SMTP")
    ap.add_argument("--force", action="store_true", help="Re-send even if .sent marker exists")
    args = ap.parse_args()

    cfg_file = Path(args.config)
    cfg = {}
    if cfg_file.exists():
        full = load_seeds(cfg_file)
        cfg = (full.get("email") or {}) if isinstance(full, dict) else {}
    if args.to:
        cfg["to"] = [x.strip() for x in args.to.split(",") if x.strip()]

    paths = iter_alerts(args)
    if not paths:
        print("[send_warnings] no alert files matched", file=sys.stderr)
        return 0

    sent = 0
    skipped = 0
    for p in paths:
        try:
            alert = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[send_warnings] skip {p}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        marker = sent_marker_path(p)
        if marker.exists() and not args.force:
            print(f"[send_warnings] skip {p.name}: already sent -> {marker}", file=sys.stderr)
            skipped += 1
            continue

        ok, why = _should_send(alert, cfg)
        if not ok:
            print(f"[send_warnings] skip {p.name}: {why}", file=sys.stderr)
            skipped += 1
            continue

        try:
            msg = build_email(alert, cfg, p)
        except Exception as exc:
            print(f"[send_warnings] build failed for {p.name}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        recipients = list(cfg.get("to") or []) + list(cfg.get("cc") or []) + list(cfg.get("bcc") or [])

        if args.dry_run:
            print(f"--- DRY RUN: {p.name} -> {', '.join(recipients)} ---", file=sys.stderr)
            print(f"Subject: {msg['Subject']}")
            print(f"From:    {msg['From']}")
            print(f"To:      {msg['To']}")
            if msg.get("Cc"):
                print(f"Cc:      {msg['Cc']}")
            print()
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    print(part.get_content())
                    break
            print()
            continue

        try:
            send_smtp(msg, recipients)
        except Exception as exc:
            print(f"[send_warnings] SMTP failed for {p.name}: {exc}", file=sys.stderr)
            skipped += 1
            continue

        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({
            "alert_id": alert.get("alert_id"),
            "case_id": alert.get("case_id"),
            "sent_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "recipients": recipients,
            "subject": msg["Subject"],
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[send_warnings] sent {p.name} -> {', '.join(recipients)}", file=sys.stderr)
        sent += 1

    print(f"[send_warnings] done: sent={sent} skipped={skipped} total={len(paths)}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
