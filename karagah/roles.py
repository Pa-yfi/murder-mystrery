"""کاتالوگ نقش‌ها، تقسیم نقش بر اساس تعداد بازیکن، و دسترسی اطلاعاتی هر نقش."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List
from .models import Align

# ability: کلید اکشن شبانه | info: نوع اطلاعاتی که فقط این نقش می‌بیند


@dataclass(frozen=True)
class RoleDef:
    name: str
    align: Align
    emoji: str
    ability: str          # "" یعنی بدون اکشن شبانه
    info: str             # نوع دسترسی اطلاعاتی اختصاصی
    desc: str


ROLES: Dict[str, RoleDef] = {r.name: r for r in [
    # ---------------- تیم شهر ----------------
    RoleDef("کارآگاه", Align.CITY, "🕵️", "investigate", "align_check",
            "هر شب هویت تیمی یک نفر را استعلام می‌کند (خنثی‌ها «مشکوک» نشان داده می‌شوند)."),
    RoleDef("بازجو", Align.CITY, "🔦", "", "interrogation_hints",
            "متهمِ داخل بازجویی را استنطاق می‌کند و سرنخ‌های مبهم دریافت می‌کند؛ حکم حبس موقت با اوست."),
    RoleDef("پزشک قانونی", Align.CITY, "🧪", "autopsy", "forensic",
            "هر شب نتیجه‌ی آزمایشگاهیِ یک مدرک را زودتر می‌بیند."),
    RoleDef("پزشک", Align.CITY, "💉", "protect", "save_log",
            "هر شب از یک نفر محافظت می‌کند؛ نمی‌تواند دو شب پشت‌سرهم یک نفر را انتخاب کند."),
    RoleDef("نگهبان", Align.CITY, "🛡️", "watch", "visit_count",
            "هر شب یک نفر را زیر نظر می‌گیرد و تعداد ملاقات‌های او را می‌بیند."),
    RoleDef("خبرنگار", Align.CITY, "📰", "reveal", "public_leak",
            "هر شب یک مدرک اضافه برای کل شهر رو می‌کند."),
    RoleDef("وکیل", Align.CITY, "⚖️", "", "jury_power",
            "می‌تواند بدون هم‌قسم شدن با دیگران، به‌تنهایی درخواست هیئت منصفه بدهد."),
    RoleDef("شهروند", Align.CITY, "👤", "", "none",
            "بدون قدرت ویژه؛ فقط منطق و رای."),
    RoleDef("کالبدشکاف", Align.CITY, "🔬", "", "autopsy_detail",
            "بعد از هر قتل، ساعت دقیق مرگ و نوع سلاح را می‌فهمد."),
    RoleDef("شکارچی", Align.CITY, "🏹", "hunter", "none",
            "اگر حبس ابد بخورد یا کشته شود، یک نفر را با شلیک آخر با خود می‌برد."),
    # ---------------- تیم قاتل ----------------
    RoleDef("قاتل", Align.KILLER, "🔪", "kill", "team_ids",
            "هر شب هدف قتل را انتخاب می‌کند؛ هم‌تیمی‌هایش را می‌شناسد."),
    RoleDef("همدست", Align.KILLER, "🧤", "frame", "team_ids",
            "هر شب اثر انگشت جعلی روی یک نفر می‌گذارد؛ مدرک روز بعد به او اشاره می‌کند."),
    RoleDef("سم‌ساز", Align.KILLER, "☠️", "poison", "team_ids",
            "هدفش دو شب بعد می‌میرد مگر پزشک او را نجات دهد."),
    RoleDef("خبرچین", Align.KILLER, "📞", "spy", "watch_officer",
            "هر شب می‌فهمد بازجو چه کسی را استنطاق کرده است."),
    # ---------------- خنثی ----------------
    RoleDef("سپر بلا", Align.NEUTRAL, "🎭", "", "none",
            "اگر حبس ابد بخورد، به‌تنهایی برنده می‌شود. کارآگاه او را «مشکوک» می‌بیند."),
    RoleDef("جانی سریالی", Align.NEUTRAL, "🩸", "kill", "none",
            "شب‌ها مستقل می‌کشد؛ در پایان باید تنها بازمانده باشد."),
    RoleDef("بقال محله", Align.NEUTRAL, "🏪", "", "rumor",
            "هر روز یک شایعه می‌شنود که ۷۰٪ درست است."),
    RoleDef("قاچاقچی", Align.NEUTRAL, "🚬", "hide", "none",
            "هر شب یک نفر را از دید کارآگاه/نگهبان مخفی می‌کند؛ برنده می‌شود اگر تا آخر زنده بماند."),
]}

# ترکیب‌ها: طبق «کمینه ۴ – بیشینه ۸»
COMPOSITIONS: Dict[int, List[str]] = {
    4: ["قاتل", "بازجو", "کارآگاه", "شهروند"],
    5: ["قاتل", "بازجو", "کارآگاه", "پزشک", "شهروند"],
    6: ["قاتل", "بازجو", "کارآگاه", "پزشک", "شهروند", "سپر بلا"],
    7: ["قاتل", "همدست", "بازجو", "کارآگاه", "پزشک", "کالبدشکاف", "شهروند"],
    8: ["قاتل", "همدست", "بازجو", "کارآگاه", "پزشک قانونی",
        "نگهبان", "کالبدشکاف", "سپر بلا"],
    9: ["قاتل", "همدست", "خبرچین", "بازجو", "کارآگاه", "پزشک",
        "نگهبان", "شکارچی", "سپر بلا"],
    10: ["قاتل", "همدست", "سم‌ساز", "بازجو", "کارآگاه", "پزشک",
         "نگهبان", "کالبدشکاف", "شکارچی", "جانی سریالی"],
}


def composition(n: int) -> List[str]:
    if n not in COMPOSITIONS:
        raise ValueError("تعداد بازیکن باید بین ۴ تا ۸ باشد.")
    return list(COMPOSITIONS[n])


def balance_report(n: int) -> Dict[str, int]:
    c = composition(n)
    out = {a.value: 0 for a in Align}
    for r in c:
        out[ROLES[r].align.value] += 1
    return out


def validate_composition(n: int) -> bool:
    """قواعد تعادل (بر پایه‌ی پژوهش مافیا/ور‌ولف):
    - همیشه دقیقاً یک بازجو
    - قاتل‌ها اقلیت و کمتر از نصف
    - نسبت نقش‌های مخفی (قاتل+خنثی) بین ۲۰٪ تا ۴۵٪
    - همیشه حداقل یک شهرِ ساده برای تعادل اطلاعات
    """
    c = composition(n)
    k = sum(1 for r in c if ROLES[r].align is Align.KILLER)
    city = sum(1 for r in c if ROLES[r].align is Align.CITY)
    hidden = sum(1 for r in c if ROLES[r].align is not Align.CITY)
    ratio = hidden / n
    return (len(c) == n and c.count("بازجو") == 1 and 0 < k < city
            and k * 2 < n and 0.20 <= ratio <= 0.45)


# ایده ۵: کول‌داون نقش — از تکرار نقش یکسان برای یک بازیکن در بازی بعدی جلوگیری می‌کند
def assign_with_cooldown(uids, n, rng, last_roles):
    """last_roles: dict[uid->str] نقش بازی قبلی. تلاش می‌کند نقش تکراری ندهد."""
    roles = composition(n)
    for _ in range(40):                    # چند بار به‌هم می‌زند تا کمترین تکرار
        rng.shuffle(roles)
        repeats = sum(1 for u, r in zip(uids, roles) if last_roles.get(u) == r)
        if repeats == 0:
            break
    return dict(zip(uids, roles))
