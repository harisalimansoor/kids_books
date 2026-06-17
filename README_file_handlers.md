# `file_handlers.py`

<!-- ## What This Script Does -->
This script is responsible for reading the text files that store the "sample questions" for different topics and grades. It reaches into your `question_bank` directory, looks up the correct grade folder, and picks up the `.txt` files related to the math subjects you wish to generate.

## How to Run It
This script is **not meant to be run directly**. It is imported and utilized as a helper file by `app.py`.

## Required Input / Output
- **Inputs**: It accepts inputs like grade-level strings (e.g., "Grade 1") and specific topic names from the app.
- **Outputs**: It returns text chunks (strings) extracted directly from your sample `.txt` files to feed into the AI.
