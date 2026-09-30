"""🌐 Network & Multiplayer: ربات تلگرامی یعنی ده‌ها کاربر هم‌زمان روی یک وضعیتِ مشترک.

- هم‌روندی: ده‌ها نخ هم‌زمان رای می‌دهند، شب را می‌بندند، اکشن می‌زنند → قفلِ هر چت؟
- خرابیِ شبکه/تلگرام: کاربری ربات را بلاک کرده، پیام پاک شده، محدودیتِ نرخ (RetryAfter)،
  TimedOut/NetworkError، Markdownِ خراب → آداپتور هرگز نمی‌افتد و راهِ جایگزین دارد
- callback تکراری (دوبار تپ / تحویلِ دوباره‌ی تلگرام) نادیده گرفته می‌شود
- ضدتقلب: فازینگِ همه‌ی اندپوینت‌ها با آرگومانِ خراب/مهاجم و کاربرِ نامجاز
- میزبانِ غایب: بازی فقط با تایمر و بازیکن‌ها تمام می‌شود (مهاجرتِ میزبان لازم نیست)
"""
from __future__ import annotations

import asyncio
import random
import threading
from types import SimpleNamespace

from karagah import bot, db
from karagah.bot import GAMES, handle
from karagah.models import Custody, Phase

from .common import Section, fresh, timed

INTERNAL = "خطای داخلی"


def _game(chat, n=8):
    handle("new", chat, 1, "Host")
    for u in range(2, n + 1):
        handle("join", chat, u, f"P{u}")
    handle("startgame", chat, 1, "force")
    return GAMES[chat]


def concurrency(sec: Section) -> None:
    fresh()
    G = -31337
    g = _game(G, 10)
    errors = []

    def spam_dawn():
        for _ in range(30):
            r = handle("dawn", G)                       # سیستم: همه با هم شب را می‌بندند
            if INTERNAL in r["text"]:
                errors.append(r["text"])

    day0 = g.s.day
    ts = [threading.Thread(target=spam_dawn) for _ in range(16)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    sec.check(g.s.day == day0 and g.s.phase is not Phase.NIGHT,
              f"۱۶ نخ هم‌زمان شب را بستند: روز {day0}→{g.s.day}، فاز {g.s.phase.value}")
    if g.s.phase is Phase.MORNING and not g.awaiting_verdict():
        handle("discuss", G)
        handle("vote", G)
    if g.s.phase is Phase.VOTE:
        voters = [p.uid for p in g.s.alive_players() if p.can_vote]
        targets = [p.uid for p in g.s.alive_players() if p.can_speak]

        def spam_vote(u):
            rng = random.Random(u)
            for _ in range(200):
                r = handle("castvote", G, u, "", str(rng.choice(targets + [0])))
                if INTERNAL in r["text"]:
                    errors.append(r["text"])

        ts = [threading.Thread(target=spam_vote, args=(u,)) for u in voters for _ in range(3)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        sec.check(len(g.s.votes) <= len(voters), f"رای‌ها بیش از رای‌دهنده‌ها: {len(g.s.votes)}")
        sec.check(set(g.s.votes) <= set(voters), "رای از کسی که حق رای ندارد")
        closers = [threading.Thread(target=lambda: handle("closevote", G)) for _ in range(12)]
        for t in closers:
            t.start()
        for t in closers:
            t.join()
        sec.check(g.s.phase is not Phase.VOTE or g.s.tie_break, "بستنِ هم‌زمانِ رای خراب شد")
        sec.metrics["concurrent_vote_calls"] = len(voters) * 3 * 200
    sec.check(not errors, f"{len(errors)} خطای داخلی زیرِ هم‌روندی")
    sec.metrics["concurrent_dawn_calls"] = 16 * 30


class FlakyBot:
    """بات تلگرامِ ساختگی که به دستور خطا می‌دهد."""

    def __init__(self, fail_send=None, fail_edit=None):
        self.sent, self.edits = [], []
        self.fail_send, self.fail_edit = fail_send or (lambda *a, **k: None), fail_edit or (lambda *a, **k: None)
        self._mid = 0

    async def send_message(self, chat_id, text, **kw):
        err = self.fail_send(chat_id, text, kw)
        if err:
            raise err
        self._mid += 1
        self.sent.append((chat_id, text, kw.get("parse_mode")))
        return SimpleNamespace(message_id=self._mid, edit_text=self._noop, delete=self._noop)

    async def edit_message_text(self, chat_id=None, message_id=None, text="", **kw):
        err = self.fail_edit(chat_id, message_id)
        if err:
            raise err
        self.edits.append((chat_id, message_id, text))

    async def _noop(self, *a, **k):
        return None


def failures(sec: Section) -> None:
    from telegram.error import BadRequest, Forbidden, NetworkError, RetryAfter, TimedOut
    from karagah import telegram_app as T
    fresh()
    G = -4242
    g = _game(G, 7)
    run = asyncio.run
    ok = 0

    # ۱) کاربر ربات را بلاک کرده: پیامِ خصوصی (کارت نقش) → تذکرِ بی‌محتوا در گروه، نه متنِ محرمانه
    fb = FlakyBot(fail_send=lambda chat, text, kw: Forbidden("bot was blocked by the user") if chat == 3 else None)
    upd = SimpleNamespace(effective_chat=SimpleNamespace(id=G, type="group"),
                          effective_user=SimpleNamespace(id=3, first_name="P3"),
                          callback_query=None, get_bot=lambda: fb)
    res = handle("myrole", G, 3)
    res["_target"] = G
    try:
        run(T._reply(upd, res))
        leaked = any("نقش تو" in t for c, t, _ in fb.sent if c == G)
        notice = any("پیام خصوصی" in t for c, t, _ in fb.sent if c == G)
        sec.check(not leaked and notice, "بلاک‌شدن: نقش در گروه لو رفت یا تذکر نیامد")
        ok += 1
    except Exception as e:                                  # noqa: BLE001
        sec.fail(f"بلاک‌شدن آداپتور را انداخت: {e!r}")

    # ۲) Markdownِ خراب → متن ساده
    fb = FlakyBot(fail_send=lambda chat, text, kw: BadRequest("Can't parse entities")
                  if kw.get("parse_mode") else None)
    try:
        sent = run(T._send(fb, G, "*ناقص _متن", None))
        sec.check(sent and fb.sent and fb.sent[-1][2] is None, "Markdownِ خراب به متن ساده برنگشت")
        ok += 1
    except Exception as e:                                  # noqa: BLE001
        sec.fail(f"Markdownِ خراب آداپتور را انداخت: {e!r}")

    # ۳) شبکه قطع: TimedOut/NetworkError روی ارسال → False، بدون استثنا
    for err in (TimedOut(), NetworkError("reset by peer")):
        fb = FlakyBot(fail_send=lambda chat, text, kw, e=err: e)
        try:
            sec.check(not run(T._send(fb, G, "سلام")), f"{type(err).__name__}: ارسالِ ناموفق باید «نرسید» برگرداند")
            ok += 1
        except Exception as e:                              # noqa: BLE001
            sec.fail(f"{type(err).__name__} آداپتور را انداخت: {e!r}")

    # ۴) ساعت: پیام پاک شده → ساعتِ تازه؛ محدودیتِ نرخ → بی‌خطا و دوباره
    T.CLOCKS.clear()
    fb = FlakyBot()
    run(T._update_clock(fb, G))
    first = T.CLOCKS[G]["mid"]
    g.s.deadline -= 10                                     # متن ساعت عوض شود
    fb.fail_edit = lambda chat, mid: BadRequest("Message to edit not found")
    run(T._update_clock(fb, G))
    sec.check(G not in T.CLOCKS, "پیامِ ساعتِ پاک‌شده رها نشد")
    fb.fail_edit = lambda chat, mid: None
    run(T._update_clock(fb, G))
    sec.check(G in T.CLOCKS and T.CLOCKS[G]["mid"] != first, "ساعتِ تازه فرستاده نشد")
    g.s.deadline -= 10
    fb.fail_edit = lambda chat, mid: RetryAfter(3)
    try:
        run(T._update_clock(fb, G))
        ok += 1
    except Exception as e:                                  # noqa: BLE001
        sec.fail(f"RetryAfter روی ساعت آداپتور را انداخت: {e!r}")

    # ۵) کلِ دورِ تایمر وقتی تلگرام قطع است: بازی باز هم جلو می‌رود و ذخیره می‌شود
    fb = FlakyBot(fail_send=lambda chat, text, kw: NetworkError("down"),
                  fail_edit=lambda chat, mid: NetworkError("down"))
    g.s.deadline = 0
    g.s.grace_day = g.s.day
    try:
        run(T._timer_job(SimpleNamespace(bot=fb)))
        sec.check(g.s.phase is not Phase.NIGHT, "با قطعیِ تلگرام تایمر بازی را جلو نبرد")
        ok += 1
    except Exception as e:                                  # noqa: BLE001
        sec.fail(f"تایمر با قطعی تلگرام افتاد: {e!r}")

    # ۶) پیامِ خیلی بلند (پرونده‌ی بزرگ) تکه‌تکه می‌رود
    fb = FlakyBot(fail_send=lambda chat, text, kw: BadRequest("Message is too long") if len(text) > 4096 else None)
    long = "\n".join(f"  ❔ *C{i}* سرنخی نسبتاً طولانی برای آزمون طولِ پیام در تلگرام" for i in range(400))
    sec.check(run(T._send(fb, G, long, {"inline_keyboard": [[{"text": "x", "callback_data": "menu"}]]})),
              "پیامِ بلند نرسید")
    sec.check(all(len(t) <= 4096 for _, t, _ in fb.sent), "تکه‌ای بیش از ۴۰۹۶")
    sec.metrics["long_message_chunks"] = len(fb.sent)
    T.CLOCKS.clear()
    sec.metrics["failure_scenarios_survived"] = ok + 2


def dup_callbacks(sec: Section) -> None:
    fresh()
    bot._LAST_CB.clear()
    first = bot.is_dup_callback(-1, 5, "vote:7")
    second = bot.is_dup_callback(-1, 5, "vote:7")
    other = bot.is_dup_callback(-1, 6, "vote:7")
    sec.check(first is False and second is True and other is False, "حذفِ callbackِ تکراری درست کار نمی‌کند")


EVIL_ARGS = ["", "0", "-1", "999999999999999999", "abc", "1:2:3:4", "'; DROP TABLE users;--", "%s%s%n",
             "../../etc/passwd", "C999", "C1:X", "‮\u0000", "🙂" * 50, "x" * 5000, "vote:1", "None", "1e9"]


def fuzz(sec: Section, quick: bool) -> None:
    """ضدتقلب/مقاومت: هر اندپوینت × آرگومانِ مهاجم × کاربرِ نامجاز (غریبه، مرده، زندانی، قاتل روی هم‌تیمی)."""
    fresh()
    G = -5150
    g = _game(G, 9)
    killer = next(p for p in g.s.players.values() if p.role == "قاتل")
    mate = next((p for p in g.s.players.values() if p.align == killer.align and p.uid != killer.uid), None)
    dead = next(p for p in g.s.players.values() if p.uid not in (killer.uid, g.s.officer_uid))
    dead.alive = False
    jailed = next(p for p in g.s.players.values() if p.alive and p.uid not in (killer.uid, g.s.officer_uid))
    jailed.custody = Custody.TEMP_JAIL
    users = [0, 777_000, dead.uid, jailed.uid, killer.uid]
    eps = sorted(e for e in bot.ENDPOINTS if e not in ("new", "blitz", "admin_ban"))
    rng = random.Random(9)
    bad, calls = [], 0
    for ep in eps:
        for arg in (EVIL_ARGS if not quick else rng.sample(EVIL_ARGS, 6)):
            for u in users:
                for chat in (G, u or 1):
                    r = handle(ep, chat, u, "Evil*_`[x](y)", arg)
                    calls += 1
                    if INTERNAL in (r.get("text") or ""):
                        bad.append(f"{ep}({arg[:12]!r}) by {u}")
    sec.metrics["fuzz_calls"] = calls
    sec.check(not bad, f"{len(bad)} خطای داخلی در فازینگ: " + "؛ ".join(bad[:6]))
    # تقلب‌های مشخص
    if g.s.phase is Phase.NIGHT and mate:
        before = dict(g.s.night_actions)
        handle("act", G, killer.uid, "", str(mate.uid))
        sec.check(f"kill:{killer.uid}" not in g.s.night_actions or g.s.night_actions.get(f"kill:{killer.uid}") != mate.uid,
                  "قاتل هم‌تیمی را هدف گرفت")
        g.s.night_actions.clear()
        g.s.night_actions.update(before)
    r = handle("castvote", G, dead.uid, "", str(killer.uid))
    sec.check(dead.uid not in g.s.votes, "مرده رای داد")
    r = handle("verdict", G, 777_000, "", "1")
    sec.check(not r["ok"], "غریبه حکم داد")
    sec.check(db.conn().execute("select count(*) from users").fetchone()[0] >= 0, "جدول users آسیب دید")


def host_gone(sec: Section) -> None:
    """میزبان بعد از شروع ناپدید می‌شود: فقط بازیکن‌ها و تایمر → بازی تمام می‌شود."""
    fresh()
    G = -6060
    g = _game(G, 7)
    rng = random.Random(1)
    for _ in range(300):
        if g.s.phase is Phase.END:
            break
        for u in list(g.pending_actors()):
            if u == 1:
                continue
            if g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
                legal = g.legal_targets(u)
                handle("act", G, u, "", str(rng.choice(legal))) if legal else handle("pass", G, u)
            elif g.s.phase is Phase.VOTE:
                handle("castvote", G, u, "", "0")
            elif g.s.phase is Phase.JURY:
                handle("juryvote", G, u, "", "1")
        g.s.deadline = 0
        handle("tick", G)
    sec.check(g.s.phase is Phase.END, f"بدون میزبان بازی تمام نشد (فاز {g.s.phase.value}، روز {g.s.day})")
    sec.metrics["host_gone_game"] = f"{g.s.winner} در {g.s.day} روز"


def run(quick: bool = True) -> Section:
    sec = Section("Network & Multiplayer", "هم‌روندی، خرابیِ تلگرام/شبکه، callbackِ تکراری، فازینگِ ضدتقلب، میزبانِ غایب")
    with timed(sec):
        for fn in (concurrency, failures, dup_callbacks, host_gone):
            try:
                fn(sec)
            except Exception as e:                          # noqa: BLE001
                sec.fail(f"{fn.__name__}: {e!r}")
        try:
            fuzz(sec, quick)
        except Exception as e:                              # noqa: BLE001
            sec.fail(f"fuzz: {e!r}")
    return sec
