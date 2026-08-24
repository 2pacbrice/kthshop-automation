# Utiliser une image Python officielle
FROM python:3.12-slim

# Éviter les fichiers .pyc
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Répertoire de travail
WORKDIR /app

# Installer les dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copier et installer les dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier le code
COPY . .

# Créer le répertoire de données
RUN mkdir -p /app/data

# Port
EXPOSE 8080

# Santé
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/dashboard/health')"

# Lancement
CMD ["uvicorn", "kthshop.automation.main:app", "--host", "0.0.0.0", "--port", "8080"]