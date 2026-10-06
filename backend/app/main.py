from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import guilds, jobs, members

app = FastAPI(title="The Guild API", version="0.2.0")

origins = [settings.frontend_url] if settings.frontend_url else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,  # we use bearer tokens, not cookies
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"name": "The Guild API", "version": "0.2.0", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "guild-backend"}


app.include_router(guilds.router)
app.include_router(members.router)
app.include_router(jobs.router)