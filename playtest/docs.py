"""خواندن همه‌ی مستندات پیش از نشستن سر میز.

هر agent یک Rulebook می‌گیرد که از روی فایل‌های Markdown ساخته شده؛ همین
خواندن، ادعاهای مستندات را هم با کد مقایسه می‌کند (عددِ تست‌ها، اندپوینت‌ها،
ترکیب نقش‌ها، پوشه‌هایی که مستندات به آن‌ها ارجاع می‌دهند).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent
_FA = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def _num(s: str) -> int:
    return int(s.translate(_FA))


@dataclass
class Rulebook:
    files: Dict[str, str] = field(default_factory=dict)      # مسیر → متن
    claims: Dict[str, int] = field(default_factory=dict)     # «۲۳۵ تست» ← ادعاهای عددی
    killers_per_size: Dict[int, int] = field(default_factory=dict)
    commands: List[str] = field(default_factory=list)        # /act ، /ready …
    folders: List[str] = field(default_factory=list)         # tests/quality …

    @property
    def text(self) -> str:
        return "\n".join(self.files.values())

    def mentions(self, word: str) -> bool:
        return word in self.text


def read_all(root: Path = ROOT) -> Rulebook:
    """همه‌ی *.md پروژه (بیرون از .venv و .git) — خواندنِ اجباری پیش از بازی."""
    rb = Rulebook()
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root).as_posix()
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue                           # .venv ، .git ، .pytest_cache …
        if rel.startswith("playtest/"):        # گزارشِ خودمان مستندِ بازی نیست
            continue
        rb.files[rel] = p.read_text(encoding="utf-8")
    txt = rb.text
    m = re.search(r"([۰-۹\d]+)\s*تست سبز", txt)
    if m:
        rb.claims["tests"] = _num(m.group(1))
    m = re.search(r"\(([۰-۹\d]+)\s*اندپوینت\)", txt)
    if m:
        rb.claims["endpoints"] = _num(m.group(1))
    m = re.search(r"([۰-۹\d]+)\s*نقش،\s*([۰-۹\d]+)\s*پرونده", txt)
    if m:
        rb.claims["roles"], rb.claims["cases"] = _num(m.group(1)), _num(m.group(2))
    for n, k in re.findall(r"([۰-۹\d]+)ن:\s*([۰-۹\d]+)", txt):
        rb.killers_per_size[_num(n)] = _num(k)
    rb.commands = sorted(set(re.findall(r"`/([a-z_]+)", txt)))
    rb.folders = sorted(set(re.findall(r"(tests/[a-z_]+)/", txt)))
    return rb


BOTFATHER = {"revoke", "newbot", "setprivacy"}   # دستورهای BotFather، نه این ربات


def cross_check(rb: Rulebook) -> List[dict]:
    """ادعاهای مستندات در برابر کد. خروجی: یافته‌ها (برای گزارش)."""
    from karagah import bot
    from karagah.cases import CASES
    from karagah.models import Align
    from karagah.roles import COMPOSITIONS, ROLES

    out: List[dict] = []

    def find(sev, title, detail):
        out.append({"sev": sev, "area": "مستندات", "title": title, "detail": detail})

    if rb.claims.get("endpoints") not in (None, len(bot.ENDPOINTS)):
        find("پایین", "عدد اندپوینت‌ها در مستندات با کد نمی‌خواند",
             f"مستندات: {rb.claims['endpoints']} — کد: {len(bot.ENDPOINTS)}")
    if rb.claims.get("roles") not in (None, len(ROLES)):
        find("پایین", "عدد نقش‌ها در مستندات با کد نمی‌خواند",
             f"مستندات: {rb.claims['roles']} — کد: {len(ROLES)}")
    if rb.claims.get("cases") not in (None, len(CASES)):
        find("پایین", "عدد پرونده‌ها در مستندات با کد نمی‌خواند",
             f"مستندات: {rb.claims['cases']} — کد: {len(CASES)}")
    for n, k in rb.killers_per_size.items():
        real = sum(1 for r in COMPOSITIONS.get(n, []) if ROLES[r].align is Align.KILLER)
        if n in COMPOSITIONS and real != k:
            find("متوسط", f"تعداد قاتل در بازی {n} نفره با PLAN.md فرق دارد",
                 f"PLAN.md: {k} قاتل — COMPOSITIONS: {real} قاتل")
    for folder in rb.folders:
        if not (ROOT / folder).exists():
            find("پایین", f"مستندات به پوشه‌ی {folder}/ ارجاع می‌دهد که وجود ندارد",
                 "README و PLAN و runner.py (quality) هر سه به آن اشاره می‌کنند؛ "
                 "«python runner.py quality» چیزی برای اجرا پیدا نمی‌کند.")
    for c in rb.commands:
        if c not in bot._ROUTES and c not in BOTFATHER:
            find("پایین", f"دستور /{c} در مستندات هست ولی ربات آن را نمی‌شناسد", "")
    used = {r for comp in COMPOSITIONS.values() for r in comp}
    never = [r for r in ROLES if r not in used]
    if never:
        find("متوسط", "نقش‌هایی که در کاتالوگ و مستندات هستند ولی هرگز پخش نمی‌شوند",
             "، ".join(never) + " — در هیچ ترکیبی از ۴ تا ۱۰ نفر نیستند؛ "
             "کاتالوگ نقش‌ها به بازیکن قولی می‌دهد که بازی نمی‌دهد.")
    return out
