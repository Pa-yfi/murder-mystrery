"""بهبود ۲ (آمادگی پیش از شروع) و ۷ (بازیکن غایب)."""
import pytest

from karagah import bot, db, ui
from karagah.bot import GAMES, handle
from karagah.engine import Game, RuleError
from karagah.models import Phase


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    yield
    GAMES.clear()
    bot.REQUIRE_READY = False


CHAT = 870


def _lobby(chat=CHAT, n=5):
    handle("new", chat, 1, "Host")
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    return GAMES[chat]


# ---------- بهبود ۲ ----------
def test_start_blocked_until_everyone_opened_the_dm():
    bot.REQUIRE_READY = True
    g = _lobby()
    r = handle("startgame", CHAT, 1)
    assert r["ok"] is False
    assert "پیوی" in r["text"]
    assert g.s.phase is Phase.LOBBY
    for u in list(g.s.players):
        assert handle("start", u, u, arg=f"ready_{CHAT}")["ok"]
    assert handle("startgame", CHAT, 1)["ok"]
    assert g.s.phase is Phase.NIGHT


def test_ready_deeplink_marks_only_that_player():
    g = _lobby()
    handle("start", 3, 3, arg=f"ready_{CHAT}")
    assert g.s.players[3].ready
    assert not g.s.players[2].ready
    assert 2 in g.not_ready()


def test_ready_reply_is_private():
    _lobby()
    r = handle("start", 3, 3, arg=f"ready_{CHAT}")
    assert r["private"] is True          # تاییدیه در پیوی، نه در گروه


def test_host_can_force_start_without_absentees():
    bot.REQUIRE_READY = True
    g = _lobby()
    assert handle("startgame", CHAT, 1)["ok"] is False
    assert handle("startgame", CHAT, 1, arg="force")["ok"]
    assert g.s.phase is Phase.NIGHT


def test_force_start_still_honours_the_case_number():
    bot.REQUIRE_READY = True
    g = _lobby()
    handle("startgame", CHAT, 1, arg="7 force")
    assert g.s.case.cid == 7


def test_lobby_shows_who_is_ready():
    g = _lobby()
    handle("start", 3, 3, arg=f"ready_{CHAT}")
    screen = ui.lobby_screen(g.s)
    assert "✅" in screen and "⏳" in screen


def test_ready_link_is_a_private_deeplink():
    assert ui.share_links(CHAT)["ready"].endswith(f"start=ready_{CHAT}")


# ---------- بهبود ۷: توقف / ادامه ----------
def test_pause_freezes_the_timer():
    g = _lobby(); handle("startgame", CHAT, 1)
    left_before = g.remaining()
    assert handle("pause", CHAT, 1)["ok"]
    assert g.s.paused and g.s.deadline is None
    assert g.remaining() == left_before
    g.s.deadline = 0                      # حتی اگر مهلت گذشته باشد
    assert g.tick() is None               # تایمر بازیِ متوقف را جلو نمی‌برد


def test_resume_restores_remaining_time():
    g = _lobby(); handle("startgame", CHAT, 1)
    handle("pause", CHAT, 1)
    left = g.remaining()
    assert handle("resume", CHAT, 1)["ok"]
    assert not g.s.paused
    assert g.remaining() is not None and abs(g.remaining() - left) <= 1


def test_only_host_can_pause():
    _lobby(); handle("startgame", CHAT, 1)
    assert handle("pause", CHAT, 999)["ok"] is False


def test_pause_rejected_in_lobby_and_twice():
    g = _lobby()
    assert handle("pause", CHAT, 1)["ok"] is False      # هنوز شروع نشده
    handle("startgame", CHAT, 1)
    assert handle("pause", CHAT, 1)["ok"]
    assert handle("pause", CHAT, 1)["ok"] is False      # دو بار پشت‌هم


# ---------- بهبود ۷: میزبان و یادآوری ----------
def test_host_transfer():
    g = _lobby(); handle("startgame", CHAT, 1)
    assert handle("host", CHAT, 1, arg="3")["ok"]
    assert g.owner == 3
    assert handle("pause", CHAT, 3)["ok"]              # میزبان تازه اختیار دارد


def test_outsider_cannot_grab_host_while_host_is_playing():
    g = _lobby(); handle("startgame", CHAT, 1)
    assert handle("host", CHAT, 4, arg="4")["ok"] is False
    assert g.owner == 1


def test_host_can_be_claimed_when_owner_is_out():
    g = _lobby(); handle("startgame", CHAT, 1)
    g.s.players[1].alive = False                       # میزبان کشته شد
    assert handle("host", CHAT, 3, arg="3")["ok"]
    assert g.owner == 3


def test_remind_names_who_is_holding_things_up():
    g = _lobby(); handle("startgame", CHAT, 1)
    r = handle("remind", CHAT, 1)
    assert r["ok"] and "منتظر" in r["text"]
    pending = g.pending_actors()
    assert any(g.s.players[u].name in r["text"] for u in pending)


def test_remind_is_quiet_when_everyone_acted():
    g = _lobby(); handle("startgame", CHAT, 1)
    for u in list(g.pending_actors()):
        tgt = g.legal_targets(u)
        if tgt:
            handle("act", CHAT, u, arg=str(tgt[0]))
    r = handle("remind", CHAT, 1)
    assert r["ok"] and "همه کارشان" in r["text"]


# ---------- بهبود ۷: اکشن نداده ----------
def test_missed_nights_are_counted_and_reset():
    g = _lobby(n=6); handle("startgame", CHAT, 1)
    killer = next(p for p in g.s.players.values() if p.role == "قاتل")
    g.resolve_night()
    assert killer.missed == 1              # هیچ اکشنی نداد
    g.s.phase = Phase.NIGHT
    victim = g.legal_targets(killer.uid)[0]
    g.night_action(killer.uid, victim)
    g.resolve_night()
    assert killer.missed == 0              # دوباره فعال شد


def test_repeated_absence_is_logged():
    g = _lobby(n=6); handle("startgame", CHAT, 1)
    for _ in range(2):
        g.s.phase = Phase.NIGHT
        g.resolve_night()
    assert any("بی‌حرکت" in l for l in g.s.log)
