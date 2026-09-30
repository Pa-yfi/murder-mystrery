"""نسخه ۵: لایه‌ی سرنخ (karagah/clues.py) — سرنخ راست به‌هم‌پیوسته، سرنخ دروغ همیشه غلط.

قاعده‌ها (RULES.md «سرنخ‌ها»):
- هر سرنخ راست یکی از مشخصاتِ واقعیِ مجرمِ همان شب است؛ پس همه‌ی سرنخ‌های راست با هم جورند.
- سرنخ دروغ (پاپوش/ردِ گمراه‌کننده) هیچ‌وقت مشخصه‌ی مجرمِ واقعیِ آن شب را نمی‌گوید.
- قطعی برق: هیچ سرنخی. قاچاقچی: ضاربِ پنهان سرنخ نمی‌گذارد.
- آزمایشگاه/کارآگاه/پزشک قانونی حقیقت را می‌گویند.
"""
import random

import pytest

from karagah import bot, clues as C, db, ui
from karagah.bot import GAMES, handle
from karagah.engine import RuleError
from karagah.models import Align, Phase
from karagah.roles import SCENARIO_RULES


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    bot._PENDING.clear()
    yield
    GAMES.clear()


def _start(chat, n=8, scenario="classic"):
    handle("new", chat, 1, "Host")
    if scenario != "classic":
        handle("scenario", chat, 1, arg=scenario)
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, arg="3")
    return GAMES[chat]


def _role(g, name):
    return next((p for p in g.s.players.values() if p.role == name and p.in_game), None)


def _play_night(g, rng):
    """هر کس توانایی دارد یک هدفِ مجاز می‌زند؛ بعد سحر."""
    for p in g.s.alive_players():
        legal = g.legal_targets(p.uid)
        if legal and g.ability_of(p):
            try:
                g.night_action(p.uid, rng.choice(legal))
            except RuleError:
                pass
    acts = g._committed_actions()
    return acts, g.resolve_night()


# ─────────────────────────── مشخصات ───────────────────────────
def test_traits_are_unique_public_profiles():
    g = _start(9001, n=10)
    keys = C.keys_for("classic")
    profiles = [tuple(p.traits[k] for k in keys) for p in g.s.players.values()]
    assert len(set(profiles)) == len(profiles)
    for p in g.s.players.values():
        assert set(p.traits) == set(keys)


def test_start_clues_follow_scenario_rules():
    for scen in ("classic", "court", "chaos"):
        g = _start(9100 + len(scen), scenario=scen)
        r = SCENARIO_RULES[scen]
        start = [c for c in g.s.clues if c["day"] == 0]
        assert sum(c["genuine"] for c in start) == r["start_true"]
        assert sum(not c["genuine"] for c in start) == r["start_false"]
        boss = g._knife_holder()
        for c in start:
            assert C.matches(g.s.players[boss], c) == c["genuine"]
        GAMES.clear()


# ─────────────────────────── راست و دروغ ───────────────────────────
@pytest.mark.parametrize("scen", ["classic", "court", "chaos"])
def test_true_clues_point_at_real_attacker_and_false_never_do(scen):
    """ویژگی اصلی: در ۳۰ بازی و چند شب، هر سرنخ راست مالِ ضاربِ واقعی و هر دروغ غلط است."""
    checked_true = checked_false = 0
    for chat in range(9200, 9230):
        g = _start(chat, n=9, scenario=scen)
        rng = random.Random(chat)
        for _ in range(3):
            if g.s.phase not in (Phase.NIGHT, Phase.INTERROGATION):
                break
            acts, res = _play_night(g, rng)
            culprits = set(acts.get("kill", {})) | set(acts.get("poison", {})) | set(g.s.poison_by.values())
            for c in res.get("clues", []):
                if c["genuine"]:
                    assert c["about"] in culprits
                    assert C.matches(g.s.players[c["about"]], c)
                    checked_true += 1
                else:
                    killers = [u for u in acts.get("kill", {}) if g.s.players[u].align is Align.KILLER]
                    for u in killers:
                        assert not C.matches(g.s.players[u], c), c
                    checked_false += 1
            if g.s.phase is Phase.END:
                break
            g.s.phase = Phase.NIGHT                 # فقط لایه‌ی شب را می‌سنجیم
            g.s.day += 1
            g.s.night_actions.clear()
        GAMES.clear()
    assert checked_true > 10 and checked_false > 5


def test_true_clues_about_same_culprit_are_connected():
    """سرنخ‌های راستِ یک مجرم هر بار مشخصه‌ی تازه‌ای می‌گویند و همه با هم جورند."""
    g = _start(9300)
    boss = g._knife_holder()
    rng = random.Random(1)
    told = {c["trait"] for c in g.s.clues if c["genuine"] and c["about"] == boss}
    keys = C.keys_for("classic")
    made = [C.true_clue(g.s, boss, rng, "kill", "خانه") for _ in range(len(keys) - len(told))]
    assert {c["trait"] for c in made}.isdisjoint(told)             # تکراری نمی‌گوید
    made += [c for c in g.s.clues if c["genuine"] and c["about"] == boss and c not in made]
    assert {c["trait"] for c in made} == set(keys)
    suspects = [p for p in g.s.players.values() if all(C.matches(p, c) for c in made)]
    assert [p.uid for p in suspects] == [boss]          # زنجیره‌ی کامل فقط یک نفر را نشان می‌دهد


def test_frame_clue_uses_framed_traits_but_not_the_killers():
    g = _start(9301)
    boss = g._knife_holder()
    rng = random.Random(2)
    for p in g.s.players.values():
        if p.uid == boss:
            continue
        c = C.false_clue(g.s, boss, rng, "frame", "خانه", framed=p.uid)
        if c is None:                                   # فقط اگر کاملاً شبیه قاتل باشد
            assert p.traits == g.s.players[boss].traits
            continue
        assert C.matches(p, c) and not C.matches(g.s.players[boss], c)
        assert c["genuine"] is False and c["about"] == p.uid


def test_blackout_leaves_no_clues():
    g = _start(9302)
    g.s.night_event = "قطعی برق 🕯️"
    before = len(g.s.clues)
    killer = _role(g, "قاتل")
    victim = next(p for p in g.s.alive_players() if p.align is Align.CITY)
    assert g._make_clues({"kill": {killer.uid: victim.uid}}, [victim.uid], []) == []
    assert len(g.s.clues) == before


def test_hidden_attacker_leaves_no_true_clue():
    g = _start(9303)
    g.s.night_event = ""
    killer = _role(g, "قاتل")
    victim = next(p for p in g.s.alive_players() if p.align is Align.CITY)
    g.s.hidden = [killer.uid]
    made = g._make_clues({"kill": {killer.uid: victim.uid}}, [victim.uid], [])
    assert not [c for c in made if c["genuine"]]


# ─────────────────────────── راستی‌آزمایی ───────────────────────────
def test_lab_reveals_truth_after_scenario_nights():
    for scen in ("classic", "court"):
        g = _start(9400 + len(scen), scenario=scen)
        c = g.s.clues[0]
        msg = g.submit_lab(c["code"])
        assert c["code"] in msg
        with pytest.raises(RuleError):
            g.submit_lab(g.s.clues[1]["code"])           # روزی یک نمونه
        due = g.s.lab_queue[c["code"]]
        assert due == g.s.day + SCENARIO_RULES[scen]["lab_nights"]
        while g.s.day < due and g.s.phase is not Phase.END:
            g.resolve_night()
            g.s.phase = Phase.NIGHT
            g.s.day += 1
        if g.s.phase is not Phase.END:
            g.resolve_night()
        assert c["verified"] is c["genuine"]
        GAMES.clear()


def test_express_lab_costs_coins_and_refunds_on_error():
    g = _start(9410)
    uid = 2
    code = g.s.clues[0]["code"]
    r = handle("lab", 9410, uid, arg=f"{code}:X")
    assert not r["ok"] and "سکه" in r["text"]
    db.spend_coins(uid, -100)
    r = handle("lab", 9410, uid, arg=f"{code}:X")
    assert r["ok"] and db.coins_of(uid) == 100 - bot.LAB_EXPRESS_COINS
    r = handle("lab", 9410, uid, arg=f"{g.s.clues[1]['code']}:X")    # روزی یک نمونه → پول برمی‌گردد
    assert not r["ok"] and db.coins_of(uid) == 100 - bot.LAB_EXPRESS_COINS


def test_detective_expose_tells_truth_and_spends_night():
    g = _start(9420)
    det = _role(g, "کارآگاه")
    for c in g.s.clues[:1]:
        res = g.expose(det.uid, c["code"])
        assert ("راست" in res) == c["genuine"]
    with pytest.raises(RuleError):
        g.expose(det.uid, g.s.clues[-1]["code"])
    legal = g.legal_targets(det.uid)
    if legal:
        with pytest.raises(RuleError):
            g.night_action(det.uid, legal[0])           # اکشنِ امشب خرجِ راستی‌آزمایی شد


def test_interp_votes_and_board_ranking_are_public_only():
    g = _start(9430)
    c = g.s.clues[0]
    assert "👍 ۱" in g.vote_interp(2, c["code"], 1)
    c["verified"] = c["genuine"]
    with pytest.raises(RuleError):
        g.vote_interp(3, c["code"], 0)
    rank = C.board_ranking(g.s)
    assert {r[0] for r in rank} == {p.uid for p in g.s.alive_players()}
    text = ui.board(g.s)
    assert "C1" in text and "genuine" not in text


def test_scenario_jury_threshold():
    g = _start(9440, scenario="court")
    assert g.jury_percent() == 50
    GAMES.clear()
    g = _start(9441)
    assert g.jury_percent() == 60


# ─────────────────────────── رابط ───────────────────────────
def test_buttons_carry_colour_styles():
    k = ui.kb([[("🚨 رای اضطراری", "sos"), ("✅ آماده‌ام", "ready"), ("🗂️ پرونده", "board")]])
    styles = [b.get("style") for b in k["inline_keyboard"][0]]
    assert styles == ["danger", "success", "primary"]


def test_group_chatter_gets_no_bot_reply():
    """گفتگوی عادی گروه (ادعا/بلوف) نباید منو یا جوابی از ربات بگیرد."""
    from playtest.table import Telegram
    from playtest.report import Report
    tg = Telegram(-777, Report())
    try:
        handle("new", -777, 1, "Host")
        before = len(tg.inbox(-777))
        tg.chat(1, "من کارآگاهم! P3 مشکوک است.")
        assert len(tg.inbox(-777)) == before + 1       # فقط خودِ پیام
    finally:
        tg.close()
