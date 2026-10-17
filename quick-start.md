# The Guild: quick start

## 0. Before you start
- Supabase dashboard: make sure the project is not paused. If it is, click Restore and wait.
- `git pull` if you worked on another machine.

## 1. Backend (terminal 1)
```powershell
cd E:\Education\Practical\Paypal\The-Guild
cd backend
.\.venv\Scripts\Activate.ps1
alembic upgrade head
python -c "import app.main; print('All imports OK')"
uvicorn app.main:app --reload
```
Check: http://127.0.0.1:8000/health/db

## 2. Frontend (terminal 2)
```powershell
cd E:\Education\Practical\Paypal\The-Guild\frontend
npm run dev
```
Open http://localhost:3000 and log in as Maya.

If Turbopack crashes:
```powershell
Remove-Item -Recurse -Force .next
npm run dev
```

## 3. When done
```powershell
cd E:\Education\Practical\Paypal\The-Guild
git add .
git commit -m "message"
git push
```

## Handy
- List API routes (from backend): `python -c "import app.main as m; [print(p) for p in m.app.openapi()['paths']]"`
- Live: backend https://guild-backend-vqg5.onrender.com, frontend https://guild-frontend.mokshadsankhe.workers.dev
- Next task: Phase 8A Autopilot agent. Bring the draft plus backend/app/models.py and backend/app/services/ai.py.
