"""بومی‌سازی خروجی: همه‌ی عددهایی که بازیکن می‌بیند با رقم فارسی.

قبلاً متن‌ها قاطی بودند («صبح روز 1» کنار «صبحِ روز ۱»). به‌جای عوض کردن صدها f-string،
پاسخِ نهاییِ ربات یک بار از این صافی رد می‌شود. دست نمی‌خورند:
  • کدهایی که به حرف لاتین چسبیده‌اند (C12، v7) — بازیکن همین کد را روی دکمه می‌بیند
  • لینک‌ها (https://…، t.me/…) و متنِ داخلِ `بک‌تیک`
  • callback_data و url دکمه‌ها (فقط برچسبِ دکمه فارسی می‌شود)
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict

FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_KEEP = re.compile(r"(https?://\S+|t\.me/\S+|`[^`]*`)")
_NUM = re.compile(r"(?<![A-Za-z_\d])\d+(?![A-Za-z_])")


def fa_digits(text: str) -> str:
    if not text or not any(ch.isdigit() and ch.isascii() for ch in text):
        return text
    parts = _KEEP.split(text)
    for i in range(0, len(parts), 2):               # زوج‌ها متنِ عادی‌اند، فردها لینک/کد
        parts[i] = _NUM.sub(lambda m: m.group(0).translate(FA), parts[i])
    return "".join(parts)


RLM = "\u200f"


def rtl_guard(text: str) -> str:
    """تلگرام جهتِ پاراگراف را از اولین حرفِ «قوی» می‌گیرد؛ پیامی که با C12 شروع شود چپ‌چین می‌شد.
    یک نشانه‌ی نامرئیِ راست‌به‌چپ (RLM) جلویش می‌گذاریم."""
    for ch in text or "":
        d = unicodedata.bidirectional(ch)
        if d in ("R", "AL"):
            return text
        if d == "L":
            return RLM + text
    return text


def localize_keyboard(kb: Any) -> Any:
    if not isinstance(kb, dict) or "inline_keyboard" not in kb:
        return kb
    rows = []
    for row in kb["inline_keyboard"]:
        new = []
        for b in row:
            b = dict(b)
            if "text" in b:
                b["text"] = fa_digits(b["text"])
            new.append(b)
        rows.append(new)
    return {**kb, "inline_keyboard": rows}


def localize(res: Dict) -> Dict:
    """پاسخِ handle(): متن، کیبورد و صندوق خروجی."""
    if not isinstance(res, dict):
        return res
    out = dict(res)
    if isinstance(out.get("text"), str):
        out["text"] = rtl_guard(fa_digits(out["text"]))
    if out.get("keyboard"):
        out["keyboard"] = localize_keyboard(out["keyboard"])
    if out.get("outbox"):
        out["outbox"] = [{**m, "text": rtl_guard(fa_digits(m.get("text", ""))),
                          "keyboard": localize_keyboard(m.get("keyboard"))} for m in out["outbox"]]
    return out
