"""Small helpers shared by discover_*.py scripts (YAML load, candidate I/O)."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def load_seeds(path: str | os.PathLike) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    text = p.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "PyYAML is required. Install with: pip install -r scripts/requirements.txt"
        ) from e
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping at the top level")
    return data


def load_subject_labels(index_path: str | os.PathLike) -> list[str]:
    p = Path(index_path)
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    labels: list[str] = []
    for s in data.get("subjects", []) or []:
        label = s.get("celebrity_label") or s.get("subject_id")
        if label:
            labels.append(label)
    return labels


def write_candidates(out_path: str | os.PathLike, rows: list[dict]) -> None:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def ytdlp_date_to_iso(d: str | None) -> str | None:
    """Convert yt-dlp's YYYYMMDD upload_date into RFC3339 at midnight UTC."""
    if not d or len(d) != 8 or not d.isdigit():
        return None
    return f"{d[0:4]}-{d[4:6]}-{d[6:8]}T00:00:00Z"


def safe_getenv_path(name: str) -> str | None:
    raw = os.environ.get(name)
    if not raw:
        return None
    return os.path.expanduser(raw)
