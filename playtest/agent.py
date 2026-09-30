"""یک بازیکنِ شبیه‌سازی: مستندات را می‌خواند، بعد فقط با دکمه بازی می‌کند.

قاعده‌ی سخت: agent فقط دکمه‌ای را می‌زند که روی پیامی در گروه یا پیویِ خودش
دیده است. اگر دکمه‌ی لازم جلوی چشمش نباشد، مثل یک آدم منوها را باز می‌کند
(«/start» در پیوی → «🎛️ همه‌ی دکمه‌ها» → دسته → دکمه). تایپ فقط برای متن آزاد
(پرسش، دفاع، وصیت، یادداشت) — همان‌جا که خود ربات متن می‌خواهد.
"""
from __future__ import annotations

import random
import re
from typing import Callable, Dict, List, Optional, Set, Tuple

from karagah import menus

from .docs import Rulebook
from .table import Message, Telegram

Pred = Callable[[dict], bool]


def cb_is(cmd: str) -> Pred:
    return lambda b: b.get("callback_data") == cmd


def cb_starts(prefix: str) -> Pred:
    return lambda b: str(b.get("callback_data", "")).startswith(prefix)


class Agent:
    def __init__(self, uid: int, name: str, tg: Telegram, rng: random.Random):
        self.uid, self.name, self.tg, self.rng = uid, name, tg, rng
        tg.names[uid] = name
        self.rb: Optional[Rulebook] = None
        self.docs_read: List[str] = []
        self.role = ""
        self.team: Set[str] = set()           # نام هم‌تیمی‌های قاتل
        self.fate: Optional[str] = None
        self.clean: Set[str] = set()          # یافته‌های کارآگاه
        self.dirty: Set[str] = set()
        self.suspicion: Dict[str, int] = {}
        self.notes_seen: List[str] = []
        self.nav_log: List[str] = []           # مسیرِ دکمه‌هایی که زده
        self.last: Optional[Message] = None    # آخرین پاسخ ربات به این agent

    # ── خواندن مستندات (اجباری) ──
    def read_docs(self, rb: Rulebook) -> None:
        self.rb = rb
        self.docs_read = list(rb.files)

    @property
    def ready_to_play(self) -> bool:
        return bool(self.rb and self.docs_read)

    # ── دیدن و زدن دکمه ──
    def _recent(self, where: Tuple[str, ...], depth: int) -> List[Message]:
        msgs: List[Message] = []
        if "dm" in where:
            msgs += self.tg.inbox(self.uid)[-depth:]
        if "group" in where:
            msgs += self.tg.inbox(self.tg.group)[-depth:]
        return sorted(msgs, key=lambda m: m.mid, reverse=True)

    def find(self, pred: Pred, where=("dm", "group"), depth=6):
        for m in self._recent(where, depth):
            for b in m.buttons():
                if pred(b):
                    return m, b
        return None

    def press(self, m: Message, b: dict) -> Optional[Message]:
        self.nav_log.append(b.get("callback_data") or b.get("url", "")[:40])
        out = self.tg.press(self.uid, m, b)
        if out is not None:
            self.last = out
        return out

    def tap(self, pred: Pred, where=("dm", "group"), depth=6, nav: Optional[str] = None):
        """دکمه را از روی پیام‌های اخیر بزن؛ اگر نبود و nav داده شده، از منو برو."""
        hit = self.find(pred, where, depth)
        if hit:
            return self.press(*hit)
        if nav:
            return self.navigate(nav, pred)
        return None

    def open_dm_menu(self) -> Message:
        self.last = self.tg.command(self.uid, "/start", self.uid)
        return self.last

    def navigate(self, cmd: str, pred: Optional[Pred] = None) -> Optional[Message]:
        """از منوی «همه‌ی دکمه‌ها» در پیوی به دکمه‌ی cmd برو و بزنش."""
        pred = pred or cb_is(cmd)
        key = next((k for k, _t, items in menus.GROUPS if any(cb == cmd for _l, cb in items)), None)
        if key is None:
            return None
        hit = self.find(cb_is("commands"), ("dm",), 2)
        if not hit:
            self.open_dm_menu()
            hit = self.find(cb_is("commands"), ("dm",), 1)
        if not hit:
            return None
        self.press(*hit)
        hit = self.find(cb_is(f"group:{key}"), ("dm",), 1)
        if not hit:
            return None
        self.press(*hit)
        hit = self.find(pred, ("dm",), 1) or self.find(cb_is(cmd), ("dm",), 1)
        return self.press(*hit) if hit else None

    def say(self, text: str) -> Message:
        """متن آزاد — فقط وقتی ربات منتظرش است (پرسش/دفاع/وصیت/یادداشت)."""
        self.last = self.tg.type_text(self.uid, text)
        return self.last

    # ── فهمیدنِ پیام‌ها ──
    def learn_role(self, text: str) -> None:
        m = re.search(r"نقش تو: ([^\*\n]+)", text)
        if m:
            self.role = m.group(1).strip()
        self.team = set(re.findall(r"هم‌تیمی: ([^\n]+)", text))
        f = re.search(r"سرنوشتت به (.+?) گره", text)
        self.fate = f.group(1) if f else None

    def learn_notes(self, text: str) -> List[str]:
        new = []
        for line in text.splitlines():
            line = line.strip(" •")
            if line and line not in self.notes_seen:
                self.notes_seen.append(line)
                new.append(line)
                m = re.match(r"شب (\d+): (.+?) → (پاک|مشکوک)", line)
                if m:
                    (self.clean if m.group(3) == "پاک" else self.dirty).add(m.group(2))
                m = re.search(r"کنار (.+?) با (.+?) روبه‌رو شدی", line)
                if m:
                    for n in m.group(2).split("، "):
                        self.suspicion[n] = self.suspicion.get(n, 0) + 1
        return new

    def buttons_named(self, msg: Optional[Message], prefix: str) -> List[dict]:
        if not msg:
            return []
        return [b for b in msg.buttons() if str(b.get("callback_data", "")).startswith(prefix)]

    def name_of_button(self, b: dict) -> str:
        return re.sub(r"^(✅|👉|👤)\s*", "", b["text"]).strip()
