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
# Generate Image
###########################################################

generation_prompt = f"""
Generate a photorealistic image.

Requirements:

- Exactly {EXPECTED_COUNT} {OBJECT_NAME}s.
- Arrange them naturally.
- White background.
- No people.
- No text.
- No watermark.
- High quality.
"""

print("=" * 60)
print("Generating image...")
print("=" * 60)

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "model": IMAGE_MODEL,
    "messages": [
        {
            "role": "user",
            "content": generation_prompt
        }
    ]
}

response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers=headers,
    json=payload
)

response.raise_for_status()

result = response.json()

###########################################################
# Extract Base64 Image
###########################################################

try:
    image_b64 = result["choices"][0]["message"]["images"][0]["image_base64"]
except Exception:
    print(json.dumps(result, indent=4))
    raise Exception("Could not find generated image.")

image = Image.open(BytesIO(base64.b64decode(image_b64)))
image.save(IMAGE_FILE)

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