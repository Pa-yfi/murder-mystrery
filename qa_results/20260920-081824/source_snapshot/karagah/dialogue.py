"""موتور دیالوگ قانون‌محور (بدون LLM).
پاسخ NPC/خنثی از روی: راز شخصی + استرس + اعتماد + سابقه‌ی دروغ ساخته می‌شود. کاملاً قطعی.
"""
from __future__ import annotations
import hashlib
from typing import List
from .models import Player, Align

CALM = [
    "من همان ساعت در آشپزخانه بودم؛ هر کسی خواست بپرسد.",
    "سؤالت را واضح‌تر بپرس، چیزی برای پنهان کردن ندارم.",
    "من مقتول را دوست داشتم. دنبال قاتل بگردید، نه من.",
]
NERVOUS = [
    "من… راستش دقیق یادم نیست ساعت چند بود.",
    "چرا همه‌ی سؤال‌ها از من است؟ از بقیه هم بپرسید.",
    "بله دیدمش، ولی فقط یک لحظه. همین.",
]
PANIC = [
    "دست از سرم بردارید! من کاری نکردم!",
    "باشد… یک چیزی هست، ولی ربطی به قتل ندارد.",
    "شما دارید مرا به کشتن می‌دهید. این عدالت نیست.",
]

TELLS = [
    "دستش می‌لرزد.",
    "به چشم‌های بازجو نگاه نمی‌کند.",
    "قبل از هر جواب مکث می‌کند.",
    "خیلی سریع و آماده جواب می‌دهد.",
    "بی‌دلیل عرق کرده است.",
    "کاملاً آرام است؛ شاید زیادی آرام.",
]


def _h(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest(), 16)


def stress_of(p: Player) -> int:
    s = p.stress
    if p.align is Align.KILLER:
        s += 25
    if p.align is Align.NEUTRAL:
        s += 10
    s += 20 * len([n for n in p.notes if n.startswith("دروغ")])
    return max(0, min(100, s))


def answer(p: Player, question: str, day: int) -> str:
    s = stress_of(p)
    pool = CALM if s < 35 else (NERVOUS if s < 70 else PANIC)
    base = pool[_h(p.uid, question, day) % len(pool)]
    if p.secrets and s >= 70:
        base += f" (زیر لب: «{p.secrets[0]}»)"
    return base


def interrogation_hints(suspect: Player, day: int, n: int = 3) -> List[str]:
    """سرنخ‌های مبهم برای بازجو — هرگز قطعی نیست.
    قاتل شانس بیشتری برای «tell» مجرمانه دارد، اما بی‌گناهِ پراسترس هم می‌تواند همان را بدهد."""
    s = stress_of(suspect)
    guilty_bias = _h(suspect.uid, day, "bias") % 100
    tells = []
    for i in range(n):
        idx = _h(suspect.uid, day, i, s) % len(TELLS)
        tells.append(TELLS[idx])
    conf = "ضعیف" if s < 35 else ("متوسط" if s < 70 else "بالا")
    tells.append(f"سطح تنش: {conf} (این سطح، اثباتِ گناه نیست).")
    if guilty_bias < 20:
        tells.append("⚠️ نشانه‌ی متناقض: داستانش با تایم‌لاین کمی جور در نمی‌آید.")
    return tells
