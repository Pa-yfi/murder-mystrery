"""نسخه ۹: طراحی (ساعت‌شنی، نوارِ درخشان، سربرگ‌ها، گذارهای تک‌ایموجی، افکت، آیکون)،
مرحله‌ی «آماده‌ام»، حذفِ دکمه‌های تکراری، و اینکه ربات حرفِ بی‌ربط به بازی نمی‌زند."""
import asyncio
import re

import pytest

from karagah import bot, db, theme, ui
from karagah.bot import GAMES, handle
from karagah.models import Phase

G = -9191


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    for d in (bot._PENDING, bot._ACTIVE_TABLE, bot._LAST_CB, bot._LAST_CALL, bot.LAST_ROSTER):
        d.clear()
    yield
    GAMES.clear()


def _lobby(n=5):
    handle("new", G, 1, "Host")
    for u in range(2, n + 1):
        handle("join", G, u, f"P{u}")
    return GAMES[G]


def _cbs(kb):
    return [b.get("callback_data") or b.get("url") for row in (kb or {}).get("inline_keyboard", []) for b in row]


# ───────── زبانِ بصری ─────────
def test_hourglass_flips_every_edit_and_bar_shines_and_turns_red():
    assert theme.hourglass(0) != theme.hourglass(1)
    a = theme.shiny_bar(50, 60, 0, "شب")
    b = theme.shiny_bar(50, 60, 1, "شب")
    assert "✨" in a and a != b and "🟪" in a                     # درخششِ متحرک روی رنگِ شب
    assert "🟥" in theme.shiny_bar(5, 60, 0, "شب")                # کم‌وقت → قرمز
    assert theme.shiny_bar(0, 60, 0) == "⬜" * 10


def test_transitions_are_single_emoji_frames_so_telegram_animates_them():
    for key, frames in ui.ANIM.items():
        for f in frames:
            assert len(f) <= 4 and not re.search(r"[؀-ۿ]", f), (key, f)
    assert set(ui.VOICE) == set(ui.ANIM)


def test_clock_text_changes_on_every_edit():
    g = _lobby()
    handle("startgame", G, 1, "force")
    t1 = bot.clock_view(G)["text"]
    g.s.deadline -= 5
    t2 = bot.clock_view(G)["text"]
    assert t1 != t2 and ("⏳" in t1) != ("⏳" in t2)


def test_announcements_use_ribbon_headers():
    g = _lobby(7)
    handle("startgame", G, 1, "force")
    r = handle("dawn", G)
    assert "┈┈ *صبح روز ۱* ┈┈" in r["text"]
    assert "┈┈ *گفتگو* ┈┈" in handle("discuss", G)["text"]


# ───────── دکمه‌های تکراری ─────────
def test_no_keyboard_repeats_a_destination():
    g = _lobby(7)
    seen = []
    for stage in ("lobby", "night", "morning"):
        if stage == "night":
            handle("startgame", G, 1, "force")
        if stage == "morning":
            handle("dawn", G)
        for ep in sorted(bot.ENDPOINTS):
            if ep in ("new", "blitz", "startgame", "leave", "admin_ban", "end"):
                continue
            for chat in (G, 3):
                r = handle(ep, chat, 3, "P3", "")
                cbs = [("menu" if c == "back" else c) for c in _cbs(r.get("keyboard"))]
                dup = {c for c in cbs if cbs.count(c) > 1}
                assert not dup, (stage, ep, dup)
                seen.append(ep)
    assert len(seen) > 150


def test_back_and_home_are_one_button():
    assert len(ui.back_only()["inline_keyboard"][0]) == 1


def test_live_card_has_no_redundant_refresh_or_menu():
    _lobby()
    handle("startgame", G, 1, "force")
    cbs = _cbs(bot.clock_view(G)["keyboard"])
    assert "dashboard" not in cbs and "menu" not in cbs and "fullmenu" in cbs


def test_main_menu_has_no_in_game_dead_buttons():
    cbs = _cbs(ui.main_menu(False, False))
    assert not {"act", "abilities", "dashboard", "board", "myrole", "admin"} & set(cbs)
    assert "new" in cbs and "tutorial" in cbs and "help" in cbs


# ───────── مرحله‌ی «آماده‌ام» ─────────
def test_new_lobby_is_the_live_card():
    r = handle("new", G, 1, "Host")
    assert r.get("clock") and "لابیِ کارآگاه" in r["text"] and "join" in _cbs(r["keyboard"])
    assert bot.clock_view(G)["key"] == "lobby"


def test_ready_marks_the_card_and_refreshes_the_group():
    g = _lobby(4)
    r = handle("start", 3, 3, "P3", f"ready_{G}")
    assert r.get("refresh") == G and "آماده‌ای" in r["text"] and "🟢" in r["text"]
    assert g.s.players[3].ready
    assert "✅ P3" in bot.clock_view(G)["text"]


def test_ready_without_join_joins_you():
    g = _lobby(4)
    handle("start", 77, 77, "تازه", f"ready_{G}")
    assert 77 in g.s.players and g.s.players[77].ready


def test_ready_after_start_explains_instead_of_lobby_talk():
    g = _lobby(5)
    handle("startgame", G, 1, "force")
    r = handle("start", 3, 3, "P3", f"ready_{G}")
    assert "شروع شده" in r["text"]


def test_lobby_card_counts_down_who_is_missing():
    g = _lobby(5)
    txt = ui.lobby_screen(g.s)
    assert "آماده: ۰/۵" in ui.lobby_screen(g.s).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")) or "۰/۵" in txt


# ───────── ربات فقط درباره‌ی بازی حرف می‌زند ─────────
def test_join_and_share_in_private_do_not_create_private_tables():
    for ep in ("join", "share"):
        r = handle(ep, 42, 42, "X")
        assert "گروه" in r["text"]
    assert 42 not in GAMES


def test_player_facing_text_has_no_technical_words():
    bad = re.compile(r"RULES|\.md|SQL|اسنپ‌شات|آیدی|اندپوینت|کانال|ایده ?[۰-۹\d]+|بهبود ?[۰-۹\d]+|نسخه ?[۰-۹\d]")
    g = _lobby(7)
    handle("startgame", G, 1, "force")
    for ep in sorted(bot.ENDPOINTS):
        if ep.startswith("admin") or ep in ("new", "blitz", "startgame", "leave"):
            continue
        for chat in (G, 3):
            t = handle(ep, chat, 3, "P3", "")["text"]
            assert not bad.search(t), (ep, bad.search(t).group(0), t[:120])


def test_help_and_tutorial_teach_the_current_rules():
    h = handle("help", 3, 3)["text"]
    assert "کاری نمی‌کنم" in h and "سرنخ" in h and "RULES" not in h
    t = handle("tutorial", 3, 3)["text"]
    assert "E1" not in t and "آزمایشگاه" in t and "کاشته" in t


def test_admin_pages_answer_privately():
    bot.ADMIN_IDS.append(1)
    try:
        for ep in ("admin", "admin_games", "admin_users", "admin_stats"):
            assert handle(ep, G, 1).get("private"), ep
    finally:
        bot.ADMIN_IDS.remove(1)


# ───────── افکت و آیکون (با بازگشتِ امن) ─────────
def test_role_cards_carry_fire_effect_and_winners_get_party():
    g = _lobby(5)
    r = handle("startgame", G, 1, "force")
    assert all(m.get("effect") == "fire" for m in r["outbox"] if "نقش تو" in m["text"])
    g.s.phase = Phase.END
    g.s.winner = "شهر 🕵️"
    r = handle("status", G)
    wins = [m for m in r["outbox"] if "بردی" in m["text"]]
    assert all(m.get("effect") == "party" for m in wins)


class _FakeBot:
    def __init__(self, reject=None):
        self.calls, self.reject = [], reject

    async def send_message(self, chat, text, **kw):
        self.calls.append(kw)
        if self.reject and self.reject(kw):
            raise RuntimeError(self.reject.__doc__ or "rejected")
        return type("M", (), {"message_id": len(self.calls)})()


def test_effect_only_in_private_and_dropped_when_telegram_rejects_it():
    from karagah import telegram_app as T
    fb = _FakeBot()
    asyncio.run(T._send(fb, -5, "گروه", None, "party"))
    assert "message_effect_id" not in fb.calls[-1]
    asyncio.run(T._send(fb, 5, "پیوی", None, "party"))
    assert fb.calls[-1].get("message_effect_id") == theme.EFFECTS["party"]

    def rej(kw):
        """EFFECT_ID_INVALID"""
        return "message_effect_id" in kw
    fb = _FakeBot(rej)
    assert asyncio.run(T._send(fb, 5, "پیوی", None, "party"))            # بی‌افکت رسید
    assert "message_effect_id" not in fb.calls[-1]


def test_custom_emoji_icons_fall_back_when_owner_has_no_premium(monkeypatch):
    from karagah import telegram_app as T
    monkeypatch.setattr(theme, "BUTTON_EMOJI", {"act": "5368324170671202286"})
    monkeypatch.setattr(T, "ICONS_OK", True)

    def rej(kw):
        """custom emoji can't be used"""
        m = kw.get("reply_markup")
        return bool(m) and any(getattr(b, "icon_custom_emoji_id", None) for row in m.inline_keyboard for b in row)
    fb = _FakeBot(rej)
    ok = asyncio.run(T._send(fb, 5, "x", {"inline_keyboard": [[{"text": "🌙", "callback_data": "act"}]]}))
    assert ok and T.ICONS_OK is False


# ───────── سرنخ ↔ رویداد ─────────
def test_night_without_any_crime_leaves_no_clue():
    g = _lobby(6)
    handle("startgame", G, 1, "force")
    for u in list(g.pending_actors()):
        handle("pass", G, u)
    assert g.s.phase is not Phase.NIGHT
    assert not [c for c in g.s.clues if c["day"] == 1]


def test_idle_lobby_stops_animating():
    from types import SimpleNamespace
    clock = SimpleNamespace(t=1_000_000.0)
    clock.time = lambda: clock.t
    orig = bot._time
    bot._time = clock
    try:
        _lobby(4)
        texts = set()
        for _ in range(4):
            clock.t += 5
            texts.add(bot.clock_view(G)["text"])
        assert len(texts) == 2                           # ساعت‌شنی می‌چرخد
        clock.t += 700
        still = {bot.clock_view(G)["text"] for _ in range(3) if not setattr(clock, "t", clock.t + 5)}
        assert len(still) == 1                           # بعد از ۱۰ دقیقه بی‌فعالیتی ثابت
    finally:
        bot._time = orig


def test_detective_cannot_expose_then_pass_then_investigate():
    """باگِ گیم‌پلی (نسخه ۹): راستی‌آزمایی → «کاری نمی‌کنم» → استعلام = دو اکشن در یک شب."""
    g = _lobby(7)
    handle("startgame", G, 1, "force")
    det = next(p for p in g.s.players.values() if p.role == "کارآگاه")
    handle("expose", G, det.uid, "", g.s.clues[0]["code"])
    assert not handle("pass", G, det.uid)["ok"]
    assert not g.legal_targets(det.uid)


def test_night_with_nobody_to_wait_for_ends_immediately():
    """باگِ گیم‌پلی (نسخه ۹): همه‌ی نقش‌های شبانه بازداشت/کشته‌اند → گروه ۶۰ ثانیه بی‌دلیل منتظر می‌ماند."""
    from karagah.models import Custody
    g = _lobby(6)
    handle("startgame", G, 1, "force")
    handle("dawn", G)
    for p in g.s.players.values():
        if g.ability_of(p) not in ("", "hunter"):
            p.custody = Custody.TEMP_JAIL
    if g.awaiting_verdict():
        g.s.suspect_uid = None
    handle("discuss", G)
    handle("vote", G)
    for p in g.s.alive_players():
        if p.can_vote:
            handle("castvote", G, p.uid, "", "0")
    r = handle("closevote", G)
    assert g.s.phase is not Phase.NIGHT
    assert any("کاری برای انجام دادن نداشت" in m["text"] for m in r["outbox"])
