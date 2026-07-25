"""
generator.py
Executes the generation of templates by calling the AI API.
"""
import os
import re
import json
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv
from .config import TemplateCombination
from .prompt_builder import build_prompt
from .metadata_builder import build_metadata

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openai/gpt-5.4-image-2"

def extract_image_url(data: dict) -> str | None:
    msg = data.get("choices", [{}])[0].get("message", {})
    images = msg.get("images", [])
    if images and isinstance(images, list):
        url = images[0].get("image_url", {}).get("url", "")
        if url: return url
    content = msg.get("content", "")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "image_url":
                return part["image_url"]["url"]
    if isinstance(content, str):
        match = re.search(r"(data:image/[a-z]+;base64,[A-Za-z0-9+/=]+)", content)
        if match: return match.group(1)
    return None

def generate_image(prompt: str) -> bytes | None:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type":  "application/json",
        "HTTP-Referer":  "http://localhost:8502",
    }
    payload = {
        "model": MODEL,
        "modalities": ["image", "text"],
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 1200,
    }
    resp = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=180)
    if resp.status_code != 200:
        print(f"  ✗ API Error: {resp.text[:300]}")
        return None
    img_ref = extract_image_url(resp.json())
    if not img_ref:
        return None
    if img_ref.startswith("data:image"):
        return base64.b64decode(img_ref.split(",", 1)[1])
    r = requests.get(img_ref, timeout=60)
    return r.content

def run_generation(combo: TemplateCombination, output_dir: Path):
    scene_dir = output_dir / combo.scene.id
    scene_dir.mkdir(parents=True, exist_ok=True)
    
    png_filename = f"{combo.template_id}.png"
    json_filename = f"{combo.template_id}.json"
    png_path = scene_dir / png_filename
    json_path = scene_dir / json_filename
    
    if png_path.exists() and json_path.exists():
        print(f"  ⏭️ Skipping {combo.template_id} (already exists)")
        return
        
    print(f"  Generating: {combo.template_id}")
    prompt = build_prompt(combo)
    
    img_bytes = generate_image(prompt)
    if not img_bytes:
        print(f"  ✗ Generation failed for {combo.template_id}")
        return
        
    # Save Image
    with open(png_path, "wb") as f:
        f.write(img_bytes)
        
    # Save Metadata
    meta = build_metadata(combo, png_filename)
    meta["prompt"] = prompt  # Store the prompt for reference/debugging
    with open(json_path, "w") as f:
        json.dump(meta, f, indent=2)
        
    print(f"  ✓ Saved {png_filename} and {json_filename}")
