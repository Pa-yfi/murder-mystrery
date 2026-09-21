"""موتور دیالوگ قانون‌محور (بدون LLM).
پاسخ NPC/خنثی از روی: راز شخصی + استرس + اعتماد + سابقه‌ی دروغ ساخته می‌شود. کاملاً قطعی.
"""
from __future__ import annotations
import hashlib
from typing import List, Optional
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

# سرنخ‌های گره‌خورده به همین پرونده — جای کلیدها از روی Case پر می‌شود
CASE_TELLS = [
    "وقتی اسم «{place}» می‌آید، حرفش را عوض می‌کند.",
    "می‌گوید {weapon} را هرگز ندیده — ولی بی‌آنکه بپرسی توصیفش کرد.",
    "درباره‌ی {victim} به زمان گذشته حرف می‌زند، انگار از قبل می‌دانسته.",
    "ادعا می‌کند ساعت {t} خواب بوده؛ صدای {place} همان ساعت شنیده شده.",
    "تا حرف «{motive}» شد، ساکت شد.",
    "می‌گوید کل شب تنها بوده و هیچ شاهدی ندارد.",
    "جزئیاتی از صحنه می‌داند که هنوز عمومی نشده است.",
]

# سرنخ‌هایی که از اتفاقِ واقعیِ دیشب می‌آیند، نه از هوا
FACT_TELLS = {
    "visited": "دیشب جایی رفته بود؛ می‌گوید «هوا خوردن»، ولی مسیرش را نمی‌گوید.",
    "was_visited": "می‌گوید دیشب کسی در خانه‌اش را زده و او باز نکرده.",
    "framed": "اثر انگشتش روی صحنه هست — و خودش هم از این بابت جا خورده.",
    "blackout": "می‌گوید در قطعی برق هیچ‌جا نرفت؛ ولی چراغ‌قوه‌اش خالی است.",
    "storm": "لباس‌هایش از طوفان دیشب خیس است، هرچند می‌گوید بیرون نرفته.",
    "threatened": "دستش به تلفن می‌رود و پشیمان می‌شود؛ انگار از کسی می‌ترسد.",
}


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


def interrogation_hints(suspect: Player, day: int, case=None,
                        facts: Optional[dict] = None, n: int = 3) -> List[str]:
    """سرنخ‌های بازجو — مبهم ولی *مشخص*: به همین پرونده و همین شب گره خورده‌اند.

    سه لایه روی هم: یک نشانه‌ی رفتاری، یک نشانه از جزئیاتِ همین پرونده، و
    نشانه‌هایی که از اتفاقِ واقعیِ دیشب می‌آیند. چون seed شامل روز است،
    شب دوم و سوم و چهارم هرگز همان متن قبلی را نمی‌دهند.
    قاتل شانس بیشتری برای «tell» مجرمانه دارد، اما بی‌گناهِ پراسترس هم می‌تواند همان را بدهد.
    """
    facts = facts or {}
    s = stress_of(suspect)
    out: List[str] = []

    # لایه ۱ — رفتار
    for i in range(max(1, n - 2)):
        out.append(TELLS[_h(suspect.uid, day, i, s) % len(TELLS)])

    # لایه ۲ — جزئیات همین پرونده
    if case is not None:
        tpl = CASE_TELLS[_h(suspect.uid, day, "case") % len(CASE_TELLS)]
        t = case.timeline[2].split("—")[0].strip() if len(case.timeline) > 2 else "۲۳:۱۵"
        out.append(tpl.format(place=case.place, weapon=case.weapon,
                              victim=case.victim, motive=case.motive, t=t))

    # لایه ۳ — آنچه دیشب واقعاً اتفاق افتاد
    for key, line in FACT_TELLS.items():
        if facts.get(key):
            out.append(line)

    conf = "ضعیف" if s < 35 else ("متوسط" if s < 70 else "بالا")
    out.append(f"سطح تنش: {conf} (این سطح، اثباتِ گناه نیست).")
    if _h(suspect.uid, day, "bias") % 100 < 20:
        out.append("⚠️ نشانه‌ی متناقض: داستانش با تایم‌لاین کمی جور در نمی‌آید.")
    return out
