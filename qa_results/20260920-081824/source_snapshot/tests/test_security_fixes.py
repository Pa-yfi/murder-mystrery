"""تست‌های رگرسیون برای باگ‌های امنیتی/دسترسی."""
import asyncio
from types import SimpleNamespace

import pytest

from karagah import bot, config, telegram_app
from karagah.bot import GAMES, handle
from karagah.models import Phase


@pytest.fixture(autouse=True)
def fresh():
    from karagah import db
    db.reset(":memory:")
    GAMES.clear()
    yield
    GAMES.clear()


# ---------- باگ ۱: نشت نقش محرمانه به گروه ----------
class _FakeBot:
    """پیوی همیشه شکست می‌خورد؛ ارسال به گروه موفق است."""

    def __init__(self, private_uid):
        self.private_uid = private_uid
        self.group_texts = []

    async def send_message(self, chat_id, text, **kw):
        if chat_id == self.private_uid:
            raise RuntimeError("Forbidden: bot can't initiate conversation with a user")
        self.group_texts.append(text)


def _update(fake, uid, chat):
    return SimpleNamespace(
        get_bot=lambda: fake,
        callback_query=None,
        effective_user=SimpleNamespace(id=uid),
        effective_chat=SimpleNamespace(id=chat),
    )


def test_private_text_never_falls_back_to_group():
    fake = _FakeBot(private_uid=42)
    secret = "🔐 نقش تو: قاتل 🔪 — هم‌تیمی: علی"
    res = {"text": secret, "keyboard": None, "private": True, "edit": False}
    asyncio.run(telegram_app._reply(_update(fake, 42, -100), res))

    assert fake.group_texts, "باید یک تذکر به گروه برود"
    joined = "\n".join(fake.group_texts)
    assert secret not in joined
    assert "قاتل" not in joined and "نقش تو" not in joined
    assert "/start" in joined              # فقط راهنمایی، نه محتوا


def test_public_text_still_delivered():
    fake = _FakeBot(private_uid=-1)        # پیوی لازم نیست
    res = {"text": "☀️ صبح روز ۱", "keyboard": None, "private": False, "edit": False}
    asyncio.run(telegram_app._reply(_update(fake, 42, -100), res))
    assert fake.group_texts == ["☀️ صبح روز ۱"]


# ---------- باگ ۲: ADMIN_IDS خالی = همه ادمین ----------
def test_empty_admin_ids_grants_nobody(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [])
    r = handle("admin", 900, 12345, "Nobody")
    assert r["ok"] is False and "ادمین" in r["text"]


def test_listed_admin_still_allowed(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [777])
    assert handle("admin", 900, 777, "Boss")["ok"] is True
    assert handle("admin", 900, 778, "Other")["ok"] is False


def test_admin_ban_requires_admin(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [])
    assert handle("admin_ban", 900, 5, "Rando", arg="6")["ok"] is False


# ---------- باگ ۳: هرکسی بازی در جریان را عوض کند ----------
def _running_game(chat=901, host=1):
    handle("new", chat, host, "Host")
    for i in range(2, 6):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, host, arg="3")
    assert GAMES[chat].s.phase is not Phase.LOBBY
    return GAMES[chat]


@pytest.mark.parametrize("cmd", ["new", "blitz"])
def test_outsider_cannot_replace_running_game(cmd):
    g = _running_game()
    r = handle(cmd, 901, 99999, "Intruder")
    assert r["ok"] is False and "میزبان" in r["text"]
    assert GAMES[901] is g                 # همان بازی سر جایش است


def test_host_can_still_restart():
    _running_game()
    assert handle("new", 901, 1, "Host")["ok"] is True
    assert GAMES[901].s.phase is Phase.LOBBY


def test_lobby_is_freely_replaceable():
    handle("new", 902, 1, "Host")          # هنوز شروع نشده → قفل نیست
    assert handle("new", 902, 2, "Other")["ok"] is True
