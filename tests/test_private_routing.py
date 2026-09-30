"""فرمان‌های خصوصی باید بازیِ گروه را پیدا کنند، نه چتِ خود کاربر."""
import asyncio
from types import SimpleNamespace

import pytest

from karagah import bot, db, telegram_app
from karagah.bot import GAMES, handle, route_chat


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    bot._ACTIVE_TABLE.clear()
    yield
    GAMES.clear()
    bot._ACTIVE_TABLE.clear()


GROUP = -1001234
OTHER_GROUP = -1005678


def _started(chat=GROUP, n=6, case=12):
    handle("new", chat, 1, "Host")
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, arg=str(case))
    return GAMES[chat]


def test_private_command_finds_the_group_game():
    _started()
    assert route_chat("night", 2, 2, private=True) == GROUP      # چت پیویِ کاربر ۲
    assert route_chat("myrole", 3, 3, private=True) == GROUP


def test_group_command_is_untouched():
    _started()
    assert route_chat("night", GROUP, 2, private=False) == GROUP


def test_global_commands_stay_in_private():
    _started()
    # «menu» دیگر جهانی نیست: وسط بازی باید میزِ فعال را پیدا کند (§۱۳ ST04)
    for cmd in ("help", "top", "roles"):
        assert route_chat(cmd, 2, 2, private=True) == 2


def test_night_action_works_from_private_chat():
    g = _started()
    killer = next(p for p in g.s.players.values() if p.role == "قاتل")
    victim = next(p.uid for p in g.s.alive_players() if p.uid != killer.uid)
    target = route_chat("night", killer.uid, killer.uid, private=True)
    r = handle("night", target, killer.uid, arg=str(victim))
    assert r["ok"] and r["private"]
    assert f"kill:{killer.uid}" in g.s.night_actions


def test_two_games_are_ambiguous_until_table_is_picked():
    _started(GROUP)
    _started(OTHER_GROUP, case=13)
    assert route_chat("night", 2, 2, private=True) == 0          # مبهم
    assert handle("table", 2, 2, arg=str(OTHER_GROUP))["ok"]
    assert route_chat("night", 2, 2, private=True) == OTHER_GROUP


def test_table_rejects_a_game_you_are_not_in():
    _started(GROUP)
    assert handle("table", 999, 999, arg=str(GROUP))["ok"] is False


def test_no_game_falls_through_to_normal_error():
    assert route_chat("night", 7, 7, private=True) == 7
    assert handle("night", 7, 7, arg="1")["ok"] is False


# ---------- سرتاسری: از آپدیت تلگرام تا موتور ----------
class _FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))


def _private_update(fake, uid):
    return SimpleNamespace(
        get_bot=lambda: fake,
        callback_query=None,
        effective_user=SimpleNamespace(id=uid, first_name="P"),
        effective_chat=SimpleNamespace(id=uid, type="private"),
    )


def test_dispatch_routes_private_myrole_to_group_game():
    g = _started()
    fake = _FakeBot()
    upd = _private_update(fake, 2)
    res = telegram_app._dispatch(upd, "myrole", "")
    assert res["ok"] and res["private"]
    asyncio.run(telegram_app._reply(upd, res))
    assert fake.sent and fake.sent[0][0] == 2        # به پیوی رفت


def test_dispatch_reports_ambiguity_instead_of_failing():
    _started(GROUP)
    _started(OTHER_GROUP, case=13)
    res = telegram_app._dispatch(_private_update(_FakeBot(), 2), "night", "3")
    assert res["ok"] is False and "/table" in res["text"]
