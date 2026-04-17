#!/usr/bin/env python3
"""
IDVault — Local video face-recognition scanner.

Adapted from faceIdentity-main/backend/video_utils.py (VideoProcessor), with
all Firebase / SQL persistence stripped out. Reads a local video file plus
the IDVault known_faces index and writes:

  * A detailed scan report (always): reports/<DATE>/scan_<video_id>.json
  * An alert (only if >=1 matched subject): reports/<DATE>/alert_<alert_id>.json

The alert JSON schema follows reports/README.md and is designed for the
"send warning" step to consume (email / webhook / etc.).

Usage:

  python3 scripts/analyze_video.py \
      --video /path/to/video.mp4 \
      --index known_faces/index.json \
      --scan-out reports/2026-04-16/scan_abc123.json \
      --alert-out reports/2026-04-16/alert_IDV-20260416-001.json \
      --alert-id IDV-20260416-001 \
      --case-id CASE-2026-04-16-001 \
      --video-url https://youtube.com/watch?v=abc123 \
      --video-title "Example title" \
      --platform youtube \
      --video-id abc123 \
      --frame-interval 30 --threshold 0.6
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# face_utils sets TF_USE_LEGACY_KERAS before importing tensorflow/deepface,
# so importing it first keeps the whole scanner on the Keras-2 path.
from face_utils import cosine_similarity, get_embedding  # noqa: E402

import cv2  # noqa: E402
import numpy as np  # noqa: E402

try:
    from deepface import DeepFace  # noqa: E402
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "deepface is required. Install with: pip install -r scripts/requirements.txt"
    ) from e


def tier(sim: float) -> str:
    if sim >= 0.75:
        return "high"
    if sim >= 0.65:
        return "medium"
    return "low"


def load_index(index_path: Path) -> list[dict]:
    data = json.loads(index_path.read_text(encoding="utf-8"))
    subjects = data.get("subjects", [])
    for s in subjects:
        s["_embedding_np"] = np.asarray(s["embedding"], dtype=np.float32)
    return subjects


def analyze(
    video_path: str,
    subjects: list[dict],
    threshold: float,
    frame_interval: int,
    max_frames: int | None = None,
) -> dict:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"error": f"cannot open video: {video_path}"}

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0:
        fps = 30.0

    per_subject: dict[str, dict] = {
        s["subject_id"]: {
            "subject_id": s["subject_id"],
            "celebrity_label": s.get("celebrity_label", s["subject_id"]),
            "votes": 0,
            "max_similarity": 0.0,
            "first_hit_ts": None,
            "hit_samples": [],
        }
        for s in subjects
    }

    frame_no = 0
    processed = 0
    frames_with_faces = 0
    t0 = time.time()

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_no += 1
        if frame_no % frame_interval != 0:
            continue
        if max_frames and processed >= max_frames:
            break
        processed += 1

        try:
            face_objs = DeepFace.extract_faces(
                img_path=frame,
                detector_backend="opencv",
                enforce_detection=False,
                align=False,
            )
        except Exception as exc:
            print(f"[analyze] DeepFace error at frame {frame_no}: {exc}")
            continue

        if not face_objs:
            continue

        frame_had_face = False
        seen_here: set[str] = set()
        ts = round(frame_no / fps, 3)

        for obj in face_objs:
            emb = get_embedding(obj["face"])
            if emb is None:
                continue
            frame_had_face = True
            for s in subjects:
                sim = cosine_similarity(emb, s["_embedding_np"])
                stats = per_subject[s["subject_id"]]
                if sim >= threshold and s["subject_id"] not in seen_here:
                    stats["votes"] += 1
                    if sim > stats["max_similarity"]:
                        stats["max_similarity"] = sim
                    if stats["first_hit_ts"] is None:
                        stats["first_hit_ts"] = ts
                    if len(stats["hit_samples"]) < 10:
                        stats["hit_samples"].append({
                            "frame": frame_no,
                            "timestamp": ts,
                            "similarity": round(sim, 4),
                        })
                    seen_here.add(s["subject_id"])

        if frame_had_face:
            frames_with_faces += 1

        if processed % 25 == 0:
            pct = (frame_no / total_frames * 100) if total_frames else 0.0
            print(f"[analyze] frame {frame_no}/{total_frames} ({pct:.1f}%), "
                  f"processed={processed}, faces_frames={frames_with_faces}")

    cap.release()
    dt = time.time() - t0

    matched: list[dict] = []
    for sid, stats in per_subject.items():
        if stats["votes"] == 0:
            continue
        likeness = (stats["votes"] / frames_with_faces * 100.0) if frames_with_faces else 0.0
        matched.append({
            "subject_id": stats["subject_id"],
            "celebrity_label": stats["celebrity_label"],
            "votes": stats["votes"],
            "max_similarity": round(stats["max_similarity"], 4),
            "similarity_tier": tier(stats["max_similarity"]),
            "likeness_percentage": round(likeness, 2),
            "first_hit_ts": stats["first_hit_ts"],
            "hit_samples": stats["hit_samples"],
        })
    matched.sort(key=lambda m: (m["max_similarity"], m["votes"]), reverse=True)

    return {
        "video_path": video_path,
        "fps": round(fps, 2),
        "total_frames": total_frames,
        "processed_frames": processed,
        "frames_with_faces": frames_with_faces,
        "frame_interval": frame_interval,
        "threshold": threshold,
        "scan_duration_sec": round(dt, 2),
        "matched_subjects": matched,
    }


def _load_licenses(licenses_dir: Path) -> dict[str, list[dict]]:
    """Load license records from licenses/*.json.

    Each file may be either a single license dict or a list of dicts.
    License shape (minimal): {license_id, subject_id, scope, valid_from, valid_until, platforms?}.
    Indexed by subject_id for quick lookup.
    """
    index: dict[str, list[dict]] = {}
    if not licenses_dir.exists():
        return index
    for p in licenses_dir.rglob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            sid = it.get("subject_id")
            if sid:
                index.setdefault(sid, []).append(it)
    return index


def _license_status(subject_id: str, platform: str, licenses: dict) -> str:
    """Very conservative license resolver.

    Returns one of: authorized | expired | not_found | ambiguous.
    Real matching of scope/use-case should be refined per business rules.
    """
    items = licenses.get(subject_id)
    if not items:
        return "not_found"
    now = datetime.now(timezone.utc).date().isoformat()
    active = []
    expired_any = False
    for it in items:
        vu = it.get("valid_until")
        vf = it.get("valid_from")
        if vu and vu < now:
            expired_any = True
            continue
        if vf and vf > now:
            continue
        platforms = it.get("platforms") or []
        if platforms and platform and platform not in platforms:
            continue
        active.append(it)
    if active:
        return "authorized"
    if expired_any:
        return "expired"
    return "not_found"


def build_alert(
    *,
    scan: dict,
    alert_id: str,
    case_id: str,
    platform: str,
    video_url: str,
    video_title: str,
    video_id: str,
    llm_summary: str,
    llm_summary_sources: list[str],
    licenses_dir: Path,
) -> dict:
    licenses = _load_licenses(licenses_dir)
    matched_out: list[dict] = []
    any_unauthorized = False
    any_expired = False
    for m in scan.get("matched_subjects", []):
        status = _license_status(m["subject_id"], platform, licenses)
        if status == "expired":
            any_expired = True
        if status != "authorized":
            any_unauthorized = True
        matched_out.append({
            "subject_id": m["subject_id"],
            "celebrity_label": m["celebrity_label"],
            "license_status": status,
            "similarity_tier": m["similarity_tier"],
            "max_similarity": m["max_similarity"],
            "likeness_percentage": m["likeness_percentage"],
            "votes": m["votes"],
            "first_hit_ts": m["first_hit_ts"],
        })

    if any_expired and not any_unauthorized:
        reason = "license_expired"
    elif any_unauthorized:
        reason = "unlicensed_face_match"
    else:
        reason = "authorized_match"  # logged but shouldn't usually produce an alert

    return {
        "alert_id": alert_id,
        "case_id": case_id,
        "platform": platform,
        "video": {
            "title": video_title,
            "url": video_url,
            "platform_video_id": video_id,
        },
        "scanned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "matched_subjects": matched_out,
        "llm_summary": llm_summary,
        "llm_summary_sources": llm_summary_sources,
        "alert_reason": reason,
        "disclaimer": "事实与授权库状态报告，非法律意见。",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="IDVault local video face scanner")
    ap.add_argument("--video", required=True, help="Local video file path")
    ap.add_argument("--index", default="known_faces/index.json")
    ap.add_argument("--scan-out", required=True, help="Where to write the full scan JSON")
    ap.add_argument("--alert-out", default=None, help="Write alert JSON only if matches exist")
    ap.add_argument("--licenses-dir", default="licenses")
    ap.add_argument("--threshold", type=float, default=0.6)
    ap.add_argument("--frame-interval", type=int, default=30)
    ap.add_argument("--max-frames", type=int, default=0, help="Cap processed frames (0=no cap)")

    ap.add_argument("--alert-id", default=None)
    ap.add_argument("--case-id", default=None)
    ap.add_argument("--platform", default="other")
    ap.add_argument("--video-url", default="")
    ap.add_argument("--video-title", default="")
    ap.add_argument("--video-id", default="")
    ap.add_argument("--llm-summary", default="")
    ap.add_argument("--llm-summary-sources", default="title")

    args = ap.parse_args()

    index_path = Path(args.index)
    if not index_path.exists():
        print(f"[analyze] index not found: {index_path}")
        print("  Run: python3 scripts/build_known_faces.py first.")
        return 2

    subjects = load_index(index_path)
    if not subjects:
        print("[analyze] index has 0 subjects; nothing to match against")
        return 2

    scan = analyze(
        video_path=args.video,
        subjects=subjects,
        threshold=args.threshold,
        frame_interval=args.frame_interval,
        max_frames=args.max_frames or None,
    )

    scan_out = Path(args.scan_out)
    scan_out.parent.mkdir(parents=True, exist_ok=True)
    scan_out.write_text(json.dumps(scan, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[analyze] scan -> {scan_out}")

    n_match = len(scan.get("matched_subjects", []))
    print(f"[analyze] matched_subjects={n_match}")

    if n_match and args.alert_out:
        alert = build_alert(
            scan=scan,
            alert_id=args.alert_id or f"IDV-{datetime.now(timezone.utc):%Y%m%d}-000",
            case_id=args.case_id or f"CASE-{datetime.now(timezone.utc):%Y-%m-%d}-000",
            platform=args.platform,
            video_url=args.video_url,
            video_title=args.video_title,
            video_id=args.video_id,
            llm_summary=args.llm_summary or (args.video_title or "(no summary)"),
            llm_summary_sources=[s for s in args.llm_summary_sources.split(",") if s],
            licenses_dir=Path(args.licenses_dir),
        )
        alert_out = Path(args.alert_out)
        alert_out.parent.mkdir(parents=True, exist_ok=True)
        alert_out.write_text(json.dumps(alert, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[analyze] alert -> {alert_out}")

    return 0 if "error" not in scan else 1


if __name__ == "__main__":
    raise SystemExit(main())
