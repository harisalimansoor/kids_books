# `pdf_generator.py`

<!-- ## What This Script Does -->
This script takes all the AI-generated raw materials—specifically the text questions and the downloaded illustrations—and compiles them into a beautiful, ready-to-print PDF workbook. It takes care of layout, fonts, inserting the pictures underneath the math questions, and also cleans up the temporary image files when finished.

## How to Run It
This script is **not meant to be run directly**. It is invoked by `app.py` after the questions and images have been successfully produced via the API.

## Required Input / Output
- **Inputs**: Student name, Grade level, Selected Topics, A list of generated questions, and A list of file paths to the downloaded images. 
- **Outputs**: Returns binary formatting (PDF bytes) which Streamlit then presents as a downloadable file named `math_workbook_for_[Name].pdf`.
