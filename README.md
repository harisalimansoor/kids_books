# 📚 Personalized Math Question Generator

Welcome to the **Personalized Math Question Generator**! This project is a fun, intelligent web application designed to create highly customized math workbooks for kids. Using Artificial Intelligence, it generates math problems centered around a child's name, their family, their friends, and their hobbies! As a fantastic finishing touch, it also illustrates the story problems with beautiful child-friendly imagery and exports the whole thing to a ready-to-print PDF.

---

## 🚀 Tech Stack Used
- **Python**: The core programming language powering the logic.
- **Streamlit**: A rapid framework used to create the beautiful web interface you interact with.
- **Groq API (Llama 3)**: A blazing-fast AI language model used to generate creative math text problems.
- **OpenAI (DALL-E 3)**: An advanced AI image generator that draws the gorgeous and colorful kid-style illustrations.
- **FPDF**: A Python library used for assembling the text and images into a final downloadable PDF.
- **Python-Dotenv**: For safely managing hidden API key variables outside of the literal code.

---

## 🛠️ Installation Steps

Follow these steps entirely if you have never run the project before.

### 1. Download and Extract the Files
Extract the provided project folder to your desired location, then open a Command Prompt or Terminal inside that folder.

### 2. Create and Activate a Virtual Environment
A virtual environment keeps your project dependencies separated from your computer's global Python settings.
- **For Windows:**
  ```bash
  python -m venv venv
  venv\Scripts\activate
  ```
- **For Mac/Linux:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  ```

### 3. Prepare Your Environment file (`.env`)
To protect your secret AI keys, you must store them in the `.env` file instead of writing them inside the Python scripts. 
There is a `.env` file provided in this repository. Open `.env` in any text editor (like Notepad), and add your API Keys:
```env
GROK_API_KEY="your_actual_grok_apiKey_here"
OPENAI_API_KEY="your_actual_openai_apiKey_here"
```

### 4. Install Required Dependencies
To make sure your Python installation has all the required tools, run the following command in your terminal (make sure your virtual environment is active!):
```bash
pip install -r requirements.txt
```

---

## 💻 How to Run the Project

Running a Streamlit app is a bit different from running standard Python code. Once you have finished your installation:

1. Open your terminal or command prompt.
2. Ensure you are situated inside the `kids_books-main` project folder.
3. Run the following command:
   ```bash
   streamlit run app.py
   ```
4. A browser window should automatically open up revealing the web page interface.
5. In the UI, enter the student's personal information, select their grade and topic from the dropdown, choose whether you want generated images, and click on **Generate Personalized Workbook**. 
6. Wait 1-2 minutes for the AI to perform its magic.
7. Click the **Download PDF Workbook** button when completed!

---

## 📂 Project File Structure
For educational convenience, here is a breakdown of what every file inside this project's folder does (also individually explained in their separate READMEs):

```text
kids_books-main/
│
├── .env                            <-- Contains your hidden, secret API keys
├── .gitignore                      <-- Prevents secret files (like .env) from being uploaded to GitHub
├── README.md                       <-- This master documentation file
│
├── app.py                          <-- The MAIN program that runs the Streamlit UI and wires everything together
├── api_clients.py                  <-- Handles all outbound communication to Groq & OpenAI APIs
├── config.py                       <-- Loads settings, constants, and links the .env secrets securely
├── file_handlers.py                <-- Looks into question_bank/ and reads the sample .txt datasets
├── pdf_generator.py                <-- Combines the AI questions and downloaded pictures into the final PDF workbook
├── prompt_builder.py               <-- Gathers all user input and formats it into instructions for the AI
├── utils.py                        <-- Carries small extra tools used for text-cleaning and formatting
│
├── README_app.md                   <-- Separate README explaining app.py
├── README_api_clients.md           <-- Separate README explaining api_clients.py
├── README_config.md                <-- Separate README explaining config.py
├── README_file_handlers.md         <-- Separate README explaining file_handlers.py
├── README_pdf_generator.md         <-- Separate README explaining pdf_generator.py
├── README_prompt_builder.md        <-- Separate README explaining prompt_builder.py
├── README_utils.md                 <-- Separate README explaining utils.py
│
├── requirements.txt                <-- A list of necessary packages to install via pip
└── question_bank/                  <-- A folder containing text files serving as sample questions for different grades
```