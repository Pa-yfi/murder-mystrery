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


def test_jury_reachable_through_normal_play():
    """بدون دست‌کاری دستیِ custody_nights — فقط با دستورهای عادی."""
    chat = 800
    g = _started(chat)
    target = _vote_out(chat, g)
    assert g.s.players[target].custody is Custody.INTERROGATION
    assert g.s.phase is Phase.INTERROGATION

    # هنوز شب نگذشته: هیئت تشکیل نمی‌شود — ولی دکمه هم بی‌جواب نمی‌ماند،
    # می‌گوید چه چیزی لازم است.
    r = handle("jury", chat, 2)
    assert g.s.phase is Phase.INTERROGATION
    assert "پایان شب" in r["text"]
    assert handle("verdict", chat, g.s.officer_uid, arg="1")["ok"] is False

    assert handle("dawn", chat)["ok"]              # شبِ بازجویی طی شد
    assert g.s.players[target].custody_nights >= 1

    jurors = [p.uid for p in g.s.alive_players() if p.uid != target][:2]
    assert handle("jury", chat, jurors[0])["ok"]
    r = handle("jury", chat, jurors[1])
    assert r["ok"] and "تشکیل شد" in r["text"]
    assert g.s.phase is Phase.JURY


def test_jury_acquittal_returns_to_day_not_night():
    chat = 801
    g = _started(chat)
    target = _vote_out(chat, g)
    handle("dawn", chat)
    day_before = g.s.day
    jurors = [p.uid for p in g.s.alive_players() if p.uid != target][:2]
    handle("jury", chat, jurors[0])
    handle("jury", chat, jurors[1])
    for u in [p.uid for p in g.s.alive_players() if p.can_vote]:
        handle("juryvote", chat, u, arg="1")
    r = handle("closejury", chat, jurors[0])
    assert "تبرئه" in r["text"]
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
    handle("dawn", chat)
    day_before = g.s.day
    assert handle("verdict", chat, g.s.officer_uid, arg="1")["ok"]
    assert g.s.players[target].custody is Custody.TEMP_JAIL
    assert g.s.phase is Phase.MORNING              # روز ادامه دارد
    assert g.s.day == day_before
