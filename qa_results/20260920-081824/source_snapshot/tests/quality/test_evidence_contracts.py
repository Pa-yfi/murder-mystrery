from karagah import bot
from karagah.cases import CASES
from karagah.models import Align
from .helpers import role_game, game, GROUP


def test_evidence_authenticity_not_predictable_by_deck_position():
    masks = {tuple(e["misleading"] for e in case.evidence) for case in CASES}
    assert len(masks) > 1, "Every case exposes the same authenticity mask, bypassing investigation"


def test_revealed_evidence_not_duplicated_after_deck_exhaustion():
    g = game()
    for _ in range(8):
        g.resolve_night(); g.open_discussion(); g.open_vote(); g.close_vote()
    assert len(g.s.revealed_evidence) == len(set(g.s.revealed_evidence))


def test_laboratory_result_contains_actionable_case_specific_information():
    g = game()
    g.submit_lab("E1")
    for _ in range(3):
        g.resolve_night(); g.open_discussion(); g.open_vote(); g.close_vote()
    results = [line for line in g.s.log if "آزمایشگاه" in line and "E1" in line and "رسید" in line]
    assert results
    # Minimum meaningful result: an actual interpretation, authenticity, identity, or timestamp.
    meaningful = [*g.s.case.evidence[0]["interpretations"], "جعلی", "اصل", "۲۱:", "۲۲:", "۲۳:"]
    assert any(term in results[0] for term in meaningful), "Generic 'narrow interpretations' message supplies no result"


def test_spy_distinguishes_questioning_from_public_nomination():
    # R02 usefulness contract: observing actual questioning must add information
    # beyond the nomination already announced publicly. Compare two worlds.
    from .helpers import interrogate
    findings = []
    for questioned in (False, True):
        g = role_game("خبرچین")
        interrogate(g)
        if questioned:
            g.ask(g.s.officer_uid, "Where were you?")
        g.night_action(1, 5); g.resolve_night()
        findings.append(list(g.s.players[1].notes))
    assert findings[0] != findings[1], "Spy only reports the public nomination, regardless of actual questioning"


def test_grocer_gets_new_daily_rumor():
    g = role_game("بقال محله")
    before = len(g.s.players[1].notes) + len(g.s.players[1].knows)
    g.resolve_night()
    after = len(g.s.players[1].notes) + len(g.s.players[1].knows)
    assert after > before


def test_trace_does_not_claim_direct_killer_for_indirect_death():
    g = role_game("پزشک")
    # Unit event fixture: target died from a hunter/linked death while doctor visited.
    g._build_traces({"protect": {1: 4}}, [4])
    assert all("قاتل بین آن‌هاست" not in line for line in g.s.traces), "A visitor is falsely guaranteed to be the killer"
