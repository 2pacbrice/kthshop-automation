"""
KTHSHOP — Dashboard API
Points d'accès pour suivre l'état du système en temps réel.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter

from ..core.config import config
from ..core.database import db
from ..core.orchestrator import orchestrator

logger = logging.getLogger("kthshop.dashboard")
router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_stats():
    """Statistiques générales du système."""
    stats = db.get_stats()
    summary = db.get_summary_metrics(days=7)
    learnings = db.get_learnings()

    return {
        "shop": config.kthshop.shop_name,
        "status": "running",
        "dry_run": config.dry_run,
        "promo_8ans_active": config.kthshop.promo_8ans_active,
        "database": stats,
        "weekly_performance": {
            "total_posts": summary.get("total_posts", 0),
            "avg_impressions": round(summary.get("avg_impressions", 0), 1),
            "avg_engagement": round(
                summary.get("avg_likes", 0) + summary.get("avg_comments", 0) + summary.get("avg_shares", 0), 1
            ),
        },
        "learnings": learnings,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/posts")
async def get_posts(limit: int = 20):
    """Liste les derniers posts."""
    posts = db.get_recent_posts(limit=limit)
    return {
        "posts": posts,
        "count": len(posts),
    }


@router.get("/calendar")
async def get_calendar():
    """Liste le calendrier éditorial."""
    entries = db.get_scheduled_posts()
    return {
        "entries": entries,
        "count": len(entries),
    }


@router.get("/products")
async def get_products(limit: int = 50):
    """Liste les produits synchronisés."""
    products = db.get_products(limit=limit)
    return {
        "products": products,
        "count": len(products),
    }


@router.post("/sync/products")
async def sync_products():
    """Déclenche une synchronisation manuelle des produits Shopify."""
    strategist = orchestrator.agents.get("strategist")
    if not strategist:
        return {"status": "error", "message": "Agent strategist non disponible"}

    count = strategist.sync_products()
    return {"status": "ok", "products_synced": count}


@router.post("/publish/now")
async def publish_now():
    """Déclenche une publication immédiate."""
    agent = orchestrator.agents.get("strategist")
    publisher = orchestrator.agents.get("publisher")

    if not agent or not publisher:
        return {"status": "error", "message": "Agents non disponibles"}

    decisions = agent.plan()
    results = []

    for dec in decisions:
        # TODO: utiliser le créateur ici
        caption = f"Décision auto: {dec.get('product_name')} — {dec.get('angle')}"
        post_id = db.add_post(
            scheduled_at=datetime.now(timezone.utc).isoformat(),
            status="ready_to_publish",
            platform=dec.get("platform", "facebook"),
            content_type=dec.get("content_type", "photo"),
            product_name=dec.get("product_name", ""),
            caption=caption,
        )

        content = {
            "post_id": post_id,
            "product_name": dec.get("product_name", "KTHSHOP"),
            "caption": caption,
            "content_type": dec.get("content_type", "photo"),
            "platform": dec.get("platform", "facebook"),
        }

        success = publisher.publish(content)
        results.append({
            "product": dec.get("product_name"),
            "success": success,
        })

    return {"status": "ok", "results": results}


@router.get("/health")
async def health():
    """Healthcheck pour Railway."""
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime": "running",
    }