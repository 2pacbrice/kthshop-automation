"""
KTHSHOP — API Webhooks
Reçoit les notifications externes (BKApay, Meta, Shopify).
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, HTTPException

from ..core.config import config
from ..core.database import db
from ..agents.publisher import Publisher

logger = logging.getLogger("kthshop.webhooks")
router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/bkapay")
async def bkapay_webhook(request: Request):
    """
    Webhook BKApay — reçoit les notifications de paiement.
    Déclenche : confirmation WhatsApp, mise à jour stock, notification.
    """
    try:
        body = await request.json()
        logger.info(f"💳 Webhook BKApay reçu: {json.dumps(body, ensure_ascii=False)[:200]}")

        event_type = body.get("event", body.get("type", "unknown"))
        transaction_id = body.get("transaction_id", body.get("id", "?"))

        if event_type in ("payment.success", "payment.completed"):
            # Paiement réussi → notification WhatsApp
            phone = body.get("phone", body.get("customer_phone", ""))
            amount = body.get("amount", "?")
            product = body.get("product_name", "Commande KTHSHOP")

            publisher = Publisher()
            message = (
                f"✅ *Paiement confirmé KTHSHOP* ✅\n\n"
                f"Merci pour ton achat !\n\n"
                f"🔖 Produit : {product}\n"
                f"💰 Montant : {amount} {config.kthshop.currency}\n"
                f"📦 Statut : En cours de préparation\n\n"
                f"Nous te contacterons dès l'expédition 🚚\n\n"
                f"📞 {config.kthshop.whatsapp_business}"
            )

            if phone:
                publisher.send_whatsapp_message(phone, message)

            # Logguer la transaction
            db.set_config(f"bkapay_last_{transaction_id}", json.dumps(body))

        return {"status": "ok", "event": event_type}

    except Exception as e:
        logger.error(f"❌ Erreur webhook BKApay: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/meta")
async def meta_webhook(request: Request):
    """
    Webhook Meta — reçoit les notifications de statut des publications.
    """
    try:
        body = await request.json()
        logger.info(f"🔔 Webhook Meta reçu")

        # Gérer la vérification hub (Meta demande ça au setup)
        if body.get("hub"):
            return {"hub.challenge": body["hub"]["challenge"]}

        # TODO: traiter les changements de statut des posts
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"❌ Erreur webhook Meta: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/shopify")
async def shopify_webhook(request: Request):
    """
    Webhook Shopify — notifications de commandes, produits, etc.
    """
    try:
        topic = request.headers.get("X-Shopify-Topic", "unknown")
        body = await request.json()
        logger.info(f"🛍️ Webhook Shopify ({topic}) reçu")

        if topic == "orders/create":
            # Nouvelle commande
            order_id = body.get("id", "?")
            total = body.get("total_price", "?")
            customer = body.get("customer", {})
            phone = customer.get("phone", "")

            logger.info(f"📦 Nouvelle commande #{order_id} — {total} {config.kthshop.currency}")

            if phone:
                publisher = Publisher()
                message = (
                    f"🛍️ *Commande confirmée KTHSHOP* 🛍️\n\n"
                    f"Merci pour ta commande !\n\n"
                    f"💰 Total : {total} {config.kthshop.currency}\n"
                    f"📦 Prépare-toi, on s'occupe de tout !\n\n"
                    f"Suivi : {config.kthshop.whatsapp_business}"
                )
                publisher.send_whatsapp_message(phone, message)

        elif topic == "products/create":
            product = body.get("product", {})
            db.upsert_product(
                id=str(product.get("id", "")),
                title=product.get("title", ""),
                vendor=product.get("vendor", "KTHSHOP"),
                price=float((product.get("variants") or [{}])[0].get("price", 0)),
                stock=int((product.get("variants") or [{}])[0].get("inventory_quantity", 0)),
                tags=product.get("tags", ""),
                image_url=((product.get("images") or [{}])[0] or {}).get("src", ""),
            )
            logger.info(f"🆕 Nouveau produit Shopify: {product.get('title')}")

        return {"status": "ok"}

    except Exception as e:
        logger.error(f"❌ Erreur webhook Shopify: {e}")
        raise HTTPException(status_code=400, detail=str(e))