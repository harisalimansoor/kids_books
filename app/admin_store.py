"""
Persistent admin configuration: model catalog, API keys, SMTP, and JSON stores.
"""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
CONFIG_DIR = REPO_ROOT / "config"
ADMIN_DIR = REPO_ROOT / "runtime" / "admin"
JOBS_DIR = REPO_ROOT / "runtime" / "jobs"

MODELS_FILE = ADMIN_DIR / "models.json"
SETTINGS_FILE = ADMIN_DIR / "settings.json"
FEEDBACK_FILE = ADMIN_DIR / "feedback.json"

_lock = threading.Lock()

DEFAULT_MODELS: dict[str, Any] = {
    "active_provider": "openrouter",
    "active_model_id": "openai/gpt-image-2",
    "providers": {
        "openrouter": {
            "id": "openrouter",
            "name": "OpenRouter",
            "description": (
                "Unified gateway for image and chat models. Current production path: "
                "openai/gpt-image-2 via the OpenRouter Images API."
            ),
            "docs_url": "https://openrouter.ai/docs",
            "api_key_env": "OPENROUTER_API_KEY",
            "models": [
                {
                    "id": "openai/gpt-image-2",
                    "name": "GPT Image 2",
                    "endpoint": "images",
                    "description": (
                        "High-fidelity multimodal image model used for workbook scenes and "
                        "front covers. Accepts reference photos plus a compact prompt."
                    ),
                    "cost_per_call": "$0.04–$0.08 per image (typical 1024²)",
                    "cost_notes": "Price varies with size and whether input references are sent.",
                    "best_for": "Production workbook illustrations",
                    "active": True,
                },
                {
                    "id": "google/gemini-2.5-flash-image",
                    "name": "Gemini 2.5 Flash Image (via OpenRouter)",
                    "endpoint": "chat",
                    "description": "Fast image-capable Gemini routed through OpenRouter chat completions.",
                    "cost_per_call": "$0.02–$0.05 per image",
                    "cost_notes": "Lower latency; slightly less identity lock than GPT Image 2.",
                    "best_for": "Faster drafts",
                    "active": False,
                },
                {
                    "id": "black-forest-labs/flux-1.1-pro",
                    "name": "FLUX 1.1 Pro",
                    "endpoint": "chat",
                    "description": "Photoreal image model available on OpenRouter for scene generation.",
                    "cost_per_call": "$0.04–$0.06 per image",
                    "cost_notes": "Strong style control; reference-photo likeness varies.",
                    "best_for": "Stylized scenes",
                    "active": False,
                },
            ],
        },
        "openai": {
            "id": "openai",
            "name": "OpenAI",
            "description": "Direct OpenAI Images API. Use when you want to skip OpenRouter.",
            "docs_url": "https://platform.openai.com/docs/api-reference/images",
            "api_key_env": "OPENAI_API_KEY",
            "models": [
                {
                    "id": "gpt-image-1",
                    "name": "GPT Image 1",
                    "endpoint": "images",
                    "description": "OpenAI native image model with prompt + optional reference edits.",
                    "cost_per_call": "$0.04–$0.19 per image depending on quality",
                    "cost_notes": "High quality tiers cost more. Input images billed separately.",
                    "best_for": "Direct OpenAI production",
                    "active": False,
                },
                {
                    "id": "dall-e-3",
                    "name": "DALL·E 3",
                    "endpoint": "images",
                    "description": "Classic DALL·E 3 generations. No native multi-reference identity lock.",
                    "cost_per_call": "$0.04 (standard 1024) / $0.08 (HD)",
                    "cost_notes": "Prompt-only. Family likeness is weaker than GPT Image 2.",
                    "best_for": "Simple illustrated scenes",
                    "active": False,
                },
            ],
        },
        "gemini": {
            "id": "gemini",
            "name": "Google Gemini",
            "description": "Google Generative Language API for Gemini/Imagen image models.",
            "docs_url": "https://ai.google.dev/gemini-api/docs/image-generation",
            "api_key_env": "GEMINI_API_KEY",
            "models": [
                {
                    "id": "gemini-2.5-flash-image",
                    "name": "Gemini 2.5 Flash Image",
                    "endpoint": "generateContent",
                    "description": "Native Gemini image generation with optional inline reference photos.",
                    "cost_per_call": "$0.02–$0.04 per image",
                    "cost_notes": "Fast and inexpensive. Identity lock is decent with references.",
                    "best_for": "Cost-efficient generation",
                    "active": False,
                },
                {
                    "id": "imagen-4.0-generate-001",
                    "name": "Imagen 4",
                    "endpoint": "predict",
                    "description": "Google Imagen 4 still-image model via the predict endpoint.",
                    "cost_per_call": "$0.04–$0.06 per image",
                    "cost_notes": "Photoreal quality. Reference photos are limited compared with GPT Image 2.",
                    "best_for": "Photoreal covers",
                    "active": False,
                },
            ],
        },
    },
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "feedback_delay_hours": 48,
    "support_email": "support@myintelibooks.com",
    "public_base_url": "http://localhost:5173",
    "api_keys": {
        "openrouter": "",
        "openai": "",
        "gemini": "",
    },
    "smtp": {
        "host": "",
        "port": 587,
        "user": "support@myintelibooks.com",
        "password": "",
        "from_email": "support@myintelibooks.com",
        "from_name": "MyInteliBooks",
        "use_tls": True,
    },
    "imap": {
        "host": "",
        "port": 993,
        "user": "support@myintelibooks.com",
        "password": "",
        "enabled": False,
    },
}


def _ensure_admin_dir() -> None:
    ADMIN_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return deepcopy(default)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return deepcopy(default)


def _write_json(path: Path, data: Any) -> None:
    _ensure_admin_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _seed_api_keys(settings: dict[str, Any]) -> dict[str, Any]:
    keys = settings.setdefault("api_keys", {})
    if not (keys.get("openrouter") or "").strip():
        keys["openrouter"] = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not (keys.get("openai") or "").strip():
        keys["openai"] = os.getenv("OPENAI_API_KEY", "").strip()
    if not (keys.get("gemini") or "").strip():
        keys["gemini"] = (
            os.getenv("GEMINI_API_KEY", "").strip()
            or os.getenv("GOOGLE_API_KEY", "").strip()
        )
    smtp = settings.setdefault("smtp", {})
    if not (smtp.get("host") or "").strip():
        smtp["host"] = os.getenv("SMTP_HOST", "").strip()
    if not smtp.get("port"):
        try:
            smtp["port"] = int(os.getenv("SMTP_PORT", "587"))
        except ValueError:
            smtp["port"] = 587
    if not (smtp.get("user") or "").strip():
        smtp["user"] = os.getenv("SMTP_USER", smtp.get("user") or "support@myintelibooks.com")
    if not (smtp.get("password") or "").strip():
        smtp["password"] = os.getenv("SMTP_PASSWORD", "").strip()
    if not (smtp.get("from_email") or "").strip():
        smtp["from_email"] = os.getenv("SMTP_FROM", "support@myintelibooks.com")
    imap = settings.setdefault("imap", {})
    if not (imap.get("host") or "").strip():
        imap["host"] = os.getenv("IMAP_HOST", "").strip()
    if not (imap.get("password") or "").strip():
        imap["password"] = os.getenv("IMAP_PASSWORD", smtp.get("password") or "")
    if not (imap.get("user") or "").strip():
        imap["user"] = os.getenv("IMAP_USER", smtp.get("user") or "support@myintelibooks.com")
    if os.getenv("PUBLIC_BASE_URL"):
        settings["public_base_url"] = os.getenv("PUBLIC_BASE_URL", settings.get("public_base_url"))
    return settings


def load_models() -> dict[str, Any]:
    with _lock:
        data = _read_json(MODELS_FILE, DEFAULT_MODELS)
        if not data.get("providers"):
            data = deepcopy(DEFAULT_MODELS)
        data.setdefault("active_provider", "openrouter")
        data.setdefault("active_model_id", "openai/gpt-image-2")
        if not MODELS_FILE.exists():
            _write_json(MODELS_FILE, data)
        return data


def save_models(data: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        _write_json(MODELS_FILE, data)
        return data


def load_settings() -> dict[str, Any]:
    with _lock:
        data = _read_json(SETTINGS_FILE, DEFAULT_SETTINGS)
        merged = deepcopy(DEFAULT_SETTINGS)
        merged.update(data or {})
        merged["api_keys"] = {**DEFAULT_SETTINGS["api_keys"], **(data.get("api_keys") or {})}
        merged["smtp"] = {**DEFAULT_SETTINGS["smtp"], **(data.get("smtp") or {})}
        merged["imap"] = {**DEFAULT_SETTINGS["imap"], **(data.get("imap") or {})}
        merged = _seed_api_keys(merged)
        if not SETTINGS_FILE.exists():
            _write_json(SETTINGS_FILE, merged)
        return merged


def save_settings(data: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        current = _read_json(SETTINGS_FILE, DEFAULT_SETTINGS)
        merged = deepcopy(DEFAULT_SETTINGS)
        merged.update(current or {})
        merged.update(data or {})
        if "api_keys" in data:
            merged["api_keys"] = {**current.get("api_keys", {}), **data["api_keys"]}
        if "smtp" in data:
            merged["smtp"] = {**current.get("smtp", {}), **data["smtp"]}
        if "imap" in data:
            merged["imap"] = {**current.get("imap", {}), **data["imap"]}
        _write_json(SETTINGS_FILE, merged)
        return merged


def load_feedback() -> list[dict[str, Any]]:
    with _lock:
        data = _read_json(FEEDBACK_FILE, [])
        if isinstance(data, dict):
            data = data.get("items") or []
        if not isinstance(data, list):
            data = []
        if not FEEDBACK_FILE.exists():
            _write_json(FEEDBACK_FILE, data)
        return data


def save_feedback(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    with _lock:
        _write_json(FEEDBACK_FILE, items)
        return items


def upsert_feedback(record: dict[str, Any]) -> dict[str, Any]:
    items = load_feedback()
    key = record.get("id") or record.get("token")
    found = False
    for i, item in enumerate(items):
        if (item.get("id") or item.get("token")) == key:
            items[i] = {**item, **record}
            record = items[i]
            found = True
            break
    if not found:
        items.append(record)
    save_feedback(items)
    return record


def mask_secret(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if "•" in raw:
        return raw
    if len(raw) <= 8:
        return "••••••••"
    return raw[:4] + "••••••••" + raw[-4:]


def is_masked_secret(value: str) -> bool:
    return "•" in (value or "")


def public_models_payload() -> dict[str, Any]:
    models = load_models()
    settings = load_settings()
    keys = settings.get("api_keys") or {}
    providers_out = {}
    for pid, provider in (models.get("providers") or {}).items():
        p = deepcopy(provider)
        key = (keys.get(pid) or "").strip()
        p["api_key_configured"] = bool(key)
        p["api_key_masked"] = mask_secret(key) if key else ""
        providers_out[pid] = p
    return {
        "active_provider": models.get("active_provider"),
        "active_model_id": models.get("active_model_id"),
        "providers": providers_out,
    }


def public_settings_payload() -> dict[str, Any]:
    settings = load_settings()
    smtp = deepcopy(settings.get("smtp") or {})
    imap = deepcopy(settings.get("imap") or {})
    keys = settings.get("api_keys") or {}
    smtp["password"] = mask_secret(smtp.get("password") or "")
    imap["password"] = mask_secret(imap.get("password") or "")
    return {
        "feedback_delay_hours": int(settings.get("feedback_delay_hours") or 48),
        "support_email": settings.get("support_email") or "support@myintelibooks.com",
        "public_base_url": settings.get("public_base_url") or "http://localhost:5173",
        "smtp": smtp,
        "imap": imap,
        "smtp_configured": bool((settings.get("smtp") or {}).get("host") and (settings.get("smtp") or {}).get("password")),
        "api_keys": {k: mask_secret(v or "") for k, v in keys.items()},
        "api_keys_configured": {k: bool((v or "").strip()) for k, v in keys.items()},
    }


def get_active_image_runtime() -> dict[str, Any]:
    """
    Resolve the provider, model id, API key, and endpoint currently selected
    in the admin panel. Falls back to OpenRouter + env vars.
    """
    models = load_models()
    settings = load_settings()
    provider_id = (models.get("active_provider") or "openrouter").strip().lower()
    model_id = (models.get("active_model_id") or "openai/gpt-image-2").strip()
    providers = models.get("providers") or {}
    provider = providers.get(provider_id) or providers.get("openrouter") or {}
    endpoint = "images"
    description = ""
    cost = ""
    for m in provider.get("models") or []:
        if m.get("id") == model_id:
            endpoint = m.get("endpoint") or "images"
            description = m.get("description") or ""
            cost = m.get("cost_per_call") or ""
            break
    keys = settings.get("api_keys") or {}
    api_key = (keys.get(provider_id) or "").strip()
    if not api_key and provider_id == "openrouter":
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key and provider_id == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key and provider_id == "gemini":
        api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    return {
        "provider": provider_id,
        "provider_name": provider.get("name") or provider_id,
        "model": model_id,
        "api_key": api_key,
        "endpoint": endpoint,
        "description": description,
        "cost_per_call": cost,
    }


def has_image_api_key() -> bool:
    rt = get_active_image_runtime()
    key = (rt.get("api_key") or "").strip()
    return bool(key) and not key.startswith("sk-or-v1-xxxx") and not key.startswith("your-")


def iter_job_metadata() -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    if not JOBS_DIR.exists():
        return jobs
    for job_dir in sorted(JOBS_DIR.iterdir()):
        if not job_dir.is_dir():
            continue
        meta_path = job_dir / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        meta.setdefault("job_id", job_dir.name)
        pdf_dir = job_dir / "generated_pdfs"
        pdfs = list(pdf_dir.glob("*.pdf")) if pdf_dir.exists() else []
        meta["has_pdf"] = bool(pdfs)
        if pdfs and not meta.get("pdf_filename"):
            meta["pdf_filename"] = pdfs[0].name
        jobs.append(meta)
    return jobs
