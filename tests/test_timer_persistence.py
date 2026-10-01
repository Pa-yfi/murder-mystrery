"""تایمر خودکار باید همان مسیر امنِ handle() را برود."""
import asyncio
from types import SimpleNamespace

import pytest

from karagah import bot, db, telegram_app
from karagah.bot import GAMES, handle
from karagah.models import Phase


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    yield
    GAMES.clear()


def _started(chat=850, n=6):
    handle("new", chat, 1, "Host")
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, arg="12")
    return GAMES[chat]


class _Ctx:
    def __init__(self):
        self.sent = []
        self.edits = []
        self.bot = SimpleNamespace(send_message=self._send, edit_message_text=self._edit)
        self._mid = 100

    async def _send(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))
        self._mid += 1
        return SimpleNamespace(message_id=self._mid)

    async def _edit(self, chat_id=None, message_id=None, text="", **kw):
        self.edits.append((chat_id, message_id, text))


@pytest.fixture(autouse=True)
def _clean_clocks():
    telegram_app.CLOCKS.clear()
    yield
    telegram_app.CLOCKS.clear()


def _snapshot_phase(chat):
    games = db.load_snapshots()
    return games[chat].s.phase if chat in games else None


def test_timer_persists_phase_change():
    chat = 850
    g = _started(chat)
    assert _snapshot_phase(chat) is Phase.NIGHT
    g.s.deadline = 0                      # مهلت شب گذشته → فرصتِ اضافه
    ctx = _Ctx()
    asyncio.run(telegram_app._timer_job(ctx))
    assert g.s.phase is Phase.NIGHT
    g.s.deadline = 0                      # فرصت هم گذشت → صبح
    asyncio.run(telegram_app._timer_job(ctx))
    assert g.s.phase is Phase.MORNING
    assert _snapshot_phase(chat) is Phase.MORNING     # حافظه و اسنپ‌شات هم‌قدم‌اند
    assert ctx.sent and ctx.sent[0][0] == chat


def test_timer_is_quiet_when_nothing_expires():
    chat = 851
    _started(chat)
    ctx = _Ctx()
    asyncio.run(telegram_app._timer_job(ctx))
    assert len(ctx.sent) == 1 and "شبِ ۱" in ctx.sent[0][1]   # فقط پیامِ ساعتِ همین فاز
    asyncio.run(telegram_app._timer_job(ctx))
    assert len(ctx.sent) == 1                                  # پیام تازه نمی‌دهد…


def test_clock_message_edits_itself_and_renews_per_phase(monkeypatch):
    """نسخه ۷: ساعتِ شب یک پیام است که خودش را ویرایش می‌کند؛ فاز عوض شد → پیامِ تازه."""
    import karagah.engine as eng
    chat = 853
    g = _started(chat)
    now = [1_000_000.0]
    monkeypatch.setattr(eng._time, "time", lambda: now[0])
    g._arm()
    ctx = _Ctx()
    asyncio.run(telegram_app._timer_job(ctx))
    first = telegram_app.CLOCKS[chat]["mid"]
    now[0] += 7
    asyncio.run(telegram_app._timer_job(ctx))
    assert len(ctx.sent) == 1 and ctx.edits and ctx.edits[-1][1] == first      # همان پیام ویرایش شد
    from karagah import config
    from karagah.ui import _mmss
    assert _mmss(config.PHASE_SECONDS["شب"] - 7) in ctx.edits[-1][2]     # ۷:۰۰ − ۷ ثانیه
    now[0] += 1                                            # یک ثانیه بعد → دوباره ویرایش (ساعتِ ثانیه‌شمار)
    n = len(ctx.edits)
    asyncio.run(telegram_app._timer_job(ctx))
    assert len(ctx.edits) == n + 1 and _mmss(config.PHASE_SECONDS["شب"] - 8) in ctx.edits[-1][2]
    handle("dawn", chat)                                   # سیستم شب را می‌بندد → صبح
    asyncio.run(telegram_app._timer_job(ctx))
    assert telegram_app.CLOCKS[chat]["mid"] != first and "صبحِ روز ۱" in ctx.sent[-1][1]
    assert any("تمام شد" in e[2] for e in ctx.edits if e[1] == first)       # ساعتِ شب بسته شد


def test_timer_finalises_a_game_that_ends_on_a_tick():
    from karagah.models import Align, Custody
    chat = 852
    g = _started(chat)
    for p in g.s.players.values():
        if p.align is Align.KILLER:
            p.custody = Custody.LIFE_JAIL
    for _ in range(2):                    # مهلت، بعد فرصتِ اضافه
        g.s.deadline = 0
        asyncio.run(telegram_app._timer_job(_Ctx()))
    assert g.s.phase is Phase.END
    assert g.s.finalized                  # نتیجه ثبت شد، نه اینکه از قلم بیفتد
    snap = db.load_snapshots()[chat]      # نسخه ۴: برای افشا بعد از ری‌استارت می‌ماند
    assert snap.s.phase is Phase.END and snap.s.finalized


def test_tiebreak_runoff_gets_a_fresh_deadline():
    chat = 853
    g = _started(chat)
    handle("dawn", chat); handle("discuss", chat); handle("vote", chat)
    voters = [p.uid for p in g.s.alive_players() if p.can_vote]
    a, b = voters[0], voters[1]
    handle("castvote", chat, voters[2], arg=str(a))
    handle("castvote", chat, voters[3], arg=str(b))
    g.s.deadline = 0                      # مهلت دور اول گذشته
    assert g.tick() is not None           # تساوی → مرگ ناگهانی
    assert g.s.tie_break and g.s.phase is Phase.VOTE
    assert g.remaining() and g.remaining() > 0        # دور دوم مهلت تازه دارد
    assert g.tick() is None                           # تیکِ بعدی آن را نمی‌بلعد


def test_default_night_and_day_are_seven_minutes_and_clock_ticks_every_second():
    from karagah import config
    assert config.PHASE_SECONDS["شب"] == 420 and config.PHASE_SECONDS["گفتگو"] == 420
    assert telegram_app.CLOCK_INTERVAL == 1


def test_flood_control_pauses_only_that_groups_clock_then_resumes(monkeypatch):
    """تلگرام «RetryAfter» داد → همان گروه تا زمانِ گفته‌شده ویرایش نمی‌شود، بعد دوباره هر ثانیه."""
    import karagah.engine as eng
    from telegram.error import RetryAfter
    chat = 854
    g = _started(chat)
    now = [2_000_000.0]
    monkeypatch.setattr(eng._time, "time", lambda: now[0])
    mono = [500.0]
    monkeypatch.setattr(telegram_app.time, "monotonic", lambda: mono[0])
    g._arm()
    ctx = _Ctx()
    asyncio.run(telegram_app._timer_job(ctx))          # پیامِ ساعت فرستاده شد

    async def flooded(**kw):
        raise RetryAfter(10)
    ctx.bot.edit_message_text = flooded
    now[0] += 1; mono[0] += 1
    asyncio.run(telegram_app._timer_job(ctx))          # تلگرام: ۱۰ ثانیه صبر کن
    assert telegram_app.FLOOD_UNTIL[chat] > mono[0]
    ctx.bot.edit_message_text = ctx._edit
    for _ in range(5):                                 # در این مدت هیچ ویرایشی (و هیچ خطایی)
        now[0] += 1; mono[0] += 1
        asyncio.run(telegram_app._timer_job(ctx))
    assert ctx.edits == [] and g.s.phase is Phase.NIGHT
    now[0] += 6; mono[0] += 6
    asyncio.run(telegram_app._timer_job(ctx))
    assert len(ctx.edits) == 1                         # دوباره ثانیه‌شمار
    telegram_app.FLOOD_UNTIL.clear()


def test_v10_phase_announcement_is_the_live_card_and_old_card_keeps_content(monkeypatch):
    """نسخه ۱۰: یک پیام برای هر فاز. اعلامِ فاز همان کارتِ زنده است و ثانیه‌شمار پایینش ویرایش می‌شود؛
    فازِ بعد که آمد، کارتِ قبلی محتوایش را نگه می‌دارد و فقط ساعت و دکمه‌هایش برداشته می‌شود."""
    import karagah.engine as eng
    chat = -8551
    handle("new", chat, 1, "Host")
    for i in range(2, 8):
        handle("join", chat, i, f"P{i}")
    now = [3_000_000.0]
    monkeypatch.setattr(eng._time, "time", lambda: now[0])
    res = handle("startgame", chat, 1, arg="force")
    assert res.get("pin") and not res.get("card")                  # پرونده جدا (و سنجاق)
    cards = [m for m in res["outbox"] if m.get("card")]
    assert len(cards) == 1 and cards[0]["chat"] == chat and "شبِ ۱" in cards[0]["text"]
    ctx = _Ctx()
    asyncio.run(telegram_app._flush_outbox(ctx.bot, res))
    night_mid = telegram_app.CLOCKS[chat]["mid"]
    sent_before = len(ctx.sent)
    now[0] += 1
    asyncio.run(telegram_app._timer_job(ctx))
    assert len(ctx.sent) == sent_before and ctx.edits[-1][1] == night_mid  # همان کارت ویرایش شد، پیامِ تازه نه

    res = handle("dawn", chat)                                          # صبح: گزارش = کارت
    assert res.get("card") and "⚰️ کشته" in res["text"] and "📅" in res["text"]
    sent = asyncio.run(telegram_app._send(ctx.bot, chat, res["text"], res.get("keyboard")))
    asyncio.run(telegram_app._adopt_card(ctx.bot, chat, sent))
    closing = [e for e in ctx.edits if e[1] == night_mid][-1][2]
    assert "☑️" in closing and "⏳" not in closing and "⌛" not in closing   # کارتِ شب بسته شد، بی‌ساعت
    assert telegram_app.CLOCKS[chat]["mid"] == sent.message_id
    now[0] += 1
    asyncio.run(telegram_app._timer_job(ctx))
    assert ctx.edits[-1][1] == sent.message_id and "⚰️ کشته" in ctx.edits[-1][2]  # گزارش می‌ماند، ساعت جلو می‌رود
    GAMES.pop(chat, None)
    bot.CARDS.pop(chat, None)


def test_v10_votes_answer_with_a_popup_not_a_group_message():
    chat = -8552
    handle("new", chat, 1, "Host")
    for i in range(2, 8):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, arg="force")
    g = GAMES[chat]
    handle("dawn", chat)
    handle("discuss", chat, 1)
    handle("vote", chat, 1)
    voter, target = [p.uid for p in g.s.alive_players() if p.can_vote][:2]
    r = handle("castvote", chat, voter, arg=str(target))
    assert r["ok"] and r.get("toast", "").startswith("✅ رای تو ثبت شد")
    view = bot.clock_view(chat)
    assert "۱/" in view["text"]                                         # شمارش روی کارتِ زنده
    GAMES.pop(chat, None)
