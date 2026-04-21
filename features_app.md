# 📚 Personalized Question Generator App

## 💡 Project Summary
 
The app is designed to assist teachers, parents, and educators by **automatically generating personalized question worksheets** for students.  
By integrating **Groq’s Llama 3.1 model**, the application takes a list of sample questions and personalizes them using the student’s name, siblings, and friends.  
The generated questions are formatted into a clean, printable **PDF worksheet**, making learning both engaging and customized for each child.

---

## 📝 Overview
The **Personalized Question Generator** is a Streamlit web application that allows users to paste sample questions and generate similar, personalized ones.  
The app leverages a Large Language Model (LLM) API to understand question context and produce natural, human-like variations.  
Finally, all personalized questions are exported into a **worksheet-style PDF** ready for classroom or home use.

---

## 🚀 Key Features

### 1. Streamlit-Based Web Interface
- Intuitive user interface for educators and parents.  
- Text fields for student name, siblings, and friends.  
- Easy paste-and-generate workflow.

### 2. Integration with Groq API
- Uses **Groq’s Llama 3.1 model (`llama-3.1-8b-instant`)** for fast and intelligent question generation.  
- Ensures that generated questions sound natural and relevant to the student’s context.

### 3. Dynamic PDF Generation
- Automatically creates a **worksheet-style PDF** with numbered questions.  
- Adds lines for answers and includes a footer message.  
- Handles encoding safely to avoid PDF corruption issues.

### 4. Real-Time Download
- PDF is generated **in memory (BytesIO)** for quick download within the app.  
- No need to save files locally.

### 5. Error Handling and Input Validation
- Warns users if any required input (e.g., student name or questions) is missing.  
- Displays success messages when the worksheet is ready.  

---

## 🧠 Technologies Used
- **Python 3**
- **Streamlit** — for interactive web interface  
- **FPDF** — for PDF creation  
- **LangChain** — for structured prompt formatting  
- **Groq API** — for natural language generation  
- **dotenv** — for securely managing API keys  
- **Requests** — for HTTP requests to the Groq API  
- **BytesIO** — for in-memory PDF file handling  

---

## ⚙️ How It Works

1. The user enters:
   - Student’s name  
   - Names of siblings and friends  
   - A list of sample questions  
2. The app sends a structured prompt to **Groq’s Llama 3.1 model** for each question.  
3. The model generates a set of **personalized questions** based on the input.  
4. All generated questions are compiled into a **beautifully formatted PDF**.  
5. The user can download the final worksheet instantly from the app interface.

---

## 📂 Project File Structure
kids_books/
│
├── app.py # Main Streamlit application
├── .env # Stores Groq API key securely
├── features_app.md # This documentation file
├── requirements.txt # Python dependencies (optional)
└── README.md # General project overview

---

## 🧾 Sample Prompt Sent to Groq

```text
Generate 3 questions similar to this: 'What is your favorite toy?'
Personalize each question naturally with the student's name 'Ali', 
siblings (Sara), and friends (Ahmed, Zain).

📄 Example Output in PDF

1. Ali, what toy do you love to play with the most at home with Sara?
2. If Ahmed and Zain came to visit, which toy would you show them first?
3. Which toy do you and Sara like playing with before bedtime?


