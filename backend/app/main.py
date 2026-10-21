import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.db import engine
from app.config import settings
from app.routers import autopilot
from app.routers import agent, claims, deposits, guilds, invoices, jobs, members, milestones, pool, tasks, webhooks, member_badges
from app.routers import platform
from app.routers import digest
from app.routers import portal
from app.routers import agreements
from app.routers import evidence
from app.routers import recovery
from app.routers import advances


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

@app.get("/health/db")
def health_db():
    with engine.connect() as conn:
        conn.execute(text("select 1"))
    return {"status": "ok", "database": "reachable"}


app.include_router(guilds.router)
app.include_router(members.router)
app.include_router(jobs.router)
app.include_router(milestones.router)
app.include_router(invoices.router)
app.include_router(pool.router)
app.include_router(webhooks.router)
app.include_router(claims.router)
app.include_router(agent.router)
app.include_router(tasks.router)
app.include_router(deposits.router)
app.include_router(member_badges.router)
app.include_router(autopilot.router)
app.include_router(platform.router)
app.include_router(digest.router)
app.include_router(portal.router)
app.include_router(portal.member_router)
app.include_router(agreements.router)
app.include_router(evidence.router)
app.include_router(recovery.router)
app.include_router(advances.router)
