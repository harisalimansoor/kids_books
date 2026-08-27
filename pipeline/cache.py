"""Versioned template cache under pipeline_cache/."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from .constants import CACHE_VERSION

DEFAULT_CACHE_ROOT = Path(__file__).resolve().parent.parent / "pipeline_cache"
DEFAULT_TEMPLATES_ROOT = (
    Path(__file__).resolve().parent.parent
    / "new_pipeline"
    / "question_templates"
)


def stem_id_from_path(stem_dir: Path, templates_root: Path) -> str:
    rel = stem_dir.resolve().relative_to(templates_root.resolve())
    return str(rel).replace("\\", "/")


def cache_dir_for(template_id: str, cache_root: Path = DEFAULT_CACHE_ROOT) -> Path:
    return cache_root / template_id


def meta_path(template_id: str, cache_root: Path = DEFAULT_CACHE_ROOT) -> Path:
    return cache_dir_for(template_id, cache_root) / "cache.json"


def is_cache_valid(template_id: str, cache_root: Path = DEFAULT_CACHE_ROOT) -> bool:
    p = meta_path(template_id, cache_root)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return False
    if data.get("cache_version") != CACHE_VERSION:
        return False
    # Masks for each role must exist
    for role_entry in data.get("faces") or []:
        mp = cache_dir_for(template_id, cache_root) / role_entry["mask_file"]
        if not mp.exists():
            return False
    return True


def save_template_cache(
    template_id: str,
    *,
    image_file: str,
    image_sha1: str,
    faces: list[dict[str, Any]],
    source: str,
    confidence: str,
    notes: str = "",
    cache_root: Path = DEFAULT_CACHE_ROOT,
) -> Path:
    """
    faces: list of {
      role, bbox, landmarks (5-pt dict), landmarks_106 (optional list),
      det_score, mask_file, mask (ndarray uint8)
    }
    """
    out_dir = cache_dir_for(template_id, cache_root)
    out_dir.mkdir(parents=True, exist_ok=True)

    face_metas = []
    for f in faces:
        mask = f["mask"]
        mask_name = f.get("mask_file") or f"mask_{f['role']}.png"
        cv2.imwrite(str(out_dir / mask_name), mask)
        entry = {
            "role": f["role"],
            "bbox": [float(x) for x in f["bbox"]],
            "landmarks": f["landmarks"],
            "det_score": float(f.get("det_score", 0.0)),
            "mask_file": mask_name,
        }
        if f.get("landmarks_106") is not None:
            entry["landmarks_106"] = f["landmarks_106"]
        face_metas.append(entry)

    payload = {
        "cache_version": CACHE_VERSION,
        "template_id": template_id,
        "image_file": image_file,
        "image_sha1": image_sha1,
        "source": source,  # "meta_seeded" | "auto_detect"
        "confidence": confidence,  # "high" | "low"
        "notes": notes,
        "faces": face_metas,
    }
    path = meta_path(template_id, cache_root)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def load_template_cache(
    template_id: str,
    cache_root: Path = DEFAULT_CACHE_ROOT,
) -> dict[str, Any]:
    path = meta_path(template_id, cache_root)
    if not path.exists():
        raise FileNotFoundError(
            f"No cache for template_id={template_id!r}. "
            f"Run: python scripts/preprocess_templates.py"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("cache_version") != CACHE_VERSION:
        raise ValueError(
            f"Stale cache for {template_id}: version {data.get('cache_version')} "
            f"!= {CACHE_VERSION}. Re-run preprocessing with --rebuild."
        )
    # Attach loaded masks
    out_dir = cache_dir_for(template_id, cache_root)
    for face in data["faces"]:
        mask = cv2.imread(str(out_dir / face["mask_file"]), cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise FileNotFoundError(f"Missing mask {face['mask_file']} for {template_id}")
        face["mask"] = mask
    return data


def file_sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_stems(templates_root: Path = DEFAULT_TEMPLATES_ROOT) -> list[Path]:
    """Stem dirs = directories that contain meta.json + at least one image."""
    stems = []
    if not templates_root.exists():
        return stems
    for meta in sorted(templates_root.rglob("meta.json")):
        stem = meta.parent
        stems.append(stem)
    return stems


def resolve_template_image(stem_dir: Path, meta: dict) -> Path:
    name = meta.get("image_file")
    if name:
        p = stem_dir / name
        if p.exists():
            return p
    pngs = sorted(stem_dir.glob("*.png"))
    if pngs:
        return pngs[0]
    jpgs = sorted(stem_dir.glob("*.jpg")) + sorted(stem_dir.glob("*.jpeg"))
    if jpgs:
        return jpgs[0]
    raise FileNotFoundError(f"No template image in {stem_dir}")
