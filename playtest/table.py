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
        self.clock_msg: Optional[Message] = None   # پیامِ ساعتِ فازِ فعلی (مثل telegram_app.CLOCKS)
        self.clock_key = None
        self.clock_final = ""                 # متنِ کارت وقتی فازش تمام شد (محتوا می‌ماند، ساعت نه)
        self.toasts: List[Message] = []      # پیامِ شناورِ روی دکمه (answerCallbackQuery) — به چت نمی‌رود
        self.clock_edits = 0
        self.clock_msgs = 0
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
            out = self._put({"text": m["text"], "keyboard": m.get("keyboard"), "ok": True},
                            m["chat"], f"outbox<{cause}")
            if m.get("card"):
                self._adopt_card(out)
        return msg

    def _adopt_card(self, msg: Message) -> None:
        """مثل telegram_app: پیامِ «کارت» ساعتِ زنده‌ی فاز می‌شود؛ کارتِ فازِ قبل محتوایش را نگه می‌دارد
        ولی ساعت و دکمه‌هایش برداشته می‌شود."""
        view = bot.clock_view(self.group)
        if view is None or msg.chat != self.group:
            return
        self._finish_clock()
        self.clock_msg, self.clock_key, self.clock_final = msg, view["key"], view.get("final", "")
        self.clock_msgs += 1

    def _finish_clock(self) -> None:
        if self.clock_msg is not None:
            self.clock_msg.text = self.clock_final or (self.clock_msg.text + "\n☑️ این مرحله تمام شد.")
            self.clock_msg.keyboard = None
        self.clock_msg, self.clock_key, self.clock_final = None, None, ""

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
        if res.get("toast") and on is not None:      # مثل on_callback: فقط پیامِ شناور برای خودِ زننده
            toast = Message(uid, res["toast"], None, cause, res.get("ok", True))
            self.toasts.append(toast)
            return toast
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
        if res.get("card") and dest == self.group:
            self._adopt_card(msg)
        elif res.get("clock") and dest == self.group:     # مثل _reply: همین پیام کارتِ زنده است
            view = bot.clock_view(self.group)
            if view:
                if self.clock_msg is not None and self.clock_msg in self.inbox(self.group):
                    self.inbox(self.group).remove(self.clock_msg)
                self.clock_msg, self.clock_key = msg, view["key"]
                self.clock_msgs += 1
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
        out = self._deliver(res, chat, uid, f"/{cmd}")
        self.update_clock()                   # مثل _reply: کارتِ زنده بلافاصله
        return out

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
            out = self._deliver(res, uid, uid, f"url:start={m.group(1)}")
            self.update_clock()               # «✅ آماده‌ام» در پیوی → کارتِ لابی در گروه
            return out
        data = button["callback_data"]
        if bot.is_dup_callback(msg.chat, uid, data):
            return None
        cmd, arg = parse_callback(data)
        res = self._run(cmd, msg.chat, uid, arg)
        out = self._deliver(res, msg.chat, uid, data, on=msg)
        self.update_clock()
        return out

    def type_text(self, uid: int, text: str) -> Message:
        """مثل on_text: اگر ربات منتظر متن است همان را می‌گیرد، وگرنه تابلوی دکمه‌ها."""
        self.clock.advance(3)
        pending = take_pending(uid)
        if pending and text:
            chat, cmd = pending
            res = handle(cmd, chat, uid, self.names.get(uid, ""), text)
            res["_target"] = chat
        else:
            res = self._run("menu", uid, uid, "")        # مثل on_text: پنلِ بازیِ جاری
        out = self._deliver(res, uid, uid, "text")
        self.update_clock()
        return out

    def chat(self, uid: int, text: str) -> Message:
        """پیامِ معمولیِ بازیکن در گروه (بحث، ادعا، بلوف). مثل on_text: اگر ربات منتظرِ متنِ او
        نیست، هیچ جوابی نمی‌دهد؛ پیام فقط برای بقیه‌ی بازیکن‌ها دیده می‌شود."""
        self.clock.advance(4)
        msg = Message(self.group, text, None, f"chat:{uid}")
        self.inbox(self.group).append(msg)
        if bot._PENDING.get(uid):                 # همان مسیرِ on_text
            chat, cmd = take_pending(uid)
            res = handle(cmd, chat, uid, self.names.get(uid, ""), text)
            res["_target"] = chat
            self._deliver(res, self.group, uid, "chat-text")
        return msg

    def timer_job(self) -> Optional[Message]:
        """مثل _timer_job: tick؛ پیام فقط وقتی فاز واقعاً جلو رفت؛ بعد پیامِ ساعت ویرایش می‌شود."""
        res = handle("tick", self.group)
        out = None
        if res.get("advanced"):               # پیام کامل + کیبورد، مثل _timer_job
            out = self._put(res, self.group, "timer")
            if res.get("card"):
                self._adopt_card(out)
        for m in res.get("outbox") or []:
            o = self._put({"text": m["text"], "keyboard": m.get("keyboard")}, m["chat"], "outbox<timer")
            if m.get("card"):
                self._adopt_card(o)
        self.update_clock()
        return out

    def update_clock(self) -> None:
        """مثل telegram_app._update_clock: یک پیام برای هر فاز؛ همان پیام ویرایش می‌شود."""
        view = bot.clock_view(self.group)
        if self.clock_msg is not None and (view is None or view["key"] != self.clock_key):
            self._finish_clock()
        if view is None:
            return
        self._check(view["text"], self.group, "clock", private=False)
        if self.clock_msg is None:
            self.clock_msg = Message(self.group, view["text"], view["keyboard"], "clock")
            self.inbox(self.group).append(self.clock_msg)
            self.clock_key, self.clock_final = view["key"], view.get("final", "")
            self.clock_msgs += 1
        elif self.clock_msg.text != view["text"]:
            self.clock_msg.text, self.clock_msg.keyboard = view["text"], view["keyboard"]
            self.clock_edits += 1
