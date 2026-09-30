"""Finite case/size coverage plus complete deterministic legal-play journeys."""
import pytest
from karagah import bot
from karagah.models import Align, Phase, Custody
from .helpers import game, GROUP


@pytest.mark.parametrize("n", range(4, 11))
@pytest.mark.parametrize("case", range(1, 41))
def test_all_case_size_opening_cycles(n, case):
    g = game(n=n, case=case)
    assert len(g.s.players) == n
    assert sum(p.role == "بازجو" for p in g.s.players.values()) == 1
    assert len({e["code"] for e in g.s.case.evidence}) == 6
    for cmd in ("dawn", "discuss", "vote", "closevote"):
        result = bot.handle(cmd, GROUP, 1)
        assert result["ok"], result["text"]
    assert g.s.phase is Phase.NIGHT and g.s.day == 2
    assert not g.s.winner


@pytest.mark.parametrize("n", range(4, 11))
@pytest.mark.parametrize("seed", [0, 1, 7, 19, 42, 99])
def test_complete_city_journey_through_public_commands(n, seed):
    """Harness knows roles to choose a winning strategy; players still use legal commands.

    No direct edits to custody, phase, death, or winner; no kills are submitted.
    Arrest independent killer first to avoid accidentally accepting early city victory.
    """
    g = game(n=n, seed=seed)
    for step in range(80):
        if g.s.phase is Phase.END:
            break
        if g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
            assert bot.handle("dawn", GROUP, 1)["ok"]
        elif g.s.phase is Phase.MORNING:
            if g.s.suspect_uid:
                assert bot.handle("verdict", GROUP, g.s.officer_uid, arg="1")["ok"]
            else:
                assert bot.handle("discuss", GROUP, 1)["ok"]
        elif g.s.phase is Phase.DISCUSSION:
            assert bot.handle("vote", GROUP, 1)["ok"]
        elif g.s.phase is Phase.VOTE:
            targets = [p for p in g.s.players.values() if p.can_vote and
                       (p.align is Align.KILLER or p.role == "جانی سریالی")]
            targets.sort(key=lambda p: p.role != "جانی سریالی")
            if targets:
                for p in g.s.players.values():
                    if p.can_vote and p.uid != targets[0].uid:
                        assert bot.handle("castvote", GROUP, p.uid, arg=str(targets[0].uid))["ok"]
            assert bot.handle("closevote", GROUP, 1)["ok"]
        else:
            pytest.fail(f"Unexpected phase {g.s.phase}; seed={seed}, n={n}, step={step}")
    assert g.s.phase is Phase.END, f"Turn cap is failure, not a completed match: n={n}, seed={seed}"
    assert g.s.winner.startswith("شهر")
    assert all(not p.in_game for p in g.s.players.values() if p.align is Align.KILLER or p.role == "جانی سریالی")
    reveal = bot.handle("end", GROUP, 1)
    assert reveal["ok"]
    assert all(p.role in reveal["text"] for p in g.s.players.values())
    from karagah import db
    before = db.q_user(1)["xp"]
    assert bot.handle("end", GROUP, 1)["ok"]
    assert db.q_user(1)["xp"] == before


def test_jury_acceptance_without_manually_setting_custody():
    g = game(n=6)
    target = next(p.uid for p in g.s.players.values() if p.uid != g.s.officer_uid and p.align is Align.CITY)
    for cmd in ("dawn", "discuss", "vote"):
        assert bot.handle(cmd, GROUP, 1)["ok"]
    for p in g.s.players.values():
        if p.uid != target:
            assert bot.handle("castvote", GROUP, p.uid, arg=str(target))["ok"]
    assert bot.handle("closevote", GROUP, 1)["ok"]
    assert not bot.handle("verdict", GROUP, g.s.officer_uid, arg="0")["ok"]
    assert bot.handle("dawn", GROUP, 1)["ok"]
    jurors = [p.uid for p in g.s.players.values() if p.can_vote]
    for uid in jurors[:2]:
        assert bot.handle("jury", GROUP, uid)["ok"]
    for uid in jurors:
        assert bot.handle("juryvote", GROUP, uid, arg="1")["ok"]
    assert bot.handle("closejury", GROUP, 1)["ok"]
    assert g.s.players[target].custody is Custody.FREE
    assert g.s.phase is Phase.MORNING
