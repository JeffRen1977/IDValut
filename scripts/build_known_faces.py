#!/usr/bin/env python3
"""
Build the IDVault known-faces index from reference images.

Expected layout (default):

    known_faces/images/<subject_id>/*.{jpg,jpeg,png,webp}
    known_faces/subjects.yaml      # optional, human metadata (display name etc.)

Output:

    known_faces/index.json         # { "subjects": [ {subject_id, label, embedding[...], sample_count} ] }

Each subject's embedding is the L2-averaged centroid of all successfully
embedded reference photos. This is what analyze_video.py loads at runtime.

The generated index may contain raw embedding floats. It is listed in
.gitignore by default so biometric data is not committed.

Usage:

    python3 scripts/build_known_faces.py [images_dir] [out_index_json]

Defaults resolve relative to the repository root (the parent of scripts/).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from face_utils import get_embedding, load_and_align_face  # noqa: E402


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _load_subject_metadata(meta_path: Path) -> dict:
    """Load optional metadata (subject_id -> {label, notes, ...}).

    Supports JSON natively; YAML is loaded only if PyYAML is installed.
    """
    if not meta_path.exists():
        return {}
    try:
        text = meta_path.read_text(encoding="utf-8")
        if meta_path.suffix.lower() in {".yaml", ".yml"}:
            import yaml  # type: ignore
            data = yaml.safe_load(text) or {}
        else:
            data = json.loads(text)
        return data.get("subjects", data) if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"[build_known_faces] could not read {meta_path}: {exc}")
        return {}


def build_index(images_dir: Path, out_path: Path) -> int:
    if not images_dir.exists():
        print(f"[build_known_faces] images dir not found: {images_dir}")
        print("  Create it and place reference photos under <subject_id>/*.jpg")
        return 0

    meta = {}
    for candidate in ("subjects.json", "subjects.yaml", "subjects.yml"):
        meta_path = images_dir.parent / candidate
        if meta_path.exists():
            meta = _load_subject_metadata(meta_path)
            break

    subjects_out: list[dict] = []
    for sub_dir in sorted(p for p in images_dir.iterdir() if p.is_dir()):
        subject_id = sub_dir.name
        label = (
            (meta.get(subject_id) or {}).get("label")
            or (meta.get(subject_id) or {}).get("name")
            or subject_id.replace("_", " ").title()
        )
        embeddings: list[np.ndarray] = []
        for img_path in sorted(sub_dir.iterdir()):
            if img_path.suffix.lower() not in IMAGE_EXTS:
                continue
            face = load_and_align_face(str(img_path))
            if face is None:
                print(f"  [skip] no face: {img_path}")
                continue
            emb = get_embedding(face)
            if emb is None:
                print(f"  [skip] no embedding: {img_path}")
                continue
            embeddings.append(emb)

        if not embeddings:
            print(f"[subject {subject_id}] no usable embeddings, skipping")
            continue

        arr = np.stack(embeddings)
        centroid = arr.mean(axis=0)
        n = float(np.linalg.norm(centroid))
        if n > 0:
            centroid = centroid / n

        subjects_out.append({
            "subject_id": subject_id,
            "celebrity_label": label,
            "sample_count": len(embeddings),
            "embedding": [float(x) for x in centroid.tolist()],
            "notes": (meta.get(subject_id) or {}).get("notes", ""),
        })
        print(f"[subject {subject_id}] label={label!r} samples={len(embeddings)}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "idvault.known_faces.index/v1",
        "model": "Facenet",
        "detector": "opencv",
        "dim": len(subjects_out[0]["embedding"]) if subjects_out else 0,
        "subjects": subjects_out,
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(subjects_out)} subjects -> {out_path}")
    return len(subjects_out)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    images_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else repo_root / "known_faces" / "images"
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else repo_root / "known_faces" / "index.json"
    count = build_index(images_dir, out_path)
    return 0 if count > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
