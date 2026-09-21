"""خط زمانی بازداشت: رای → شبِ بازجویی → حکم/هیئت منصفه."""
import pytest

from karagah import db
from karagah.bot import GAMES, handle
from karagah.engine import Game, RuleError
from karagah.models import Custody, Phase


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    yield
    GAMES.clear()


def _started(chat=800, n=6):
    handle("new", chat, 1, "Host")
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, arg="12")
    return GAMES[chat]


def _vote_out(chat, g):
    """کل گروه به یک نفر رای می‌دهند تا به بازجویی برود."""
    handle("dawn", chat)
    handle("discuss", chat)
    handle("vote", chat)
    target = next(p.uid for p in g.s.alive_players()
                  if p.uid != g.s.officer_uid and p.can_vote)
    for p in g.s.alive_players():
        if p.can_vote and p.uid != target:
            handle("castvote", chat, p.uid, arg=str(target))
    handle("closevote", chat)
    return target


def _gate(g, suspect, chat):
    """rules.md v2 R07.1."""
    off = g.s.officer_uid
    handle("ask", chat, off, arg="دیشب کجا بودی؟")
    handle("reply", chat, suspect, arg="خانه بودم.")
    handle("closeroom", chat, off)
    handle("hints", chat, off)


def test_jury_reachable_through_normal_play():
    """v2: هیئت را بازجو بعد از دروازه‌ی گفتگو تشکیل می‌دهد."""
    chat = 800
    g = _started(chat)
    target = _vote_out(chat, g)
    assert g.s.players[target].custody is Custody.INTERROGATION
    assert g.s.phase is Phase.INTERROGATION

    # پیش از دروازه: نه حکم، نه ارجاع — ولی دکمه توضیح می‌دهد چه لازم است
    r = handle("jury", chat, 2)
    assert g.s.phase is Phase.INTERROGATION and "گفتگو" in r["text"]
    assert handle("verdict", chat, g.s.officer_uid, arg="1")["ok"] is False
    assert handle("refer", chat, g.s.officer_uid)["ok"] is False

    _gate(g, target, chat)
    assert handle("refer", chat, g.s.officer_uid)["ok"]
    assert g.s.phase is Phase.JURY and len(g.s.jury_panel) == 2


def test_jury_acquittal_returns_to_day_not_night():
    chat = 801
    g = _started(chat)
    target = _vote_out(chat, g)
    _gate(g, target, chat)
    day_before = g.s.day
    handle("refer", chat, g.s.officer_uid)
    for u in g.s.jury_panel:
        handle("juryvote", chat, u, arg="1")       # هر دو: آزادی
    r = handle("closejury", chat, g.s.officer_uid)
    assert "آزاد" in r["text"]
    assert g.s.players[target].custody is Custody.FREE
    assert g.s.phase is not Phase.NIGHT            # شب دوباره تکرار نمی‌شود
    assert g.s.day == day_before


def test_others_still_act_during_interrogation_night():
    """شبِ بازجویی یک شب واقعی است: قاتل می‌کشد."""
    chat = 802
    g = _started(chat)
    target = _vote_out(chat, g)
    killer = next(p for p in g.s.players.values() if p.role == "قاتل")
    if killer.uid == target:
        pytest.skip("قاتل خودش متهم شد")
    victim = next(p.uid for p in g.s.alive_players()
                  if p.uid not in (killer.uid, target))
    assert handle("night", chat, killer.uid, arg=str(victim))["ok"]
    handle("dawn", chat)
    assert not g.s.players[victim].alive


def test_verdict_keeps_the_day_going():
    chat = 803
    g = _started(chat)
    target = _vote_out(chat, g)
    _gate(g, target, chat)
    day_before = g.s.day
    assert handle("verdict", chat, g.s.officer_uid, arg="1")["ok"]
    assert g.s.players[target].custody is Custody.TEMP_JAIL
    assert g.s.phase is Phase.MORNING              # روز ادامه دارد
    assert g.s.day == day_before
