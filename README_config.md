# `config.py`

<!-- ## What This Script Does -->
This script is the **configuration hub** for the entire project. It stores important settings, constants, and loads your secret API keys from the `.env` file using the `dotenv` package. This ensures your private keys are never hardcoded directly into the main code files.

It also contains:
- Mappings for Grade folders.
- API models and base URLs.
- Image styles and cost calculations for DALL-E.

## How to Run It
This script is **not meant to be run directly**. Other scripts import from it whenever they need configuration settings or API keys.

## Required Input / Output
- **Inputs**: It automatically reads your `.env` file on load to get the API keys (`GROK_API_KEY` and `OPENAI_API_KEY`). 
- **Outputs**: It provides configuration variables to any other Python script that imports them.
