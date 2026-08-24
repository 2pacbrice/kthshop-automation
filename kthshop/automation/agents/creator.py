"""
KTHSHOP — Agent Créateur
Génère les visuels (Higgsfield) et les textes (légendes, CTA).
Parallélise la création pour être plus rapide.
"""

import logging
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from ..core.config import config
from ..core.database import db

logger = logging.getLogger("kthshop.creator")


class Creator:
    """
    Agent Créateur — le pôle créatif.
    - Génère des images produit via Higgsfield
    - Rédige les légendes avec templates + CTA
    - Adapte le ton selon l'angle marketing
    """

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="creator")
        self.temp_dir = tempfile.mkdtemp(prefix="kthshop_")

    def create(self, decision: dict) -> Optional[dict]:
        """
        Crée le contenu complet pour une décision de publication.
        Parallélise la génération image + rédaction texte.
        """
        product_name = decision.get("product_name", "Nouveauté KTHSHOP")
        content_type = decision.get("content_type", "photo")
        angle = decision.get("angle", "desir")
        platform = decision.get("platform", "facebook")

        logger.info(f"🎨 Création contenu : {content_type} — {product_name} (angle: {angle})")

        # Lancer image + texte en parallèle
        results = {}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(self._generate_image, decision): "image",
                pool.submit(self._generate_caption, decision): "caption",
            }
            for fut in as_completed(futures):
                key = futures[fut]
                try:
                    results[key] = fut.result(timeout=120)
                except Exception as e:
                    logger.error(f"❌ Erreur génération {key}: {e}")
                    results[key] = None

        image_url = results.get("image")
        caption = results.get("caption", self._fallback_caption(product_name))

        if not image_url:
            logger.warning(f"⚠️ Pas d'image générée pour {product_name}")

        # Enregistrer dans la base
        post_id = db.add_post(
            scheduled_at=datetime.now(timezone.utc).isoformat(),
            status="ready_to_publish",
            platform=platform,
            content_type=content_type,
            product_id=decision.get("product_id", ""),
            product_name=product_name,
            caption=caption,
            image_url=image_url,
        )

        return {
            "post_id": post_id,
            "product_name": product_name,
            "content_type": content_type,
            "platform": platform,
            "image_url": image_url,
            "caption": caption,
            "angle": angle,
            "decision": decision,
        }

    # ─── Génération d'images ────────────────────────────────

    def _generate_image(self, decision: dict) -> Optional[str]:
        """
        Génère l'image du produit via Higgsfield.
        Si Higgsfield n'est pas disponible, utilise une image existante.
        """
        product_name = decision.get("product_name", "")
        product_id = decision.get("product_id", "")
        content_type = decision.get("content_type", "photo")
        angle = decision.get("angle", "desir")

        # 1. Essayer avec Higgsfield si la clé est configurée
        if config.higgsfield.api_key:
            return self._generate_with_higgsfield(product_name, angle, content_type)

        # 2. Chercher une image existante du produit
        if product_id:
            products = db.get_products(limit=100)
            for p in products:
                if str(p.get("id")) == product_id and p.get("image_url"):
                    logger.info(f"📸 Utilisation image existante pour {product_name}")
                    return p["image_url"]

        # 3. Fallback : aucune image disponible
        logger.warning(f"⚠️ Aucune image trouvée pour {product_name}")
        return None

    def _generate_with_higgsfield(self, product_name: str, angle: str, content_type: str) -> Optional[str]:
        """Génère une image avec Higgsfield via la CLI."""
        try:
            # Construction du prompt selon l'angle
            prompts = {
                "urgence": f"Chaussure femme élégante {product_name}, promotion urgente -44%, style luxe africain, fond bleu nuit et or, étiquette promo visible, photoréaliste, 1:1",
                "nouveaute": f"Nouvelle chaussure femme {product_name}, élégance africaine moderne, fond blanc minimaliste, éclairage studio professionnel, photoréaliste, 1:1",
                "preuve_sociale": f"Femme africaine portant {product_name}, style urbain Douala, confiance et élégance, lumière naturelle, photoréaliste, 1:1",
                "storytelling": f"Chaussure femme {product_name}, Paris-Douala voyage, style luxe, fond dégradé bleu nuit, photoréaliste, 1:1",
                "desir": f"Chaussure femme de luxe {product_name}, détails raffinés, focus produit, fond bleu nuit et doré, photoréaliste, 1:1",
                "conseil": f"Chaussure femme {product_name} avec accessoires assortis, style conseil mode, fond neutre élégant, photoréaliste, 1:1",
                "concours": f"Cadeau boîte cadeau luxueuse avec chaussure femme {product_name}, ruban doré, confettis, fond bleu nuit, photoréaliste, 1:1",
            }

            prompt = prompts.get(angle, prompts["desir"])

            # Appel Higgsfield via la CLI (si disponible)
            result = subprocess.run(
                ["higgsfield-generate", "--prompt", prompt, "--output", self.temp_dir],
                capture_output=True, text=True, timeout=120
            )

            if result.returncode == 0:
                # Extraire l'URL ou le chemin de l'image du résultat
                output = result.stdout.strip()
                logger.info(f"🎨 Image générée Higgsfield pour {product_name}")
                return output
            else:
                logger.warning(f"⚠️ Higgsfield échec: {result.stderr[:200]}")
                return None

        except Exception as e:
            logger.error(f"❌ Erreur Higgsfield: {e}")
            return None

    # ─── Génération de légendes ─────────────────────────────

    def _generate_caption(self, decision: dict) -> str:
        """Génère la légende complète selon l'angle marketing."""
        product_name = decision.get("product_name", "Nouveauté")
        angle = decision.get("angle", "desir")
        content_type = decision.get("content_type", "photo")
        template = decision.get("caption_template", "")

        # Si un template est fourni, l'utiliser
        if template:
            return self._render_template(template, product_name)

        # Templates par angle
        caption_templates = {
            "urgence": (
                f"⚠️ DERNIÈRE CHANCE ⚠️\n\n"
                f"La {product_name} est presque partie !\n"
                f"{'🔥 PROMO -44% pour nos 8 ANS !' if config.kthshop.promo_8ans_active else ''}\n\n"
                f"👉 Prix : {config.kthshop.default_price} {config.kthshop.currency}\n"
                f"📦 Livraison partout au Cameroun\n"
                f"💳 Paiement Mobile Money (BKApay)\n\n"
                f"Ne laisse pas passer cette occasion ✨\n"
                f"Commande direct : {config.kthshop.whatsapp_business}?text=Bonjour%20KTHSHOP%2C%20je%20veux%20{product_name.replace(' ', '%20')}\n\n"
                f"#KTHSHOP #ModeCameroun #ChaussuresFemme #Douala #Promo"
            ),
            "nouveaute": (
                f"🆕 NOUVEAUTÉ KTHSHOP 🆕\n\n"
                f"Elle est arrivée : {product_name} ✨\n\n"
                f"Le coup de cœur de la semaine 💙\n\n"
                f"👉 {config.kthshop.default_price} {config.kthshop.currency}\n"
                f"📦 Livraison Cameroun\n"
                f"💳 BKApay Mobile Money\n\n"
                f"Toi aussi, adopte-la !\n"
                f"👉 {config.kthshop.whatsapp_business}?text=Bonjour%20KTHSHOP%2C%20je%20veux%20{product_name.replace(' ', '%20')}\n\n"
                f"#Nouveauté #KTHSHOP #ModeFemme #Cameroun #Chaussures"
            ),
            "preuve_sociale": (
                f"⭐ ELLES ONT ADORÉ ⭐\n\n"
                f"« {product_name} — encore plus belle en vrai ! »\n\n"
                f"Nos clientes sont ravies, et toi ?\n\n"
                f"👉 {config.kthshop.default_price} {config.kthshop.currency}\n"
                f"📦 Livraison rapide partout au Cameroun\n"
                f"💳 Paiement Mobile Money\n\n"
                f"Rejoins la famille KTHSHOP 💫\n"
                f"{config.kthshop.whatsapp_business}?text=Bonjour%20KTHSHOP%2C%20je%20veux%20{product_name.replace(' ', '%20')}\n\n"
                f"#AvisClient #KTHSHOP #ModeCameroun #Satisfaction"
            ),
            "storytelling": (
                f"🌍 De Paris à Douala — une histoire de style\n\n"
                f"{product_name} — l'élégance qui traverse les frontières ✈️\n\n"
                f"Chez KTHSHOP, on sélectionne pour toi le meilleur de la mode…\n"
                f"pour que tu sois impeccable en toute occasion 💫\n\n"
                f"👉 {config.kthshop.default_price} {config.kthshop.currency}\n"
                f"📦 Livraison Cameroun\n\n"
                f"{config.kthshop.whatsapp_business}?text=Bonjour%20KTHSHOP%2C%20je%20veux%20{product_name.replace(' ', '%20')}\n\n"
                f"#KTHSHOP #Storytelling #ModeFemme #Élégance #Douala"
            ),
            "desir": (
                f"{product_name} ✨\n\n"
                f"Parce que tu mérites ce qu'il y a de mieux… 💙\n\n"
                f"👉 {config.kthshop.default_price} {config.kthshop.currency}\n"
                f"📦 Livraison partout au Cameroun\n"
                f"💳 BKApay Mobile Money\n\n"
                f"Commande vite :\n"
                f"{config.kthshop.whatsapp_business}?text=Bonjour%20KTHSHOP%2C%20je%20veux%20{product_name.replace(' ', '%20')}\n\n"
                f"#KTHSHOP #Luxueuse #ChaussuresFemme #Cameroun #Style"
            ),
            "conseil": (
                f"💡 ASTUCE STYLE 💡\n\n"
                f"Comment porter {product_name} ?\n\n"
                f"➡️ Avec un jean taille haute pour un look décontracté-chic\n"
                f"➡️ Ou une robe midi pour le soir\n\n"
                f"La polyvalence qu'il te faut dans ton dressing !\n\n"
                f"👉 {config.kthshop.default_price} {config.kthshop.currency}\n"
                f"{config.kthshop.whatsapp_business}?text=Bonjour%20KTHSHOP%2C%20je%20veux%20{product_name.replace(' ', '%20')}\n\n"
                f"#ConseilMode #KTHSHOP #StyleFemme #Cameroun"
            ),
            "concours": (
                f"🎁 CONCOURS KTHSHOP 🎁\n\n"
                f"Tente de gagner {product_name} !\n\n"
                f"Pour participer c'est simple :\n"
                f"1️⃣ Suis @kthshoponline\n"
                f"2️⃣ Tag 2 copines en commentaire\n"
                f"3️⃣ Partage cette publication en story\n\n"
                f"Le tirage aura lieu bientôt ! 🍀\n\n"
                f"#Concours #KTHSHOP #ModeCameroun #Gagner"
            ),
        }

        caption = caption_templates.get(angle, caption_templates["desir"])

        # Ajouter la promo 8 ans en filigrane si active
        if config.kthshop.promo_8ans_active and angle != "concours":
            promo_line = f"\n🔥 PROMO -{config.kthshop.promo_8ans}% valable jusqu'au {config.kthshop.promo_8ans_until} 🔥"
            if promo_line not in caption:
                caption = caption.replace("\n\n#", f"{promo_line}\n\n#")

        return caption

    def _render_template(self, template: str, product_name: str) -> str:
        """Remplit un template de légende avec les variables."""
        replacements = {
            "{product_name}": product_name,
            "{price}": str(config.kthshop.default_price),
            "{currency}": config.kthshop.currency,
            "{whatsapp}": config.kthshop.whatsapp_business,
            "{shop_url}": config.kthshop.shop_url,
            "{promo}": f"-{config.kthshop.promo_8ans}%" if config.kthshop.promo_8ans_active else "",
            "{promo_text}": f"PROMO -{config.kthshop.promo_8ans}% pour nos 8 ANS !" if config.kthshop.promo_8ans_active else "",
        }
        result = template
        for key, val in replacements.items():
            result = result.replace(key, val)
        return result

    def _fallback_caption(self, product_name: str) -> str:
        """Légende de secours simple."""
        return (
            f"{product_name} ✨\n\n"
            f"Disponible chez KTHSHOP\n\n"
            f"👉 {config.kthshop.default_price} {config.kthshop.currency}\n"
            f"📦 Livraison Cameroun\n"
            f"💳 BKApay\n\n"
            f"{config.kthshop.whatsapp_business}\n\n"
            f"#KTHSHOP #ModeCameroun"
        )