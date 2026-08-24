"""
KTHSHOP — Agent Publieur
Publie le contenu sur tous les canaux (Facebook, Instagram, WhatsApp).
Gère les limites de taux, les erreurs, et les retentatives.
"""

import logging
import json
import requests
import time
from datetime import datetime, timezone
from typing import Optional

from ..core.config import config
from ..core.database import db

logger = logging.getLogger("kthshop.publisher")


class Publisher:
    """
    Agent Publieur — la diffusion multi-canal.
    - Publie sur Facebook (Page + Feed)
    - Publie sur Instagram (Feed + Reels)
    - Envoie notifications WhatsApp
    - Gère les rate limits avec backoff exponentiel
    """

    def __init__(self):
        self.fb_token = config.facebook.page_token
        self.fb_page_id = config.facebook.page_id
        self.ig_user_id = config.facebook.ig_user_id
        self.wa_token = config.whatsapp.token
        self.wa_phone_id = config.whatsapp.phone_number_id
        self.graph_base = f"https://graph.facebook.com/{config.facebook.graph_api_version}"

    def publish(self, content: dict) -> bool:
        """
        Publie le contenu sur le(s) canal(aux) spécifié(s).
        Retourne True si au moins un canal a réussi.
        """
        platform = content.get("platform", "facebook")
        post_id = content.get("post_id")

        logger.info(f"📤 Publication sur {platform} : {content.get('product_name')}")

        if config.dry_run:
            logger.info(f"🔷 DRY RUN - Publication simulée sur {platform}")
            if post_id:
                db.update_post(post_id, status="published",
                               published_at=datetime.now(timezone.utc).isoformat())
            return True

        success = False

        try:
            if platform in ("facebook", "both"):
                if self._publish_facebook(content):
                    success = True

            if platform in ("instagram", "both"):
                if self._publish_instagram(content):
                    success = True

            # WhatsApp notification
            if content.get("notify_wa", True):
                self._notify_whatsapp(content)

            if success and post_id:
                db.update_post(post_id, status="published",
                               published_at=datetime.now(timezone.utc).isoformat())
                logger.info(f"✅ Publié avec succès : {content.get('product_name')}")

        except Exception as e:
            logger.error(f"❌ Erreur publication: {e}")
            if post_id:
                db.update_post(post_id, status="failed", error=str(e))

        return success

    # ─── Facebook ───────────────────────────────────────────

    def _publish_facebook(self, content: dict) -> bool:
        """Publie sur Facebook Page."""
        if not self.fb_token or not self.fb_page_id:
            logger.warning("⚠️ Facebook non configuré (token ou page_id manquant)")
            return False

        caption = content.get("caption", "")
        image_url = content.get("image_url")
        content_type = content.get("content_type", "photo")

        try:
            if content_type == "reel" and image_url:
                # Vidéo / Reel
                return self._post_facebook_video(caption, image_url)
            else:
                # Photo standard
                return self._post_facebook_photo(caption, image_url)

        except Exception as e:
            logger.error(f"❌ Erreur Facebook: {e}")
            return False

    def _post_facebook_photo(self, caption: str, image_url: Optional[str]) -> bool:
        """Poste une photo sur Facebook."""
        url = f"{self.graph_base}/{self.fb_page_id}/photos"

        data = {
            "access_token": self.fb_token,
            "message": caption,
        }

        if image_url:
            data["url"] = image_url

        with self._rate_limited_session() as session:
            resp = session.post(url, data=data, timeout=30)

        if resp.status_code == 200:
            result = resp.json()
            post_id = result.get("id", "?")
            logger.info(f"📸 Photo Facebook publiée (post_id: {post_id})")
            return True
        else:
            logger.error(f"❌ Erreur FB photo: {resp.status_code} {resp.text[:200]}")
            return False

    def _post_facebook_video(self, caption: str, video_url: Optional[str]) -> bool:
        """Poste une vidéo/reel sur Facebook."""
        if not video_url:
            logger.warning("⚠️ Pas d'URL vidéo pour le reel")
            return False

        url = f"{self.graph_base}/{self.fb_page_id}/videos"

        data = {
            "access_token": self.fb_token,
            "description": caption,
            "file_url": video_url,
        }

        with self._rate_limited_session() as session:
            resp = session.post(url, data=data, timeout=120)

        if resp.status_code == 200:
            result = resp.json()
            video_id = result.get("id", "?")
            logger.info(f"🎬 Video Facebook publiée (video_id: {video_id})")
            return True
        else:
            logger.error(f"❌ Erreur FB video: {resp.status_code} {resp.text[:200]}")
            return False

    # ─── Instagram ──────────────────────────────────────────

    def _publish_instagram(self, content: dict) -> bool:
        """Publie sur Instagram (compte connecté à la Page Facebook)."""
        if not self.fb_token or not self.ig_user_id:
            logger.warning("⚠️ Instagram non configuré")
            return False

        caption = content.get("caption", "")
        image_url = content.get("image_url")
        content_type = content.get("content_type", "photo")

        try:
            if content_type == "reel":
                return self._post_instagram_reel(caption, image_url)
            else:
                return self._post_instagram_photo(caption, image_url)

        except Exception as e:
            logger.error(f"❌ Erreur Instagram: {e}")
            return False

    def _post_instagram_photo(self, caption: str, image_url: Optional[str]) -> bool:
        """Poste une photo sur Instagram (en 2 étapes : création + publication)."""
        if not image_url:
            logger.warning("⚠️ Pas d'URL image pour Instagram")
            return False

        # Étape 1 : Créer le media container
        create_url = f"{self.graph_base}/{self.ig_user_id}/media"
        create_data = {
            "access_token": self.fb_token,
            "image_url": image_url,
            "caption": caption,
        }

        with self._rate_limited_session() as session:
            resp = session.post(create_url, data=create_data, timeout=30)

        if resp.status_code != 200:
            logger.error(f"❌ Erreur création container IG: {resp.status_code} {resp.text[:200]}")
            return False

        container_id = resp.json().get("id")
        if not container_id:
            logger.error("❌ Pas d'ID container IG dans la réponse")
            return False

        # Étape 2 : Publier le container
        time.sleep(2)  # Pause obligatoire pour la génération
        publish_url = f"{self.graph_base}/{self.ig_user_id}/media_publish"
        publish_data = {
            "access_token": self.fb_token,
            "creation_id": container_id,
        }

        with self._rate_limited_session() as session:
            resp = session.post(publish_url, data=publish_data, timeout=30)

        if resp.status_code == 200:
            media_id = resp.json().get("id", "?")
            logger.info(f"📸 Instagram publié (media_id: {media_id})")
            return True
        else:
            logger.error(f"❌ Erreur publication IG: {resp.status_code} {resp.text[:200]}")
            return False

    def _post_instagram_reel(self, caption: str, video_url: Optional[str]) -> bool:
        """Poste un reel sur Instagram."""
        if not video_url:
            logger.warning("⚠️ Pas d'URL vidéo pour le reel IG")
            return False

        create_url = f"{self.graph_base}/{self.ig_user_id}/media"
        create_data = {
            "access_token": self.fb_token,
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
        }

        with self._rate_limited_session() as session:
            resp = session.post(create_url, data=create_data, timeout=60)

        if resp.status_code != 200:
            logger.error(f"❌ Erreur création reel IG: {resp.status_code} {resp.text[:200]}")
            return False

        container_id = resp.json().get("id")
        if not container_id:
            return False

        # Publication
        time.sleep(5)
        publish_url = f"{self.graph_base}/{self.ig_user_id}/media_publish"
        publish_data = {
            "access_token": self.fb_token,
            "creation_id": container_id,
        }

        with self._rate_limited_session() as session:
            resp = session.post(publish_url, data=publish_data, timeout=60)

        if resp.status_code == 200:
            media_id = resp.json().get("id", "?")
            logger.info(f"🎬 Reel Instagram publié (media_id: {media_id})")
            return True
        else:
            logger.error(f"❌ Erreur publication reel IG: {resp.status_code} {resp.text[:200]}")
            return False

    # ─── WhatsApp ───────────────────────────────────────────

    def _notify_whatsapp(self, content: dict):
        """Envoie une notification WhatsApp (promo, nouveau produit)."""
        if not self.wa_token or not self.wa_phone_id:
            logger.debug("ℹ️ WhatsApp non configuré pour notification")
            return

        product_name = content.get("product_name", "Nouveauté")
        angle = content.get("angle", "desir")

        # Ne pas spammer — seulement pour les angles importants
        if angle not in ("urgence", "nouveaute", "concours"):
            return

        message = (
            f"🛍️ *KTHSHOP*\n\n"
            f"{product_name} est disponible !\n"
            f"👉 {config.kthshop.default_price} {config.kthshop.currency}\n"
            f"📦 Livraison Cameroun\n\n"
            f"Commande : {config.kthshop.whatsapp_business}"
        )

        # TODO: À terme, envoyer aux abonnés WhatsApp
        # Pour l'instant, juste logguer
        logger.info(f"📱 Notification WhatsApp prête pour {product_name}")
        logger.debug(f"   Message: {message[:100]}...")

    def send_whatsapp_message(self, to: str, message: str) -> bool:
        """Envoie un message WhatsApp à un numéro spécifique."""
        if not self.wa_token or not self.wa_phone_id:
            logger.warning("⚠️ WhatsApp non configuré")
            return False

        url = f"https://graph.facebook.com/{config.facebook.graph_api_version}/{self.wa_phone_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.wa_token}",
            "Content-Type": "application/json",
        }
        data = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"preview_url": True, "body": message},
        }

        try:
            resp = requests.post(url, headers=headers, json=data, timeout=15)
            if resp.status_code == 200:
                logger.info(f"✅ WhatsApp envoyé à {to}")
                return True
            else:
                logger.error(f"❌ Erreur WhatsApp: {resp.status_code} {resp.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"❌ Erreur envoi WhatsApp: {e}")
            return False

    # ─── Gestion rate limit ─────────────────────────────────

    def _rate_limited_session(self) -> requests.Session:
        """Crée une session avec retry et backoff."""
        session = requests.Session()

        class RateLimitAdapter(requests.adapters.HTTPAdapter):
            def send(self, request, **kwargs):
                max_retries = 3
                for attempt in range(max_retries):
                    response = super().send(request, **kwargs)
                    if response.status_code == 429:  # Rate limited
                        wait = min(2 ** attempt * 5, 60)
                        logger.warning(f"⏳ Rate limit (429), attente {wait}s (tentative {attempt + 1}/{max_retries})")
                        time.sleep(wait)
                        continue
                    return response
                return response

        session.mount("https://", RateLimitAdapter())
        return session

    # ─── Publication du calendrier éditorial ───────────────

    def publish_all_pending(self) -> int:
        """Publie tous les posts en attente. Retourne le nombre de publications."""
        pending = db.get_pending_posts()
        success_count = 0

        for post in pending:
            content = {
                "post_id": post["id"],
                "product_name": post.get("product_name", "KTHSHOP"),
                "caption": post.get("caption", ""),
                "image_url": post.get("image_url"),
                "content_type": post.get("content_type", "photo"),
                "platform": post.get("platform", "facebook"),
                "notify_wa": False,
            }

            if self.publish(content):
                success_count += 1

        return success_count