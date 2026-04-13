# AI Resume Analyzer API (FastAPI MVP)

Production-ready MVP API to parse resumes, score resumes, run skill-gap analysis, and persist metadata to Supabase.
Includes optional AI ATS evaluation using Gemini.

## Project Structure

```
.
├── app
│   ├── core
│   │   └── config.py
│   ├── data
│   │   ├── role_templates.json
│   │   └── skills.json
│   ├── models
│   │   └── schemas.py
│   ├── routes
│   │   └── resume.py
│   ├── services
│   │   ├── ai_evaluator_service.py
│   │   ├── analyzer_service.py
│   │   ├── data_service.py
│   │   ├── nlp_service.py
│   │   ├── pdf_service.py
│   │   └── supabase_service.py
│   └── main.py
├── .env.example
├── docker-compose.yml
├── Dockerfile
├── main.py
├── pyproject.toml
├── supabase
│   └── setup.sql
└── requirements.txt
```

## Endpoints

- `POST /resume/analyze`
  - Form-data: `file` (PDF), `job_role` (optional)
  - Returns parsed data + scores + skill gap + recommendations + improvements
- `POST /resume/parse`
  - Form-data: `file` (PDF)
  - Returns structured parse only
- `POST /resume/score`
  - Form-data: `file` (PDF), `job_role` (optional)
  - Returns `resume_score` + breakdown
- `POST /resume/skill-gap`
  - JSON body: `{ "resume_text": "...", "job_role": "devops engineer" }`
  - Returns matched skills, missing skills, match score
- `POST /resume/ai-evaluate`
  - Form-data: `file` (PDF), `job_role` (required)
  - Uses Gemini + deterministic ATS metrics
  - Returns:
    - `summary`
    - `strengths`
    - `weaknesses`
    - `skills`
    - `missing_skills`
    - `match_score`
    - `resume_score`
    - `ats_score`
    - `recommended_roles`
    - `improvements`
    - `final_verdict`

## Gemini Setup

- Set `GEMINI_API_KEY` in `.env`.
- Optional: set `GEMINI_MODEL` (default: `gemini-2.0-flash-lite`).
- `GEMINI_FALLBACK_ENABLED=true` (default): if Gemini fails (quota/rate/auth/network), API returns deterministic strict ATS JSON.
- Set `GEMINI_FALLBACK_ENABLED=false` to fail request on Gemini errors.

## Supabase Setup

Recommended for backend API:
- Set `SUPABASE_SERVICE_ROLE_KEY` in `.env` and keep it server-side only.

If you are using an anon/publishable key and seeing `42501` / RLS errors:
- Run [supabase/setup.sql](/home/kushan/Documents/Resume_to_json/supabase/setup.sql) in Supabase SQL Editor.
- This creates tables, bucket, grants, and RLS policies needed for MVP writes.

Optional behavior:
- Set `SUPABASE_STRICT=true` to fail requests when Supabase write fails.
- Default `SUPABASE_STRICT=false` returns analysis even if persistence fails.

## Local Run

1. Create virtual environment and install deps.
2. Copy `.env.example` to `.env` and set Supabase/Gemini values.
3. Run API.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m spacy download en_core_web_sm
cp .env.example .env
uvicorn app.main:app --reload
```

Open: `http://127.0.0.1:8000/docs`

## Docker Deploy

```bash
docker build -t ai-resume-analyzer .
docker run --rm -p 8000:8000 --env-file .env ai-resume-analyzer
```

or

```bash
docker compose up --build
```

## Notes

- PDF-only uploads are enforced.
- Logic is deterministic and intentionally simple for MVP speed.
- If Supabase credentials are not set, API still works without persistence.
