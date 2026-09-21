from types import SimpleNamespace
from unittest.mock import AsyncMock
from karagah import bot
from karagah.engine import Game
from karagah.models import Align, Phase
from karagah.roles import ROLES

GROUP = -700001


def game(n=6, seed=7, case=1, chat=GROUP):
    g = Game(chat, seed=seed, owner=1)
    for uid in range(1, n + 1):
        g.join(uid, f"Player {uid}")
        g.mark_ready(uid)
    g.start(case, force=False)
    bot.GAMES[chat] = g
    return g


def role_game(role):
    """Explicit UNIT fixture; not a claim this role is assigned in production."""
    g = game()
    for p in g.s.players.values():
        p.role, p.align = "شهروند", Align.CITY
        p.notes.clear()
    for uid, name in ((2, "بازجو"), (3, "قاتل"), (1, role)):
        g.s.players[uid].role, g.s.players[uid].align = name, ROLES[name].align
    g.s.officer_uid = 1 if role == "بازجو" else 2
    g.s.fate_pair = None
    return g


def update(uid, chat=None, callback=None, transport=None):
    chat = uid if chat is None else chat
    transport = transport or SimpleNamespace(send_message=AsyncMock(), send_photo=AsyncMock(), send_voice=AsyncMock())
    return SimpleNamespace(effective_chat=SimpleNamespace(id=chat, type="private" if chat == uid else "group"),
        effective_user=SimpleNamespace(id=uid, first_name=f"Player {uid}"),
        callback_query=callback, get_bot=lambda: transport), transport


def interrogate(g, target=4):
    g.resolve_night()
    g.open_discussion()
    g.open_vote()
    for p in g.s.players.values():
        if p.can_vote and p.uid != target:
            g.vote(p.uid, target)
    assert g.close_vote() == target
    assert g.s.phase is Phase.INTERROGATION
