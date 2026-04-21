# `prompt_builder.py`

<!-- ## What This Script Does -->
This script functions as the "brain's translator" for the AI. It takes all the fragmented pieces of information entered by the user (student name, hobbies, family members, selected grade, and the sample questions) and elegantly combines them into a single, cohesive, long-form instruction (the "Prompt") to send to the AI API.

## How to Run It
This script is **not meant to be run directly**. It acts as a helper tool primarily used inside of `app.py`.

## Required Input / Output
- **Inputs**: Raw strings and variables regarding student data (name, gender, family members), and sample math materials.
- **Outputs**: It returns one massive, well-structured text prompt specifically formatted to get the best possible personalized math questions out of Groq's Large Language Model.
