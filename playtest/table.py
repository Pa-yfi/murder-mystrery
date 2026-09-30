"""تلگرامِ شبیه‌سازی‌شده: یک گروه + پیویِ هر بازیکن، با دکمه‌های واقعیِ ربات.

همان مسیری را می‌رود که karagah/telegram_app.py در تلگرام واقعی می‌رود:
callback_data با parse_callback تفسیر می‌شود، تپ تکراری با is_dup_callback
گرفته می‌شود، پیوی با route_chat به بازی گروه می‌رسد، و پاسخِ غیرخصوصی در
همان چتی می‌افتد که دکمه آنجا زده شده (مثل _reply در آداپتور).

ساعت مجازی است تا ضد اسپم (۰٫۶ ثانیه) و تایمر فازها دقیق و بی‌انتظار تست شوند.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from karagah import bot, engine
from karagah.bot import handle, route_chat, take_pending
from karagah.telegram_app import AMBIGUOUS, parse_callback

# نشانه‌هایی که فقط باید در پیوی دیده شوند؛ دیدنشان در گروه یعنی نشت
PRIVATE_MARKERS = ("نقش تو:", "هم‌تیمی:", "سرنخ‌های بازجویی", "→ پاک", "→ مشکوک",
                   "یافته‌های نقش تو", "اطلاعات محرمانه")


class Clock:
    """جایگزین ماژول time در bot و engine — ثانیه‌ها را خودمان جلو می‌بریم."""

    def __init__(self, start: float = 1_700_000_000.0):
        self.now = start

    def time(self) -> float:
        return self.now

    def advance(self, sec: float) -> None:
        self.now += sec


_ids = itertools.count(1)


@dataclass
class Message:
    chat: int                      # گروه یا آیدیِ پیویِ بازیکن
    text: str
    keyboard: Optional[dict]
    cause: str                     # چه دکمه/دستوری این پیام را ساخت
    ok: bool = True
    mid: int = field(default_factory=lambda: next(_ids))

    def buttons(self) -> List[dict]:
        if not self.keyboard:
            return []
        return [b for row in self.keyboard.get("inline_keyboard", []) for b in row]


class Telegram:
    def __init__(self, group: int, report):
        self.group = group
        self.report = report                  # playtest.report.Report
        self.clock = Clock()
        self.chats: Dict[int, List[Message]] = {group: []}
        self.names: Dict[int, str] = {}
        self.presses = 0
        self._orig = (bot._time, engine._time)
        bot._time = self.clock                # ضد اسپم، dedup و تایمر روی ساعت مجازی
        engine._time = self.clock
        bot.RATE_LIMIT_ENABLED = True         # مثل main() در telegram_app
        bot.REQUIRE_READY = True

    def close(self) -> None:
        bot._time, engine._time = self._orig
        bot.RATE_LIMIT_ENABLED = False
        bot.REQUIRE_READY = False

    # ── دیدن ────────────────────────────────────────────
    def inbox(self, chat: int) -> List[Message]:
        return self.chats.setdefault(chat, [])

    def last(self, chat: int) -> Optional[Message]:
        box = self.inbox(chat)
        return box[-1] if box else None

    def visible_to(self, uid: int, chat: int, msg: Message) -> bool:
        return msg.chat == chat and (chat == self.group or chat == uid)

    # ── فرستادن ─────────────────────────────────────────
    def _deliver(self, res: dict, chat: int, uid: int, cause: str,
                 on: Optional[Message] = None) -> Message:
        """مثل telegram_app._reply: پاسخ اصلی، بعد صندوق خروجی (پیام به دیگران)."""
        msg = self._deliver_main(res, chat, uid, cause, on)
        for m in res.get("outbox") or []:
            self._put({"text": m["text"], "keyboard": m.get("keyboard"), "ok": True},
                      m["chat"], f"outbox<{cause}")
        return msg

    def _put(self, res: dict, dest: int, cause: str) -> Message:
        self._check(res.get("text", ""), dest, cause, private=dest != self.group)
        msg = Message(dest, res.get("text", ""), res.get("keyboard"), cause, res.get("ok", True))
        self.inbox(dest).append(msg)
        return msg

    def _check(self, text: str, dest: int, cause: str, private: bool) -> None:
        if "خطای داخلی" in text:
            self.report.find("بالا", "کد", f"خطای داخلی پس از «{cause}»",
                             text, key=f"internal:{cause.split(':')[0]}")
        if dest == self.group and not private:
            for m in PRIVATE_MARKERS:
                if m in text:
                    self.report.find("بالا", "امنیت", "اطلاعات محرمانه در گروه",
                                     f"«{m}» پس از «{cause}» در گروه دیده شد.",
                                     key=f"leak:{m}")

    def _deliver_main(self, res: dict, chat: int, uid: int, cause: str,
                      on: Optional[Message] = None) -> Message:
        """خصوصی → پیوی؛ edit روی پیامِ همان دکمه؛ اعلامِ عمومی از پیوی → گروهِ بازی."""
        text = res.get("text", "")
        target = res.get("_target")
        if res.get("announce") and target and target != chat and not res.get("private"):
            out = self._put(res, target, cause)
            self._put({"text": "📣 در گروهِ بازی اعلام شد."}, chat, cause)
            return out
        private = bool(res.get("private"))
        dest = uid if private else chat
        self._check(text, dest, cause, private)
        if res.get("edit") and on is not None and not private and on.chat == dest:
            on.text, on.keyboard, on.cause, on.ok = text, res.get("keyboard"), cause, res.get("ok", True)
            box = self.inbox(dest)            # پیامِ ویرایش‌شده را ته صف بیاور
            box.remove(on)
            box.append(on)
            return on
        msg = Message(dest, text, res.get("keyboard"), cause, res.get("ok", True))
        self.inbox(dest).append(msg)
        return msg

    def _run(self, cmd: str, chat: int, uid: int, arg: str) -> dict:
        private = chat != self.group
        target = route_chat(cmd, chat, uid, private)
        if not target:
            return {"ok": False, "text": AMBIGUOUS, "keyboard": None, "private": True}
        res = handle(cmd, target, uid, self.names.get(uid, ""), arg)
        res["_target"] = target               # مثل telegram_app._dispatch
        return res

    def command(self, uid: int, text: str, chat: int) -> Message:
        """دستور تایپ‌شده (فقط /start و /new برای باز کردن منو لازم است)."""
        self.clock.advance(2)
        cmd, _, arg = text.lstrip("/").partition(" ")
        if cmd not in bot._ROUTES:
            cmd, arg = "menu", ""
        res = self._run(cmd, chat, uid, arg)
        return self._deliver(res, chat, uid, f"/{cmd}")

    def press(self, uid: int, msg: Message, button: dict) -> Optional[Message]:
        """تپ روی دکمه‌ای که واقعاً روی پیامِ قابل‌دیدنِ این کاربر است."""
        if msg not in self.inbox(msg.chat) or button not in msg.buttons():
            raise AssertionError(f"دکمه‌ی {button} روی پیام {msg.mid} نیست")
        if msg.chat not in (self.group, uid):
            raise AssertionError("این پیام را این کاربر نمی‌بیند")
        self.presses += 1
        self.clock.advance(2)                 # آدم‌ها سریع‌تر از ۲ ثانیه نمی‌زنند
        if "url" in button:
            m = re.search(r"[?&]start=([^&]+)", button["url"])
            if not m:
                return None                   # لینک اشتراک/افزودن به گروه — بیرون از ربات
            res = self._run("start", uid, uid, m.group(1))
            return self._deliver(res, uid, uid, f"url:start={m.group(1)}")
        data = button["callback_data"]
        if bot.is_dup_callback(msg.chat, uid, data):
            return None
        cmd, arg = parse_callback(data)
        res = self._run(cmd, msg.chat, uid, arg)
        return self._deliver(res, msg.chat, uid, data, on=msg)

    def type_text(self, uid: int, text: str) -> Message:
        """مثل on_text: اگر ربات منتظر متن است همان را می‌گیرد، وگرنه تابلوی دکمه‌ها."""
        self.clock.advance(3)
        pending = take_pending(uid)
        if pending and text:
            chat, cmd = pending
            res = handle(cmd, chat, uid, self.names.get(uid, ""), text)
            res["_target"] = chat
        else:
            res = self._run("commands", uid, uid, "")
        return self._deliver(res, uid, uid, "text")

    def timer_job(self) -> Optional[Message]:
        """مثل _timer_job: هر ۱۵ ثانیه tick؛ فقط وقتی فاز واقعاً جلو رفت پیام می‌دهد."""
        res = handle("tick", self.group)
        out = None
        if res.get("advanced"):               # پیام کامل + کیبورد، مثل _timer_job
            out = self._put(res, self.group, "timer")
        for m in res.get("outbox") or []:
            self._put({"text": m["text"], "keyboard": m.get("keyboard")}, m["chat"], "outbox<timer")
        return out
