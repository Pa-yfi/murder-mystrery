"""همه‌ی فرمان‌ها به‌صورت دکمه — هیچ بازیکنی نباید دستور تایپ کند.

قاعده‌ی کلی: هر هندلری که آرگومان می‌خواهد، *بدون* آرگومان فهرست دکمه‌ها را
نشان می‌دهد. مثلاً به‌جای تایپ «lab E2» دکمه‌ی «🧪 مدرک E2» را می‌زنی.

GROUPS تنها سرچشمه‌ی دکمه‌هاست و REACHES می‌گوید هر دکمه به کدام اندپوینت‌ها
می‌رسد؛ تست از روی همین دو تا ثابت می‌کند هیچ فرمانی بدون دکمه نمانده است.
"""
from __future__ import annotations
from typing import Dict, List, Tuple

from .models import Custody, GameState, Phase
from .roles import ROLES

BACK = ("🔙 بازگشت", "commands")
HOME = ("🏠 منوی اصلی", "menu")


def kb(rows: List[List[tuple]]) -> Dict:
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in r] for r in rows]}


def _pairs(items: List[tuple]) -> List[List[tuple]]:
    """دو دکمه در هر سطر — روی موبایل خواناتر است."""
    return [items[i:i + 2] for i in range(0, len(items), 2)]


# ── گروه‌های دکمه: (کلید، عنوان، دکمه‌ها) ─────────────────────────────
GROUPS: List[Tuple[str, str, List[tuple]]] = [
    ("play", "🎮 بازی", [
        ("🎮 بازی جدید", "new"), ("⚡ بلیتز", "blitz"),
        ("🙋 ورود به لابی", "join"), ("🚪 خروج از لابی", "leave"),
        ("✅ آماده‌ام", "ready"), ("🎬 شروع بازی", "startgame"),
        ("🔐 نقش من", "myrole"), ("🖼️ کارت نقش", "rolecard"),
        ("🎯 توانایی‌های من", "abilities"), ("🌙 اکشن شبانه", "act"),
        ("🌅 پایان شب", "dawn"), ("💬 گفتگو", "discuss"),
        ("🗳️ رای‌گیری", "vote"), ("📊 بستن رای‌گیری", "closevote"),
        ("📋 داشبورد", "dashboard"), ("🏙️ وضعیت شهر", "status"),
        ("🏁 پایان و افشا", "end"),
    ]),
    ("interro", "🔦 بازجویی و دادگاه", [
        ("🔦 سرنخ‌ها", "hints"), ("💬 پرسش از متهم", "ask"),
        ("⚖️ حکم بازجو", "verdict"), ("🕊️ آزادی زندانی قبلی", "clear"),
        ("🛡️ دفاع من", "defense"), ("⚖️ هیئت منصفه", "jury"),
        ("📊 نتیجه‌ی هیئت", "closejury"), ("🚨 رای اضطراری", "sos"),
    ]),
    ("clues", "🔎 مدارک و دفترچه", [
        ("🧪 آزمایشگاه", "lab"), ("🧠 تفسیر مدرک", "interp"),
        ("🔍 راستی‌آزمایی مدرک", "expose"), ("📝 یادداشت تازه", "note"),
        ("📓 دفترچه‌ی من", "notes"), ("📜 وصیت‌نامه", "will"),
        ("🏹 هدف شلیک آخر", "hunter"),
    ]),
    ("progress", "🏆 پیشرفت", [
        ("📊 پروفایل", "profile"), ("🏆 برترین‌ها", "top"),
        ("🌍 لیگ گروه‌ها", "league"), ("📅 فصل", "season"),
        ("🎯 ماموریت‌ها", "missions"), ("🏅 دستاوردها", "achv"),
    ]),
    ("table", "⚙️ میز و میزبانی", [
        ("🎲 انتخاب میز", "table"), ("➕ میز تازه", "newtable"),
        ("📺 تماشاچی", "spectate"), ("🕶️ ناشناس/علنی", "voteanon"),
        ("🔁 دور دوباره", "rematch"), ("⏰ یادآوری", "remind"),
        ("⏸️ توقف بازی", "pause"), ("▶️ ادامه‌ی بازی", "resume"),
        ("👑 انتقال میزبانی", "host"), ("⏳ بررسی تایمر", "tick"),
    ]),
    ("guide", "📚 راهنما", [
        ("📖 قوانین", "help"), ("🎭 کاتالوگ نقش‌ها", "roles"),
        ("🎓 آموزش", "tutorial"), ("🔗 دعوت دوستان", "share"),
        ("📨 لینک دعوت", "sharelink"), ("🏠 منوی اصلی", "menu"),
    ]),
    ("admin", "🛠️ ادمین", [
        ("🛠️ پنل ادمین", "admin"), ("🎲 بازی‌های فعال", "admin_games"),
        ("👤 کاربران", "admin_users"), ("📈 آمار کلی", "admin_stats"),
        ("📊 تعادل نقش‌ها", "balance"), ("🚫 مسدودسازی", "admin_ban"),
    ]),
]

# اندپوینت‌هایی که دکمه‌ی مستقیم ندارند ولی از دل یک دکمه‌ی دیگر باز می‌شوند
REACHES: Dict[str, str] = {
    "castvote": "vote",        # vote_kb یک دکمه به ازای هر بازیکن می‌سازد
    "juryvote": "jury",        # jury_kb: تبرئه / ادامه
    "night": "act",            # نام قدیمی همان پنل اکشن
    "roleinfo": "roles",       # کاتالوگ نقش‌ها → کارت هر نقش
    "commands": "menu",        # دکمه‌ی «🎛️ همه‌ی دکمه‌ها» روی منوی اصلی
    "group": "commands",       # صفحه‌ی هر گروه
    "start": "menu",           # ورودی دیپ‌لینک
    "back": "menu",
    "cancel": "commands",
}


def all_buttons() -> List[str]:
    return [cb for _k, _t, items in GROUPS for _label, cb in items]


def commands_menu() -> Dict:
    rows = [[(title, f"group:{key}")] for key, title, _items in GROUPS]
    return kb(rows + [[HOME]])


def commands_screen() -> str:
    return ("🎛️ *همه‌ی دکمه‌ها*\n" + "─" * 18 +
            "\nهیچ دستوری لازم نیست تایپ کنی؛ یک دسته را باز کن."
            "\nهر دکمه‌ای که ورودی بخواهد، خودش فهرست انتخاب‌ها را نشان می‌دهد.")


def group_kb(key: str) -> Dict:
    items = next(items for k, _t, items in GROUPS if k == key)
    return kb(_pairs(items) + [[BACK, HOME]])


def group_title(key: str) -> str:
    return next(t for k, t, _i in GROUPS if k == key)


# ── کاتالوگ نقش‌ها: یک دکمه برای هر نقش ───────────────────────────────
ROLE_NAMES: List[str] = list(ROLES)

ABILITY_FA = {
    "kill": "🔪 هر شب یک نفر را هدف می‌گیرد",
    "investigate": "🕵️ هر شب هویت تیمی یک نفر را استعلام می‌کند",
    "protect": "💉 هر شب از یک نفر محافظت می‌کند",
    "watch": "🛡️ هر شب تعداد ملاقات‌های یک نفر را می‌شمارد",
    "poison": "☠️ هدفش دو شب بعد می‌میرد، مگر پزشک برسد",
    "frame": "🧤 روی یک نفر اثر انگشت جعلی می‌گذارد",
    "spy": "📞 می‌فهمد بازجو سراغ چه کسی رفته",
    "hide": "🚬 یک نفر را از دید کارآگاه و نگهبان پنهان می‌کند",
    "autopsy": "🧪 اصالت مدرک امشب را زودتر می‌بیند",
    "reveal": "📰 یک مدرک اضافه برای کل شهر رو می‌کند",
    "hunter": "🏹 هنگام مرگ یا حبس ابد، یک نفر را با خود می‌برد",
    "": "🌙 اکشن شبانه ندارد",
}


def roles_kb() -> Dict:
    items = [(f"{ROLES[n].emoji} {n}", f"roleinfo:{i}") for i, n in enumerate(ROLE_NAMES)]
    return kb(_pairs(items) + [[BACK, HOME]])


def role_detail(name: str) -> str:
    r = ROLES[name]
    return (f"{r.emoji} *{r.name}*\n" + "─" * 18 +
            f"\n🎯 تیم: {r.align.value}"
            f"\n🌙 کار شبانه: {ABILITY_FA.get(r.ability, r.ability)}"
            f"\n📜 {r.desc}")


def role_detail_kb() -> Dict:
    return kb([[("🎭 بقیه‌ی نقش‌ها", "roles")], [BACK, HOME]])


# ── «الان چه کارهایی از من برمی‌آید؟» ─────────────────────────────────
def abilities_text(g, p) -> str:
    s: GameState = g.s
    r = ROLES[p.role] if p.role else None
    lines: List[str] = []
    if r is None:
        return "🎭 هنوز نقشی نگرفته‌ای؛ بازی شروع نشده."
    lines.append(f"{r.emoji} *{r.name}* — تیم {r.align.value}")
    lines.append(f"🌙 کار شبانه: {ABILITY_FA.get(r.ability, r.ability)}")
    lines.append("─" * 18)

    if p.custody is Custody.LIFE_JAIL or not p.alive:
        lines.append("⛓️ از بازی بیرونی؛ فقط تماشا.")
        return "\n".join(lines)
    if p.custody is Custody.TEMP_JAIL:
        lines.append("🔒 در حبس موقتی: نه اکشن شبانه، نه رای، نه حرف.")
        return "\n".join(lines)

    now: List[str] = []
    if s.phase in (Phase.NIGHT, Phase.INTERROGATION):
        if p.custody is Custody.INTERROGATION:
            now.append("🔦 امشب در اتاق بازجویی‌ای — اکشن شبانه نداری.")
            now.append("🛡️ می‌توانی «دفاع من» را بفرستی.")
        elif r.ability and r.ability != "hunter":
            now.append("🌙 «اکشن شبانه» را بزن و هدفت را انتخاب کن.")
        else:
            now.append("😴 امشب کاری از تو برنمی‌آید؛ صبح بحث کن.")
        if r.ability == "hunter":
            now.append("🏹 «هدف شلیک آخر» را از قبل مشخص کن.")
        if p.role == "کارآگاه":
            now.append("🔍 به‌جای استعلام می‌توانی اصالت یک مدرک را بسنجی.")
    elif s.phase is Phase.VOTE:
        now.append("🗳️ رای بده — یا ممتنع.")
    elif s.phase is Phase.JURY:
        now.append("⚖️ در هیئت منصفه رای بده: تبرئه یا ادامه.")
    elif s.phase is Phase.MORNING:
        if s.suspect_uid == p.uid:
            now.append("🛡️ متهمی: «دفاع من» را بفرست.")
        if p.uid == s.officer_uid and s.suspect_uid:
            now.append("⚖️ بازجویی: سرنخ بگیر، بپرس، حکم بده.")
        if s.suspect_uid:
            need = "به‌تنهایی" if p.role == "وکیل" else "با یک نفر دیگر"
            now.append(f"⚖️ می‌توانی {need} هیئت منصفه بخواهی.")
        now.append("💬 «گفتگو» را باز کنید.")
    elif s.phase is Phase.DISCUSSION:
        now.append("💬 بحث کن، بعد «رای‌گیری».")
    if p.uid == s.officer_uid:
        now.append("🔦 تو بازجویی؛ حکم حبس موقت با توست.")
    if p.uid == g.owner:
        now.append("👑 میزبانی: توقف/ادامه، انتقال میزبانی، شروع بازی.")

    lines.append("*همین حالا:*")
    lines += [f"  • {x}" for x in now]
    lines.append("─" * 18)
    lines.append("همیشه در دسترس: 📓 دفترچه · 📝 یادداشت · 📜 وصیت‌نامه · 🧪 آزمایشگاه")
    return "\n".join(lines)


def abilities_kb(g, p) -> Dict:
    rows: List[List[tuple]] = []
    r = ROLES[p.role] if p.role else None
    if r and r.ability and r.ability != "hunter":
        rows.append([("🌙 اکشن شبانه", "act")])
    if r and r.ability == "hunter":
        rows.append([("🏹 هدف شلیک آخر", "hunter")])
    rows.append([("📓 دفترچه", "notes"), ("🔐 نقش من", "myrole")])
    rows.append([("🎛️ همه‌ی دکمه‌ها", "commands"), HOME])
    return kb(rows)


# ── انتخابگرها: به‌جای تایپ آرگومان ───────────────────────────────────
def evidence_kb(s: GameState, cmd: str) -> Dict:
    """دکمه‌ی هر مدرک برای lab / expose / interp."""
    # عنوان مدرک روی دکمه می‌آید تا کسی مجبور نباشد کدها را حفظ کند
    items = [(f"{e['title']} ({e['code']})", f"{cmd}:{e['code']}") for e in s.case.evidence]
    return kb([[i] for i in items] + [[BACK, HOME]])


def interp_kb(ev: Dict) -> Dict:
    rows = [[(f"{i+1}. {txt[:40]}", f"interp:{ev['code']}:{i}")]
            for i, txt in enumerate(ev["interpretations"])]
    return kb(rows + [[("🧠 مدرک دیگر", "interp")], [BACK, HOME]])


def player_kb(s: GameState, cmd: str, exclude=(), only_custody=None) -> Dict:
    """دکمه‌ی هر بازیکن برای sos / clear / host / hunter …"""
    items = []
    for p in s.players.values():
        if p.uid in exclude:
            continue
        if only_custody is not None and p.custody is not only_custody:
            continue
        if only_custody is None and not p.in_game:
            continue
        items.append((f"👤 {p.name}", f"{cmd}:{p.uid}"))
    if not items:
        return kb([[("— کسی در دسترس نیست —", "commands")], [BACK, HOME]])
    return kb(_pairs(items) + [[BACK, HOME]])


def verdict_kb(s: GameState) -> Dict:
    sus = s.players[s.suspect_uid].name if s.suspect_uid else "—"
    return kb([[(f"🔒 حبس موقت برای {sus}", "verdict:1")],
               [(f"🔓 تایید بی‌گناهی {sus}", "verdict:0")],
               [("🔦 سرنخ‌ها", "hints"), ("💬 پرسش", "ask")],
               [BACK, HOME]])


def users_kb(rows, cmd: str) -> Dict:
    items = [(f"👤 {r['name']}", f"{cmd}:{r['uid']}") for r in rows[:20]]
    if not items:
        return kb([[("— کاربری نیست —", "admin")], [BACK, HOME]])
    return kb(_pairs(items) + [[BACK, HOME]])


# ── ورودی متنی: تنها جایی که تایپ لازم است ───────────────────────────
PROMPTS = {
    "note": ("📝 *یادداشت تازه*", "متن یادداشتت را همین حالا بفرست."),
    "will": ("📜 *وصیت‌نامه*", "متن وصیتت را بفرست؛ اگر کشته شوی صبح خوانده می‌شود."),
    "ask": ("💬 *پرسش از متهم*", "سؤالت را بفرست تا از متهم پرسیده شود."),
    "defense": ("🛡️ *دفاع تو*", "متن دفاعت را بفرست."),
}


def prompt_text(cmd: str) -> str:
    title, body = PROMPTS[cmd]
    return f"{title}\n{'─' * 18}\n{body}\n\n(برای انصراف «✖️ بی‌خیال» را بزن.)"


def prompt_kb() -> Dict:
    return kb([[("✖️ بی‌خیال", "cancel")], [BACK, HOME]])
