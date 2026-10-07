import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import agent, claims, guilds, invoices, jobs, members, milestones, pool, webhooks

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="The Guild API", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url] if settings.frontend_url else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"name": "The Guild API", "version": "0.3.0", "docs": "/docs"}


@app.get("/health")
def health():
    return {"status": "ok", "service": "guild-backend"}


app.include_router(guilds.router)
app.include_router(members.router)
app.include_router(jobs.router)
app.include_router(milestones.router)
app.include_router(invoices.router)
app.include_router(pool.router)
app.include_router(webhooks.router)
app.include_router(claims.router)
app.include_router(agent.router)