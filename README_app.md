# `app.py`

<!-- ## What This Script Does -->
This is the **main script** for the Personalized Math Question Generator. It runs the user interface (UI) using Streamlit. It handles user inputs (like student name, grade, topics), connects to the other scripts to generate personalized math questions and images, and finally creates a downloadable PDF workbook.

## How to Run It
You don't run this script directly with normal Python. Because it's a Streamlit web app, you must run it using the `streamlit` command in the terminal.

1. Open your terminal or command prompt.
2. Navigate to the project folder.
3. Make sure all requirements are installed:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the script with:
   ```bash
   streamlit run app.py
   ```

## Required Input / Output
- **Inputs**: Interacting through the web interface (Student Name, Grade, Topic(s), etc.).
- **Outputs**: Displays the generated questions and provides a download button for the final PDF workbook (`math_workbook_for_[Name].pdf`).
