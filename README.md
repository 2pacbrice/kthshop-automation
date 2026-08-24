# KTHSHOP Automation

KTHSHOP est une boutique Shopify de chaussures femme basée au Cameroun.
Ce dossier contient l'automatisation multi-agents pour le marketing, les publications,
et la relation client.

## Architecture

```
automation/
├── main.py              → Point d'entrée FastAPI
├── core/
│   ├── config.py        → Configuration centralisée
│   ├── database.py      → SQLite persistante
│   └── orchestrator.py  → Coordonne les 4 agents
├── agents/
│   ├── strategist.py    → Agent Stratège (quoi/quand/comment publier)
│   ├── creator.py       → Agent Créateur (visuels + textes)
│   ├── publisher.py     → Agent Publieur (Facebook/Instagram/WhatsApp)
│   └── analyst.py       → Agent Analyste (métriques + apprentissage)
├── api/
│   ├── webhooks.py      → BKApay, Meta, Shopify
│   └── dashboard.py     → Tableau de bord API
├── calendrier.yaml      → Calendrier éditorial structuré
├── .env.template        → Variables d'environnement
├── requirements.txt
├── Dockerfile
└── railway.toml
```

## Déploiement Railway

1. Connecter ce dossier à Railway
2. Définir les variables d'environnement (cf. .env.template)
3. Mettre `DRY_RUN=false` pour publication réelle
4. Railway build auto, healthcheck sur `/dashboard/health`

## Utilisation locale

```bash
cd kthshop/automation
cp .env.template .env   # et remplir les clés
pip install -r requirements.txt
python -m kthshop.automation.main
```

## Dashboard

Une fois lancé :
- `GET /` → Status général
- `GET /dashboard/stats` → Statistiques
- `GET /dashboard/posts` → Posts récents
- `GET /dashboard/calendar` → Calendrier
- `POST /dashboard/sync/products` → Sync Shopify
- `POST /dashboard/publish/now` → Publication immédiate

## Webhooks

- `POST /webhooks/bkapay` → Paiements BKApay
- `POST /webhooks/meta` → Notifications Meta
- `POST /webhooks/shopify` → Commandes Shopify