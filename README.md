# GENAI_Hiring_Assessment
An AI Powered GenAI Assessment Engine

## To run frontend:
cd frontend
cd assessment-ui
rmdir /s /q node_modules
delete package-lock.json
npm install
npm install @vitejs/plugin-react --save-dev
npm run dev

## To run backend:
python -m venv venv
venv\Scripts\activate
cd ..
pip install -r requirements.txt
pip install python-dotenv
If you see llm problems in your terminal, especially points to llm.py file --> follow these steps
pip install python-dotenv
place these two blocks just before from openai import OpenAI library
    from dotenv import load_dotenv
    load_dotenv()
uvicorn main:app --reload
