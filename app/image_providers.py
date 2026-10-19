"""
Direct OpenAI and Gemini image-generation clients used when the admin
panel selects a provider other than OpenRouter.
"""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image


class ProviderImageError(RuntimeError):
    pass


def generate_provider_image(
    *,
    provider: str,
    model: str,
    api_key: str,
    prompt: str,
    image_entries: list | None = None,
    timeout: int = 180,
) -> Image.Image:
    pid = (provider or "").strip().lower()
    if pid == "openai":
        return _openai_image(model=model, api_key=api_key, prompt=prompt, image_entries=image_entries, timeout=timeout)
    if pid == "gemini":
        return _gemini_image(model=model, api_key=api_key, prompt=prompt, image_entries=image_entries, timeout=timeout)
    raise ProviderImageError(f"Unknown image provider '{provider}'")


def _portrait_size(model: str) -> str:
    """Portrait size closest to the question-image window. Square is only for DALL-E 2."""
    name = (model or "").lower()
    if "dall-e-2" in name:
        return "1024x1024"
    if "dall-e-3" in name:
        return "1024x1792"
    return "1024x1536"


def _openai_image(*, model: str, api_key: str, prompt: str, image_entries, timeout: int) -> Image.Image:
    import requests

    headers = {"Authorization": f"Bearer {api_key}"}
    compact = prompt
    # DALL·E 3 is prompt-only. gpt-image-1 can take edits with a source image.
    use_edits = bool(image_entries) and "dall-e" not in model.lower()
    if use_edits:
        label, img_path = _first_entry(image_entries)
        files = {
            "image": (Path(img_path).name, open(img_path, "rb"), "application/octet-stream"),
        }
        data = {"model": model, "prompt": compact, "n": "1", "size": _portrait_size(model)}
        try:
            resp = requests.post(
                "https://api.openai.com/v1/images/edits",
                headers=headers,
                files=files,
                data=data,
                timeout=timeout,
            )
        finally:
            files["image"][1].close()
    else:
        headers["Content-Type"] = "application/json"
        payload: dict[str, Any] = {
            "model": model,
            "prompt": compact,
            "n": 1,
            "size": _portrait_size(model),
        }
        if "dall-e-3" in model.lower():
            payload["response_format"] = "b64_json"
        resp = requests.post(
            "https://api.openai.com/v1/images/generations",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    if resp.status_code != 200:
        raise ProviderImageError(f"OpenAI HTTP {resp.status_code}: {(resp.text or '')[:700]}")
    data = resp.json()
    if data.get("error"):
        raise ProviderImageError(str(data["error"])[:500])
    items = data.get("data") or []
    if not items:
        raise ProviderImageError("OpenAI returned no image data")
    item = items[0]
    if item.get("b64_json"):
        return Image.open(BytesIO(base64.b64decode(item["b64_json"]))).convert("RGB")
    url = item.get("url")
    if url:
        img_resp = requests.get(url, timeout=timeout)
        img_resp.raise_for_status()
        return Image.open(BytesIO(img_resp.content)).convert("RGB")
    raise ProviderImageError("OpenAI response had neither b64_json nor url")


def _gemini_image(*, model: str, api_key: str, prompt: str, image_entries, timeout: int) -> Image.Image:
    import requests

    compact = prompt
    if "imagen" in model.lower():
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict"
            f"?key={api_key}"
        )
        payload = {
            "instances": [{"prompt": compact}],
            "parameters": {"sampleCount": 1},
        }
        resp = requests.post(url, json=payload, timeout=timeout)
        if resp.status_code != 200:
            raise ProviderImageError(f"Gemini/Imagen HTTP {resp.status_code}: {(resp.text or '')[:700]}")
        data = resp.json()
        preds = data.get("predictions") or []
        if not preds:
            raise ProviderImageError("Imagen returned no predictions")
        b64 = preds[0].get("bytesBase64Encoded") or preds[0].get("b64")
        if not b64:
            raise ProviderImageError("Imagen prediction missing image bytes")
        return Image.open(BytesIO(base64.b64decode(b64))).convert("RGB")

    parts: list[dict[str, Any]] = [{"text": compact}]
    if image_entries:
        for entry in image_entries[:4]:
            label, img_path = _first_entry([entry]) if not isinstance(entry, (list, tuple)) else (entry[0], entry[1]) if len(entry) == 2 else ("", entry)
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                label, img_path = entry
            else:
                label, img_path = "", entry
            try:
                raw = Path(img_path).read_bytes()
                b64 = base64.b64encode(raw).decode("ascii")
                ext = Path(img_path).suffix.lower().lstrip(".")
                mime = {
                    "png": "image/png",
                    "jpg": "image/jpeg",
                    "jpeg": "image/jpeg",
                    "webp": "image/webp",
                    "gif": "image/gif",
                    "bmp": "image/bmp",
                    "tiff": "image/tiff",
                    "tif": "image/tiff",
                    "heic": "image/heic",
                    "heif": "image/heif",
                }.get(ext, "image/jpeg")
                if label:
                    parts.append({"text": f"Reference photo for {label}:"})
                parts.append({"inline_data": {"mime_type": mime, "data": b64}})
            except Exception:
                continue
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={api_key}"
    )
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    if resp.status_code != 200:
        raise ProviderImageError(f"Gemini HTTP {resp.status_code}: {(resp.text or '')[:700]}")
    data = resp.json()
    for cand in data.get("candidates") or []:
        for part in ((cand.get("content") or {}).get("parts") or []):
            inline = part.get("inline_data") or part.get("inlineData") or {}
            b64 = inline.get("data")
            if b64:
                return Image.open(BytesIO(base64.b64decode(b64))).convert("RGB")
    raise ProviderImageError(f"Gemini returned no image: {str(data)[:400]}")


def _first_entry(image_entries):
    entry = image_entries[0]
    if isinstance(entry, (list, tuple)) and len(entry) == 2:
        return entry[0], entry[1]
    return "", entry
