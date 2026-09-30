"""نسخه ۴: قواعد دقیق‌تر (RULES.md) و رفع همه‌ی یافته‌های playtest.

هر تست یک یافته‌ی گزارش playtest را می‌بندد؛ نام تست همان قاعده است.
"""
import asyncio
from types import SimpleNamespace

import pytest

from karagah import bot, config, db, engine, telegram_app
from karagah.bot import GAMES, handle
from karagah.engine import Game, RuleError
from karagah.models import Align, Custody, Phase
from karagah.roles import ROLES, SCENARIOS, composition, validate_composition


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    bot._PENDING.clear()
    yield
    GAMES.clear()
    bot.REQUIRE_READY = False


CHAT = 4040


def _started(n=7, case=5, chat=CHAT, scenario="classic"):
    handle("new", chat, 1, "Host")
    if scenario != "classic":
        handle("scenario", chat, 1, arg=scenario)
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, arg=str(case))
    return GAMES[chat]


def _role(g, name):
    return next((p for p in g.s.players.values() if p.role == name), None)


def _city(g, *skip):
    ids = {p.uid if hasattr(p, "uid") else p for p in skip}
    return next(p for p in g.s.alive_players()
                if p.align is Align.CITY and p.uid not in ids and p.uid != g.s.officer_uid)


def _to_interrogation(g, target, chat=CHAT):
    """شب → صبح → گفتگو → رای همه به target → بازجویی (با uid سیستم)."""
    if g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
        handle("dawn", chat)
    handle("discuss", chat)
    handle("vote", chat)
    for p in g.s.alive_players():
        if p.can_vote and p.uid != target:
            handle("castvote", chat, p.uid, arg=str(target))
    handle("closevote", chat)
    assert g.s.suspect_uid == target


def _storm_free(g):
    """روزی انتخاب کن که طوفان حمله را لغو نکند."""
    import random
    g.s.day = next(d for d in range(g.s.day, g.s.day + 60)
                   if not (0.12 <= random.Random(g.s.chat_id * 1000 + d).random() < 0.22))


# ───────── سناریوها ─────────
def test_every_role_is_dealt_in_some_scenario():
    dealt = {r for _n, _d, comps in SCENARIOS.values() for c in comps.values() for r in c}
    assert dealt == set(ROLES)


@pytest.mark.parametrize("key", list(SCENARIOS))
def test_every_scenario_is_balanced_for_4_to_10(key):
    for n in range(4, 11):
        assert validate_composition(n, key), (key, n)
        assert len(composition(n, key)) == n


def test_only_host_picks_scenario_and_only_in_lobby():
    handle("new", CHAT, 1, "Host")
    handle("join", CHAT, 2, "P2")
    assert handle("scenario", CHAT, 2, arg="chaos")["ok"] is False
    assert handle("scenario", CHAT, 1, arg="chaos")["ok"]
    assert GAMES[CHAT].scenario == "chaos"
    assert "آشوب" in handle("status", CHAT, 1)["text"] or GAMES[CHAT].s.scenario == "chaos"
    for i in range(3, 7):
        handle("join", CHAT, i, f"P{i}")
    handle("startgame", CHAT, 1)
    assert sorted(p.role for p in GAMES[CHAT].s.players.values()) == sorted(composition(6, "chaos"))
    assert handle("scenario", CHAT, 1, arg="classic")["ok"] is False


# ───────── دسترسی به دکمه‌های فاز ─────────
def test_only_host_starts_the_game():
    handle("new", CHAT, 1, "Host")
    for i in range(2, 6):
        handle("join", CHAT, i, f"P{i}")
    assert handle("startgame", CHAT, 3)["ok"] is False
    assert GAMES[CHAT].s.phase is Phase.LOBBY
    assert handle("startgame", CHAT, 1)["ok"]


def test_killer_cannot_close_the_night_before_others_act():
    g = _started()
    killer = _role(g, "قاتل")
    handle("act", CHAT, killer.uid, arg=str(_city(g, killer).uid))
    r = handle("dawn", CHAT, killer.uid)
    assert r["ok"] is False and "⏳" in r["text"]
    assert g.s.phase is Phase.NIGHT


def test_outsider_cannot_advance_any_phase():
    g = _started()
    for cmd in ("dawn", "discuss", "vote", "closevote", "closejury"):
        assert handle(cmd, CHAT, 99999)["ok"] is False
    assert g.s.phase is Phase.NIGHT


def test_host_waits_for_pending_actions_until_deadline():
    g = _started()
    assert g.pending_actors()
    assert handle("dawn", CHAT, 1)["ok"] is False          # هنوز اکشن‌ها نیامده
    g.s.deadline = 0                                        # مهلت گذشت
    assert handle("dawn", CHAT, 1)["ok"]


def test_everyone_acted_means_any_player_can_end_the_night():
    g = _started()
    for u in list(g.pending_actors()):
        handle("act", CHAT, u, arg=str(g.legal_targets(u)[0]))
    assert handle("dawn", CHAT, 2)["ok"]


def test_paused_game_cannot_be_advanced_by_buttons():
    g = _started()
    handle("pause", CHAT, 1)
    g.s.deadline = 0
    assert handle("dawn", CHAT, 1)["ok"] is False


# ───────── شب: بازداشت، هم‌تیمی، جانشینی ─────────
def test_detained_suspect_is_immune_to_night_kills():
    g = _started()
    x = _city(g)
    _to_interrogation(g, x.uid)
    killer = _role(g, "قاتل")
    assert x.uid not in g.legal_targets(killer.uid)
    with pytest.raises(RuleError):
        g.night_action(killer.uid, x.uid)


def test_killers_cannot_target_teammates():
    g = _started(7)
    killer, acc = _role(g, "قاتل"), _role(g, "همدست")
    assert acc.uid not in g.legal_targets(killer.uid)
    assert killer.uid not in g.legal_targets(acc.uid)


def test_every_killer_knows_the_whole_team_including_the_spy():
    g = _started(9, scenario="court")
    spy = _role(g, "خبرچین")
    assert any("هم‌تیمی" in k for k in spy.knows)


def test_kill_passes_to_the_accomplice_when_the_killer_is_out():
    g = _started(7)
    killer, acc = _role(g, "قاتل"), _role(g, "همدست")
    killer.custody = Custody.LIFE_JAIL          # قاتل حبس ابد گرفت
    g.resolve_night()
    assert g.ability_of(acc) == "kill"
    assert any("چاقو دست توست" in n for n in acc.notes)
    g.s.phase = Phase.NIGHT
    victim = _city(g, acc)
    g.night_action(acc.uid, victim.uid)
    _storm_free(g)
    r = g.resolve_night()
    assert victim.uid in r["killed"] or victim.uid in [u for u in g.s.players if not g.s.players[u].alive]


def test_heir_is_announced_privately_not_to_the_town():
    g = _started(7)
    _role(g, "قاتل").custody = Custody.LIFE_JAIL
    r = handle("dawn", CHAT)
    assert "چاقو" not in r["text"]
    acc = _role(g, "همدست")
    assert any(m["chat"] == acc.uid and "چاقو" in m["text"] for m in r["outbox"])


def test_player_without_legal_targets_is_not_awaited():
    g = _started(4)
    killer = _role(g, "قاتل")
    for p in g.s.players.values():               # همه‌ی بقیه بازداشت‌اند
        if p.uid != killer.uid:
            p.custody = Custody.TEMP_JAIL
    assert g.legal_targets(killer.uid) == []
    assert killer.uid not in g.pending_actors()


def test_doctor_cannot_repeat_even_after_switching_targets():
    g = _started(7)
    doc = _role(g, "پزشک")
    a, b = _city(g, doc), _city(g, doc, _city(g, doc))
    g.night_action(doc.uid, a.uid)
    g.resolve_night()
    g.s.phase = Phase.NIGHT
    g.night_action(doc.uid, b.uid)               # اول کس دیگر…
    with pytest.raises(RuleError):
        g.night_action(doc.uid, a.uid)           # …بعد هدفِ دیشب: باز هم ممنوع


def test_detective_cooldown_survives_the_dawn():
    g = _started(7)
    det = _role(g, "کارآگاه")
    a = _city(g, det)
    g.night_action(det.uid, a.uid)
    g.resolve_night()
    g.s.phase = Phase.NIGHT
    assert a.uid not in g.legal_targets(det.uid)


def test_suspect_is_not_counted_as_idle():
    g = _started(7)
    killer = _role(g, "قاتل")
    _to_interrogation(g, killer.uid)
    assert killer.uid not in g.pending_actors()
    before = killer.missed
    handle("dawn", CHAT)
    assert killer.missed == before


# ───────── بازجویی و حکم ─────────
def test_officer_as_suspect_goes_to_an_automatic_jury():
    g = _started(7)
    off = g.s.players[g.s.officer_uid]
    _to_interrogation(g, off.uid)
    r = handle("dawn", CHAT)
    assert g.s.phase is Phase.JURY and g.s.auto_jury
    assert any(b["callback_data"].startswith("jury:")
               for row in r["keyboard"]["inline_keyboard"] for b in row)
    with pytest.raises(RuleError):
        g.officer_verdict(off.uid, False)        # خودش را تبرئه نمی‌کند


def test_dead_officer_cannot_rule_and_jury_takes_over():
    g = _started(7)
    x = _city(g)
    _to_interrogation(g, x.uid)
    g.s.players[g.s.officer_uid].alive = False
    handle("dawn", CHAT)
    assert g.s.phase is Phase.JURY
    for p in g.s.alive_players():
        if p.can_vote:
            handle("juryvote", CHAT, p.uid, arg="0")
    handle("closejury", CHAT)
    assert x.custody is Custody.TEMP_JAIL        # تبرئه نکرد + بازجو نیست = حبس موقت


def test_stale_verdict_button_is_refused():
    g = _started(7)
    x = _city(g)
    _to_interrogation(g, x.uid)
    handle("dawn", CHAT)
    handle("verdict", CHAT, g.s.officer_uid, arg=f"{x.uid}:0")
    y = _city(g, x)
    _to_interrogation(g, y.uid)
    handle("dawn", CHAT)
    cmd, arg = telegram_app.parse_callback(f"ver:{x.uid}:1")   # دکمه‌ی پیامِ دیروز
    r = handle(cmd, CHAT, g.s.officer_uid, arg=arg)
    assert r["ok"] is False and y.custody is Custody.INTERROGATION


def test_discussion_waits_for_the_verdict():
    g = _started(7)
    x = _city(g)
    _to_interrogation(g, x.uid)
    handle("dawn", CHAT)
    assert handle("discuss", CHAT)["ok"] is False
    handle("verdict", CHAT, g.s.officer_uid, arg="1")
    assert handle("discuss", CHAT)["ok"]


def test_question_reaches_the_suspect_and_answer_reaches_the_officer():
    g = _started(7)
    x = _city(g)
    _to_interrogation(g, x.uid)
    off = g.s.officer_uid
    r = handle("ask", CHAT, off, arg="کجا بودی؟")
    assert r["private"]
    assert any(m["chat"] == x.uid and "کجا بودی" in m["text"] for m in r["outbox"])
    r = handle("answer", CHAT, x.uid, arg="در کتابخانه")
    assert any(m["chat"] == off and "کتابخانه" in m["text"] for m in r["outbox"])
    assert handle("answer", CHAT, _city(g, x).uid, arg="من")["ok"] is False


def test_defense_is_announced_to_the_group():
    g = _started(7)
    x = _city(g)
    _to_interrogation(g, x.uid)
    r = handle("defense", CHAT, x.uid, arg="من بی‌گناهم")
    assert r["ok"] and r["announce"] and "آخرین دفاع" in r["text"]


def test_jury_requests_only_from_players_in_the_game():
    g = _started(7)
    x = _city(g)
    _to_interrogation(g, x.uid)
    handle("dawn", CHAT)
    r = handle("jury", CHAT, 99999)
    assert r["ok"] is False and "خطای داخلی" not in r["text"]
    dead = _city(g, x)
    dead.alive = False
    assert handle("jury", CHAT, dead.uid)["ok"] is False


# ───────── رای ─────────
def test_abstain_counts_as_voted_but_not_in_the_tally():
    g = _started(7)
    handle("dawn", CHAT); handle("discuss", CHAT); handle("vote", CHAT)
    u = next(p.uid for p in g.s.alive_players() if p.can_vote)
    r = handle("castvote", CHAT, u, arg="0")
    assert r["ok"] and "ممتنع" in r["text"]
    assert u not in g.pending_actors()


def test_runoff_is_only_between_the_tied():
    g = _started(7)
    handle("dawn", CHAT); handle("discuss", CHAT); handle("vote", CHAT)
    v = [p.uid for p in g.s.alive_players() if p.can_vote]
    handle("castvote", CHAT, v[2], arg=str(v[0]))
    handle("castvote", CHAT, v[3], arg=str(v[1]))
    r = handle("closevote", CHAT)
    assert g.s.phase is Phase.VOTE and "دور دوم" in r["text"]
    cbs = {b["callback_data"] for row in r["keyboard"]["inline_keyboard"] for b in row}
    assert {f"vote:{v[0]}", f"vote:{v[1]}"} <= cbs and f"vote:{v[4]}" not in cbs
    assert handle("castvote", CHAT, v[2], arg=str(v[4]))["ok"] is False


def test_vote_edits_do_not_inflate_accuracy():
    g = _started(7)
    killer = _role(g, "قاتل")
    handle("dawn", CHAT); handle("discuss", CHAT); handle("vote", CHAT)
    voter = _city(g).uid
    for _ in range(5):
        handle("castvote", CHAT, voter, arg=str(killer.uid))
    assert g.s.vote_history == []                # فقط هنگام بستن ثبت می‌شود
    handle("closevote", CHAT)
    assert sum(1 for _d, v, t in g.s.vote_history if v == voter) == 1


# ───────── رای اضطراری ─────────
def test_sos_is_refused_in_lobby_and_at_night():
    handle("new", CHAT, 1, "Host")
    for i in range(2, 6):
        handle("join", CHAT, i, f"P{i}")
    for u in (1, 2, 3, 4):
        handle("sos", CHAT, u, arg="5")
    assert GAMES[CHAT].s.players[5].custody is Custody.FREE
    handle("startgame", CHAT, 1)
    g = GAMES[CHAT]
    with pytest.raises(RuleError):
        g.sos(1, 2)                               # شب


# ───────── برد، امتیاز، سقف روز ─────────
def test_serial_killer_wins_a_duel_and_gets_winner_xp():
    g = _started(10, scenario="chaos")
    sk = _role(g, "جانی سریالی")
    other = _city(g, sk)
    for p in g.s.players.values():
        if p.uid not in (sk.uid, other.uid):
            p.alive = False
    g._check_win()
    assert g.s.winner.startswith("جانی")
    assert g.is_winner(sk) and sk.xp >= 120


def test_town_does_not_win_while_the_serial_killer_lives():
    g = _started(10, scenario="chaos")
    for p in g.s.players.values():
        if p.align is Align.KILLER:
            p.custody = Custody.LIFE_JAIL
    g._check_win()
    assert g.s.winner is None


def test_survivor_neutrals_win_alongside_the_winner():
    g = _started(8, scenario="chaos")
    grocer = _role(g, "بقال محله")
    for p in g.s.players.values():
        if p.align is Align.KILLER or p.role == "جانی سریالی":
            p.custody = Custody.LIFE_JAIL
    g._check_win()
    assert g.s.winner.startswith("شهر") and g.is_winner(grocer)
    assert "کنار برنده" in g.ending_report()


def test_a_dead_scapegoat_cannot_win_by_posthumous_life_jail():
    g = _started(6)
    goat = _role(g, "سپر بلا")
    goat.alive = False
    goat.custody = Custody.LIFE_JAIL
    g._check_win()
    assert not (g.s.winner or "").startswith("سپر")


def test_hunter_shoots_when_given_life_jail():
    g = _started(9)
    hunter = _role(g, "شکارچی")
    victim = _city(g, hunter)
    g.set_hunter(hunter.uid, victim.uid)
    hunter.custody, hunter.custody_nights = Custody.TEMP_JAIL, 1
    g.s.fate_pair = None
    r = g.resolve_night()
    assert hunter.custody is Custody.LIFE_JAIL
    assert victim.uid in r["killed"]


def test_day_cap_ends_a_stalled_game_in_a_draw(monkeypatch):
    monkeypatch.setattr(engine, "MAX_DAYS", 2)
    g = _started(7)
    g.s.day = 3
    g.resolve_night()
    assert g.s.phase is Phase.END and g.s.winner.startswith("بدون برنده")


# ───────── تایمر: همان پیام کامل ─────────
def test_timer_dawn_posts_the_full_morning_message():
    g = _started(7)
    g.s.deadline = 0
    r = handle("tick", CHAT)
    assert r["advanced"] and "کشته‌شده" in r["text"] and "مدرک" in r["text"]


def test_timer_opens_the_vote_with_vote_buttons():
    g = _started(7)
    handle("dawn", CHAT); handle("discuss", CHAT)
    g.s.deadline = 0
    r = handle("tick", CHAT)
    cbs = [b["callback_data"] for row in r["keyboard"]["inline_keyboard"] for b in row]
    assert g.s.phase is Phase.VOTE and any(c.startswith("vote:") for c in cbs)


def test_morning_times_out_into_discussion_or_jury():
    g = _started(7)
    handle("dawn", CHAT)
    g.s.deadline = 0
    handle("tick", CHAT)
    assert g.s.phase is Phase.DISCUSSION
    x = _city(g)
    handle("vote", CHAT)
    for p in g.s.alive_players():
        if p.can_vote and p.uid != x.uid:
            handle("castvote", CHAT, p.uid, arg=str(x.uid))
    handle("closevote", CHAT); handle("dawn", CHAT)
    g.s.deadline = 0
    handle("tick", CHAT)                           # بازجو حکم نداد → هیئت منصفه
    assert g.s.phase is Phase.JURY
    g.s.deadline = 0
    handle("tick", CHAT)                           # هیئت منصفه‌ی خالی → حبس موقت
    assert x.custody is Custody.TEMP_JAIL


# ───────── پیام‌ها: اعلام عمومی، پیوی، بعد از پایان ─────────
def test_role_cards_and_night_results_are_pushed_privately():
    handle("new", CHAT, 1, "Host")
    for i in range(2, 8):
        handle("join", CHAT, i, f"P{i}")
    r = handle("startgame", CHAT, 1, arg="5")
    assert {m["chat"] for m in r["outbox"]} == set(range(1, 8))
    g = GAMES[CHAT]
    det = _role(g, "کارآگاه")
    handle("act", CHAT, det.uid, arg=str(_city(g, det).uid))
    r = handle("dawn", CHAT)
    assert any(m["chat"] == det.uid and "→" in m["text"] for m in r["outbox"])
    assert all("→ پاک" not in r["text"] and "→ مشکوک" not in r["text"] for _ in [0])


def test_public_steps_are_flagged_as_announcements():
    g = _started(7)
    assert handle("dawn", CHAT)["announce"]
    assert handle("discuss", CHAT)["announce"]
    assert handle("vote", CHAT)["announce"]


def test_announcement_pressed_in_private_goes_to_the_group():
    g = _started(7)
    sent = []

    class _Bot:
        async def send_message(self, chat_id, text, **kw):
            sent.append((chat_id, text))

    upd = SimpleNamespace(
        effective_chat=SimpleNamespace(id=1, type="private"),
        effective_user=SimpleNamespace(id=1, first_name="Host"),
        callback_query=None, get_bot=lambda: _Bot())
    g.s.deadline = 0
    res = telegram_app._dispatch(upd, "dawn", "")
    asyncio.run(telegram_app._reply(upd, res))
    assert sent[0][0] == CHAT and "صبح روز" in sent[0][1]
    assert sent[1][0] == 1 and "اعلام شد" in sent[1][1]


def test_notes_reachable_from_private_after_the_game_ends():
    g = _started(4)
    for p in g.s.players.values():
        if p.align is Align.KILLER:
            p.custody = Custody.LIFE_JAIL
    g._check_win()
    handle("status", CHAT, 1)
    assert bot.route_chat("notes", 2, 2, private=True) == CHAT


def test_banned_user_cannot_press_game_buttons(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [1])
    g = _started(7)
    killer = _role(g, "قاتل")
    handle("admin_ban", CHAT, 1, arg=str(killer.uid))
    assert handle("act", CHAT, killer.uid)["ok"] is False


def test_hunter_menu_button_opens_the_target_list():
    g = _started(9)
    hunter = _role(g, "شکارچی")
    r = handle("hunter", CHAT, hunter.uid)
    assert r["ok"] and any(b["callback_data"].startswith("hunter:")
                           for row in r["keyboard"]["inline_keyboard"] for b in row)
    assert "ورودی نامعتبر" not in handle("hunter", CHAT, _city(g, hunter).uid)["text"]


def test_non_players_cannot_vote_on_evidence():
    _started(7)
    r = handle("interp", CHAT, 99999)
    assert r["ok"] is False


# ───────── مستندات ─────────
def test_rules_md_matches_the_code():
    """جدول سناریوهای RULES.md باید دقیقاً همان SCENARIOS باشد."""
    from pathlib import Path
    fa = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    text = (Path(__file__).resolve().parent.parent / "RULES.md").read_text(encoding="utf-8")
    for key, (name, _d, comps) in SCENARIOS.items():
        assert f"### 🎭 {name} (`{key}`)" in text
        for n, roles in comps.items():
            k = sum(1 for r in roles if ROLES[r].align is Align.KILLER)
            row = f"| {str(n).translate(fa)} | {str(k).translate(fa)} | {'، '.join(roles)} |"
            assert row in text, row
    assert f"MAX_DAYS={config.MAX_DAYS}" in text
