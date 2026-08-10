# Setting up for the first time

This guide walks a first-time user through cloning the repo, installing tools, configuring API keys, pulling large `data/` files with Git LFS, and running the app.

## 1. Accounts and API keys

Create accounts and keys as needed (store them only in a local `.env` file, never in git):

| Variable | Where to get it |
|---|---|
| `OPENAI_API_KEY` | [OpenAI API keys](https://platform.openai.com/api-keys) |
| `GROK_API_KEY` | [xAI / Grok console](https://console.x.ai/) |
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) |
| `OPENROUTER_API_KEY` | [OpenRouter keys](https://openrouter.ai/keys) |
| `HF_API_KEY` | [Hugging Face access tokens](https://huggingface.co/settings/tokens) |

## 2. Install Git and Git LFS

The `data/` folder stores large PDFs, PPTX, DOCX, and MP4 files with **Git LFS**.

1. Install Git if needed.
2. Install Git LFS:
   - macOS: `brew install git-lfs`
   - Then run once: `git lfs install`
3. Confirm: `git lfs version`

Without Git LFS, clones only get tiny pointer files instead of the real media under `data/`.

## 3. Clone the repository

```bash
git clone https://github.com/harisalimansoor/kids_books.git
cd kids_books
```

Git LFS downloads large files during clone when LFS is installed. If files under `data/` look like text pointers, run:

```bash
git lfs pull
```

## 4. Create a Python virtual environment

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 5. Configure secrets in `.env`

In the **repo root**, copy the example file and fill in real keys:

```bash
cp .env.example .env
```

Edit `.env` (example shape):

```bash
OPENAI_API_KEY=...
GROK_API_KEY=...
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
HF_API_KEY=...
```

`.env` is gitignored. Do not commit it.

## 6. Run the project

```bash
source venv/bin/activate
streamlit run app.py
```

Open the URL Streamlit prints (usually `http://localhost:8501`).

## 7. Git LFS notes for this repo

- `.gitattributes` tracks `data/**/*.pdf`, `data/**/*.pptx`, `data/**/*.docx`, and `data/**/*.mp4` with LFS.
- On a normal machine with Git LFS installed, your working copy keeps **real files** (not pointer stubs).
- Pushing or pulling `data/` needs GitHub LFS storage/bandwidth quota. Free accounts include a small LFS quota; large uploads may need a [GitHub LFS data pack](https://docs.github.com/en/billing/managing-billing-for-git-large-file-storage).

## 8. Quick checklist

- [ ] Git + `git lfs install`
- [ ] Clone / `git lfs pull`
- [ ] `venv` + `pip install -r requirements.txt`
- [ ] Root `.env` filled from `.env.example`
- [ ] `streamlit run app.py`
