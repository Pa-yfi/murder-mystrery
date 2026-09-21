"""ایده ۳۰: لایه‌ی رشته‌های دوزبانه — فارسی پیش‌فرض، انگلیسی آماده‌ی توسعه."""
from __future__ import annotations
from .config import LANG

STRINGS = {
    "fa": {
        "main_menu": "🏠 *منوی اصلی*",
        "welcome": "🕵️ *به «کارآگاه» خوش آمدی!*",
        "lobby": "🏛️ *لابی کارآگاه*",
        "unknown": "🕵️ فرمان را نشناختم. منوی اصلی:",
        "timer": "⏳ زمان باقی‌مانده",
    },
    "en": {
        "main_menu": "🏠 *Main Menu*",
        "welcome": "🕵️ *Welcome to Karagah!*",
        "lobby": "🏛️ *Detective Lobby*",
        "unknown": "🕵️ Unknown command. Main menu:",
        "timer": "⏳ Time left",
    },
}


def t(key: str, lang: str | None = None) -> str:
    lang = lang or LANG
    return STRINGS.get(lang, STRINGS["fa"]).get(key, STRINGS["fa"].get(key, key))
