"""Regression contracts for inspected defects, not implementation-mirroring tests."""
import copy
import pytest
from karagah import bot, db
from karagah.engine import RuleError
from karagah.models import Align, Custody, Phase
from karagah.roles import ROLES, COMPOSITIONS
from .helpers import game, role_game, interrogate, GROUP


def test_doctor_edit_cannot_bypass_previous_target_rule():
    g = role_game("پزشک")
    g.s._protect_prev = 4
    g.night_action(1, 5)
    with pytest.raises(RuleError):
        g.night_action(1, 4)


def test_detective_previous_target_survives_dawn():
    g = role_game("کارآگاه")
    g.night_action(1, 4)
    g.resolve_night(); g.open_discussion(); g.open_vote(); g.close_vote()
    with pytest.raises(RuleError):
        g.night_action(1, 4)


def test_serial_killer_prevents_premature_city_victory():
    g = role_game("جانی سریالی")
    g.s.players[3].alive = False
    assert g._check_win() is None


def test_serial_killer_receives_winner_rewards():
    g = role_game("جانی سریالی")
    for uid, p in g.s.players.items():
        p.alive = uid == 1
    g._check_win()
    assert g.s.winner.startswith("جانی سریالی")
    assert g.s.players[1].xp == 120 and g.s.players[1].coins == 60


def test_hunter_last_shot_on_life_imprisonment():
    g = role_game("شکارچی")
    g.set_hunter(1, 4)
    g.s.players[1].custody = Custody.TEMP_JAIL
    g.s.players[1].custody_nights = g.temp_jail_nights - 1
    g.s.pending_jail.append(1)
    g._advance_custody()
    assert g.s.players[1].custody is Custody.LIFE_JAIL
    assert not g.s.players[4].alive


def test_pause_preserves_remaining_time(monkeypatch):
    g = game()
    monkeypatch.setattr("karagah.engine._time.time", lambda: 1000)
    g.s.deadline = 1030
    g.pause()
    assert g.remaining() == 30
    monkeypatch.setattr("karagah.engine._time.time", lambda: 2000)
    g.resume()
    assert g.s.deadline == 2030


def test_pause_at_zero_does_not_remove_timer(monkeypatch):
    g = game()
    monkeypatch.setattr("karagah.engine._time.time", lambda: 1000)
    g.s.deadline = 1000
    g.pause(); g.resume()
    assert g.s.deadline == 1000


def test_paused_game_rejects_night_action():
    g = role_game("قاتل")
    g.pause()
    with pytest.raises(RuleError):
        g.night_action(1, 4)


@pytest.mark.parametrize("command", ["startgame", "dawn", "discuss", "vote", "closevote"])
def test_outsider_cannot_control_phases(command):
    g = game()
    if command in ("discuss", "vote", "closevote"):
        g.resolve_night()
    if command in ("vote", "closevote"):
        g.open_discussion()
    if command == "closevote":
        g.open_vote()
    before = copy.deepcopy(g.s)
    response = bot.handle(command, GROUP, 999, "Outsider")
    assert not response["ok"]
    assert g.s == before


def test_start_twice_rejected():
    g = game()
    with pytest.raises(RuleError):
        g.start()


def test_dead_player_cannot_petition_jury():
    g = role_game("شهروند")
    interrogate(g); g.resolve_night()
    g.s.players[1].alive = False
    with pytest.raises(RuleError):
        g.request_jury(1)


def test_outsider_petition_does_not_mutate_requests():
    g = role_game("شهروند")
    interrogate(g); g.resolve_night()
    before = copy.deepcopy(g.s.jury_requests)
    response = bot.handle("jury", GROUP, 999)
    assert not response["ok"]
    assert g.s.jury_requests == before


def test_verdict_cannot_corrupt_active_jury():
    g = role_game("شهروند")
    interrogate(g); g.resolve_night()
    g.request_jury(1); g.request_jury(5)
    assert g.s.phase is Phase.JURY
    with pytest.raises(RuleError):
        g.officer_verdict(2, False)


def test_repeated_ballot_does_not_farm_xp():
    g = role_game("شهروند")
    g.resolve_night(); g.open_discussion(); g.open_vote()
    for _ in range(10):
        g.vote(1, 3)
    g.s.players[3].alive = False
    g._check_win()
    assert g.s.players[1].xp == 120 + 15


def test_banned_user_cannot_join():
    bot.handle("new", GROUP, 1)
    db.touch_user(2, "Banned"); db.ban(2)
    assert not bot.handle("join", GROUP, 2)["ok"]
    assert 2 not in bot.GAMES[GROUP].s.players


@pytest.mark.parametrize("role", list(ROLES), ids=[f"role-{i+1}" for i in range(18)])
def test_advertised_role_reachable_in_a_supported_composition(role):
    assert any(role in composition for composition in COMPOSITIONS.values()), "Advertised but not assignable in a standard game"


def test_finalization_retries_after_write_failure(monkeypatch):
    g = game()
    for p in g.s.players.values():
        if p.align is Align.KILLER:
            p.alive = False
    original = db.record_results
    def unavailable(_):
        raise RuntimeError("simulated temporary DB failure")
    monkeypatch.setattr(db, "record_results", unavailable)
    assert not bot.handle("dawn", GROUP, 1)["ok"]
    monkeypatch.setattr(db, "record_results", original)
    assert bot.handle("end", GROUP, 1)["ok"]
    assert db.q_user(1)["games"] == 1


def test_ended_result_available_after_restart():
    g = game()
    for p in g.s.players.values():
        if p.align is Align.KILLER:
            p.alive = False
    assert bot.handle("dawn", GROUP, 1)["ok"]
    bot.GAMES.clear(); bot.restore_games()
    assert bot.handle("end", GROUP, 1)["ok"]


def test_snapshot_roundtrip_file_database(tmp_path):
    path = str(tmp_path / "isolated.sqlite3")
    db.reset(path)
    g = game()
    bot.handle("status", GROUP, 1)
    before = copy.deepcopy(g.s)
    db.reset(path); bot.GAMES.clear()
    assert bot.restore_games() == 1
    assert bot.GAMES[GROUP].s == before
