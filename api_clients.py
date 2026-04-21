"""
API client functions for Groq and OpenAI
"""
import time
import requests
import streamlit as st
from openai import OpenAI
from config import GROK_API_KEY, OPENAI_API_KEY, GROQ_API_URL, DEFAULT_MODEL, IMAGE_STYLES


def call_groq(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """
    Call Groq API to generate math questions.
    
    Args:
        prompt: The prompt to send to the API
        model: The model to use (default from config)
    
    Returns:
        Generated text response
    """
    headers = {
        "Authorization": f"Bearer {GROK_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        else:
            st.error(f"Groq API error {resp.status_code}: {resp.text}")
            return "Sorry, something went wrong with the API call."
    except Exception as e:
        st.error(f"Request exception: {e}")
        return "Sorry, something went wrong with the API call."


def generate_image_for_question(
    question_text: str, 
    student_name: str, 
    image_style: str = "cartoon", 
    image_quality: str = "standard"
):
    """
    Uses OpenAI's DALL-E 3 to create a kid-friendly illustration for each math question.
    
    Args:
        question_text: The math question text
        student_name: Student's name for context
        image_style: Visual style (cartoon, simple, etc.)
        image_quality: "standard" or "hd"
    
    Returns:
        Image URL or None if generation fails
    """
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    try:
        style = IMAGE_STYLES.get(image_style, "colorful cartoon style")
        
        # Create a child-friendly prompt
        simplified_prompt = (
            f"A {style} illustration for children showing a math problem scenario: "
            f"{question_text[:200]}. Make it colorful, engaging, and appropriate for "
            f"elementary students. No text, numbers, or words in the image, just the visual scene."
        )
        
        response = client.images.generate(
            model="dall-e-3",
            prompt=simplified_prompt,
            size="1024x1024",
            quality=image_quality,
            style="vivid",
            n=1
        )
        
        return response.data[0].url
        
    except Exception as e:
        st.warning(f"⚠️ Image generation failed: {str(e)[:100]}")
        return None


def download_image(image_url: str, save_path: str, max_retries: int = 3) -> bool:
    """
    Downloads an image from URL and saves it locally.
    
    Args:
        image_url: URL of the image
        save_path: Path to save the image
        max_retries: Number of retry attempts
    
    Returns:
        True if successful, False otherwise
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(image_url, timeout=30)
            if response.status_code == 200:
                with open(save_path, "wb") as f:
                    f.write(response.content)
                return True
            else:
                time.sleep(1)
        except Exception as e:
            if attempt == max_retries - 1:
                st.warning(f"Failed to download image after {max_retries} attempts")
            time.sleep(1)
    return False