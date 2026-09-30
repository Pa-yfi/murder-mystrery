"""نسخه ۶: صحنه‌ها — هر سناریو مکان، متنِ سرنخ، مشخصه‌ی ویژه و پرونده‌های خودش را دارد،
و هر مکانِ سرنخ‌دار هر روز یک جزئیاتِ تازه (و هرگز تکراری) نشان می‌دهد."""
import random

import pytest

from karagah import bot, clues as C, db, scenes as SC, ui
from karagah.bot import GAMES, handle
from karagah.cases import CASES
from karagah.models import Phase


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    bot._PENDING.clear()
    yield
    GAMES.clear()


def _start(chat, scenario="classic", n=8, case=None):
    handle("new", chat, 1, "Host")
    if scenario != "classic":
        handle("scenario", chat, 1, arg=scenario)
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, arg=str(case) if case else "")
    return GAMES[chat]


def _nights(g, k, seed=0):
    rng = random.Random(seed)
    out = []
    for _ in range(k):
        if g.s.phase is Phase.END:
            break
        for p in g.s.alive_players():
            legal = g.legal_targets(p.uid)
            if legal and g.ability_of(p):
                try:
                    g.night_action(p.uid, rng.choice(legal))
                except Exception:
                    pass
        out.append(g.resolve_night())
        g.s.phase = Phase.NIGHT
        g.s.day += 1
        g.s.night_actions.clear()
    return out


def test_case_pools_cover_all_cases_once():
    ids = [c for pool in SC.CASE_POOL.values() for c in pool]
    assert sorted(ids) == [c.cid for c in CASES]


@pytest.mark.parametrize("scen", ["classic", "court", "chaos"])
def test_scenario_gets_its_own_case_traits_and_places(scen):
    g = _start(7000 + len(scen), scen)
    assert g.s.case.cid in SC.CASE_POOL[scen]
    key = SC.extra_trait(scen)[0]
    assert all(key in p.traits for p in g.s.players.values())
    others = {SC.extra_trait(o)[0] for o in SC.CASE_POOL if o != scen}
    assert not any(k in p.traits for p in g.s.players.values() for k in others)
    _nights(g, 3)
    allowed = set(SC.LOCATIONS[scen]) | {f"🕯️ {g.s.case.place}"}
    for c in g.s.clues:
        assert c["place"] in allowed
        assert SC.trait_text(scen, c["trait"], c["value"]) in c["text"]


def test_start_clues_sit_at_the_case_scene_on_day_zero():
    g = _start(7100)
    first = [c for c in g.s.clues if c["day"] == 0]
    assert first and all(c["place"] == f"🕯️ {g.s.case.place}" for c in first)


def test_every_evidence_place_shows_a_new_detail_each_day_and_never_repeats():
    for chat in range(7200, 7215):
        g = _start(chat, ("classic", "court", "chaos")[chat % 3], n=9)
        _nights(g, 6, seed=chat)
        for loc, rows in SC.history(g.s).items():
            details = [d for _, d in rows]
            days = [d for d, _ in rows]
            assert len(details) == len(set(details)), (loc, details)
            assert len(days) == len(set(days)), (loc, days)
        GAMES.clear()


def test_details_never_run_out():
    g = _start(7300)
    rng = random.Random(1)
    loc = next(iter(SC.LOCATIONS["classic"]))
    seen = set()
    for d in range(60):
        g.s.day = d + 1
        x = SC.fresh_detail(g.s, loc, rng)
        assert x not in seen
        seen.add(x)


def test_clues_of_one_crime_share_a_place_so_location_does_not_reveal_frames():
    g = _start(7400)
    g.s.day = 5
    killer = next(p for p in g.s.alive_players() if p.role == "قاتل")
    victim = next(p for p in g.s.alive_players() if p.align.name == "CITY")
    innocent = next(p for p in g.s.alive_players() if p.uid not in (killer.uid, victim.uid)
                    and p.align.name == "CITY")
    g.s.night_event = ""
    made = g._make_clues({"kill": {killer.uid: victim.uid}, "frame": {99: innocent.uid}}, [victim.uid], [])
    places = {c["place"] for c in made}
    assert len(places) == 1


def test_morning_shows_patrol_and_board_shows_scene_map():
    g = _start(7500, "chaos")
    res = _nights(g, 3)
    rows = [r for x in res for r in x.get("patrol", [])]
    assert rows, "صحنه‌های قبلی باید هر روز چیزی تازه نشان دهند"
    assert "گشتِ صبحگاهی" in ui.patrol_block(rows)
    assert "نقشه‌ی صحنه‌ها" in ui.board(g.s)


def test_blackout_shows_no_patrol():
    g = _start(7600)
    _nights(g, 1)
    g.s.night_event = "قطعی برق 🕯️"
    from karagah import engine
    orig = engine.random.Random

    class Always(orig):                     # رویدادِ شب را روی قطعی برق نگه دار
        def random(self):
            return 0.0
    engine.random.Random = Always
    try:
        r = g.resolve_night()
    finally:
        engine.random.Random = orig
    assert g.s.night_event.startswith("قطعی برق")
    assert r["patrol"] == [] and r["clues"] == []
