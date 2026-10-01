"""نسخه ۷: جریانِ زنده‌ی بازی.

- هر فراخوانیِ ربات وسط بازی (/start، /menu، 🏠، متن در پیوی) بازیِ جاری را نشان می‌دهد، نه منو.
- شب بسته نمی‌شود تا همه‌ی نقش‌ها تصمیم بگیرند (هدف یا «🙅 کاری نمی‌کنم»)؛ آخرین تصمیم صبح را می‌آورد.
- مهلت تمام شد و کسی تصمیم نگرفته → یک بار فرصتِ اضافه + یادآوری خصوصی؛ بعد «کاری نکرد».
- شبِ بازجویی منتظرِ «✅ بازجویی تمام شد» بازجو هم می‌ماند.
- ساعتِ فاز: شب نامِ کسی را نمی‌برد؛ مسیرِ روز/شب درست است.
"""
import pytest

from karagah import bot, db, ui
from karagah.bot import GAMES, handle
from karagah.models import Align, Custody, Phase

CHAT = -7070


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    bot._PENDING.clear()
    bot._ACTIVE_TABLE.clear()
    yield
    GAMES.clear()


def _started(n=7, chat=CHAT, scenario="classic"):
    handle("new", chat, 1, "Host")
    if scenario != "classic":
        handle("scenario", chat, 1, arg=scenario)
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, arg="5")
    return GAMES[chat]


def _role(g, name):
    return next((p for p in g.s.players.values() if p.role == name and p.in_game), None)


# ───────── منو وسط بازی ─────────
@pytest.mark.parametrize("cmd", ["start", "menu", "back"])
def test_calling_the_bot_in_the_group_mid_game_shows_the_game(cmd):
    g = _started()
    r = handle(cmd, CHAT, 3)
    assert r["ok"] and "بازیِ جاری" in r["text"] and "شبِ ۱" in r["text"]
    cbs = [b["callback_data"] for row in r["keyboard"]["inline_keyboard"] for b in row if "callback_data" in b]
    assert "act" in cbs and "fullmenu" in cbs
    assert "منوی اصلی" in handle("fullmenu", CHAT, 3)["text"]


def test_calling_the_bot_in_private_mid_game_shows_my_part_of_the_game():
    g = _started()
    killer = _role(g, "قاتل")
    r = handle("menu", killer.uid, killer.uid)            # پیوی: chat = uid
    assert "بازیِ جاری" in r["text"] and "قاتل" in r["text"] and "منتظرِ تصمیمِ توست" in r["text"]
    cbs = [b["callback_data"] for row in r["keyboard"]["inline_keyboard"] for b in row]
    assert "act" in cbs and "pass" in cbs
    assert r.get("private")


def test_outside_a_game_the_menu_is_the_menu():
    r = handle("menu", 555, 555)
    assert "منوی اصلی" in r["text"]


def test_after_the_game_ends_menu_is_the_menu_again():
    g = _started()
    g.s.phase = Phase.END
    assert "منوی اصلی" in handle("menu", CHAT, 3)["text"]


# ───────── شب منتظرِ همه ─────────
def test_night_waits_for_every_role_then_the_last_decision_brings_morning():
    g = _started()
    pend = list(g.pending_actors())
    assert len(pend) >= 2
    handle("act", CHAT, pend[0], arg=str(g.legal_targets(pend[0])[0]))
    r = handle("dawn", CHAT, 1)                         # میزبان هم نمی‌تواند زودتر ببندد
    assert not r["ok"] and "تصمیم نگرفته" in r["text"]
    for u in pend[1:-1]:
        handle("pass", CHAT, u)
    assert g.s.phase is Phase.NIGHT
    r = handle("act", CHAT, pend[-1], arg=str(g.legal_targets(pend[-1])[0]))
    assert g.s.phase is Phase.MORNING and g.s.day == 1
    assert any(m["chat"] == CHAT and "صبح روز ۱" in m["text"] for m in r["outbox"])


def test_host_cannot_close_the_night_early_even_after_half_the_time():
    g = _started()
    g.s.deadline = bot._time.time() + 5                 # بیشتر از نیمه‌ی مهلت گذشته
    assert not handle("dawn", CHAT, 1)["ok"]
    assert g.s.phase is Phase.NIGHT


def test_pass_can_be_changed_to_an_action_and_back():
    g = _started()
    doc = _role(g, "پزشک")
    t = g.legal_targets(doc.uid)[0]
    handle("act", CHAT, doc.uid, arg=str(t))
    handle("pass", CHAT, doc.uid)
    assert g.chosen_target(doc.uid) is None and g.passed(doc.uid)
    assert "_last_protect" not in g.s.night_actions          # نجاتِ لغوشده «دو شب پیاپی» نمی‌سازد
    handle("act", CHAT, doc.uid, arg=str(t))
    assert g.chosen_target(doc.uid) == t and not g.passed(doc.uid)


def test_roles_without_a_night_action_cannot_pass_and_are_never_awaited():
    g = _started()
    cit = _role(g, "شهروند")
    assert cit.uid not in g.pending_actors()
    assert not handle("pass", CHAT, cit.uid)["ok"]


def test_deadline_gives_one_grace_with_private_reminders_then_undecided_count_as_passed():
    g = _started()
    pend = set(g.pending_actors())
    g.s.deadline = 0
    r = handle("tick", CHAT)
    assert r["advanced"] and "فرصتِ اضافه" in r["text"] and g.s.phase is Phase.NIGHT
    reminded = {m["chat"] for m in r["outbox"]}
    assert pend <= reminded                                # هر منتظر در پیوی خودش یادآوری گرفت
    assert not any(g.s.players[u].name in r["text"] for u in pend)   # در گروه نام نمی‌برد
    g.s.deadline = 0
    r = handle("tick", CHAT)
    assert g.s.phase is Phase.MORNING and "کشته‌شده" in r["text"]


def test_detective_clue_check_counts_as_a_decision():
    g = _started()
    det = _role(g, "کارآگاه")
    for u in list(g.pending_actors()):
        if u != det.uid:
            handle("pass", CHAT, u)
    assert g.s.phase is Phase.NIGHT
    handle("expose", CHAT, det.uid, arg=g.s.clues[0]["code"])
    assert g.s.phase is Phase.MORNING


def test_interrogation_night_waits_for_the_officer_to_finish():
    g = _started()
    handle("dawn", CHAT)                                   # سیستم: شب ۱ → صبح
    handle("discuss", CHAT)
    handle("vote", CHAT)
    x = next(p for p in g.s.alive_players() if p.align is Align.CITY and p.uid != g.s.officer_uid)
    for p in g.s.alive_players():
        if p.can_vote and p.uid != x.uid:
            handle("castvote", CHAT, p.uid, arg=str(x.uid))
    handle("closevote", CHAT)
    assert g.s.phase is Phase.INTERROGATION and g.s.day == 2
    for u in list(g.pending_actors()):
        if u != g.s.officer_uid:
            handle("pass", CHAT, u)
    assert g.s.phase is Phase.INTERROGATION and g.pending_actors() == [g.s.officer_uid]
    r = handle("pass", CHAT, g.s.officer_uid)
    assert "بازجویی" in r["text"] and g.s.phase is Phase.MORNING


# ───────── ساعت و مسیر ─────────
def test_night_clock_names_nobody_and_shows_the_path():
    g = _started()
    view = bot.clock_view(CHAT)
    assert "شبِ ۱" in view["text"] and "📅 🌙۱▶️" in view["text"]
    assert not any(p.name in view["text"] for p in g.s.players.values())
    handle("dawn", CHAT)
    v2 = bot.clock_view(CHAT)
    # نسخه ۱۰: کارتِ صبح خودِ گزارشِ صبح است (کشته‌ها، سرنخ‌ها) و ساعت پایینش
    assert v2["key"] != view["key"] and "صبح روز ۱" in v2["text"] and "🌙۱ ☀️۱▶️" in v2["text"]
    assert "⚰️ کشته" in v2["text"] and v2["text"].index("⚰️") < v2["text"].index("📅")


def test_day_and_night_numbers_follow_night1_day1_night2_day2():
    g = _started()
    seen = [(g.s.phase, g.s.day)]
    for _ in range(3):
        handle("dawn", CHAT)
        seen.append((g.s.phase, g.s.day))
        if g.s.phase is Phase.END:
            break
        if g.s.phase is Phase.MORNING and not g.awaiting_verdict():
            handle("discuss", CHAT); handle("vote", CHAT); handle("closevote", CHAT)
            seen.append((g.s.phase, g.s.day))
        if g.s.phase is Phase.END:
            break
    nights = [d for ph, d in seen if ph in (Phase.NIGHT, Phase.INTERROGATION)]
    mornings = [d for ph, d in seen if ph is Phase.MORNING]
    assert nights[:3] == [1, 2, 3][:len(nights[:3])]
    assert mornings[:3] == nights[:len(mornings[:3])]       # صبحِ N همیشه بعد از شبِ N


def test_action_panel_outside_the_night_says_the_night_is_over():
    g = _started()
    doc = _role(g, "پزشک")
    handle("dawn", CHAT)
    r = handle("act", CHAT, doc.uid)
    assert "الان شب نیست" in r["text"] and "منتظرِ تصمیمِ توست" not in r["text"]
