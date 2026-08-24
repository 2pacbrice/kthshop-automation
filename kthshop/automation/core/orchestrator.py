"""
KTHSHOP — Orchestrateur principal
Coordonne les 4 agents en parallèle, gère le planning et la résilience.
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from typing import Optional

from ..core.config import config
from ..core.database import db

logger = logging.getLogger("kthshop.orchestrator")


class Orchestrator:
    """
    Chef d'orchestre des 4 agents KTHSHOP.
    - Planifie et coordonne l'exécution
    - Parallélise les tâches indépendantes
    - Assure la résilience (timeout, retry, fallback)
    - Tient le journal de bord
    """

    def __init__(self):
        self.running = False
        self.executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="kthshop")
        self.agents = {}
        self._tasks = []

    def register_agent(self, name: str, agent_instance):
        """Enregistre un agent pour qu'il soit accessible."""
        self.agents[name] = agent_instance
        logger.info(f"✅ Agent « {name} » enregistré")

    # ─── Cycle principal ────────────────────────────────────

    async def tick(self):
        """
        Un cycle complet du système (appelé périodiquement).
        Exécute les agents en parallèle selon leur rôle.
        """
        logger.info("🔄 Tick orchestrateur — début du cycle")

        try:
            # Étape 1 : Le stratège analyse ce qu'il faut publier
            strategist = self.agents.get("strategist")
            if strategist:
                decisions = await asyncio.get_event_loop().run_in_executor(
                    self.executor, strategist.plan
                )
                logger.info(f"📋 Stratège : {len(decisions)} décisions de publication")
            else:
                decisions = []
                logger.warning("⚠️ Agent strategist non enregistré")

            # Étape 2 : Pour chaque décision, lancer créateur + préparation en parallèle
            if decisions:
                creator = self.agents.get("creator")
                publisher = self.agents.get("publisher")
                analyst = self.agents.get("analyst")

                creator_tasks = []
                for dec in decisions:
                    if creator:
                        t = asyncio.get_event_loop().run_in_executor(
                            self.executor, creator.create, dec
                        )
                        creator_tasks.append(t)

                if creator_tasks:
                    contents = await asyncio.gather(*creator_tasks, return_exceptions=True)
                    logger.info(f"🎨 Créateur : {len([c for c in contents if not isinstance(c, Exception)])}/{len(contents)} contenus générés")

                    # Étape 3 : Publication en parallèle
                    pub_tasks = []
                    for content in contents:
                        if isinstance(content, Exception):
                            logger.error(f"❌ Erreur création: {content}")
                            continue
                        if publisher and content:
                            t = asyncio.get_event_loop().run_in_executor(
                                self.executor, publisher.publish, content
                            )
                            pub_tasks.append(t)

                    if pub_tasks:
                        results = await asyncio.gather(*pub_tasks, return_exceptions=True)
                        success = len([r for r in results if not isinstance(r, Exception) and r])
                        logger.info(f"📤 Publieur : {success}/{len(results)} publications réussies")

                # Étape 4 : L'analyste tourne en parallèle
                if analyst:
                    await asyncio.get_event_loop().run_in_executor(
                        self.executor, analyst.collect_metrics
                    )

            # Étape 5 : Apprentissage et optimisation (période longue)
            analyst = self.agents.get("analyst")
            if analyst:
                await asyncio.get_event_loop().run_in_executor(
                    self.executor, analyst.learn
                )

        except Exception as e:
            logger.error(f"💥 Erreur orchestrateur: {e}", exc_info=True)

        logger.info("✅ Cycle orchestrateur terminé")

    # ─── Tâches planifiées ──────────────────────────────────

    def get_scheduler_tasks(self):
        """
        Retourne les tâches planifiées pour APScheduler.
        Appelé par main.py lors du démarrage.
        """
        return [
            {
                "id": "kthshop_hourly",
                "func": self._run_tick,
                "trigger": "interval",
                "hours": 1,
                "name": "Vérification publication (chaque heure)",
            },
            {
                "id": "kthshop_metrics",
                "func": self._collect_metrics,
                "trigger": "interval",
                "hours": 6,
                "name": "Collecte métriques (6h)",
            },
            {
                "id": "kthshop_daily_analysis",
                "func": self._daily_analysis,
                "trigger": "cron",
                "hour": 23,
                "minute": 30,
                "name": "Analyse quotidienne (23h30)",
            },
            {
                "id": "kthshop_weekly_report",
                "func": self._weekly_report,
                "trigger": "cron",
                "day_of_week": "sun",
                "hour": 22,
                "minute": 0,
                "name": "Rapport hebdomadaire (dimanche 22h)",
            },
            {
                "id": "kthshop_product_sync",
                "func": self._sync_products,
                "trigger": "interval",
                "hours": 12,
                "name": "Sync produits Shopify (12h)",
            },
        ]

    def _run_tick(self):
        """Wrapper synchrone pour le scheduler."""
        asyncio.run(self.tick())

    def _collect_metrics(self):
        """Collecte des métriques des posts publiés."""
        analyst = self.agents.get("analyst")
        if analyst:
            try:
                analyst.collect_metrics()
                logger.info("📊 Métriques collectées")
            except Exception as e:
                logger.error(f"❌ Erreur collecte métriques: {e}")

    def _daily_analysis(self):
        """Analyse quotidienne et ajustement stratégique."""
        analyst = self.agents.get("analyst")
        strategist = self.agents.get("strategist")
        if analyst and strategist:
            try:
                learnings = analyst.learn()
                if learnings:
                    strategist.adjust_strategy(learnings)
                logger.info("📈 Analyse quotidienne terminée")
            except Exception as e:
                logger.error(f"❌ Erreur analyse quotidienne: {e}")

    def _weekly_report(self):
        """Génération du rapport hebdomadaire."""
        analyst = self.agents.get("analyst")
        if analyst:
            try:
                report = analyst.generate_report()
                logger.info(f"📬 Rapport hebdo :\n{report}")
                # TODO: envoyer le rapport par WhatsApp
            except Exception as e:
                logger.error(f"❌ Erreur rapport hebdo: {e}")

    def _sync_products(self):
        """Syncronisation des produits Shopify."""
        strategist = self.agents.get("strategist")
        if strategist:
            try:
                count = strategist.sync_products()
                logger.info(f"📦 {count} produits synchronisés depuis Shopify")
            except Exception as e:
                logger.error(f"❌ Erreur sync produits: {e}")

    # ─── Démarrage / Arrêt ──────────────────────────────────

    async def start(self):
        self.running = True
        logger.info("🚀 Orchestrateur KTHSHOP démarré")
        # Premier tick immédiat
        await self.tick()

    def stop(self):
        self.running = False
        self.executor.shutdown(wait=False)
        logger.info("🛑 Orchestrateur arrêté")


# Singleton
orchestrator = Orchestrator()