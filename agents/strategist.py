"""
KTHSHOP — Agent Stratège
Décide QUOI publier, QUAND et sous QUEL ANGLE.
S'adapte en fonction des performances passées.
"""

import logging
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..core.config import config
from ..core.database import db

logger = logging.getLogger("kthshop.strategist")


class Strategist:
    """
    Agent Stratège — le cerveau marketing.
    - Lit le calendrier éditorial
    - Choisit le meilleur produit à promouvoir
    - Décide de l'angle marketing optimal
    - S'adapte selon les apprentissages de l'analyste
    """

    def __init__(self):
        self.shopify_token = config.shopify.access_token
        self.shopify_url = f"https://{config.shopify.store_url}"

    # ─── Planification principale ───────────────────────────

    def plan(self) -> list:
        """
        Décide ce qu'il faut publier MAINTENANT.
        Retourne une liste de décisions de publication.
        """
        decisions = []

        # 1. Vérifier le calendrier pour aujourd'hui
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        now = datetime.now(timezone.utc).strftime("%H:%M")

        calendar_entries = db.get_scheduled_posts(date=today)
        logger.info(f"📅 Calendrier aujourd'hui ({today}) : {len(calendar_entries)} entrées")

        for entry in calendar_entries:
            if entry["status"] != "pending":
                continue

            # Vérifier si c'est l'heure
            entry_time = entry.get("time", "")
            if entry_time and entry_time <= now:
                decision = self._build_decision_from_calendar(entry)
                if decision:
                    decisions.append(decision)
                    db.mark_calendar_done(entry["id"])
                    logger.info(f"✅ Décision prise depuis calendrier : {entry.get('content_type')} - {entry.get('product_name')}")

        # 2. Si rien dans le calendrier, décision intelligente
        if not decisions:
            auto_decision = self._auto_plan()
            if auto_decision:
                decisions.append(auto_decision)
                logger.info(f"🤖 Décision auto-générée : {auto_decision.get('content_type')}")

        return decisions

    # ─── Décisions depuis le calendrier ─────────────────────

    def _build_decision_from_calendar(self, entry: dict) -> Optional[dict]:
        """Convertit une entrée calendrier en décision de publication."""
        product_name = entry.get("product_name", "") or "Nouveauté KTHSHOP"
        angle = entry.get("angle", "desir")

        return {
            "product_id": entry.get("product_id", ""),
            "product_name": product_name,
            "content_type": entry.get("content_type", "photo"),
            "platform": entry.get("platform", "facebook"),
            "angle": angle,
            "caption_template": entry.get("caption_template", ""),
            "scheduled_for": f"{entry['date']} {entry['time']}",
            "source": "calendar",
        }

    # ─── Décision automatique ───────────────────────────────

    def _auto_plan(self) -> Optional[dict]:
        """
        Planification automatique quand le calendrier est vide.
        Utilise les apprentissages pour choisir le meilleur contenu.
        """
        products = db.get_products(limit=20)
        if not products:
            logger.warning("⚠️ Aucun produit en base — impossible de planifier auto")
            return None

        # Sélectionner le meilleur produit
        product = self._pick_best_product(products)
        if not product:
            return None

        # Choisir le meilleur type de contenu
        content_type = self._pick_best_content_type()

        # Choisir le meilleur angle
        angle = self._pick_best_angle(product)

        # Choisir le meilleur créneau horaire
        time_slot = self._pick_best_time_slot()

        return {
            "product_id": str(product.get("id", "")),
            "product_name": product.get("title", "Nouveauté KTHSHOP"),
            "content_type": content_type,
            "platform": "facebook",
            "angle": angle,
            "caption_template": "",
            "scheduled_for": time_slot,
            "source": "auto",
        }

    def _pick_best_product(self, products: list) -> Optional[dict]:
        """
        Choisit le meilleur produit à promouvoir.
        Priorité : stock disponible + jamais promu récemment + apprentissages.
        """
        if not products:
            return None

        # Voir les apprentissages sur les produits
        learnings = db.get_learnings("product")
        product_scores = {}

        for p in products:
            score = 0.5  # score de base
            pid = str(p.get("id", ""))

            # Bonus si en stock
            if p.get("stock", 0) > 0:
                score += 0.2

            # Bonus si appris comme performant
            if learnings and pid in learnings:
                score += learnings[pid] * 0.3

            product_scores[pid] = {
                "product": p,
                "score": score,
            }

        if not product_scores:
            return random.choice(products)

        # Prendre le meilleur score, avec un peu d'aléatoire pour explorer
        best = max(product_scores.values(), key=lambda x: x["score"])
        return best["product"]

    def _pick_best_content_type(self) -> str:
        """Choisit le type de contenu le plus performant."""
        learnings = db.get_learnings("content_type")
        if learnings:
            # Prendre le type avec le meilleur taux d'engagement
            sorted_types = sorted(
                learnings.items(), key=lambda x: x[1], reverse=True
            )
            if sorted_types:
                # 80% meilleur type, 20% exploration
                if random.random() < 0.8:
                    return sorted_types[0][0]

        # Fallback: alternance
        return random.choice(config.kthshop.content_types)

    def _pick_best_angle(self, product: dict) -> str:
        """Choisit l'angle marketing le plus adapté."""
        learnings = db.get_learnings("angle")

        # Vérifier si promo 8 ans encore active
        if config.kthshop.promo_8ans_active:
            promo_end = datetime.strptime(config.kthshop.promo_8ans_until, "%Y-%m-%d")
            if datetime.now() < promo_end:
                return "urgence"  # promouvoir l'urgence de la promo

        # Angle basé sur le stock
        stock = product.get("stock", 0)
        if stock and stock < 5:
            return "urgence"

        # Apprentissage : meilleur angle global
        if learnings:
            sorted_angles = sorted(
                learnings.items(), key=lambda x: x[1], reverse=True
            )
            if sorted_angles and random.random() < 0.8:
                return sorted_angles[0][0]

        return random.choice(config.kthshop.angles)

    def _pick_best_time_slot(self) -> str:
        """Choisit le meilleur créneau horaire selon les apprentissages."""
        learnings = db.get_learnings("time_slot")
        if learnings:
            sorted_slots = sorted(
                learnings.items(), key=lambda x: x[1], reverse=True
            )
            if sorted_slots and random.random() < 0.8:
                return sorted_slots[0][0]

        # Créneau par défaut
        now = datetime.now(timezone.utc)
        # Décalage pour Africa/Douala (UTC+1)
        hour = (now.hour + 1) % 24

        if hour < 12:
            return "12:30"
        elif hour < 14:
            return "14:00"
        elif hour < 18:
            return "18:30"
        else:
            return "21:00"

    # ─── Ajustement stratégique ─────────────────────────────

    def adjust_strategy(self, learnings: dict):
        """
        Ajuste la stratégie en fonction des apprentissages.
        Appelé après chaque cycle d'analyse.
        """
        logger.info("🎯 Ajustement stratégique basé sur les apprentissages")

        # Analyser les meilleurs créneaux
        if "time_slot" in learnings:
            best_slot = learnings["time_slot"][0]["key"]
            best_val = learnings["time_slot"][0]["value"]
            logger.info(f"  🕐 Meilleur créneau : {best_slot} (score: {best_val:.2f})")

        # Analyser les meilleurs types de contenu
        if "content_type" in learnings:
            best_type = learnings["content_type"][0]["key"]
            best_val = learnings["content_type"][0]["value"]
            logger.info(f"  📱 Meilleur type : {best_type} (score: {best_val:.2f})")

        # Analyser les meilleurs angles
        if "angle" in learnings:
            best_angle = learnings["angle"][0]["key"]
            best_val = learnings["angle"][0]["value"]
            logger.info(f"  🎬 Meilleur angle : {best_angle} (score: {best_val:.2f})")

    # ─── Sync produits Shopify ──────────────────────────────

    def sync_products(self) -> int:
        """
        Synchronise les produits depuis Shopify.
        Retourne le nombre de produits synchronisés.
        """
        if not self.shopify_token:
            logger.warning("⚠️ Pas de token Shopify — sync impossible")
            return 0

        import requests

        headers = {
            "X-Shopify-Access-Token": self.shopify_token,
            "Content-Type": "application/json",
        }

        try:
            url = f"{self.shopify_url}/admin/api/{config.shopify.api_version}/products.json"
            params = {"limit": 250, "status": "active"}

            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                products = response.json().get("products", [])
                count = 0
                for p in products:
                    variant = (p.get("variants") or [{}])[0]
                    image = (p.get("images") or [{}])
                    img_url = image[0].get("src", "") if image else ""

                    db.upsert_product(
                        id=str(p["id"]),
                        title=p.get("title", ""),
                        vendor=p.get("vendor", "KTHSHOP"),
                        price=float(variant.get("price", 0)),
                        stock=int(variant.get("inventory_quantity", 0)),
                        tags=p.get("tags", ""),
                        image_url=img_url,
                    )
                    count += 1
                logger.info(f"✅ {count} produits synchronisés depuis Shopify")
                return count
            else:
                logger.error(f"❌ Erreur Shopify API: {response.status_code} {response.text[:200]}")
                return 0

        except Exception as e:
            logger.error(f"❌ Erreur sync Shopify: {e}")
            return 0