# `ai_renderer.py` — Step 2: AI Photorealistic Rendering

## Purpose
Sends the blueprint image (coloured shapes) to OpenRouter's `openai/gpt-5.4-image-2` for photorealistic rendering. Uses img2img with the blueprint as reference, with a text2img fallback.

## Strategy Hierarchy
1. **img2img** with GPT-5.4 Image 2 — sends blueprint image + structured prompt
2. **text2img** with GPT-5.4 Image 2 — coordinate-rich text-only prompt (if img2img fails)
3. **None** — caller uses the pre-composite blueprint as fallback

## Public API

### `render_image(pre_composite, metadata, output_path, strength, preserve_faces, gender) -> str | None`
- **`pre_composite`**: PIL Image (blueprint with optional pasted faces)
- **`metadata`**: Blueprint metadata dict with character/object positions
- **`output_path`**: Where to save the rendered JPEG
- **`strength`**: img2img strength (0.0–1.0), defaults to 0.75
- **`preserve_faces`**: If True, uses lower strength (max 0.4) to avoid altering pasted face photos
- **`gender`**: "Boy" / "Girl" / "Other" — controls child character descriptions in prompts
- **Returns**: Path to saved image, or `None`

## Prompt Building

### `_build_prompt(metadata, preserve_faces=False, gender="Boy") -> str`
Two variants:
- **Face-preservation mode**: Tells the AI to keep pasted face photos exactly as-is, blend only the edges.
- **Generic mode**: Tells the AI to ignore green head circles and generate appropriate generic faces.

Both variants include:
- Colour legend (🔵🟢🔴⬜) explaining shape meanings
- Character descriptions with role-specific render hints
- Object descriptions with exact coordinates and appearance definitions
- Scene context and photorealistic style instructions
- Anatomy & positioning rules (feet on ground, correct proportions)
- Count verification requirement
- List of banned behaviors (no extra objects, no piles, no cartoon style, etc.)

### `_build_text_prompt(metadata, gender="Boy") -> str`
Text-only alternative for models that can't accept image input. Same coordinate-rich content but without the shape legend.

## OpenRouter API Calls

### `_call_img2img(image_data_url, prompt, model, strength) -> str | None`
- Sends image + text to OpenRouter with `modalities: ["image", "text"]`
- Returns image URL or `"NEEDS_TEXT"` (indicating text2img fallback) or `None`

### `_call_text2img(prompt, model) -> str | None`
- Text-only call for models that don't support image input
- Returns image URL or `None`

### `_extract_image(data) -> str | None`
Extracts image URL or base64 from the OpenRouter response JSON, checking both `images` array and `content` blocks.

### `_download_image(image_url, save_path) -> bool`
Handles both base64 data URIs and HTTP URLs. Saves as JPEG quality 95.

## Constants
- `PRIMARY_MODEL`: `"openai/gpt-5.4-image-2"`
- `OBJECT_APPEARANCE`: Dict mapping 60+ object keywords to visual descriptions (e.g. "shiny red apples with a small stem")
- `ROLE_RENDER_HINTS`: Character role descriptions (e.g. "a woman in her 30s, wearing a casual top and jeans")

## Dependencies
- `requests`, `PIL`, `os`, `io`, `json`, `base64`
- `config` — `OPENROUTER_API_KEY`, `OPENROUTER_URL`
