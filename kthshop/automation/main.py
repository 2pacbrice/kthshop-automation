"""
KTHSHOP — Automation Intelligence
Serveur FastAPI + Orchestrateur multi-agents.
Déploiement : Railway.
"""

import logging
import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core.config import config
from .core.database import db
from .core.orchestrator import orchestrator

from .agents.strategist import Strategist
from .agents.creator import Creator
from .agents.publisher import Publisher
from .agents.analyst import Analyst

from .api.webhooks import router as webhooks_router
from .api.dashboard import router as dashboard_router

# ─── Logging ────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, config.log_level, logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("kthshop")


# ─── Initialisation des agents ─────────────────────────────

def init_agents():
    """Enregistre les 4 agents dans l'orchestrateur."""
    strategist = Strategist()
    creator = Creator()
    publisher = Publisher()
    analyst = Analyst()

    orchestrator.register_agent("strategist", strategist)
    orchestrator.register_agent("creator", creator)
    orchestrator.register_agent("publisher", publisher)
    orchestrator.register_agent("analyst", analyst)

    logger.info("🤖 Agents enregistrés : strategist, creator, publisher, analyst")


# ─── Planificateur APScheduler ──────────────────────────────

def init_scheduler(app: FastAPI):
    """Configure le planificateur intégré."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from apscheduler.triggers.cron import CronTrigger

        scheduler = BackgroundScheduler(timezone="UTC")

        # Enregistrer les tâches depuis l'orchestrateur
        for task in orchestrator.get_scheduler_tasks():
            trigger_type = task.get("trigger", "interval")

            if trigger_type == "interval":
                trigger = IntervalTrigger(hours=task.get("hours", 1))
            elif trigger_type == "cron":
                trigger = CronTrigger(
                    hour=task.get("hour", 0),
                    minute=task.get("minute", 0),
                    day_of_week=task.get("day_of_week", "*"),
                )
            else:
                continue

            scheduler.add_job(
                task["func"],
                trigger=trigger,
                id=task["id"],
                name=task.get("name", ""),
                replace_existing=True,
            )
            logger.info(f"⏰ Tâche planifiée : {task.get('name', task['id'])}")

        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("✅ Planificateur démarré")

    except ImportError:
        logger.warning("⚠️ APScheduler non installé — pas de planification automatique")
        app.state.scheduler = None


# ─── Application FastAPI ────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cycle de vie de l'application."""
    # Démarrage
    logger.info("🚀 Démarrage de KTHSHOP Automation...")
    logger.info(f"   Mode dry_run: {config.dry_run}")
    logger.info(f"   Base de données: {config.database_path}")
    logger.info(f"   Promo 8 ans active: {config.kthshop.promo_8ans_active}")

    init_agents()
    init_scheduler(app)

    # Premier cycle orchestrateur
    await orchestrator.start()

    yield

    # Arrêt
    logger.info("🛑 Arrêt de KTHSHOP Automation...")
    orchestrator.stop()
    scheduler = getattr(app.state, "scheduler", None)
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="KTHSHOP Automation",
    description="Community Manager Automatique — Multi-agents intelligents",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(webhooks_router)
app.include_router(dashboard_router)


# ─── Routes racine ──────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "name": "KTHSHOP Automation",
        "version": "1.0.0",
        "status": "running",
        "agents": list(orchestrator.agents.keys()),
        "dry_run": config.dry_run,
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ Exception globale: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne du serveur", "error": str(exc)},
    )


# ─── Point d'entrée direct (pour `python -m kthshop.automation`) ─────

def main():
    """Lance le serveur directement (sans Railway)."""
    import uvicorn
    uvicorn.run(
        "kthshop.automation.main:app",
        host="0.0.0.0",
        port=config.port,
        reload=config.debug,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()