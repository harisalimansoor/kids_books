# Swapping Engine

Face swap + AI blend package for the **Grade 1 workbook pipeline**.

Used by:

- `streamlit run new_pipeline/newapp.py`
- `new_pipeline/stem_pipeline.py` → `build_workbook_items()`

**All face-swap / AI-blend code for the workbook lives inside this folder.**  
There is no call out to `kitchen_scenes/`, `interactive_templates/` swap helpers, or other repo packages for swapping.

---

## What it does

Given a worksheet **template image** (with YuNet face boxes in `meta.json`) and **upload photos** (child ± adult), the engine:

1. Crops heads from the uploads  
2. Pastes them onto the template body (aligned to face landmarks + neck/shoulders)  
3. Sends the result to an **AI image model** (OpenRouter) to remove sticker edges and match lighting  
4. Quality-checks the AI result (shift, tilt, grow, double-face, ghosting)  
5. Body-locks drifted faces without creating temple/double-face ghosts  
6. Recolours neck/arms toward upload skin and locks object pixels so maths counts stay correct  

Output: a personalised RGB illustration ready for the PDF workbook.

---

## Package layout

| File | Responsibility |
|---|---|
| `__init__.py` | Public exports: `personalize_stem`, `run_child_adult_face_pipeline`, `run_child_only_face_pipeline` |
| `personalize.py` | **Orchestrator** — paste, AI blend, composite, QA, skin recolour, stem I/O |
| `face_detect.py` | YuNet ONNX face detection + 5-point landmarks |
| `face_swap.py` | Crop upload face / head / portrait; optional region scale |
| `body_align.py` | Body-aware placement (segmentation / pose) + post-AI snap |

Templates themselves stay in `new_pipeline/question_templates/` (not inside this package).

---

## High-level pipeline

```
Upload photos          Template PNG + meta.json face_regions
      │                           │
      ▼                           ▼
 face_swap.crop_*          face_detect / annotated boxes
      │                           │
      └──────────┬────────────────┘
                 ▼
        Soft paste (personalize)
        · align_head_in_box (body_align)
        · elliptical jaw fade into collar
                 │
                 ▼
        AI blend (OpenRouter)
        · adult pass, then child pass
                 │
                 ▼
        Accept / reject (_ai_blend_acceptable)
                 │
                 ▼
        Face-only composite + object lock
                 │
                 ▼
        Body lock (snap_ai_faces_to_reference)
                 │
                 ▼
        Skin recolour + degreen
                 │
                 ▼
              Final PNG
```

### Two modes

Both modes are **implemented in this package** (`personalize.py`). Nothing outside `new_pipeline/` is used for the swap/blend steps.

| Mode | When | Entry (in `swapping_engine`) |
|---|---|---|
| **Child + adult** | Template has child + adult faces (e.g. mother) | `run_child_adult_face_pipeline` |
| **Child-only** | Template has only a child face | `run_child_only_face_pipeline` |

`personalize_stem(stem_dir, …)` loads `meta.json`, picks the mode, and writes `out_path`.

> Note: the old name `run_kitchen_face_pipeline` is kept as an **alias** of `run_child_adult_face_pipeline` only. It does **not** call `kitchen_scenes/` or any other external swap code.
---

## Module details

### 1. `face_detect.py` — where is the face?

Uses **OpenCV YuNet** (`models/face_detection_yunet_2023mar.onnx`; auto-downloaded if missing).

For each detected face returns:

- bounding box `x, y, w, h`
- landmarks: `right_eye`, `left_eye`, `nose`, `mouth_right`, `mouth_left`
- confidence

Helpers:

- `detect_faces(image)` — raw detections  
- `pick_primary_face(faces, size)` — best face for an upload crop  
- `interocular(face)` — eye distance (scale cue)  
- `face_regions_for_template` / `annotate_template` — write YuNet boxes into template JSON  

Stem `meta.json` stores these as `face_regions` (roles: `child`, `mother`, `father`, …). The paste step trusts those annotated boxes as the source of truth.

---

### 2. `face_swap.py` — what to paste from the upload?

| Function | Crop |
|---|---|
| `crop_upload_face` | Tight face |
| `crop_upload_head` | Face + hair (preferred for kitchen paste) |
| `crop_upload_portrait` | Larger bust crop |

Also: `resize_face_keep_aspect`, `scale_region_for_role` (env-tunable; defaults leave annotated box size unchanged).

---

### 3. `body_align.py` — seat the head on the body

#### Placement (`align_head_in_box`)

Places an upload head into a paste box so it matches the template face:

1. **Eye-line tilt** — small rotation (±10°) so upload eyes match template eyes  
2. **Scale** — blend of interocular ratio, face-box ratio, and optional **head-to-body** width  
3. **Anchor** — eye / mouth-nose midpoint, pulled toward a **neck/collar** point  

#### Body anchor (`estimate_body_anchor`)

Builds a neck/shoulder target from (best available):

| Signal | Method |
|---|---|
| Skin segmentation | Skin pixels in a band below the chin |
| Selfie segmentation | MediaPipe (if installed) |
| Body width | Shoulder-band skin width (HOG person detector if OpenCV exposes it) |
| Pose | MediaPipe shoulders (if installed) |

Falls back gracefully when MediaPipe / HOG is unavailable.

#### Post-AI body lock (`snap_ai_faces_to_reference`)

If the AI moved/resized/tilted a face relative to soft-paste:

| Drift | Action |
|---|---|
| **Severe** | Keep soft-paste for that region (no composite) |
| **Mild** | Erase old soft-paste face footprint, paste reseated AI face with a **near-binary** mask (~2px feather) |
| **Post-snap still ≥2 faces** | Fall back to soft-paste |

**Why erase + tight mask?**  
Older code alpha-blended the moved AI face over intact soft-paste with a wide Gaussian mask. Fractional alpha mixed two offset faces → **temple / double-face ghosting**. That path is intentionally removed.

---

### 4. `personalize.py` — full personalisation

#### Soft paste (`_paste_into_annotated_region`)

1. Crop upload head (`crop_upload_head`)  
2. Expand adult paste box slightly for hair; child stays near YuNet face  
3. Align via `_cover_fit_face_aligned` → `align_head_in_box` + body anchor  
4. Paste with `_head_paste_mask` (opaque core, soft jaw → collar fade)  
5. Preserve upload skin tone (do not match to template neck at paste time)

Result is the **soft-paste** image — already personalised, but edges can look sticker-like.

#### AI blend (`_ai_blend_kitchen_style`)

Calls OpenRouter chat/completions with an image model (`PERSONALIZE_IMAGE_MODEL`, default `openai/gpt-5.4-image-2`).

Typical kitchen order:

1. **Adult focus** — blend adult jaw/hairline into body  
2. **Child focus** — remove child sticker edges; keep adult stable  

Prompts stress identity lock, neck seating, and not rewriting maths objects.

#### Accept / reject (`_ai_blend_acceptable` + `_choose_ai_or_soft`)

Reject AI (keep soft-paste) when:

| Check | Meaning |
|---|---|
| ≥2 faces in slot | Double-face |
| Face area too large | Head grew beyond annotated box |
| Centroid shift | Face slid off neck (`AI_MAX_FACE_SHIFT`) |
| Eye-line tilt drift | Face rotated (`AI_MAX_TILT_DEG`) |
| Bimodal ghosting | Mix of unchanged + heavily rewritten pixels |
| Soft ghosting | Large **mid-diff** band (12–45) — typical of alpha-blended double faces |

**Hard rejects** (shift / tilt / ghosting / double-face) cannot be overridden by “sticker looks better” scores. That prevents forcing a bad AI frame that later ghosts under body-lock.

#### Composite + lock

- `_face_only_composite` — take AI only inside face/hair ovals; keep base elsewhere  
- `_lock_objects_by_image_diff` — restore soft-paste pixels outside faces so object counts stay correct  
- `_body_lock_faces` → `snap_ai_faces_to_reference`  
- `_degreen_face` / `_recolor_body_to_upload` — clean colour cast; push neck/arms toward upload skin  

---

## Public API

```python
# With new_pipeline on sys.path (Streamlit does this):
from swapping_engine import personalize_stem

personalize_stem(
    stem_dir,                 # folder with meta.json + template PNG
    child_photo="child.jpg",
    adult_photo="mother.jpg", # omit for child-only stems
    adult_role="mother",
    out_path="out.png",
    run_ai_finish=True,
    soft_cartoon=False,
    require_ai=True,          # raise if AI required but failed
)
```

Lower-level:

```python
from swapping_engine import run_child_adult_face_pipeline, run_child_only_face_pipeline
# operate on an already-open PIL Image + region dicts
```

---

## Integration with the workbook

1. User uploads faces in Streamlit (`newapp.py`)  
2. `select_stems` picks templates with personalisable face regions  
3. `build_workbook_items` calls `personalize_stem` per question  
4. Failed stems can be skipped; successful PNGs go into the PDF  

Stem selection filters out templates missing a `child`/`user` face box when illustrations are on.

---

## Requirements

| Dependency | Role |
|---|---|
| `OPENROUTER_API_KEY` in repo `.env` | AI blend |
| `opencv-python` + YuNet ONNX | Face detect |
| `Pillow`, `numpy`, `requests` | Images / API |
| `mediapipe` (optional) | Pose + selfie segmentation for better body anchors |

---

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | — | Required for AI blend |
| `PERSONALIZE_IMAGE_MODEL` | `openai/gpt-5.4-image-2` | OpenRouter image model |
| `AI_MAX_FACE_SHIFT` | `0.12` | Max centroid drift (fraction of face box) |
| `AI_MAX_TILT_DEG` | `8.0` | Max eye-line tilt drift (degrees) |
| `AI_MAX_FACE_GROW` | `1.55` | Max AI face area vs annotated box |
| `AI_GHOST_LOW_FRAC` | `0.32` | Ghost: fraction of near-unchanged core pixels |
| `AI_GHOST_HIGH_FRAC` | `0.22` | Ghost: fraction of heavily rewritten pixels |
| `AI_GHOST_MID_FRAC` | `0.40` | Soft ghost: mid-diff band coverage |
| `OBJECT_LOCK_THRESHOLD` | `12` | Diff threshold for restoring non-face pixels |
| `OBJECT_LOCK_FACE_PAD` | `0.55` | Padding around faces left to AI |
| `FACE_ANNOTATED_PAD` | `1.0` | Scale on annotated boxes |
| `FACE_BLEND_PASS` | `1` | Compositor: `0` skips AI blend |
| `FACE_REGION_SCALE` / `MOTHER_FACE_SCALE` | `1.0` | Optional paste-box scale |

---

## Design principles

1. **Annotated YuNet boxes are ground truth** for size and seat — AI must not invent a second head elsewhere.  
2. **Soft-paste is a safe fallback** — always identity-correct; AI is optional beautification.  
3. **Never alpha-mix two misaligned faces** with a wide soft mask (ghosting).  
4. **Maths objects stay locked** — personalisation must not change countable items.  
5. **Upload skin is identity** — prefer recolouring the template body toward the upload, not the face toward the template.  

---

## Debugging tips

Watch Streamlit / terminal logs for:

- `body anchor: segment+body` (or `pose+…`) — placement used body cues  
- `accepted (ok; …)` / `rejected hard (… shifted|ghosting|tilt …)` — AI gate  
- `↳ body-lock … erased old face` — mild snap without ghost  
- `↳ body-lock … kept soft-paste` — severe drift or post-snap double-face  

Outputs land in `new_pipeline/_runtime/personalized/` during workbook builds.

---

## CLI (optional)

From repo root, with `new_pipeline` on `PYTHONPATH`:

```bash
python -m swapping_engine.face_detect --force   # YuNet helper (optional)
```

Primary path for product use remains the Streamlit workbook app.
