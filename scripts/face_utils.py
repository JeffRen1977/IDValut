"""
IDVault — Local face detection, alignment, embedding, and similarity helpers.

Extracted and adapted from faceIdentity-main/backend/face_utils_deepface.py so
that IDVault can run face recognition fully locally without any Firebase /
SQL dependency. The public functions are intentionally kept compatible:

    load_and_align_face(image_path) -> np.ndarray | None
    get_embedding(face_img)         -> np.ndarray | None  (float32, Facenet)
    cosine_similarity(a, b)         -> float              (-1.0 .. 1.0)

All heavy work goes through DeepFace + OpenCV. No external services.
"""

from __future__ import annotations

import os

# DeepFace uses tf.keras (Keras 2). TensorFlow >= 2.16 defaults to Keras 3,
# which breaks DeepFace. Force the legacy path *before* importing tensorflow
# via deepface. Users installing on Python 3.10/3.11 with TF 2.15 can ignore.
os.environ.setdefault("TF_USE_LEGACY_KERAS", "1")
# Quiet TF's info/warning spam unless the caller opts in.
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

import cv2  # noqa: E402
import numpy as np  # noqa: E402

try:
    from deepface import DeepFace  # noqa: E402
except ImportError as e:  # pragma: no cover
    raise ImportError(
        "deepface is required. Install with: pip install -r scripts/requirements.txt"
    ) from e


FACE_SIZE = (160, 160)
EMBEDDING_MODEL = "Facenet"
DETECTOR_BACKEND = "opencv"


def load_and_align_face(image_path: str):
    """Detect and align a single face from an image file."""
    try:
        face_objs = DeepFace.extract_faces(
            img_path=image_path,
            detector_backend=DETECTOR_BACKEND,
            enforce_detection=False,
            align=True,
        )
        if not face_objs:
            return None

        face_img = face_objs[0]["face"]
        if face_img.dtype != np.uint8:
            face_img = (face_img * 255).astype(np.uint8)
        face_img = cv2.resize(face_img, FACE_SIZE)
        return face_img
    except Exception as exc:
        print(f"[face_utils] load_and_align_face failed for {image_path}: {exc}")
        return None


def get_embedding(face_img: np.ndarray):
    """Compute a Facenet embedding for an aligned face image."""
    try:
        if face_img is None:
            return None

        if face_img.dtype != np.uint8:
            face_img = (face_img * 255).astype(np.uint8)

        if face_img.ndim == 3 and face_img.shape[2] == 3:
            face_img_rgb = cv2.cvtColor(face_img, cv2.COLOR_BGR2RGB)
        else:
            face_img_rgb = face_img

        embedding_result = DeepFace.represent(
            img_path=face_img_rgb,
            model_name=EMBEDDING_MODEL,
            detector_backend=DETECTOR_BACKEND,
            enforce_detection=False,
        )
        if embedding_result:
            return np.array(embedding_result[0]["embedding"], dtype=np.float32)
        return None
    except Exception as exc:
        print(f"[face_utils] get_embedding failed: {exc}")
        return None


def cosine_similarity(vec1, vec2) -> float:
    """Cosine similarity; robust to None and zero-norm inputs."""
    if vec1 is None or vec2 is None:
        return 0.0
    vec1 = np.asarray(vec1, dtype=np.float32)
    vec2 = np.asarray(vec2, dtype=np.float32)
    n1 = float(np.linalg.norm(vec1))
    n2 = float(np.linalg.norm(vec2))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return float(np.dot(vec1, vec2) / (n1 * n2))
