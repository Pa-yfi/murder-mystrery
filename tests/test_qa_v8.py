"""نسخه ۸: آزمون‌های واحد/یکپارچگی/پسرفت برای هر چیزی که مجموعه‌ی QA پیدا و درست کرد.

هر تست یک باگِ واقعی را نگه می‌دارد تا دوباره برنگردد (Regression).
"""
import asyncio
import threading
from types import SimpleNamespace

import pytest

from karagah import bot, config, db, menus, ui
from karagah.bot import GAMES, handle
from karagah.l10n import fa_digits, localize, rtl_guard
from karagah.models import Phase

CHAT = -8080


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    for d in (bot._PENDING, bot._ACTIVE_TABLE, bot._LAST_CB, bot._LAST_CALL, bot.LAST_ROSTER, bot._LOCKS):
        d.clear()
    yield
    GAMES.clear()


def _started(n=7, chat=CHAT):
    handle("new", chat, 1, "Host")
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, "force")
    return GAMES[chat]


# ───────── L10n (واحد) ─────────
def test_digits_become_persian_but_codes_links_and_code_spans_stay():
    s = fa_digits("روز 12، سرنخ C12، t.me/bot?start=join_-100123 و `id 42` و (3 رای)")
    assert "روز ۱۲" in s and "C12" in s and "join_-100123" in s and "`id 42`" in s and "(۳ رای)" in s


def test_rtl_guard_only_for_latin_first_text():
    assert rtl_guard("C3 سرنخ").startswith("‏")
    assert rtl_guard("🔎 سرنخ C3") == "🔎 سرنخ C3"
    assert rtl_guard("  ❔ *C2* روز") .startswith("‏")


def test_every_bot_reply_is_localized():
    g = _started()
    import re
    loose = re.compile(r"(?<![A-Za-z_\d])[0-9]")          # رقمِ لاتینی که به حرفِ لاتین نچسبیده (C12، P2 مجازند)
    for cmd in ("dashboard", "board", "status", "menu"):
        r = handle(cmd, CHAT, 2)
        assert not loose.search(r["text"]), (cmd, r["text"][:200])
        assert not any(loose.search(b["text"]) for row in (r["keyboard"] or {}).get("inline_keyboard", [])
                       for b in row), cmd


def test_night_log_has_no_python_list_repr():
    g = _started()
    handle("dawn", CHAT)
    assert not any("['" in l or "=[" in l for l in g.s.log)


# ───────── نام و متنِ آزاد (امنیت/قالب) ─────────
def test_names_lose_bidi_controls_keep_zwnj_and_are_capped():
    assert bot._sanitize("‮خانم‬ رضایی") == "خانم رضایی"
    assert "‌" in bot._sanitize("زهرا‌سادات")
    assert len(bot._sanitize("A" * 80)) == bot.NAME_MAX
    assert bot._name("‏‎  ", 7) == "کارآگاه 7"


def test_free_text_cannot_break_markdown():
    g = _started()
    handle("dawn", CHAT); handle("discuss", CHAT); handle("vote", CHAT)
    sus = next(p.uid for p in g.s.alive_players() if p.uid != g.s.officer_uid)
    for p in g.s.alive_players():
        if p.can_vote and p.uid != sus:
            handle("castvote", CHAT, p.uid, "", str(sus))
    handle("closevote", CHAT)
    handle("ask", CHAT, g.s.officer_uid, "", "*چرا _آنجا `بودی [x]")
    r = handle("answer", CHAT, sus, "", "*من _نبودم`")
    from playtest.qa.compat import md_ok
    assert all(md_ok(m["text"]) for m in r["outbox"])


# ───────── سقف‌های تلگرام ─────────
def test_long_messages_are_split_under_4096():
    from karagah.telegram_app import chunks
    text = "\n".join("سطرِ نسبتاً بلندی برای آزمونِ تکه‌تکه کردن " * 3 for _ in range(300))
    parts = chunks(text)
    assert len(parts) > 1 and all(len(p) <= 4096 for p in parts)
    assert "".join(p.replace("\n", "") for p in parts) == text.replace("\n", "")


def test_send_puts_the_keyboard_on_the_last_chunk_only():
    from karagah import telegram_app as T
    sent = []

    class B:
        async def send_message(self, chat, text, **kw):
            sent.append(kw.get("reply_markup"))
    asyncio.run(T._send(B(), 1, "x\n" * 5000, {"inline_keyboard": [[{"text": "a", "callback_data": "menu"}]]}))
    assert len(sent) > 1 and all(k is None for k in sent[:-1]) and sent[-1] is not None


# ───────── نگه‌داری طولانی (soak) ─────────
def test_gc_evicts_ended_games_idle_lobbies_and_stale_entries():
    clock = SimpleNamespace(t=1_000_000.0)
    clock.time = lambda: clock.t
    orig = bot._time
    bot._time = clock
    try:
        g = _started(chat=-1)
        g.s.phase = Phase.END
        handle("status", -1)                     # نهایی‌سازی → ended_at
        handle("new", -2, 50, "H")               # لابیِ رهاشده
        bot._LAST_CALL[(9, "x")] = clock.t
        db.save_snapshot(-1, g)
        clock.t += config.IDLE_TTL + config.ENDED_TTL + 10
        handle("tick", -2)                       # تیک «فعالیت» نیست
        out = bot.gc()
        assert -1 not in GAMES and -2 not in GAMES and out["games_evicted"] == 2
        assert (9, "x") not in bot._LAST_CALL and -1 not in db.load_snapshots()
    finally:
        bot._time = orig


def test_idle_tick_writes_nothing_to_the_database():
    g = _started()
    n0 = db.conn().execute("select count(*) from events").fetchone()[0]
    for _ in range(20):
        handle("tick", CHAT)
    assert db.conn().execute("select count(*) from events").fetchone()[0] == n0


def test_restored_games_get_activity_and_end_stamps():
    g = _started()
    g.s.touched = 0
    db.save_snapshot(CHAT, g)
    GAMES.clear()
    bot.restore_games()
    assert GAMES[CHAT].s.touched > 0


# ───────── شبکه/چندنفره ─────────
def test_database_is_thread_safe():
    errs = []

    def worker(k):
        try:
            for i in range(150):
                db.touch_user(k * 1000 + i, "x")
                db.log_event(-1, k, "t", "")
        except Exception as e:                   # noqa: BLE001
            errs.append(e)
    ts = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errs


def test_supergroup_migration_keeps_the_game():
    g = _started(chat=-11)
    assert bot.migrate_chat(-11, -1001)
    assert -1001 in GAMES and -11 not in GAMES and GAMES[-1001].s.chat_id == -1001
    assert handle("dashboard", -1001)["ok"]


# ───────── UX ─────────
def test_lab_chooser_hides_clues_already_in_the_lab():
    g = _started()
    code = g.s.clues[0]["code"]
    g.submit_lab(code)
    cbs = [b["callback_data"] for row in menus.evidence_kb(g.s, "lab")["inline_keyboard"] for b in row]
    assert f"lab:{code}" not in cbs


def test_clue_buttons_are_short_enough_for_phones():
    g = _started()
    labels = [b["text"] for row in menus.evidence_kb(g.s, "interp")["inline_keyboard"] for b in row]
    assert all(len(t) <= 34 for t in labels)


def test_not_ready_start_offers_a_force_button_not_a_typed_command():
    bot.REQUIRE_READY = True
    try:
        handle("new", CHAT, 1, "Host")
        for i in range(2, 6):
            handle("join", CHAT, i, f"P{i}")
        r = handle("startgame", CHAT, 1)
        cbs = [b["callback_data"] for row in r["keyboard"]["inline_keyboard"] for b in row]
        assert not r["ok"] and "startgame:force" in cbs and "/startgame" not in r["text"]
    finally:
        bot.REQUIRE_READY = False


# ───────── دود (همان ماژولِ QA، سریع) ─────────
def test_smoke_suite_passes():
    from playtest.qa import smoke
    sec = smoke.run()
    assert sec.passed, sec.findings
