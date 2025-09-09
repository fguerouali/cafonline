
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import random
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------
# ⚙️ Paramètres
# ---------------------------------
URL = os.getenv("WATCH_URL", "https://tickets.cafonline.com/fr")
CHECK_EVERY_SECONDS = int(os.getenv("CHECK_EVERY_SECONDS", "180"))
JITTER_MAX_SECONDS = int(os.getenv("JITTER_MAX_SECONDS", "60"))
STATE_FILE = os.getenv("STATE_FILE", "last_hash.txt")

TELEGRAM_BOT_TOKEN = "7263674375:AAEdRAXfb1LZAxfqMl09rbVoDARF29Yxoy4"
TELEGRAM_CHAT_ID = ["1271546430"]

PW_NAV_TIMEOUT_MS = int(os.getenv("PW_NAV_TIMEOUT_MS", "60000"))
PW_WAIT_AFTER_LOAD_MS = int(os.getenv("PW_WAIT_AFTER_LOAD_MS", "5000"))
PW_PROXY = os.getenv("PW_PROXY")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    "Referer": "https://www.google.com/",
}

# ---------------------------------
# 🪵 Logging
# ---------------------------------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# ---------------------------------
# 🔧 Utilitaires
# ---------------------------------
def send_telegram(message: str) -> None:
    logging.info("Préparation envoi Telegram...")
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("TELEGRAM_BOT_TOKEN/CHAT_ID manquant(s) : message non envoyé.")
        return
    api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(api, data=payload, timeout=20)
        r.raise_for_status()
        logging.info("✅ Message Telegram envoyé avec succès.")
    except Exception as e:
        logging.error(f"❌ Erreur envoi Telegram: {e}")

def normalize_html_for_hash(html: str) -> str:
    logging.debug("Normalisation du HTML pour calcul hash...")
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ", strip=True).split())
    return text

def compute_hash(content: str) -> str:
    h = hashlib.sha256(content.encode("utf-8")).hexdigest()
    logging.debug(f"Hash calculé: {h}")
    return h

def load_last_hash(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            val = f.read().strip() or None
            logging.debug(f"Dernier hash chargé: {val}")
            return val
    except FileNotFoundError:
        logging.info("Aucun hash précédent trouvé (premier lancement).")
        return None

def save_last_hash(path: str, h: str) -> None:
    logging.info(f"Sauvegarde du hash actuel: {h}")
    with open(path, "w", encoding="utf-8") as f:
        f.write(h)

# ---------------------------------
# 🌐 Playwright
# ---------------------------------
def fetch_with_playwright(url: str) -> str:
    logging.info("Ouverture Chromium headless avec Playwright...")
    launch_kwargs = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
    context_kwargs = {
        "user_agent": HEADERS["User-Agent"],
        "locale": "fr-FR",
        "viewport": {"width": 1366, "height": 768},
    }
    if PW_PROXY:
        logging.info(f"Utilisation proxy: {PW_PROXY}")
        context_kwargs["proxy"] = {"server": PW_PROXY}

    try:
        from playwright_stealth import stealth_sync
    except Exception:
        stealth_sync = None

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            if stealth_sync:
                logging.debug("Activation mode stealth Playwright.")
                stealth_sync(page)

            page.set_default_timeout(PW_NAV_TIMEOUT_MS)
            logging.info(f"Navigation vers {url} ...")
            page.goto(url, wait_until="domcontentloaded")

            try:
                page.wait_for_load_state("networkidle", timeout=PW_NAV_TIMEOUT_MS)
            except PWTimeout:
                logging.warning("Timeout atteint avant 'networkidle'.")

            page.wait_for_selector("body", timeout=PW_NAV_TIMEOUT_MS)
            page.wait_for_timeout(PW_WAIT_AFTER_LOAD_MS)

            html = page.content()
            logging.info(f"Longueur HTML récupéré: {len(html)} caractères")

            if not html or len(html) < 1000:
                logging.warning("HTML trop court, tentative de reload...")
                page.reload(wait_until="domcontentloaded")
                try:
                    page.wait_for_load_state("networkidle", timeout=PW_NAV_TIMEOUT_MS)
                except PWTimeout:
                    pass
                page.wait_for_timeout(PW_WAIT_AFTER_LOAD_MS)
                html = page.content()
                logging.info(f"HTML après reload: {len(html)} caractères")

            return html
        finally:
            browser.close()
            logging.debug("Navigateur fermé.")

def fetch_page_resilient() -> str:
    for attempt in range(1, 3):
        try:
            logging.info(f"Tentative Playwright {attempt}/2")
            html = fetch_with_playwright(URL)
            return html
        except Exception as e:
            logging.warning(f"Echec tentative {attempt}/2 : {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError("Impossible de récupérer la page via Playwright.")

# ---------------------------------
# 🔍 Détection
# ---------------------------------
def check_once() -> Optional[str]:
    logging.info("🔄 Vérification en cours...")
    html = fetch_page_resilient()
    normalized = normalize_html_for_hash(html)
    current_hash = compute_hash(normalized)

    last_hash = load_last_hash(STATE_FILE)
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%SZ')

    if last_hash is None:
        save_last_hash(STATE_FILE, current_hash)
        logging.info("Premier enregistrement du hash.")
        return (f"🔎 Surveillance initialisée sur <a href=\"{URL}\">tickets.cafonline.com/fr</a>\n"
                f"⏱ {now} UTC")

    if current_hash != last_hash:
        logging.info("⚠️ Changement détecté !")
        save_last_hash(STATE_FILE, current_hash)
        return (f"🟢 CHANGEMENT DÉTECTÉ sur <a href=\"{URL}\">tickets.cafonline.com/fr</a>\n"
                f"⏱ {now} UTC")

    logging.info("Aucun changement détecté.")
    return None

# ---------------------------------
# ▶️ Main
# ---------------------------------
def main():
    logging.info(f"Démarrage surveillance URL={URL} | intervalle={CHECK_EVERY_SECONDS}s (+ jitter ≤ {JITTER_MAX_SECONDS}s)")

    send_telegram(f"🚀 Script de surveillance démarré pour <a href=\"{URL}\">{URL}</a>")

    try:
        msg = check_once()
        if msg:
            send_telegram(msg)
    except Exception as e:
        logging.error(f"Erreur initiale: {e}")

    consecutive_errors = 0
    while True:
        try:
            msg = check_once()
            if msg:
                send_telegram(msg)
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            logging.error(f"Erreur boucle ({consecutive_errors}): {e}")
            time.sleep(min(60, 5 * consecutive_errors))
        sleep_for = CHECK_EVERY_SECONDS + random.randint(0, max(0, JITTER_MAX_SECONDS))
        logging.info(f"Prochain check dans {sleep_for} secondes...")
        time.sleep(sleep_for)

if __name__ == "__main__":
    main()
