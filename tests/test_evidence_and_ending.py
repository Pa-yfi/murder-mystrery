"""بهبود ۵ (مدرکِ برخاسته از بازی) و ۶ (پایانِ قابل‌فهم)."""
import pytest

from karagah import db
from karagah.bot import GAMES, handle
from karagah.engine import Game, RuleError
from karagah.models import Align, Custody, Phase


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    yield
    GAMES.clear()


CHAT = 880


def _started(n=10, case=5, chat=CHAT):
    handle("new", chat, 1, "Host")
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, arg=str(case))
    return GAMES[chat]


def _role(g, name):
    return next(p for p in g.s.players.values() if p.role == name)


# ---------- بهبود ۵ ----------
def test_no_visits_means_no_footprint_trace():
    g = _started()
    g.resolve_night()
    assert not any("سر زدند" in t for t in g.s.traces)


def test_victim_visit_count_is_reported():
    g = _started()
    killer = _role(g, "قاتل")
    victim = next(p for p in g.s.alive_players() if p.uid != killer.uid)
    g.night_action(killer.uid, victim.uid)
    g.resolve_night()
    assert any(victim.name in t and "سر زدند" in t for t in g.s.traces)


def test_count_is_ambiguous_with_more_than_one_visitor():
    """عدد به‌تنهایی قاتل را لو نمی‌دهد — چند نفر سر یک نفر می‌روند."""
    g = _started()
    killer, poisoner = _role(g, "قاتل"), _role(g, "سم‌ساز")
    victim = next(p for p in g.s.alive_players()
                  if p.uid not in (killer.uid, poisoner.uid))
    g.night_action(killer.uid, victim.uid)
    g.night_action(poisoner.uid, victim.uid)
    g.resolve_night()
    assert not victim.alive
    trace = next(t for t in g.s.traces if "سر زدند" in t)
    assert "2 نفر" in trace
    assert "پزشک و نگهبان هم سر می‌زنند" in trace     # هشدارِ ابهام


def test_a_saved_victim_leaves_no_crime_scene():
    """پزشک نجاتش داد → جنازه‌ای نیست، پس ردِ صحنه هم نیست."""
    g = _started()
    killer, doc = _role(g, "قاتل"), _role(g, "پزشک")
    victim = next(p for p in g.s.alive_players()
                  if p.uid not in (killer.uid, doc.uid))
    g.night_action(killer.uid, victim.uid)
    g.night_action(doc.uid, victim.uid)
    g.resolve_night()
    assert victim.alive
    assert not any("سر زدند" in t for t in g.s.traces)
    # ولی قاتل و پزشک همدیگر را دیده‌اند
    assert any(doc.name in n for n in killer.notes)


def test_co_visitors_learn_each_other_privately():
    g = _started()
    killer, doc = _role(g, "قاتل"), _role(g, "پزشک")
    victim = next(p for p in g.s.alive_players()
                  if p.uid not in (killer.uid, doc.uid))
    g.night_action(killer.uid, victim.uid)
    g.night_action(doc.uid, victim.uid)
    g.resolve_night()
    assert any(doc.name in n for n in killer.notes)     # قاتل پزشک را دید
    assert any(killer.name in n for n in doc.notes)     # و برعکس


def test_watching_leaves_no_footprint():
    g = _started()
    watcher = _role(g, "نگهبان")
    target = next(p for p in g.s.alive_players() if p.uid != watcher.uid)
    g.night_action(watcher.uid, target.uid)
    g.resolve_night()
    assert not any("هم‌زمان نزدیک" in t for t in g.s.traces)


def test_frame_shows_up_as_a_plantable_fingerprint():
    g = _started()
    acc = _role(g, "همدست")
    mark = next(p for p in g.s.alive_players()
                if p.align is Align.CITY and p.uid != acc.uid)
    g.night_action(acc.uid, mark.uid)
    g.resolve_night()
    g.s.phase = Phase.NIGHT
    g.s.day += 1
    g.resolve_night()
    trace = next((t for t in g.s.traces if "اثر انگشت" in t), None)
    assert trace and mark.name in trace
    assert "کاشت" in trace                     # هشدار پاپوش هست


def test_traces_reach_the_morning_message():
    g = _started()
    killer = _role(g, "قاتل")
    victim = next(p for p in g.s.alive_players() if p.uid != killer.uid)
    handle("act", CHAT, killer.uid, arg=str(victim.uid))
    r = handle("dawn", CHAT)
    assert "ردهای دیشب" in r["text"]


def test_traces_reset_each_night():
    g = _started()
    killer = _role(g, "قاتل")
    victim = next(p for p in g.s.alive_players() if p.uid != killer.uid)
    g.night_action(killer.uid, victim.uid)
    g.resolve_night()
    assert g.s.traces
    g.s.phase = Phase.NIGHT
    g.resolve_night()
    assert not any("سر زدند" in t for t in g.s.traces)   # ردِ دیشب کهنه نمی‌ماند


# ---------- بهبود ۶ ----------
def _finish_city_win(g):
    for p in g.s.players.values():
        if p.align is Align.KILLER:
            p.custody = Custody.LIFE_JAIL
    g._check_win()


def test_ending_explains_why_the_side_won():
    g = _started()
    _finish_city_win(g)
    r = handle("end", CHAT, 1)
    assert r["ok"]
    assert g.s.win_reason and g.s.win_reason.split()[0] in r["text"]
    assert "هیچ قاتلی" in r["text"]


def test_ending_reveals_every_role_and_fate():
    g = _started()
    _finish_city_win(g)
    text = handle("end", CHAT, 1)["text"]
    for p in g.s.players.values():
        assert p.name in text and p.role in text
    assert "حبس ابد" in text


def test_ending_flags_wrongly_jailed_innocents():
    g = _started()
    innocent = next(p for p in g.s.players.values() if p.align is Align.CITY)
    innocent.custody = Custody.LIFE_JAIL
    _finish_city_win(g)
    text = handle("end", CHAT, 1)["text"]
    assert "بی‌گناه حبس ابد" in text and innocent.name in text


def test_killer_parity_win_states_the_numbers():
    g = _started(n=6, case=9, chat=881)
    for p in list(g.s.alive_players()):
        if p.align is not Align.KILLER:
            p.alive = False
            if len([x for x in g.s.alive_players() if x.align is not Align.KILLER]) <= 1:
                break
    g._check_win()
    assert g.s.winner and "قاتل" in g.s.winner
    assert "قاتل‌ها" in g.s.win_reason


def test_ending_report_refuses_before_the_game_ends():
    g = _started()
    with pytest.raises(RuleError):
        g.ending_report()
