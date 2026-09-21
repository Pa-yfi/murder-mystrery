"""🕵️ کارآگاه — نسخه‌ی پیشرفته‌ی مافیا + معمای قتل برای تلگرام (فارسی)."""
__version__ = "3.1.0"

from . import config, models, roles, cases, dialogue, engine, ui, db, bot, cards, strings
from .engine import Game, RuleError
from .models import Align, Custody, Phase, Player
from .bot import handle, ENDPOINTS, COMMANDS

__all__ = ["config", "models", "roles", "cases", "dialogue", "engine", "ui", "db", "bot",
           "Game", "RuleError", "Align", "Custody", "Phase", "Player",
           "handle", "ENDPOINTS", "COMMANDS"]
