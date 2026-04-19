#!/usr/bin/env python3
"""
iv — IDVault query CLI (stub for the @idvault chat bridge).

This is a minimum viable entry point for the OpenClaw @-prefix router
so that `@idvault ...` messages don't dead-end at "CLI not installed".
Functional commands are stubbed and will be wired to the real
face-detection / portrait-verification pipeline in a later patch.

Commands:
    iv help                        list commands
    iv status                      report which reports/<DATE> dir is in use
    iv date                        alias for status
    iv list    [DATE]              list identities with reports today
    iv verify  <IMAGE_PATH>        (TODO) verify a portrait against known_faces/

Design notes:
    - Read-only; mirrors the PriCredit `pc` CLI so the router skill
      can dispatch to either interchangeably.
    - Output stays ≤ 3800 chars so it fits in one WhatsApp reply.
    - `iv verify` is deliberately unimplemented here; wiring it to the
      deepface pipeline requires a venv with tensorflow, and we don't
      want the chat bridge silently pulling in 1 GB of deps on first
      use. Returning a "not yet wired" message is preferable to
      either a long startup or a confusing crash.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR_DEFAULT = ROOT / "reports"
KNOWN_FACES_DIR = ROOT / "known_faces"


def _is_date_dir(name: str) -> bool:
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}", name))


def _latest_reports_dir(reports_root: Path) -> Path | None:
    if not reports_root.exists():
        return None
    candidates = [p for p in reports_root.iterdir()
                  if p.is_dir() and _is_date_dir(p.name)]
    if not candidates:
        return None
    candidates.sort(key=lambda p: (p.name[:10], p.stat().st_mtime),
                    reverse=True)
    return candidates[0]


def _print(text: str) -> int:
    try:
        sys.stdout.write(text)
        if not text.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
    except BrokenPipeError:
        try:
            sys.stdout = open(os.devnull, "w")
        except Exception:
            pass
    return 0


def cmd_help(_args, _root) -> int:
    return _print(
        "IDVault CLI (stub, read-only):\n"
        "  iv status                 which reports/<DATE> is \"today\"\n"
        "  iv list [DATE]            identities with reports today\n"
        "  iv verify <IMAGE_PATH>    (TODO) run face verification\n"
        "  iv help                   this message\n"
    )


def cmd_status(_args, reports_root: Path) -> int:
    d = _latest_reports_dir(reports_root)
    if not d:
        return _print("IDVault: no reports/<DATE>/ directory yet.")
    n_subjects = len([p for p in d.iterdir() if p.is_dir()])
    n_known = len([p for p in KNOWN_FACES_DIR.glob("images/*")
                   if p.is_dir()]) if KNOWN_FACES_DIR.exists() else 0
    return _print(
        f"IDVault reports dir: {d.relative_to(ROOT) if d.is_relative_to(ROOT) else d}\n"
        f"subjects in latest run: {n_subjects}\n"
        f"known_faces registered: {n_known}\n"
    )


def cmd_list(args, reports_root: Path) -> int:
    d = (reports_root / args.date) if args.date else _latest_reports_dir(reports_root)
    if not d or not d.exists():
        return _print("IDVault: no matching reports/<DATE>/ directory.")
    subjects = sorted([p.name for p in d.iterdir() if p.is_dir()])
    if not subjects:
        return _print(f"IDVault: no subjects in {d.name}.")
    lines = [f"IDVault subjects · {d.name} · {len(subjects)} total"]
    for s in subjects[:40]:
        lines.append(f"  {s}")
    if len(subjects) > 40:
        lines.append(f"  … +{len(subjects) - 40} more")
    return _print("\n".join(lines))


def cmd_verify(args, _root) -> int:
    path = Path(args.image_path).expanduser()
    if not path.exists():
        return _print(f"IDVault: image not found: {path}")
    return _print(
        f"IDVault: `iv verify` is not wired to the face pipeline yet.\n"
        f"Image received: {path}\n"
        f"known_faces dir: {KNOWN_FACES_DIR}\n"
        f"Next: route through scripts/run-daily-idvault.sh's verification step."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="iv", description="IDVault query CLI")
    ap.add_argument("--reports-root", default=str(REPORTS_DIR_DEFAULT))
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("help"); p.set_defaults(func=cmd_help)
    p = sub.add_parser("status"); p.set_defaults(func=cmd_status)
    p = sub.add_parser("date"); p.set_defaults(func=cmd_status)  # alias
    p = sub.add_parser("list"); p.add_argument("date", nargs="?"); p.set_defaults(func=cmd_list)
    p = sub.add_parser("verify"); p.add_argument("image_path"); p.set_defaults(func=cmd_verify)

    args = ap.parse_args(argv)
    reports_root = Path(args.reports_root).expanduser()

    if not args.cmd:
        return cmd_help(args, reports_root)
    return args.func(args, reports_root)


if __name__ == "__main__":
    raise SystemExit(main())
