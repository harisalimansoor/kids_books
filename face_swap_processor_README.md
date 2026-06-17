# `face_swap_processor.py` — Post-AI Face Swapping

## Purpose
After the AI renders the scene with generic faces, this module swaps user-uploaded face photos onto the correct character positions using insightface (InSwapper).

## Dependencies
- `insightface` (FaceAnalysis with `buffalo_l` model)
- `inswapper_128.onnx` (downloaded automatically on first use)
- `opencv-python`, `numpy`, `PIL`

## Model Initialization
Models are **lazy-loaded** on first `swap_faces()` call via `_load_models()`. Uses a singleton pattern (`_detector`, `_swapper` globals).

### `_load_models()`
- Initializes `FaceAnalysis(name="buffalo_l")` with CPU inference (`ctx_id=-1`, `det_size=(640,640)`)
- Loads `inswapper_128.onnx` from `~/.insightface/models/` (auto-downloads if missing)

### `_models_ready() -> bool`
Returns True if both detector and swapper loaded successfully.

## Public API

### `swap_faces(ai_image_path, metadata, face_map) -> str`
- **`ai_image_path`**: Path to AI-generated JPEG with generic faces
- **`metadata`**: Blueprint metadata dict with `characters` array (each having `body_rect.x` for L-R ordering)
- **`face_map`**: Dict mapping `role_key` → user photo file path (e.g. `{"user_name": "personalized_faces/user_face.png"}`)
- **Returns**: Path to the swapped image (`*_swapped.jpg`) if successful, or the original path if no swap performed

## Algorithm
1. Load AI image → detect all faces
2. Sort detected faces **left-to-right** by bounding box min-X
3. Sort characters from metadata **left-to-right** by `body_rect.x`
4. For each matching pair (up to `min(len(faces), len(chars))`):
   - Look up the character's `role_key` in `face_map`
   - Detect face in the user photo, pick the **largest** face
   - Call `_swapper.get()` to swap the target face with the user face
5. Save as `{basename}_swapped{ext}`

## Notes
- If models fail to load, the original image is returned unchanged
- If no faces are detected in either the AI image or user photo, no swap occurs
- Face count mismatch is logged but doesn't cause failure — only matches up to the minimum count

## Script Test
When run as `__main__`, tests with `test_rendered.jpg`, `test_metadata.json`, and `personalized_faces/` directory.
