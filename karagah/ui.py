"""لایه‌ی رابط کاربری فارسی: صفحه‌ها، کیبوردهای اینلاین، ایموجی و انیمیشن‌ها.
همه‌ی callback_dataها به اندپوینت واقعی در bot._ROUTES اشاره می‌کنند (دکمه‌ی مرده نداریم).
"""
from __future__ import annotations
from typing import Dict, List
from .models import Custody, GameState
from .roles import ROLES
from .config import BOT_USERNAME

DIV = "─" * 18

ANIM: Dict[str, List[str]] = {
    "night": ["🌆 شهر می‌خوابد…", "🌃 چراغ‌ها خاموش شد…", "🌌 سکوت مطلق…", "🔪 چیزی در تاریکی حرکت کرد…"],
    "morning": ["🌅 سپیده زد…", "📰 شهر بیدار شد…", "🚨 خبر بد…"],
    "vote": ["🗳️ صندوق باز شد…", "🗳️▫️ شمارش…", "🗳️✅ نتیجه!"],
    "interrogation": ["🚪 در اتاق بازجویی بسته شد…", "🔦 چراغ روی صورت متهم…", "🎙️ ضبط شروع شد."],
    "jail": ["⛓️ صدای زنجیر…", "🔒 در سلول قفل شد.", "🤫 نقشش فاش نمی‌شود."],
    "court": ["⚖️ دادگاه رسمی است…", "📜 پرونده باز شد…", "👨‍⚖️ حکم نهایی!"],
}

CUSTODY_ICON = {
    Custody.FREE: "🟢", Custody.INTERROGATION: "🔦",
    Custody.TEMP_JAIL: "🔒", Custody.LIFE_JAIL: "⛓️",
}

BACK = ("🔙 بازگشت", "menu")
HOME = ("🏠 منوی اصلی", "menu")

MENU = [
    [("🎮 شروع بازی همین‌جا", "new"), ("⚡ بلیتز", "blitz")],
    [("🔗 دعوت دوستان", "share"), ("📋 داشبورد", "dashboard")],
    [("🎓 آموزش تعاملی", "tutorial"), ("🎭 نقش‌ها", "roles")],
    [("🏆 برترین‌ها", "top"), ("📅 فصل", "season")],
    [("🎯 ماموریت‌ها", "missions"), ("🏅 دستاوردها", "achv")],
    [("📊 پروفایل", "profile"), ("🛠️ پنل ادمین", "admin")],
]


def kb(rows: List[List[tuple]]) -> Dict:
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in r] for r in rows]}


def with_back(rows: List[List[tuple]]) -> Dict:
    return kb(rows + [[BACK, HOME]])


def back_only() -> Dict:
    return kb([[BACK, HOME]])


def main_menu() -> Dict:
    return kb(MENU)


# ── صفحه‌ی اول: افزودن به گروه / دعوت دوست ──
def first_screen() -> str:
    return ("🕵️ *به «کارآگاه» خوش آمدی!*\n" + DIV +
            "\nنسخه‌ی پیشرفته‌ی مافیا + معمای قتل — کاملاً فارسی."
            "\n👥 ۴ تا ۸ بازیکن | 🕯️ ۴۰ پرونده | 🔦 حذف سه‌مرحله‌ای\n\n"
            "برای شروع، ربات را به گروه اضافه کن یا دوستانت را دعوت کن:")


def first_kb(chat_id: int) -> Dict:
    l = share_links(chat_id)
    rows = [
        [{"text": "👥 افزودن به گروه", "url": l["group"]}],
        [{"text": "📨 دعوت دوست", "url": l["share"]}],
        [{"text": "📢 افزودن به کانال", "url": l["channel"]}],
    ]
    return {"inline_keyboard": rows + kb(MENU)["inline_keyboard"]}


def newbie_guide() -> str:
    return ("🎓 *خوش آمدی، کارآگاه تازه‌کار!*\n" + DIV +
            "\n🔪 بین ما قاتل هست؛ حتی خودش هم مطمئن نیست دیده شده یا نه!"
            "\n🌙 شب‌ها نقش‌ها اکشن می‌زنند، ☀️ روزها بحث و رای."
            "\n🔦 رای گروه → بازجویی (۱ شب) → 🔒 حبس موقت (۲ شب) → ⛓️ حبس ابد."
            "\n⛓️ نقشِ حبس‌ابدی تا آخر بازی فاش نمی‌شود!"
            "\n\n۱) «🔐 نقش من» را بزن تا نقش محرمانه‌ات به پیوی بیاید."
            "\n۲) منتظر شروع بازی توسط میزبان بمان. موفق باشی! 🍀")


def owner_panel(s: GameState) -> str:
    return ("🎛️ *پنل میزبان — فقط تو این را می‌بینی*\n" + DIV + "\n" + lobby_screen(s) +
            "\n\n▫️ وقتی ۴+ نفر شدید «🎬 شروع بازی» را بزن."
            "\n▫️ «📨 دعوت دوست» برای فرستادن لینک به بقیه.")


def owner_kb(chat_id: int) -> Dict:
    l = share_links(chat_id)
    return {"inline_keyboard": [
        [{"text": "🙋 منم بازی می‌کنم!", "callback_data": "join"}],
        [{"text": "🎬 شروع بازی", "callback_data": "startgame"}],
        [{"text": "📨 دعوت دوست", "url": l["share"]},
         {"text": "👥 افزودن به گروه", "url": l["group"]}],
        [{"text": "📋 وضعیت", "callback_data": "status"},
         {"text": "🏠 منو", "callback_data": "menu"}],
    ]}


def lobby_kb(chat_id: int) -> Dict:
    """کیبورد لابی — هر کسی در گروه فوراً با یک تپ وارد می‌شود."""
    l = share_links(chat_id)
    return {"inline_keyboard": [
        [{"text": "🙋 منم بازی می‌کنم!", "callback_data": "join"}],
        [{"text": "🎬 شروع بازی", "callback_data": "startgame"},
         {"text": "🚪 خروج از لابی", "callback_data": "leave"}],
        [{"text": "📨 دعوت دوست", "url": l["share"]}],
        [{"text": BACK[0], "callback_data": BACK[1]}, {"text": HOME[0], "callback_data": HOME[1]}],
    ]}


def lobby_screen(s: GameState) -> str:
    names = "\n".join(f"  {i+1}. 👤 {p.name}" for i, p in enumerate(s.players.values())) or "  — هنوز کسی نیست —"
    return (f"🏛️ *لابی کارآگاه*\n{DIV}\n{names}\n{DIV}\n"
            f"👥 {len(s.players)}/۸ (حداقل ۴ نفر)\n🎬 «🎬 شروع بازی» را بزن.")


def role_card(role: str, knows: List[str]) -> str:
    r = ROLES[role]
    extra = "\n".join(f"  • {k}" for k in knows) or "  • اطلاعات ویژه‌ای نداری."
    return (f"{r.emoji} *نقش تو: {r.name}*\n{DIV}\n🎯 تیم: {r.align.value}\n"
            f"📜 {r.desc}\n{DIV}\n🔐 *اطلاعات محرمانه:*\n{extra}\n\n"
            f"⚠️ این پیام را به هیچ‌کس نشان نده.")


def status_board(s: GameState) -> str:
    rows = []
    for p in s.players.values():
        icon = CUSTODY_ICON[p.custody] if p.alive else "💀"
        tag = "" if p.custody is Custody.FREE else f" — {p.custody.value}"
        rows.append(f"{icon} {p.name}{tag}")
    return (f"📋 *وضعیت شهر — روز {s.day} | فاز: {s.phase.value}*\n{DIV}\n" +
            "\n".join(rows) + f"\n{DIV}\n🔎 مدارک رو شده: {len(s.revealed_evidence)}/۶")


def case_intro(s: GameState) -> str:
    c = s.case
    tl = "\n".join(f"  • {t}" for t in c.timeline)
    return (f"🕯️ *پرونده #{c.cid} — {c.title}*\n{DIV}\n"
            f"⚰️ مقتول: {c.victim}\n📍 صحنه: {c.place}\n🔪 سلاح احتمالی: {c.weapon}\n"
            f"💰 انگیزه‌ی محتمل: {c.motive}\n{DIV}\n🕰️ تایم‌لاین:\n{tl}")


def evidence_card(ev: Dict) -> str:
    it = "\n".join(f"  ▫️ {i}" for i in ev["interpretations"])
    return (f"🔎 *مدرک {ev['code']}: {ev['title']}*\n{DIV}\n🧠 تفسیرهای ممکن:\n{it}\n\n"
            "❗ هیچ مدرکی به‌تنهایی قاتل را ثابت نمی‌کند.")


def vote_kb(s: GameState) -> Dict:
    rows = [[(f"👉 {p.name}", f"vote:{p.uid}")] for p in s.alive_players() if p.can_speak]
    rows.append([("⏭️ رای ممتنع", "vote:0")])
    rows.append([("📊 بستن رای‌گیری", "closevote")])
    return kb(rows)


def officer_kb(uid: int) -> Dict:
    return kb([[("🔦 سرنخ‌ها", "hints"), ("💬 پرسش", f"ask:{uid}")],
               [("🔒 حبس موقت", f"ver:{uid}:1")],
               [("🔓 تایید بی‌گناهی و آزادی", f"ver:{uid}:0")]])


def jury_kb() -> Dict:
    return kb([[("🕊️ تبرئه", "jury:1"), ("⚖️ ادامه‌ی بازجویی", "jury:0")],
               [("📊 نتیجه", "closejury")]])


def help_text() -> str:
    return ("📖 *قوانین حذف سه‌مرحله‌ای*\n" + DIV +
            "\n۱) 🔦 بازجویی — با رای گروه. فاصله: ۱ شب. بازجو سؤال می‌پرسد و سرنخ مبهم می‌گیرد."
            "\n۲) 🔒 حبس موقت — با تایید بازجو. فاصله: ۲ شب. آزادی فقط وقتی متهم جدیدی وارد بازجویی شود"
            " و بازجو بی‌گناهی قبلی را تایید کند."
            "\n۳) ⛓️ حبس ابد — حذف کامل، بدون افشای نقش. تا پایان بازی معلوم نمی‌شود قاتل بود یا بی‌گناه."
            "\n\n⚖️ بعد از یک شب بازجویی، بازیکنان می‌توانند هیئت منصفه تشکیل دهند (وکیل به‌تنهایی می‌تواند).")


# ── اشتراک‌گذاری ──
def share_links(chat_id: int) -> Dict[str, str]:
    u = BOT_USERNAME
    return {
        "join": f"https://t.me/{u}?start=join_{chat_id}",
        "group": f"https://t.me/{u}?startgroup=play",
        "channel": f"https://t.me/{u}?startchannel=play",
        "share": ("https://t.me/share/url?url="
                  f"https://t.me/{u}?start=join_{chat_id}"
                  "&text=" + "بیا%20بازی%20کارآگاه%20🕵️"),
    }


def share_screen(chat_id: int, players: int) -> str:
    l = share_links(chat_id)
    return (f"🔗 *دعوت به بازی*\n{DIV}\n👥 {players}/۸ نفر داخل لابی‌اند.\n\n"
            f"لینک دعوت مستقیم:\n`{l['join']}`\n\n"
            "با دکمه‌های زیر بفرست یا ربات را به گروه/کانال اضافه کن.")


def share_kb(chat_id: int) -> Dict:
    l = share_links(chat_id)
    return {"inline_keyboard": [
        [{"text": "📨 ارسال برای دوستان", "url": l["share"]}],
        [{"text": "👥 افزودن به گروه", "url": l["group"]},
         {"text": "📢 افزودن به کانال", "url": l["channel"]}],
        [{"text": "🔗 کپی لینک دعوت", "callback_data": "sharelink"}],
        [{"text": BACK[0], "callback_data": BACK[1]}, {"text": HOME[0], "callback_data": HOME[1]}],
    ]}


# ── پنل ادمین (رندر از ردیف‌های SQL) ──
def admin_menu() -> Dict:
    return with_back([[("🎲 بازی‌های فعال", "admin_games")],
                      [("👤 کاربران", "admin_users")],
                      [("📈 آمار کلی", "admin_stats")]])


def admin_games_sql(rows) -> str:
    if not rows:
        return "🎲 هیچ بازی‌ای ثبت نشده است."
    out = []
    for r in rows:
        w = f" | 🏁 {r['winner']}" if r["winner"] else ""
        out.append(f"🆔 `{r['chat_id']}` | فاز: {r['phase']} | روز {r['day']} | "
                   f"👥 {r['players']} | 🕯️ {r['case_title'] or '—'}{w}")
    return "🎲 *بازی‌های ثبت‌شده*\n" + DIV + "\n" + "\n".join(out)


def admin_users_sql(rows) -> str:
    if not rows:
        return "👥 هنوز کاربری ثبت نشده."
    out = []
    for r in rows:
        b = " 🚫" if r["banned"] else ""
        out.append(f"👤 {r['name']} — 🆔 `{r['uid']}` — ⭐{r['xp']} — بازی‌ها: {r['in_games']}{b}")
    return ("👥 *کاربران*\n" + DIV + "\n" + "\n".join(out) +
            "\n\nبرای جزئیات: /admin_users <آیدی>")


def admin_user_card_sql(u, games, events) -> str:
    g = "\n".join(
        f"  • بازی `{r['chat_id']}` | {r['role'] or '—'} ({r['align'] or '—'}) | "
        f"{r['custody']} | {'زنده' if r['alive'] else 'کشته'} | فاز {r['phase']}"
        for r in games) or "  • در هیچ بازی‌ای نیست"
    e = "\n".join(f"  • {r['kind']}: {r['detail']}" for r in events) or "  • رویدادی ثبت نشده"
    b = " 🚫 (مسدود)" if u["banned"] else ""
    return (f"👤 *{u['name']}*{b}\n{DIV}\n"
            f"🆔 آیدی: `{u['uid']}`\n⭐ XP: {u['xp']} | 🪙 {u['coins']}\n"
            f"🎮 بازی‌ها: {u['games']} | 🏆 برد: {u['wins']}\n{DIV}\n"
            f"🎭 حضور در بازی‌ها:\n{g}\n{DIV}\n📝 رویدادهای اخیر:\n{e}\n\n"
            f"🚫 برای مسدودسازی: /admin_ban {u['uid']}")


def admin_stats_sql(st: Dict) -> str:
    top = "\n".join(f"  {i+1}. {r['name']} — ⭐{r['xp']}" for i, r in enumerate(st["top"])) or "  —"
    return (f"📈 *آمار کلی (SQL)*\n{DIV}\n"
            f"👥 کاربران: {st['users']} (مسدود: {st['banned']})\n"
            f"🎲 بازی‌ها: {st['games']} (فعال: {st['active']})\n"
            f"📝 رویدادها: {st['events']}\n{DIV}\n🏆 برترین‌ها:\n{top}")


# ── ایده ۲۸: آموزش تعاملی (شبیه‌سازی یک دور مینی) ──
def tutorial_text() -> str:
    return ("🎓 *آموزش تعاملی — یک دور مینی با بات‌ها*\n" + DIV +
            "\n🌙 *شب:* سارا (قاتلِ فرضی) رضا را هدف می‌گیرد. پزشک از مریم محافظت می‌کند."
            "\n☀️ *صبح:* جسد رضا پیدا شد! مدرک E1: 🖐️ اثر انگشت — سه تفسیر دارد، هیچ‌کدام قطعی نیست."
            "\n💬 *گفتگو:* سارا می‌گوید «من خواب بودم». علی می‌گوید «سارا را نزدیک اتاق دیدم»."
            "\n🗳️ *رای:* اکثریت به سارا → 🔦 بازجویی (۱ شب)."
            "\n🔦 *بازجویی:* بازجو می‌پرسد «کجا بودی؟» و سرنخ مبهم می‌گیرد: «دستش می‌لرزد»."
            "\n⚖️ دو نفر هیئت منصفه می‌خواهند؛ رای نمی‌آورد → 🔒 حبس موقت (۲ شب)."
            "\n⛓️ دو شب بی‌تبرئه → حبس ابد؛ *نقشش فاش نمی‌شود!*"
            "\n🏁 پایان: معلوم می‌شود سارا واقعاً قاتل بود — شهر برد! ⭐ MVP: علی."
            "\n\nحالا خودت: «🎮 شروع بازی» را بزن!")


# ── ایده ۲۹: نگاشت صدای فاز (اگر فایل موجود باشد، آداپتور ویس می‌فرستد) ──
VOICE = {"night": "night.ogg", "morning": "morning.ogg", "vote": "vote.ogg",
         "interrogation": "interrogation.ogg", "jail": "jail.ogg", "court": "court.ogg"}


# ── بهبود ۱: پنل اکشن خصوصی — انتخاب هدف با نام، بدون آیدی عددی ──
ABILITY_TEXT = {
    "kill": ("🔪 قتل", "امشب چه کسی را هدف می‌گیری؟"),
    "investigate": ("🕵️ استعلام هویت", "هویت تیمیِ چه کسی را استعلام می‌کنی؟ نتیجه سحر می‌رسد."),
    "protect": ("💉 محافظت", "امشب از چه کسی محافظت می‌کنی؟"),
    "watch": ("🛡️ نگهبانی", "چه کسی را زیر نظر می‌گیری؟ تعداد ملاقات‌هایش را می‌بینی."),
    "poison": ("☠️ مسموم‌سازی", "چه کسی را مسموم می‌کنی؟ دو شب بعد می‌میرد مگر پزشک برسد."),
    "frame": ("🧤 پاپوش‌دوزی", "اثر انگشت جعلی روی چه کسی بگذارم؟"),
    "spy": ("📞 خبرچینی", "یک نفر را انتخاب کن؛ می‌فهمی بازجو سراغ چه کسی رفته."),
    "hide": ("🚬 مخفی‌کاری", "چه کسی را از دید کارآگاه و نگهبان پنهان می‌کنی؟"),
    "autopsy": ("🧪 آزمایشگاه", "یک نفر را انتخاب کن؛ اصالت مدرک امشب را می‌فهمی."),
    "reveal": ("📰 افشاگری", "یک نفر را انتخاب کن؛ یک مدرک اضافه برای کل شهر رو می‌شود."),
}


def action_panel(s: GameState, p, chosen=None) -> str:
    """متن پنل اکشن شبانه‌ی یک بازیکن."""
    ab = ROLES[p.role].ability
    if ab == "hunter":
        title, ask = "🏹 شلیک آخر", "اگر کشته شوی یا حبس ابد بگیری، چه کسی را با خودت می‌بری؟"
    elif not ab:
        return (f"{ROLES[p.role].emoji} *{p.role}*\n{DIV}\n"
                "🌙 نقش تو اکشن شبانه ندارد. بخواب و صبح بحث کن.")
    else:
        title, ask = ABILITY_TEXT.get(ab, (f"🌙 {ab}", "هدفت را انتخاب کن:"))
    done = f"\n\n✅ انتخاب فعلی: *{s.players[chosen].name}* (می‌توانی عوض کنی)" if chosen else ""
    return (f"{title} — شب {s.day}\n{DIV}\n{ask}{done}")


def action_kb(s: GameState, p, targets: List[int], chosen=None) -> Dict:
    """دکمه‌ی هر هدف با نام؛ بدون تایپ آیدی."""
    cmd = "hunter" if ROLES[p.role].ability == "hunter" else "act"
    rows = [[(("✅ " if t == chosen else "👉 ") + s.players[t].name, f"{cmd}:{t}")]
            for t in targets]
    if not rows:
        rows = [[("— هدف مجازی نیست —", "notes")]]
    return kb(rows + [[("📋 داشبورد", "dashboard")], [BACK, HOME]])


# ── بهبود ۳: داشبورد راهنما ──
def dashboard(s: GameState, remaining=None, pending=(), next_step="") -> str:
    rows = []
    for p in s.players.values():
        icon = CUSTODY_ICON[p.custody] if p.alive else "💀"
        tag = "" if p.custody is Custody.FREE or not p.alive else f" — {p.custody.value}"
        wait = " ⏳" if p.uid in pending else ""
        rows.append(f"{icon} {p.name}{tag}{wait}")
    timer = f"\n⏳ باقی‌مانده: {remaining} ثانیه" if remaining is not None else ""
    who = ""
    if pending:
        names = "، ".join(s.players[u].name for u in pending)
        who = f"\n⏳ منتظر: {names}"
    return (f"📋 *داشبورد — روز {s.day} | فاز: {s.phase.value}*{timer}\n{DIV}\n"
            + "\n".join(rows) +
            f"\n{DIV}\n🔎 مدارک رو شده: {len(s.revealed_evidence)}/۶{who}"
            f"\n➡️ *قدم بعدی:* {next_step}")


def dashboard_kb(s: GameState) -> Dict:
    """دکمه‌ی «کار بعدی» متناسب با فاز — بازیکن دنبال دستور نگردد."""
    from .models import Phase
    ph = s.phase
    rows = []
    if ph in (Phase.NIGHT, Phase.INTERROGATION):
        rows = [[("🌙 اکشن شبانه‌ی من", "act")], [("🌙 پایان شب", "dawn")]]
    elif ph is Phase.MORNING:
        rows = [[("💬 گفتگو", "discuss")]]
        if s.suspect_uid:
            rows.insert(0, [("⚖️ هیئت منصفه", "jury")])
    elif ph is Phase.DISCUSSION:
        rows = [[("🗳️ رای‌گیری", "vote")]]
    elif ph is Phase.VOTE:
        rows = [[("📊 بستن رای‌گیری", "closevote")]]
    elif ph is Phase.JURY:
        rows = [[("📊 نتیجه‌ی هیئت", "closejury")]]
    elif ph is Phase.END:
        rows = [[("🏁 پایان و افشای نقش‌ها", "end")]]
    return kb(rows + [[("🔄 بروزرسانی", "dashboard"), ("📝 دفترچه", "notes")], [BACK, HOME]])
