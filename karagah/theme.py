"""نسخه ۹: زبانِ بصریِ ربات — یک جا برای همه‌ی قاب‌ها، نوارها، ساعت‌ها و گذارها.

بر پایه‌ی امکاناتِ تازه‌ی تلگرام (Bot API 9.4 تا 10.x، ۲۰۲۶):
  • رنگِ دکمه‌ها با فیلدِ style (danger / success / primary) — ui.style_for
  • آیکونِ ایموجیِ متحرک روی دکمه (icon_custom_emoji_id) — فقط اگر صاحب ربات Premium دارد؛
    شناسه‌ها از .env (BUTTON_EMOJI) و در صورتِ رد شدن، آداپتور بی‌آیکون دوباره می‌فرستد
  • افکتِ پیام (message_effect_id: 🎉 🔥 …) — فقط در پیوی؛ شناسه‌ها از .env قابل عوض کردن‌اند
    چون تلگرام آن‌ها را بی‌اعلام عوض می‌کند (EFFECT_ID_INVALID → بی‌افکت)
  • پیامی که فقط یک ایموجی است، بزرگ و متحرک نمایش داده می‌شود → فریم‌های گذار تک‌ایموجی‌اند
  • ویرایشِ پیامِ ساعت: ساعت‌شنیِ ⏳/⌛ هر ویرایش برمی‌گردد و درخششِ ✨ روی نوار جلو می‌رود
"""
from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

# ── گذارهای تک‌ایموجی (بزرگ و متحرک در تلگرام) ──────────────────────────
ANIM: Dict[str, List[str]] = {
    "night": ["🌇", "🌆", "🌃", "🌙"],
    "morning": ["🌌", "🌄", "🌅", "☀️"],
    "vote": ["🗳️", "📊"],
    "interrogation": ["🚪", "🔦"],
    "jail": ["🔒", "⛓️"],
    "court": ["⚖️", "👨‍⚖️"],
    "end": ["🏁", "🎉"],
    "start": ["🕯️", "🔍", "🕵️"],
}

# ── رنگ‌بندیِ هر فاز: (ایموجیِ فاز، رنگِ نوار، رنگِ نوارِ کم‌وقت) ─────────────
PALETTE: Dict[str, tuple] = {
    "لابی": ("🏛️", "🟦", "🟧"),
    "شب": ("🌙", "🟪", "🟥"),
    "اتاق بازجویی": ("🔦", "🟪", "🟥"),
    "صبح": ("☀️", "🟨", "🟥"),
    "گفتگو": ("💬", "🟩", "🟥"),
    "رای‌گیری": ("🗳️", "🟧", "🟥"),
    "هیئت منصفه": ("⚖️", "🟫", "🟥"),
    "پایان": ("🏁", "🟩", "🟩"),
}

HOURGLASS = ("⏳", "⌛")
EMPTY = "⬜"
SHINE = "✨"


def hourglass(tick: int) -> str:
    """ساعت‌شنی با هر تیکِ ساعت (هر ثانیه) یک بار برمی‌گردد."""
    return HOURGLASS[tick % 2]


def shiny_bar(left: int, full: int, tick: int, phase: str = "", cells: int = 10) -> str:
    """نوارِ رنگی: رنگِ فاز، در ۲۰٪ آخر قرمز؛ یک ✨ روی بخشِ پر هر تیک یک خانه جلو می‌رود."""
    _icon, color, low = PALETTE.get(phase, ("", "🟩", "🟥"))
    if full <= 0:
        return EMPTY * cells
    filled = max(0, min(cells, round(cells * left / full)))
    c = low if left <= full * 0.2 else color
    bar = [c] * filled + [EMPTY] * (cells - filled)
    if filled >= 3:
        bar[tick % filled] = SHINE
    return "".join(bar)


DIV = "┈" * 16                     # تنها جداکننده‌ی متن‌ها


def ribbon(icon: str, title: str) -> str:
    """سربرگِ هر کارت: ایموجی دو طرف و خطِ نازک — در راست‌به‌چپ هم مرتب می‌ماند."""
    return f"{icon} ┈┈ *{title}* ┈┈ {icon}"


def card(icon: str, title: str, lines: List[str], foot: Optional[str] = None) -> str:
    body = "\n".join(l for l in lines if l)
    out = f"{ribbon(icon, title)}\n{body}"
    if foot:
        out += f"\n{DIV}\n{foot}"
    return out


def dots(done: int, total: int) -> str:
    """پیشرفتِ گسسته (آمادگی لابی، رای‌ها): 🟢🟢⚪⚪"""
    done = max(0, min(total, done))
    return "🟢" * done + "⚪" * (total - done)


# ── افکتِ پیام (فقط پیوی) و آیکونِ ایموجیِ دکمه (فقط صاحبِ Premium) ─────────
EFFECTS: Dict[str, str] = {
    "fire": "5104841245755180586",     # 🔥
    "party": "5046509860389126442",    # 🎉
    "like": "5107584321108051014",     # 👍
    "dislike": "5104858069142078462",  # 👎
    "heart": "5159385139981059251",    # ❤️
}
try:
    EFFECTS.update(json.loads(os.getenv("MESSAGE_EFFECTS", "{}") or "{}"))
except ValueError:
    pass
EFFECTS_ON = os.getenv("MESSAGE_EFFECTS_ENABLED", "1") != "0"


def effect_id(name: Optional[str]) -> Optional[str]:
    if not name or not EFFECTS_ON:
        return None
    return EFFECTS.get(name)


# {"act": "5368324170671202286", "vote": "…"} — پیشوندِ callback → شناسه‌ی ایموجیِ سفارشی
try:
    BUTTON_EMOJI: Dict[str, str] = json.loads(os.getenv("BUTTON_EMOJI", "{}") or "{}")
except ValueError:
    BUTTON_EMOJI = {}


def button_icon(cb: str) -> Optional[str]:
    if not cb or not BUTTON_EMOJI:
        return None
    key = cb.split(":")[0]
    return BUTTON_EMOJI.get(cb) or BUTTON_EMOJI.get(key)
