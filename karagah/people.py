"""ظاهر شخصیت‌ها و سرنخ‌های شاهد.

هر بازیکن یک ظاهرِ ثابت دارد (قد، هیکل، مو، نشانه‌ی چهره، لباسِ آن شب).
شاهدها این‌ها را *ناقص* می‌بینند: یک یا دو ویژگی، نه یک پرونده‌ی کامل.

قاعده‌ی طراحی: ویژگی‌ها عمداً بین چند نفر مشترک‌اند. «مرد بلندقامت با پالتو
تیره» باید به سه نفر بخورد، نه یکی؛ وگرنه اولین سرنخِ شاهد بازی را تمام
می‌کند. همان اصلِ «سرنخ محدودکننده است، نه شناساگر».
"""
from __future__ import annotations
import random
from typing import Dict, List

HEIGHT = ["بلندقامت", "میان‌بالا", "کوتاه‌قد"]
BUILD = ["لاغر", "چهارشانه", "میان‌اندام"]
HAIR = ["موی کوتاه", "موی بلند", "موی جوگندمی", "سر تراشیده", "موی فرفری"]
MARK = ["عینک", "سبیل پرپشت", "زخمی روی ابرو", "خالی کنار چانه",
        "ریش کوتاه", "گوشواره", "بدون نشانه‌ی خاص", "کلاه همیشگی"]
COAT = ["پالتو تیره", "کاپشن روشن", "بارانی بلند", "ژاکت خاکستری",
        "کت اسپرت", "شال‌گردن قرمز"]

# ویژگی‌هایی که شاهد ممکن است به یاد بیاورد، به ترتیبِ «چقدر از دور دیده می‌شود»
VISIBLE = ("height", "build", "coat", "hair", "mark")

FIELD_FA = {"height": "قد", "build": "هیکل", "hair": "مو",
            "mark": "نشانه", "coat": "لباس آن شب"}


def assign(uids: List[int], rng: random.Random) -> Dict[int, Dict[str, str]]:
    """ظاهرِ همه — با برخوردِ عمدی.

    از استخرهای کوچک برمی‌داریم تا چند نفر قد یا لباسِ یکسان داشته باشند.
    """
    small_h = rng.sample(HEIGHT, min(2, len(HEIGHT)))      # فقط دو قد در شهر
    small_c = rng.sample(COAT, min(3, len(COAT)))
    out: Dict[int, Dict[str, str]] = {}
    for u in uids:
        out[u] = {
            "height": rng.choice(small_h),
            "build": rng.choice(BUILD),
            "hair": rng.choice(HAIR),
            "mark": rng.choice(MARK),
            "coat": rng.choice(small_c),
        }
    return out


def describe(app: Dict[str, str]) -> str:
    """پرونده‌ی کاملِ ظاهر — چیزی که کارآگاه با استعلامش می‌گیرد."""
    if not app:
        return "— ثبتی نیست —"
    return "، ".join(f"{FIELD_FA[k]}: {app[k]}" for k in VISIBLE if k in app)


def witness_line(app: Dict[str, str], rng: random.Random) -> str:
    """آنچه شاهد می‌گوید: یک یا دو ویژگی، با تردیدِ صادقانه."""
    if not app:
        return ""
    n = rng.choice((1, 2, 2))
    keys = rng.sample(VISIBLE, n)
    bits = "، ".join(app[k] for k in keys if k in app)
    hedge = rng.choice((
        "چهره‌اش را ندیدم.",
        "از پشت دیدمش.",
        "هوا تاریک بود؛ مطمئن نیستم.",
        "فقط یک لحظه بود.",
    ))
    return f"کسی {bits} آنجا بود. {hedge}"


def matches(app: Dict[str, str], line: str) -> List[str]:
    """کدام ویژگی‌های این شخص در متنِ شاهد آمده — برای تطبیقِ کارآگاه."""
    return [FIELD_FA[k] for k in VISIBLE if app.get(k) and app[k] in line]
