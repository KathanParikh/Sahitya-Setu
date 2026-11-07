# Sahitya-Setu
AI-powered RAG platform for Gujarati literature. Upload any Gujarati book and ask questions, get cited answers with page numbers.

## Setup

The backend needs Python 3.14, a free [Supabase](https://supabase.com) project, and Gemini or Groq API keys.

```bash
# OCR
brew install poppler tesseract
curl -L -o /opt/homebrew/share/tessdata/guj.traineddata \
  https://github.com/tesseract-ocr/tessdata_best/raw/main/guj.traineddata

# Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
cp .env.example .env    # then fill it in
```

In Supabase, run `backend/db/schema.sql` in the SQL Editor, create a private bucket called `books`, and enable email sign-in. Then start the server:

```bash
.venv/bin/uvicorn api.main:app --port 8000
.venv/bin/python -m unittest discover -s tests   # run the tests
```
