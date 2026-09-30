"""تایمر خودکار باید همان مسیر امنِ handle() را برود."""
import asyncio
from types import SimpleNamespace

import pytest

from karagah import db, telegram_app
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
    assert "۰:۵۳" in ctx.edits[-1][2]
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
