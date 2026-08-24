"""
KTHSHOP — Agent Analyste
Collecte les métriques, apprend des performances, ajuste la stratégie.
C'est le cerveau qui permet au système de s'améliorer en continu.
"""

import logging
import json
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional

from ..core.config import config
from ..core.database import db

logger = logging.getLogger("kthshop.analyst")


class Analyst:
    """
    Agent Analyste — l'apprentissage continu.
    - Collecte les métriques des posts publiés (FB/IG)
    - Analyse les tendances (meilleurs créneaux, types de contenu, angles)
    - Met à jour la base d'apprentissage
    - Génère des rapports de performance
    - Détecte les patterns gagnants
    """

    def __init__(self):
        self.fb_token = config.facebook.page_token
        self.fb_page_id = config.facebook.page_id
        self.ig_user_id = config.facebook.ig_user_id
        self.graph_base = f"https://graph.facebook.com/{config.facebook.graph_api_version}"

    # ─── Collecte des métriques ────────────────────────────

    def collect_metrics(self):
        """
        Collecte les métriques des posts récents.
        Parcourt tous les posts publiés et récupère leurs stats.
        """
        recent_posts = db.get_recent_posts(limit=50)
        logger.info(f"📊 Collecte métriques pour {len(recent_posts)} posts récents")

        for post in recent_posts:
            if post["status"] != "published":
                continue

            post_id = post["id"]

            try:
                metrics = self._get_post_insights(post)

                if metrics:
                    db.add_metrics(
                        post_id=post_id,
                        platform=post.get("platform", "facebook"),
                        **metrics
                    )
                    logger.debug(f"✅ Métriques post #{post_id}: {metrics.get('impressions', 0)} impressions")
            except Exception as e:
                logger.error(f"❌ Erreur collecte post #{post_id}: {e}")

        logger.info("📊 Collecte métriques terminée")

    def _get_post_insights(self, post: dict) -> Optional[dict]:
        """
        Récupère les insights d'un post spécifique via Facebook Graph API.
        """
        if not self.fb_token or not self.fb_page_id:
            return None

        # Récupérer le post_id stocké (format Facebook: pageId_postId)
        platform = post.get("platform", "facebook")
        if platform == "facebook" and self.fb_page_id:
            # Tentative avec l'API
            url = f"{self.graph_base}/{self.fb_page_id}/feed"
            params = {
                "access_token": self.fb_token,
                "fields": "id,impressions,reach,likes.summary(true),comments.summary(true),shares",
                "limit": 5,
            }

            try:
                resp = requests.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    # On prend les metrics globales plutôt
                    return self._get_page_insights()
            except Exception as e:
                logger.warning(f"⚠️ Erreur insights FB: {e}")

        # Fallback: retourner les stats globales de la page
        return self._get_page_insights()

    def _get_page_insights(self) -> dict:
        """
        Récupère les insights généraux de la Page Facebook.
        """
        if not self.fb_token or not self.fb_page_id:
            return {}

        # Métriques disponibles sur 7 jours
        metrics = "page_impressions,page_impressions_unique,page_engaged_users,page_fan_adds"
        url = f"{self.graph_base}/{self.fb_page_id}/insights"
        params = {
            "access_token": self.fb_token,
            "metric": metrics,
            "period": "day",
            "since": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
            "until": datetime.now().strftime("%Y-%m-%d"),
        }

        try:
            resp = requests.get(url, params=params, timeout=15)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                result = {}
                for metric in data:
                    name = metric.get("name", "")
                    values = metric.get("values", [{}])
                    if values:
                        val = values[-1].get("value", 0)
                        if name == "page_impressions":
                            result["impressions"] = val
                        elif name == "page_impressions_unique":
                            result["reach"] = val
                        elif name == "page_engaged_users":
                            result["likes"] = val
                        elif name == "page_fan_adds":
                            result["saves"] = val
                return result
        except Exception as e:
            logger.debug(f"⚠️ Insights page: {e}")

        return {}

    # ─── Apprentissage automatique ─────────────────────────

    def learn(self) -> dict:
        """
        Analyse les métriques collectées et met à jour la base d'apprentissage.
        Identifie les patterns gagnants.
        """
        summary = db.get_summary_metrics(days=7)
        total_posts = summary.get("total_posts", 0)

        if total_posts < 3:
            logger.info(f"📚 Pas assez de données pour apprendre ({total_posts} posts)")
            return {}

        learnings = {}

        # 1. Analyse des types de contenu
        content_type_perf = self._analyze_content_types()
        for ct, score in content_type_perf.items():
            db.update_learning("content_type", ct, score)
        learnings["content_type"] = content_type_perf

        # 2. Analyse des angles marketing
        angle_perf = self._analyze_angles()
        for angle, score in angle_perf.items():
            db.update_learning("angle", angle, score)
        learnings["angle"] = angle_perf

        # 3. Analyse des créneaux horaires
        time_perf = self._analyze_time_slots()
        for slot, score in time_perf.items():
            db.update_learning("time_slot", slot, score)
        learnings["time_slot"] = time_perf

        # 4. Analyse des produits
        product_perf = self._analyze_products()
        for pid, score in product_perf.items():
            db.update_learning("product", pid, score)
        learnings["product"] = product_perf

        # 5. Analyse des plateformes
        platform_perf = self._analyze_platforms()
        for plat, score in platform_perf.items():
            db.update_learning("platform", plat, score)
        learnings["platform"] = platform_perf

        logger.info(f"📚 Apprentissage terminé — {sum(len(v) for v in learnings.values())} règles mises à jour")
        return learnings

    def _analyze_content_types(self) -> dict:
        """Analyse la performance des types de contenu."""
        # Pour l'instant, on utilise les métriques globales
        # Plus tard, on pourra faire du post-hoc par type
        summary = db.get_summary_metrics(days=14)
        results = {}

        # Parcourir les posts récents et les classer par type
        posts = db.get_recent_posts(limit=100)
        type_stats = {}
        for p in posts:
            ct = p.get("content_type", "photo")
            if ct not in type_stats:
                type_stats[ct] = {"count": 0, "total_likes": 0}
            type_stats[ct]["count"] += 1

            metrics_list = db.get_post_metrics(p["id"])
            for m in metrics_list:
                type_stats[ct]["total_likes"] += m.get("likes", 0)

        for ct, stats in type_stats.items():
            if stats["count"] > 0:
                results[ct] = stats["total_likes"] / stats["count"]

        return results

    def _analyze_angles(self) -> dict:
        """Analyse la performance des angles marketing."""
        posts = db.get_recent_posts(limit=100)
        angle_stats = {}
        for p in posts:
            # Récupérer l'angle depuis le calendrier ou les données du post
            angle = p.get("performance_data", "")
            if angle:
                try:
                    perf = json.loads(angle)
                    a = perf.get("angle", "desir")
                except:
                    a = "desir"
            else:
                a = "desir"

            if a not in angle_stats:
                angle_stats[a] = {"count": 0, "total_engagement": 0}
            angle_stats[a]["count"] += 1

            metrics_list = db.get_post_metrics(p["id"])
            for m in metrics_list:
                angle_stats[a]["total_engagement"] += (
                    m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0)
                )

        results = {}
        for a, stats in angle_stats.items():
            if stats["count"] > 0:
                results[a] = stats["total_engagement"] / stats["count"]

        return results

    def _analyze_time_slots(self) -> dict:
        """Analyse la performance des créneaux horaires."""
        posts = db.get_recent_posts(limit=100)
        slot_stats = {}
        for p in posts:
            scheduled = p.get("scheduled_at", "")
            if not scheduled or len(scheduled) < 16:
                continue
            try:
                hour = scheduled[11:16]  # HH:MM
                # Regrouper par créneau
                h = int(scheduled[11:13])
                if h < 13:
                    slot = "12:30"
                elif h < 15:
                    slot = "14:00"
                elif h < 20:
                    slot = "18:30"
                else:
                    slot = "21:00"

                if slot not in slot_stats:
                    slot_stats[slot] = {"count": 0, "total_engagement": 0}
                slot_stats[slot]["count"] += 1

                metrics_list = db.get_post_metrics(p["id"])
                for m in metrics_list:
                    slot_stats[slot]["total_engagement"] += (
                        m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0)
                    )
            except:
                continue

        results = {}
        for slot, stats in slot_stats.items():
            if stats["count"] > 0:
                results[slot] = stats["total_engagement"] / stats["count"]

        return results

    def _analyze_products(self) -> dict:
        """Analyse la performance des produits."""
        posts = db.get_recent_posts(limit=100)
        product_stats = {}
        for p in posts:
            pid = p.get("product_id", "")
            if not pid:
                continue
            if pid not in product_stats:
                product_stats[pid] = {"count": 0, "total_likes": 0}
            product_stats[pid]["count"] += 1

            metrics_list = db.get_post_metrics(p["id"])
            for m in metrics_list:
                product_stats[pid]["total_likes"] += m.get("likes", 0)

        results = {}
        for pid, stats in product_stats.items():
            if stats["count"] > 0:
                results[pid] = stats["total_likes"] / stats["count"]

        return results

    def _analyze_platforms(self) -> dict:
        """Analyse la performance des plateformes."""
        posts = db.get_recent_posts(limit=100)
        plat_stats = {}
        for p in posts:
            plat = p.get("platform", "facebook")
            if plat not in plat_stats:
                plat_stats[plat] = {"count": 0, "total_engagement": 0}
            plat_stats[plat]["count"] += 1

            metrics_list = db.get_post_metrics(p["id"])
            for m in metrics_list:
                plat_stats[plat]["total_engagement"] += (
                    m.get("likes", 0) + m.get("comments", 0) + m.get("shares", 0)
                )

        results = {}
        for plat, stats in plat_stats.items():
            if stats["count"] > 0:
                results[plat] = stats["total_engagement"] / stats["count"]

        return results

    # ─── Rapport hebdomadaire ──────────────────────────────

    def generate_report(self) -> str:
        """Génère un rapport de performance lisible."""
        summary = db.get_summary_metrics(days=7)
        learnings = db.get_learnings()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        report = f"""
┌─────────────────────────────────────┐
│   📊 RAPPORT HEBDOMADAIRE KTHSHOP   │
│   {today}                             │
└─────────────────────────────────────┘

📈 PERFORMANCE GLOBALE (7 jours)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Posts publiés      : {summary.get('total_posts', 0)}
• Impressions moy.   : {summary.get('avg_impressions', 0):.0f}
• Clics moyens       : {summary.get('avg_clicks', 0):.0f}
• Likes moyens       : {summary.get('avg_likes', 0):.0f}
• Commentaires moy.  : {summary.get('avg_comments', 0):.0f}
• Partages moyens    : {summary.get('avg_shares', 0):.0f}
"""

        if learnings:
            report += """
🏆 APPRENTISSAGES DE LA SEMAINE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            for category, items in learnings.items():
                report += f"\n  [{category}]\n"
                for item in items[:3]:  # Top 3
                    report += f"  • {item['key']}: {item['value']:.3f} (n={item['sample_size']})\n"

        return report