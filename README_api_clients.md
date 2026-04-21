# `api_clients.py`

<!-- ## What This Script Does -->
This script handles all communication with external Artificial Intelligence (AI) services. It has two main jobs:
1. It connects to the **Groq API** to generate the personalized math text questions securely.
2. It connects to **OpenAI's DALL-E 3 API** to create beautiful, kid-friendly illustrations for the generated math problems.

## How to Run It
This script is a "helper" module and is **not meant to be run directly**. It is imported and used by `app.py`.

## Required Input / Output
- **Inputs**: It takes prompts (text instructions) from the `app.py` script. It also requires `GROK_API_KEY` and `OPENAI_API_KEY` from your `.env` file to authorize the connection.
- **Outputs**: It returns text strings containing the generated math questions, and image URLs for the downloaded illustrations. It also downloads and saves the generated images temporarily to your machine.
