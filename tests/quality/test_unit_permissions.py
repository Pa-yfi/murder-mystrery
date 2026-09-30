"""SEC-05: all catalog roles across phase/life/custody authorization boundaries."""
import copy
import pytest
from karagah.engine import RuleError
from karagah.models import Custody, Phase
from karagah.roles import ROLES
from .helpers import role_game, interrogate

ROLE_NAMES = list(ROLES)
STATES = ["free", "interrogation", "temporary", "life", "dead"]


def set_status(p, status):
    p.alive = status != "dead"
    p.custody = {"free": Custody.FREE, "interrogation": Custody.INTERROGATION,
                 "temporary": Custody.TEMP_JAIL, "life": Custody.LIFE_JAIL, "dead": Custody.FREE}[status]


@pytest.mark.parametrize("role", ROLE_NAMES, ids=[f"role-{i+1}" for i in range(18)])
@pytest.mark.parametrize("phase", list(Phase), ids=lambda p: p.name)
@pytest.mark.parametrize("status", STATES)
def test_normal_night_capability_matrix(role, phase, status):
    g = role_game(role)
    g.s.phase = phase
    set_status(g.s.players[1], status)
    before = copy.deepcopy(g.s)
    ability = ROLES[role].ability
    allowed = phase in (Phase.NIGHT, Phase.INTERROGATION) and status == "free" and ability not in ("", "hunter")
    if allowed:
        g.night_action(1, 4)
        assert g.s.night_actions[f"{ability}:1"] == 4
        assert set(g._committed_actions()) == {ability}
    else:
        with pytest.raises(RuleError):
            g.night_action(1, 4)
        assert g.s == before


@pytest.mark.parametrize("role", ROLE_NAMES, ids=[f"role-{i+1}" for i in range(18)])
@pytest.mark.parametrize("command,authorized", [("expose", "کارآگاه"), ("hunter", "شکارچی"),
    ("hints", "بازجو"), ("ask", "بازجو"), ("verdict", "بازجو")])
def test_exclusive_capabilities_reject_all_other_roles(role, command, authorized):
    g = role_game(role)
    interrogate(g)
    if command == "verdict":
        g.resolve_night()
    invoke = {"expose": lambda: g.expose(1, "E1"), "hunter": lambda: g.set_hunter(1, 4),
              "hints": lambda: g.officer_hints(1), "ask": lambda: g.ask(1, "Where?"),
              "verdict": lambda: g.officer_verdict(1, False)}[command]
    before = copy.deepcopy(g.s)
    if role == authorized:
        invoke()
    else:
        with pytest.raises(RuleError):
            invoke()
        assert g.s == before


@pytest.mark.parametrize("role,method", [("کارآگاه", "expose"), ("شکارچی", "hunter"), ("بازجو", "hints")])
@pytest.mark.parametrize("status", ["interrogation", "temporary", "life", "dead"])
def test_ineligible_roles_lose_special_powers(role, method, status):
    g = role_game(role)
    interrogate(g)
    set_status(g.s.players[1], status)
    invoke = {"expose": lambda: g.expose(1, "E1"), "hunter": lambda: g.set_hunter(1, 4),
              "hints": lambda: g.officer_hints(1)}[method]
    with pytest.raises(RuleError):
        invoke()
