# The Guild — Backend

FastAPI backend for The Guild. Hosted on Render.

## Endpoints
- `GET /` — service info
- `GET /health` — health check (used by Render)

## Local dev
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in values
uvicorn app.main:app --reload