"""
KTHSHOP — Configuration centralisée
Toutes les clés API et réglages depuis les variables d'environnement.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ShopifyConfig:
    access_token: str = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    store_url: str = os.getenv("SHOPIFY_STORE_URL", "royal-heel-boutique-754wk.myshopify.com")
    api_version: str = "2024-01"


@dataclass
class FacebookConfig:
    page_id: str = os.getenv("FB_PAGE_ID", "")
    page_token: str = os.getenv("FB_PAGE_TOKEN", "")
    ig_user_id: str = os.getenv("IG_USER_ID", "")
    graph_api_version: str = "v19.0"


@dataclass
class HiggsfieldConfig:
    api_key: str = os.getenv("HIGGSFIELD_API_KEY", "")
    model_default: str = "gpt_image_2"


@dataclass
class WhatsAppConfig:
    phone_number_id: str = os.getenv("WA_PHONE_NUMBER_ID", "")
    token: str = os.getenv("WA_TOKEN", "")
    business_account_id: str = os.getenv("WA_BUSINESS_ACCOUNT_ID", "")
    partner_phone: str = os.getenv("KTHSHOP_PARTNER_PHONE", "237655505539")


@dataclass
class KTHSHOPConfig:
    shop_name: str = "KTHSHOP"
    shop_url: str = "https://kthshop.com"
    whatsapp_business: str = "https://wa.me/237655505539"
    currency: str = "FCFA"
    default_price: int = 45000
    promo_8ans_active: bool = True
    promo_8ans_discount: int = 44
    promo_8ans_until: str = "2026-08-15"
    timezone: str = "Africa/Douala"

    content_pillars: dict = field(default_factory=lambda: {
        "desir_produit": {"label": "Désir produit", "weight": 0.40},
        "style_conseils": {"label": "Style & conseils", "weight": 0.20},
        "confiance_preuve": {"label": "Confiance & preuve", "weight": 0.20},
        "communaute": {"label": "Communauté & culture", "weight": 0.15},
        "marque_histoire": {"label": "Marque & histoire", "weight": 0.05},
    })

    best_time_slots: list = field(default_factory=lambda: [
        "12:30", "14:00", "18:30", "21:00"
    ])

    content_types: list = field(default_factory=lambda: [
        "reel", "carrousel", "photo", "story"
    ])

    angles: list = field(default_factory=lambda: [
        "urgence", "nouveaute", "preuve_sociale",
        "storytelling", "desir", "conseil", "concours"
    ])


@dataclass
class AppConfig:
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    dry_run: bool = os.getenv("DRY_RUN", "false").lower() == "true"
    database_path: str = os.getenv("DATABASE_PATH", "data/kthshop.db")
    port: int = int(os.getenv("PORT", "8080"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    shopify: ShopifyConfig = field(default_factory=ShopifyConfig)
    facebook: FacebookConfig = field(default_factory=FacebookConfig)
    higgsfield: HiggsfieldConfig = field(default_factory=HiggsfieldConfig)
    whatsapp: WhatsAppConfig = field(default_factory=WhatsAppConfig)
    kthshop: KTHSHOPConfig = field(default_factory=KTHSHOPConfig)


# Singleton
config = AppConfig()