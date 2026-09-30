"""موتور سرنخ — لایه‌ی «معمای قتل» که به بازیِ واقعی وصل است.

ایده (RULES.md بخش «سرنخ‌ها»):
- هر بازیکن یک «پرونده‌ی ظاهری» عمومی دارد: سایز کفش، رنگ کت، دست غالب، عادت، عطر،
  و یک مشخصه‌ی ویژه‌ی سناریو (کلاسیک 💍 انگشتر، دادگاه 🖋️ جوهر، آشوب 🐍 خالکوبی).
  همه‌ی این مشخصات را همه می‌بینند (مثل ظاهر آدم‌ها در یک مهمانی).
- هر جنایتِ واقعی یک **سرنخ راست** می‌گذارد: یکی از مشخصاتِ خودِ ضارب. سرنخ‌های راست
  همه درباره‌ی همان مجرم‌های واقعی‌اند، پس با هم جور درمی‌آیند و دایره‌ی مظنونان را تنگ می‌کنند.
- **سرنخ دروغ** یا کاشته‌ی همدست است (مشخصاتِ بی‌گناهی که پاپوشش را دوخته) یا ردِ گمراه‌کننده‌ی
  تصادفی. سرنخ دروغ هیچ‌وقت مشخصه‌ای از مجرم‌های واقعی را نمی‌گوید.
- هر سرنخ در یک مکانِ سناریو با یک جزئیاتِ تازه پیدا می‌شود (karagah/scenes.py).
- آزمایشگاه، کارآگاه (راستی‌آزمایی) و پزشک قانونی راست/دروغ بودنِ سرنخ را معلوم می‌کنند؛
  «🗂️ پرونده» سرنخ‌های تاییدشده را به هم وصل می‌کند و فهرست مظنونان را نشان می‌دهد.

هر سرنخ یک dict ساده است (برای اسنپ‌شات):
  code, day, trait, value, text, genuine, source, about, verified, votes, place, detail
"""
from __future__ import annotations

import random
from typing import Dict, Iterable, List, Optional

from . import scenes

# کلید → (ایموجی، نام، مقدارها) — پنج مشخصه‌ی پایه + مشخصه‌ی ویژه‌ی هر سناریو
TRAITS: Dict[str, tuple] = {
    "shoe": ("👟", "سایز کفش", ["۳۹", "۴۲", "۴۵"]),
    "coat": ("🧥", "رنگ کت", ["قرمز", "آبی", "مشکی", "سبز"]),
    "hand": ("✋", "دست غالب", ["چپ", "راست"]),
    "habit": ("☕", "عادت", ["سیگاری", "قهوه‌خور", "آدامس‌جو"]),
    "scent": ("🌸", "عطر", ["تلخ", "شیرین", "بی‌بو"]),
}
BASE_KEYS = list(TRAITS)
for _key, _def in scenes.EXTRA_TRAITS.values():
    TRAITS[_key] = _def
TRAIT_KEYS = list(TRAITS)          # همه‌ی مشخصه‌های ممکن (برای خواندنِ نام‌ها)

STATUS_ICON = {None: "❔", True: "✅", False: "❌"}


def keys_for(scenario: str) -> List[str]:
    """مشخصه‌هایی که در این سناریو پخش می‌شوند: ۵ پایه + ۱ ویژه."""
    return BASE_KEYS + [scenes.extra_trait(scenario)[0]]


def game_keys(s) -> List[str]:
    p = next(iter(s.players.values()), None)
    return list(p.traits) if p is not None and p.traits else keys_for(getattr(s, "scenario", "classic"))


def trait_line(traits: Dict[str, str]) -> str:
    return " ".join(f"{TRAITS[k][0]}{traits[k]}" for k in TRAIT_KEYS if k in traits)


def assign_traits(uids: List[int], rng: random.Random, scenario: str = "classic") -> Dict[int, Dict[str, str]]:
    """پرونده‌ی ظاهریِ یکتا برای هر بازیکن (هیچ دو نفری کاملاً یکسان نیستند)."""
    keys = keys_for(scenario)
    used, out = set(), {}
    for u in uids:
        for _ in range(200):
            t = {k: rng.choice(TRAITS[k][2]) for k in keys}
            key = tuple(t[k] for k in keys)
            if key not in used:
                break
        used.add(key)
        out[u] = t
    return out


def new_clue(s, *, trait: str, value: str, genuine: bool, source: str,
             about: Optional[int], place: Optional[str] = None, note: str = "",
             rng: Optional[random.Random] = None) -> dict:
    """یک سرنخ به پرونده اضافه می‌کند و برمی‌گرداند. کد: C1، C2، …
    place کلیدِ صحنه است: سرنخ‌های یک صحنه (یک قربانی) در همان شب یک مکان دارند."""
    rng = rng or random.Random(len(s.clues) * 7 + s.day)
    loc, detail = scenes.stamp(s, rng, place)
    body = scenes.trait_text(getattr(s, "scenario", "classic"), trait, value)
    code = f"C{len(s.clues) + 1}"
    c = {"code": code, "day": s.day, "trait": trait, "value": value,
         "text": f"{body}{(' ' + note) if note else ''}\n      📍 {loc} — {detail}",
         "genuine": genuine, "source": source, "about": about,
         "verified": None, "votes": {}, "place": loc, "detail": detail}
    s.clues.append(c)
    return c


def true_clue(s, culprit: int, rng: random.Random, source: str, place: Optional[str] = None,
              note: str = "") -> dict:
    """سرنخ راست: مشخصه‌ای از مجرمِ واقعی که هنوز سرنخِ راستی درباره‌اش نیامده (زنجیره‌ی به‌هم‌پیوسته)."""
    p = s.players[culprit]
    keys = list(p.traits)
    told = {c["trait"] for c in s.clues if c["genuine"] and c["about"] == culprit}
    fresh = [k for k in keys if k not in told] or keys
    k = rng.choice(fresh)
    return new_clue(s, trait=k, value=p.traits[k], genuine=True, source=source,
                    about=culprit, place=place, note=note, rng=rng)


def false_clue(s, culprit: Optional[int], rng: random.Random, source: str, place: Optional[str] = None,
               framed: Optional[int] = None, avoid: Iterable[int] = (), note: str = "") -> Optional[dict]:
    """سرنخ دروغ: مشخصه‌ای که **هیچ‌کدام** از مجرم‌های واقعیِ امشب (culprit + avoid) ندارند.
    اگر پاپوش است، مشخصه‌ی همان بی‌گناه؛ اگر چنین مشخصه‌ای نباشد، پاپوش جا نمی‌افتد (None)."""
    guilty = [s.players[u].traits for u in {culprit, *avoid} if u is not None and u in s.players]
    taken = lambda k, v: any(t.get(k) == v for t in guilty)
    keys = game_keys(s)
    rng.shuffle(keys)
    if framed is not None:
        mark = s.players[framed].traits
        for k in keys:
            if k in mark and not taken(k, mark[k]):
                return new_clue(s, trait=k, value=mark[k], genuine=False, source=source,
                                about=framed, place=place, note=note, rng=rng)
        return None
    for k in keys:
        wrong = [v for v in TRAITS[k][2] if not taken(k, v)]
        if wrong:
            return new_clue(s, trait=k, value=rng.choice(wrong), genuine=False, source=source,
                            about=None, place=place, note=note, rng=rng)
    return None


def matches(p, clue: dict) -> bool:
    return p.traits.get(clue["trait"]) == clue["value"]


def board_ranking(s) -> List[tuple]:
    """(uid، تعداد سرنخ‌های تاییدشده‌ی راستی که با او جور است، تعداد سرنخ‌های تاییدنشده‌ای که جور است)
    — فقط از اطلاعات عمومی ساخته می‌شود؛ هیچ‌چیز درباره‌ی اینکه سرنخ مالِ چه کسی بوده لو نمی‌رود."""
    sure = [c for c in s.clues if c["verified"] is True]
    open_ = [c for c in s.clues if c["verified"] is None]
    rows = [(p.uid, sum(matches(p, c) for c in sure), sum(matches(p, c) for c in open_))
            for p in s.alive_players()]
    return sorted(rows, key=lambda r: (-r[1], -r[2], r[0]))


def clue_line(c: dict, show_truth: bool = False) -> str:
    st = STATUS_ICON[c["verified"]] if not show_truth else ("✅" if c["genuine"] else "❌")
    return f"{st} *{c['code']}* (روز {c['day']}): {c['text']}"
