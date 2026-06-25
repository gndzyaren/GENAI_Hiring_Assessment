# GENAI_Hiring_Assessment
An AI Powered GenAI Assessment Engine

## To run frontend:
1) cd frontend
2) cd assessment-ui
3) rmdir /s /q node_modules
4) delete package-lock.json
5) npm install
6) npm install @vitejs/plugin-react --save-dev
7) npm run dev

## To run backend:
1) python -m venv venv
2) venv\Scripts\activate
3) cd ..
4) pip install -r requirements.txt
5) pip install python-dotenv
6) If you see llm problems in your terminal, especially points to llm.py file --> follow these steps
    - pip install python-dotenv
7) Place these two blocks just before from openai import OpenAI library
    - from dotenv import load_dotenv
    - load_dotenv()
8) uvicorn main:app --reload
