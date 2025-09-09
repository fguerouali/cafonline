# Image Playwright Python officielle (navigateurs + deps système déjà inclus)
FROM mcr.microsoft.com/playwright/python:v1.54.0-noble

# Bonnes pratiques pour les logs
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code
COPY . .

# Variables par défaut (tu pourras les surcharger dans Render)
ENV CHECK_EVERY_SECONDS=180 \
    JITTER_MAX_SECONDS=60 \
    PW_NAV_TIMEOUT_MS=60000 \
    PW_WAIT_AFTER_LOAD_MS=5000

# Lancement du worker
CMD ["python", "watch_caf_tickets_playwright.py"]
