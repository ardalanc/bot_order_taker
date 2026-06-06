# config.py
import os

ADMIN_IDS = [715337548,60794725]

BOT_TOKEN = os.environ.get("BOT_TOKEN")

DB_NAME = os.environ.get("database_name")

database_config = {
    "host": os.environ.get("DB_HOST"),
    "user": os.environ.get("DB_USER"),
    "password": os.environ.get("DB_PASSWORD")
}
