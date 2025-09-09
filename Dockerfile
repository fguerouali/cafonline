# Image Playwright officielle (navigateurs + deps déjà inclus)
FROM mcr.microsoft.com/playwright/python:v1.54.0-noble

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie tout (watch_caf.py, etc.)
COPY . .

# (Optionnel) variables par défaut
ENV CHECK_EVERY_SECONDS=180 \
    JITTER_MAX_SECONDS=60 \
    PW_NAV_TIMEOUT_MS=60000 \
    PW_WAIT_AFTER_LOAD_MS=5000 \
    STATE_FILE=/data/last_hash.txt

# Si tu veux PERSISTer le hash entre redéploiements, on montera un Render Disk sur /data
# (voir étape 5). Sinon mets simplement STATE_FILE=last_hash.txt

CMD ["python", "-u", "watch_caf.py"]
