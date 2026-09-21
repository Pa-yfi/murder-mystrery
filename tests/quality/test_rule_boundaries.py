"""Additional target-rule boundaries; failures are honest release-gate failures."""
import copy
import pytest
from karagah import bot
from karagah.models import Phase, Custody
from karagah.engine import RuleError
from .helpers import role_game, interrogate, GROUP


def jury_game():
    g = role_game("شهروند")
    interrogate(g); g.resolve_night()
    g.request_jury(1); g.request_jury(5)
    assert g.s.phase is Phase.JURY
    return g


@pytest.mark.parametrize("yes_count", [2, 3, 4, 5])
def test_jury_sixty_percent_boundary_with_full_turnout(yes_count):
    g = jury_game()
    jurors = [p.uid for p in g.s.players.values() if p.can_vote]
    assert len(jurors) == 5
    for i, uid in enumerate(jurors):
        g.jury_vote(uid, i < yes_count)
    g.close_jury()
    assert (g.s.players[4].custody is Custody.FREE) is (yes_count >= 3)


def test_one_vote_cannot_acquit_without_quorum():
    g = jury_game(); g.jury_vote(1, True); g.close_jury()
    assert g.s.players[4].custody is not Custody.FREE


def test_officer_cannot_acquit_self():
    g = role_game("بازجو")
    interrogate(g, target=1); g.resolve_night()
    with pytest.raises(RuleError):
        g.officer_verdict(1, False)


def test_empty_survivor_set_is_draw_not_city_win():
    g = role_game("شهروند")
    for p in g.s.players.values():
        p.alive = False
    g._check_win()
    assert not (g.s.winner or "").startswith("شهر")


def test_suspect_death_closes_interrogation_state():
    g = role_game("قاتل")
    interrogate(g)
    # Isolate attack from random weather by selecting a known non-storm chat/day.
    import random
    while 0.12 <= random.Random(g.s.chat_id * 1000 + g.s.day).random() < 0.22:
        g.s.chat_id += 1
    g.night_action(1, 4); g.resolve_night()
    assert not g.s.players[4].alive
    assert g.s.suspect_uid is None


def test_evidence_interpretation_requires_membership():
    g = role_game("شهروند")
    before = copy.deepcopy(g.s.interp_votes)
    result = bot.handle("interp", GROUP, 999, arg="E1:0")
    assert not result["ok"]
    assert g.s.interp_votes == before


def test_lab_requires_membership():
    g = role_game("شهروند")
    result = bot.handle("lab", GROUP, 999, arg="E1")
    assert not result["ok"]
    assert not g.s.lab_queue


def test_completed_game_rejects_emergency_detention():
    g = role_game("شهروند")
    g.s.players[3].alive = False; g._check_win()
    assert g.s.phase is Phase.END
    with pytest.raises(RuleError):
        g.sos(1, 4)
