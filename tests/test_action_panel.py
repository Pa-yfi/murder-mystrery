"""بهبود ۱ و ۳: انتخاب هدف با نام + داشبورد راهنما."""
import pytest

from karagah import db, ui
from karagah.bot import GAMES, handle
from karagah.engine import Game, RuleError
from karagah.models import Custody, Phase


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    yield
    GAMES.clear()


def _started(chat=860, n=10, case=5):
    handle("new", chat, 1, "Host")
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, arg=str(case))
    return GAMES[chat]


def _role(g, name):
    return next(p for p in g.s.players.values() if p.role == name)


def _cbs(kbd):
    return [b["callback_data"] for row in kbd["inline_keyboard"] for b in row]


def _labels(kbd):
    return [b["text"] for row in kbd["inline_keyboard"] for b in row]


# ---------- بهبود ۱: دکمه‌ی هدف با نام ----------
def test_panel_lists_targets_by_name_not_id():
    g = _started()
    killer = _role(g, "قاتل")
    r = handle("act", 860, killer.uid)
    assert r["ok"] and r["private"]
    labels = _labels(r["keyboard"])
    # نام بازیکن‌ها روی دکمه‌هاست
    others = [p.name for p in g.s.alive_players() if p.uid != killer.uid]
    assert any(n in "".join(labels) for n in others)
    assert "قتل" in r["text"]


def test_panel_buttons_carry_the_action_callback():
    g = _started()
    killer = _role(g, "قاتل")
    cbs = _cbs(handle("act", 860, killer.uid)["keyboard"])
    victim = next(p.uid for p in g.s.alive_players() if p.uid != killer.uid)
    assert f"act:{victim}" in cbs


def test_tapping_a_target_records_the_action():
    g = _started()
    killer = _role(g, "قاتل")
    victim = next(p.uid for p in g.s.alive_players() if p.uid != killer.uid)
    r = handle("act", 860, killer.uid, arg=str(victim))
    assert r["ok"] and r["private"]
    assert g.s.night_actions.get(f"kill:{killer.uid}") == victim
    assert g.s.players[victim].name in r["text"]


def test_panel_marks_the_current_choice():
    g = _started()
    killer = _role(g, "قاتل")
    victim = next(p.uid for p in g.s.alive_players() if p.uid != killer.uid)
    handle("act", 860, killer.uid, arg=str(victim))
    r = handle("act", 860, killer.uid)
    assert "✅" in "".join(_labels(r["keyboard"]))
    assert g.s.players[victim].name in r["text"]


def test_illegal_targets_are_not_offered():
    """دکمه‌ها از همان قواعدِ موتور می‌آیند — خودِ قاتل در فهرست نیست."""
    g = _started()
    killer = _role(g, "قاتل")
    assert killer.uid not in g.legal_targets(killer.uid)
    assert f"act:{killer.uid}" not in _cbs(handle("act", 860, killer.uid)["keyboard"])


def test_doctor_cannot_be_offered_last_nights_target():
    g = _started()
    doc = _role(g, "پزشک")
    a = next(p.uid for p in g.s.alive_players() if p.uid != doc.uid)
    g.night_action(doc.uid, a)
    g.resolve_night()
    g.s.phase = Phase.NIGHT
    assert a not in g.legal_targets(doc.uid)       # دو شب پیاپی ممنوع


def test_roleless_player_gets_a_clear_message():
    g = _started()
    plain = next((p for p in g.s.alive_players()
                  if not __import__("karagah.roles", fromlist=["ROLES"]).ROLES[p.role].ability), None)
    if plain is None:
        pytest.skip("این ترکیب نقش بی‌اکشن ندارد")
    r = handle("act", 860, plain.uid)
    assert r["ok"] and "اکشن شبانه ندارد" in r["text"]


def test_hunter_panel_sets_last_shot():
    g = _started()
    hunter = _role(g, "شکارچی")
    victim = next(p.uid for p in g.s.alive_players() if p.uid != hunter.uid)
    cbs = _cbs(handle("act", 860, hunter.uid)["keyboard"])
    assert f"hunter:{victim}" in cbs
    handle("hunter", 860, hunter.uid, arg=str(victim))
    assert hunter.hunter_target == victim


def test_night_command_without_arg_opens_the_panel():
    g = _started()
    killer = _role(g, "قاتل")
    r = handle("night", 860, killer.uid)
    assert r["ok"] and r["keyboard"]              # دیگر خطای «آیدی بده» نیست


# ---------- بهبود ۳: داشبورد ----------
def test_dashboard_shows_phase_and_next_step():
    g = _started()
    r = handle("dashboard", 860, 1)
    assert g.s.phase.value in r["text"]
    assert "قدم بعدی" in r["text"]
    assert "اکشن" in r["text"]


def test_dashboard_lists_who_still_owes_an_action():
    g = _started()
    killer = _role(g, "قاتل")
    before = handle("dashboard", 860, 1)["text"]
    assert killer.name in before                   # منتظر قاتل هستیم
    victim = next(p.uid for p in g.s.alive_players() if p.uid != killer.uid)
    handle("act", 860, killer.uid, arg=str(victim))
    after = handle("dashboard", 860, 1)["text"]
    pending = g.pending_actors()
    assert killer.uid not in pending
    assert "منتظر" in after


def test_dashboard_pending_tracks_votes():
    g = _started()
    handle("dawn", 860); handle("discuss", 860); handle("vote", 860)
    voters = [p.uid for p in g.s.alive_players() if p.can_vote]
    assert set(g.pending_actors()) == set(voters)
    target = next(u for u in voters if u != voters[0])
    handle("castvote", 860, voters[0], arg=str(target))
    assert voters[0] not in g.pending_actors()


def test_dashboard_button_matches_phase():
    g = _started()
    assert "dawn" in _cbs(ui.dashboard_kb(g.s))
    handle("dawn", 860)
    assert "discuss" in _cbs(ui.dashboard_kb(g.s))
    handle("discuss", 860)
    assert "vote" in _cbs(ui.dashboard_kb(g.s))
    handle("vote", 860)
    assert "closevote" in _cbs(ui.dashboard_kb(g.s))
