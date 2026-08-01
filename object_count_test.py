import os
import json
import base64
import requests
from io import BytesIO
from PIL import Image
from dotenv import load_dotenv

###########################################################
# Load API Key
###########################################################

load_dotenv()

from config import OPENROUTER_API_KEY, OPENROUTER_URL

API_KEY = OPENROUTER_API_KEY

if API_KEY is None:
    raise Exception("OPENROUTER_API_KEY not found!")

###########################################################
# CONFIGURATION
###########################################################

# Image Generation Model
IMAGE_MODEL = "openai/gpt-5.4-image-2"

# Vision Language Model
VISION_MODEL = "qwen/qwen2.5-vl-72b-instruct"

OBJECT_NAME = "cupcake"
EXPECTED_COUNT = 6

IMAGE_FILE = "generated.png"

###########################################################
# Extract Image (same logic as ai_renderer.py)
###########################################################

def extract_image(response_json):
    """
    Extract image URL or base64 data from an OpenRouter response.
    Supports multiple response formats.
    """

    message = response_json.get("choices", [{}])[0].get("message", {})

    # Format 1
    images = message.get("images", [])
    if images and isinstance(images, list):
        url = images[0].get("image_url", {}).get("url")
        if url:
            return url

    # Format 2
    content = message.get("content", "")

    if isinstance(content, list):
        for block in content:

            if not isinstance(block, dict):
                continue

            if block.get("type") == "image_url":
                return block.get("image_url", {}).get("url")

            text = block.get("text", "")
            if isinstance(text, str) and text.startswith("data:image"):
                return text

    # Format 3
    if isinstance(content, str) and content.startswith("data:image"):
        return content

    return None


def save_image(image_data, save_path):
    """
    Save image returned from OpenRouter.
    Supports both URLs and base64 data URLs.
    """

    if image_data.startswith("data:image"):

        _, encoded = image_data.split(",", 1)

        image = Image.open(BytesIO(base64.b64decode(encoded)))

        image.convert("RGB").save(
            save_path,
            format="PNG"
        )

        return True

    # Download URL
    response = requests.get(image_data)

    if response.status_code != 200:
        return False

    image = Image.open(BytesIO(response.content))

    image.convert("RGB").save(
        save_path,
        format="PNG"
    )

    return True


image_data = extract_image(result)

if image_data is None:
    print(json.dumps(result, indent=4))
    raise Exception("No image found in API response.")

if not save_image(image_data, IMAGE_FILE):
    raise Exception("Failed to save image.")

print(f"\nImage saved as {IMAGE_FILE}")
print(f"\nImage saved as {IMAGE_FILE}")

###########################################################
# Encode Image
###########################################################

with open(IMAGE_FILE, "rb") as f:
    encoded_image = base64.b64encode(f.read()).decode("utf-8")

###########################################################
# Verification Prompt
###########################################################

verification_prompt = f"""
You are an image verification assistant.

Your task is to inspect the image carefully.

Count ONLY the visible {OBJECT_NAME}s.

Rules:

- Count each {OBJECT_NAME} only once.
- Ignore decorations.
- Ignore shadows.
- Ignore reflections.
- Do not estimate.

Return ONLY valid JSON.

Example:

{{
    "object": "{OBJECT_NAME}",
    "count": 6
}}
"""

###########################################################
# Send Image to Vision Model
###########################################################

print("\nSending image to Vision Model...")

vision_payload = {
    "model": VISION_MODEL,
    "messages": [
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": verification_prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{encoded_image}"
                    }
                }
            ]
        }
    ]
}

response = reuests.post(
    OPENROUTER_URL,
    headers=headers,
    json=vision_payload
)

response.raise_for_status()

vision_result = response.json()

###########################################################
# Parse Response
###########################################################

reply = vision_result["choices"][0]["message"]["content"]

print("\nModel Response:")
print(reply)

try:
    parsed = json.loads(reply)
    detected_count = parsed["count"]
except Exception:
    print("\nCould not parse JSON response.")
    exit()

###########################################################
# Compare Counts
###########################################################

print("\n" + "=" * 60)
print("Verification Result")
print("=" * 60)

print(f"Object          : {OBJECT_NAME}")
print(f"Expected Count  : {EXPECTED_COUNT}")
print(f"Detected Count  : {detected_count}")

if detected_count == EXPECTED_COUNT:
    print("\nPASS")
else:
    print("\nFAIL")

print("=" * 60)