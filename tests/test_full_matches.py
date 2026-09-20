"""بهبود ۱۰: بازیِ کامل از لابی تا افشای نقش — با ری‌استارت، تایمر،
هیئت منصفه و شکستِ پیام خصوصی."""
import asyncio
from types import SimpleNamespace

import pytest

from karagah import bot, db, telegram_app
from karagah.bot import GAMES, handle
from karagah.models import Align, Custody, Phase


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    yield
    GAMES.clear()
    bot.REQUIRE_READY = False


def _lobby(chat, n=6):
    handle("new", chat, 1, "Host")
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    return GAMES[chat]


def _everyone_ready(chat, g):
    for u in list(g.s.players):
        handle("start", u, u, arg=f"ready_{chat}")


def _night_actions(chat, g):
    """هر کسی که اکشن دارد، اولین هدف مجازش را می‌زند."""
    for u in list(g.pending_actors()):
        targets = g.legal_targets(u)
        if targets:
            handle("act", chat, u, arg=str(targets[0]))


def _vote_someone_out(chat, g):
    handle("discuss", chat)
    handle("vote", chat)
    target = next((p.uid for p in g.s.alive_players()
                   if p.can_vote and p.uid != g.s.officer_uid), None)
    if target is None:
        return None
    for p in g.s.alive_players():
        if p.can_vote and p.uid != target:
            handle("castvote", chat, p.uid, arg=str(target))
    handle("closevote", chat)
    return target


def test_full_match_from_lobby_to_reveal():
    chat = 910
    bot.REQUIRE_READY = True
    g = _lobby(chat)
    assert handle("startgame", chat, 1)["ok"] is False      # هنوز آماده نیستند
    _everyone_ready(chat, g)
    assert handle("startgame", chat, 1)["ok"]

    for _ in range(12):                                     # تا پایان طبیعی
        if g.s.phase is Phase.END:
            break
        if g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
            _night_actions(chat, g)
            handle("dawn", chat)
        elif g.s.phase is Phase.MORNING:
            if g.s.suspect_uid is not None:
                handle("verdict", chat, g.s.officer_uid, arg="1")
            else:
                _vote_someone_out(chat, g)
        else:
            _vote_someone_out(chat, g)

    assert g.s.phase is Phase.END, f"در فاز {g.s.phase} گیر کرد"
    r = handle("end", chat, 1)
    assert r["ok"] and g.s.winner in r["text"]
    assert g.s.win_reason.split()[0] in r["text"]
    for p in g.s.players.values():
        assert p.role in r["text"]


def test_full_match_driven_only_by_the_timer():
    """هیچ‌کس دکمه نمی‌زند — تایمر باید بازی را جلو ببرد و ذخیره کند."""
    chat = 911
    g = _lobby(chat)
    handle("startgame", chat, 1, arg="8")

    class _Ctx:
        def __init__(self):
            self.sent = []
            self.bot = SimpleNamespace(
                send_message=lambda chat_id, text, **kw: self._rec(chat_id, text))

        async def _send(self, *a, **k):
            pass

        def _rec(self, chat_id, text):
            self.sent.append((chat_id, text))
            async def _noop():
                return None
            return _noop()

    seen = set()
    for _ in range(14):
        if g.s.phase is Phase.END:
            break
        g.s.deadline = 0                       # مهلت این فاز گذشت
        asyncio.run(telegram_app._timer_job(_Ctx()))
        seen.add(g.s.phase)
        if g.s.phase is Phase.MORNING:         # تایمر برای صبح مهلتی ندارد
            handle("discuss", chat)
    assert Phase.MORNING in seen and Phase.VOTE in seen
    snap = db.load_snapshots()
    if g.s.phase is not Phase.END:
        assert snap[chat].s.phase is g.s.phase   # اسنپ‌شات با حافظه هم‌قدم است


def test_full_match_with_a_jury_appeal():
    chat = 912
    g = _lobby(chat)
    handle("startgame", chat, 1, arg="14")
    _night_actions(chat, g)
    handle("dawn", chat)
    target = _vote_someone_out(chat, g)
    assert g.s.phase is Phase.INTERROGATION
    handle("dawn", chat)                                 # شبِ بازجویی
    jurors = [p.uid for p in g.s.alive_players() if p.uid != target][:2]
    handle("jury", chat, jurors[0])
    assert handle("jury", chat, jurors[1])["ok"]
    for u in [p.uid for p in g.s.alive_players() if p.can_vote]:
        handle("juryvote", chat, u, arg="1")
    assert "تبرئه" in handle("closejury", chat, jurors[0])["text"]
    assert g.s.players[target].custody is Custody.FREE
    assert g.s.phase is not Phase.NIGHT


def test_match_survives_a_restart_mid_game():
    chat = 913
    g = _lobby(chat)
    handle("startgame", chat, 1, arg="11")
    _night_actions(chat, g)
    handle("dawn", chat)
    before = (g.s.phase, g.s.day, len(g.s.players))

    GAMES.clear()                                        # ری‌استارتِ ربات
    assert bot.restore_games() == 1
    g2 = GAMES[chat]
    assert (g2.s.phase, g2.s.day, len(g2.s.players)) == before
    assert handle("discuss", chat)["ok"]                 # بازی ادامه پیدا می‌کند


def test_restart_does_not_resurrect_a_finished_match():
    chat = 914
    g = _lobby(chat)
    handle("startgame", chat, 1, arg="9")
    for p in g.s.players.values():
        if p.align is Align.KILLER:
            p.custody = Custody.LIFE_JAIL
    g._check_win()
    handle("status", chat, 1)
    GAMES.clear()
    assert bot.restore_games() == 0


def test_secret_never_leaks_during_a_real_match():
    """همه‌ی پاسخ‌های خصوصیِ یک بازی، با پیویِ خراب، باز هم چیزی لو ندهند."""
    chat = 915
    g = _lobby(chat)
    handle("startgame", chat, 1, arg="16")

    class _Bot:
        def __init__(self):
            self.group = []

        async def send_message(self, chat_id, text, **kw):
            if chat_id != chat:
                raise RuntimeError("Forbidden: can't initiate conversation")
            self.group.append(text)

    roles = [p.role for p in g.s.players.values()]
    for uid in list(g.s.players):
        for cmd in ("myrole", "act", "notes"):
            res = handle(cmd, chat, uid)
            if not res.get("private"):
                continue
            fake = _Bot()
            upd = SimpleNamespace(
                get_bot=lambda b=fake: b, callback_query=None,
                effective_user=SimpleNamespace(id=uid, first_name="P"),
                effective_chat=SimpleNamespace(id=chat, type="group"))
            asyncio.run(telegram_app._reply(upd, res))
            leaked = "\n".join(fake.group)
            assert "نقش تو" not in leaked
            for r in roles:
                assert f"نقش تو: {r}" not in leaked


def test_abandoned_then_restarted_match_is_recorded():
    chat = 916
    _lobby(chat)
    handle("startgame", chat, 1, arg="17")
    handle("new", chat, 1, "Host")            # میزبان نیمه‌کاره رهایش کرد
    assert db.q_abandonment()["abandoned"] == 1
    assert GAMES[chat].s.phase is Phase.LOBBY
