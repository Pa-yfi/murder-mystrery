"""لایه‌ی اندپوینت ربات — مستقل از شبکه، پس کاملاً تست‌پذیر.
هر هندلر یک dict برمی‌گرداند: {ok, text, keyboard?, anim?, private?}
اتصال به python-telegram-bot فقط با map کردن این هندلرها انجام می‌شود.
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

from . import ui, db, cards, menus
from .strings import t
from .config import ADMIN_IDS
from .engine import Game, RuleError
from .models import Custody, Phase
from .roles import ROLES

import time as _time
import threading

log = logging.getLogger("karagah.bot")
GAMES: Dict[int, Game] = {}
LAST_ROSTER: Dict[int, list] = {}   # ایده ۲۴: دور دوباره
_LOCKS: Dict[int, threading.RLock] = {}          # ایده ۱: قفل هر چت (ضد ریس)
_LAST_CALL: Dict[tuple, float] = {}              # ایده ۹: نرخ‌محدودساز
_LAST_CB: Dict[tuple, float] = {}                # ایده ۲: حذف callback تکراری
RATE_WINDOW = 0.6                                # ثانیه بین دو فرمانِ یک کاربر
RATE_LIMIT_ENABLED = False                       # فقط آداپتور تلگرام روشنش می‌کند
REQUIRE_READY = False                            # بهبود ۲ — همان الگو: فقط در محیط واقعی
DEDUP_WINDOW = 1.5                               # ثانیه: تپ تکراری روی یک دکمه


def _lock(chat: int) -> threading.RLock:
    return _LOCKS.setdefault(chat, threading.RLock())


def _sanitize(text: str) -> str:
    """ایده ۸: خنثی‌سازی نویسه‌های Markdown برای جلوگیری از تزریق/خرابی رندر."""
    if not text:
        return ""
    for ch in ("*", "_", "`", "[", "]", "(", ")", "~", ">", "#", "|", "{", "}"):
        text = text.replace(ch, "")
    return text[:120].strip()


def is_dup_callback(chat: int, uid: int, cb: str) -> bool:
    """ایده ۲: اگر همان کاربر همان دکمه را در پنجره‌ی کوتاه دوباره زد → نادیده."""
    key = (chat, uid, cb)
    now = _time.time()
    last = _LAST_CB.get(key, 0)
    _LAST_CB[key] = now
    return (now - last) < DEDUP_WINDOW


def restore_games() -> int:
    """بعد از ری‌استارت، بازی‌های ناتمام را از SQLite برمی‌گرداند."""
    loaded = db.load_snapshots()
    GAMES.update(loaded)
    if loaded:
        log.info("♻️ %d بازی از اسنپ‌شات بازیابی شد: %s", len(loaded), list(loaded))
    return len(loaded)


def _name(name: str, uid: int) -> str:
    n = _sanitize(name)
    return n if n else f"کارآگاه {uid}"


def _ok(text, keyboard=None, anim=None, private=False, edit=False):
    """edit=True یعنی آداپتور به‌جای پیام جدید، همان پیام را ویرایش کند."""
    return {"ok": True, "text": text, "keyboard": keyboard, "anim": anim,
            "private": private, "edit": edit}


def _err(msg):
    return {"ok": False, "text": f"⛔ {msg}", "keyboard": ui.back_only(), "edit": False}


def _g(chat: int) -> Game:
    if chat not in GAMES:
        raise RuleError("بازی فعالی وجود ندارد. با «🎮 شروع بازی» یک لابی بساز.")
    return GAMES[chat]


def _player(chat: int, uid: int):
    """بازیکن را برمی‌گرداند یا خطای دوستانه — دیگر KeyError خام نداریم."""
    g = _g(chat)
    if uid not in g.s.players:
        raise RuleError("تو هنوز وارد این بازی نشده‌ای. اول «➕ ورود» را بزن.")
    return g, g.s.players[uid]


# فرمان‌هایی که به بازی وابسته نیستند و در پیوی همان‌جا اجرا می‌شوند
GLOBAL_CMDS = {"start", "menu", "back", "help", "roles", "tutorial", "share",
               "balance",
               "sharelink", "top", "league", "season", "missions", "achv",
               "new", "blitz", "newtable", "table",
               "admin", "admin_games", "admin_users", "admin_stats", "admin_ban"}

_ACTIVE_TABLE: Dict[int, int] = {}        # uid → چتِ بازیِ انتخاب‌شده
_PENDING: Dict[int, tuple] = {}           # uid → (chat, cmd) — منتظر متنِ کاربر
TEXT_CMDS = tuple(menus.PROMPTS)          # تنها فرمان‌هایی که متن می‌خواهند


def await_text(uid: int, chat: int, cmd: str) -> None:
    _PENDING[uid] = (chat, cmd)


def take_pending(uid: int):
    """اگر منتظرِ متنیم، برش دار (یک‌بارمصرف)."""
    return _PENDING.pop(uid, None)


def games_of(uid: int) -> list:
    """چت‌های بازی‌های تمام‌نشده‌ای که این کاربر در آن‌هاست."""
    return [c for c, g in GAMES.items()
            if uid in g.s.players and g.s.phase is not Phase.END]


def route_chat(cmd: str, chat: int, uid: int, private: bool) -> int:
    """در پیوی، chat_id خودِ کاربر است و بازی گروه را پیدا نمی‌کند.
    بازیِ فعالِ کاربر را برمی‌گرداند؛ ۰ یعنی مبهم/پیدا نشد."""
    if not private or cmd in GLOBAL_CMDS:
        return chat
    if chat in GAMES and uid in GAMES[chat].s.players:
        return chat                       # پیویِ خودش واقعاً یک میز است
    pinned = _ACTIVE_TABLE.get(uid)
    if pinned in GAMES and uid in GAMES[pinned].s.players:
        return pinned
    found = games_of(uid)
    if len(found) == 1:
        return found[0]
    return 0 if found else chat           # هیچ بازی‌ای نداری → خطای عادی


def h_table(chat, uid, name, arg):
    """انتخاب میز برای فرمان‌های پیوی وقتی کاربر در چند بازی است."""
    found = games_of(uid)
    if arg:
        target = int(arg)
        if target not in found:
            raise RuleError("در این بازی عضو نیستی.")
        _ACTIVE_TABLE[uid] = target
        return _ok(f"✅ میز فعالت: `{target}`", ui.back_only(), private=True)
    if not found:
        raise RuleError("در هیچ بازی فعالی نیستی.")
    rows = [[(f"🎲 میز {c}", f"table:{c}")] for c in found]
    return _ok("🎲 *کدام میز؟* برای فرمان‌های خصوصی یکی را انتخاب کن:",
               ui.kb(rows + [[ui.BACK, ui.HOME]]), private=True)


def _ensure(chat: int, uid: int, name: str) -> Game:
    """اگر لابی نبود (یا بازی قبلی تمام شده)، بسازش تا دکمه‌ای بی‌واکنش نماند."""
    g = GAMES.get(chat)
    if g is None or g.s.phase is Phase.END:
        GAMES[chat] = Game(chat, seed=chat or 1, owner=uid)
    return GAMES[chat]


# فرمان‌هایی که نرخ‌محدود نمی‌شوند (خواندنی/بی‌ضرر)
_NO_RATE = {"status", "dashboard", "tick", "help", "roles", "menu", "back", "profile"}


def handle(cmd: str, chat: int, uid: int = 0, name: str = "", arg: str = "") -> Dict:
    """تنها نقطه‌ی ورود. هرگز استثنا پرت نمی‌کند و هرگز بی‌پاسخ نمی‌ماند.
    ایمن در برابر: ریس (قفل هر چت)، اسپم (نرخ‌محدود)، تزریق (پاکسازی)، دستور ناشناخته."""
    db.touch_user(uid, _sanitize(name))
    if cmd not in _ROUTES:                      # ایده ۳: دستور/کالبک نامعتبر
        return _ok(t("unknown"), ui.main_menu())
    # ایده ۹: نرخ‌محدودساز
    if RATE_LIMIT_ENABLED and uid and cmd not in _NO_RATE:
        key = (uid, cmd)
        now = _time.time()
        if now - _LAST_CALL.get(key, 0) < RATE_WINDOW:
            return {"ok": False, "text": "⏳ کمی آرام‌تر! چند لحظه صبر کن.",
                    "keyboard": None, "edit": True}
        _LAST_CALL[key] = now
    with _lock(chat):                           # ایده ۱: قفل هر چت
        try:
            res = _ROUTES[cmd](chat, uid, name, arg)
            db.log_event(chat, uid, cmd, arg[:40])   # ایده ۷: audit log
            if chat in GAMES:
                g = GAMES[chat]
                db.save_game(g)
                if g.s.phase is Phase.END:
                    # نتیجه فقط یک بار ثبت می‌شود، ولی خودِ بازی در حافظه می‌ماند
                    # تا /end بتواند نقش‌ها، MVP و بازسازی پرونده را نشان بدهد.
                    if not g.s.finalized:
                        g.s.finalized = True
                        db.record_results(g)
                        LAST_ROSTER[chat] = [(p.uid, p.name) for p in g.s.players.values()]
                        db.drop_snapshot(chat)
                else:
                    db.save_snapshot(chat, g)
            return res
        except RuleError as e:
            return _err(str(e))
        except (ValueError, TypeError):
            return _err("ورودی نامعتبر است؛ یک عدد/آیدی درست بده.")
        except Exception:
            log.exception("handler %s failed", cmd)
            return _err(f"خطای داخلی هنگام اجرای «{cmd}». دوباره /start بزن.")


# ================= منو و شروع =================
def h_start(chat, uid, name, arg):
    """/start همیشه یا لابیِ دعوت را باز می‌کند یا منوی اصلی را نشان می‌دهد."""
    if arg.startswith("ready_"):                # بهبود ۲: تاییدِ «پیویم باز است»
        try:
            target = int(arg[6:])
        except ValueError:
            return _ok(ui.first_screen(), ui.first_kb(chat))
        if target not in GAMES:
            return _err("این لابی دیگر فعال نیست.")
        return h_ready(target, uid, name, "")
    if arg.startswith("join_"):                 # دیپ‌لینک دعوت
        try:
            target = int(arg[5:])
        except ValueError:
            return _ok(ui.first_screen(), ui.first_kb(chat))
        if target not in GAMES:
            return _err("این لابی دیگر فعال نیست. با «🎮 شروع بازی» لابی تازه بساز.")
        g = GAMES[target]
        if uid == g.owner:                      # فرستنده‌ی لینک → پنل میزبان
            return _ok(ui.owner_panel(g.s), ui.owner_kb(target))
        if uid not in g.s.players:
            try:
                g.join(uid, _name(name, uid))
            except RuleError as e:
                return _err(str(e))
        return _ok(ui.newbie_guide() + "\n\n" + ui.lobby_screen(g.s), ui.back_only())
    return _ok(ui.first_screen(), ui.first_kb(chat))


def h_menu(chat, uid, name, arg):
    return _ok("🏠 *منوی اصلی*", ui.main_menu())


def _guard_replace(chat, uid):
    """بازی در جریان را فقط میزبانش می‌تواند دور بیندازد."""
    g = GAMES.get(chat)
    if g is None:
        return
    if g.s.phase in (Phase.LOBBY, Phase.END):
        return
    if uid != g.owner:
        raise RuleError("یک بازی در جریان است؛ فقط میزبان می‌تواند آن را لغو کند.")
    db.record_abandoned(g)      # بهبود ۸: بازیِ نیمه‌کاره در آمار رهاشدگی بماند


def h_new(chat, uid, name, arg):
    _guard_replace(chat, uid)
    GAMES[chat] = Game(chat, seed=chat or 1, owner=uid)
    if uid:
        GAMES[chat].join(uid, _name(name, uid))     # سازنده خودکار عضو می‌شود
    return _ok(ui.owner_panel(GAMES[chat].s), ui.owner_kb(chat))


def h_join(chat, uid, name, arg):
    g = _ensure(chat, uid, name)                # دکمه هرگز بی‌واکنش نماند
    g.join(uid, _name(name, uid))
    # ویرایش همان پیام لابی؛ پیام جدید فرستاده نمی‌شود تا چت شلوغ نشود
    return _ok(ui.lobby_screen(g.s), ui.lobby_kb(chat), edit=True)


def h_leave(chat, uid, name, arg):
    g = _g(chat)
    g.leave(uid)
    return _ok(ui.lobby_screen(g.s), ui.lobby_kb(chat), edit=True)


def h_startgame(chat, uid, name, arg):
    g = _g(chat)
    asked = "force" in (arg or "").lower()
    case = (arg or "").replace("force", "").strip()
    g.start(int(case) if case else None, force=asked or not REQUIRE_READY)
    db.log_event(chat, uid, "start", g.s.case.title if g.s.case else "")
    return _ok(ui.case_intro(g.s) + "\n\n" + ui.status_board(g.s) +
               "\n\n🔐 هر کس /myrole را بزند نقش محرمانه‌اش به پیوی می‌رود.",
               ui.kb([[("🔐 نقش من", "myrole")], [("🌙 پایان شب", "dawn")], [ui.BACK, ui.HOME]]),
               anim=ui.ANIM["night"])


def h_myrole(chat, uid, name, arg):
    g, p = _player(chat, uid)
    if not p.role:
        return _err("بازی هنوز شروع نشده؛ نقش‌ها پخش نشده‌اند.")
    return _ok(ui.role_card(p.role, p.knows), private=True)


# ================= شب / روز =================
def h_act(chat, uid, name, arg):
    """پنل اکشن شبانه: بدون آرگومان = فهرست هدف‌ها با نام؛ با آرگومان = ثبت."""
    g, p = _player(chat, uid)
    if not p.role:      # هنوز نقشی پخش نشده → خطای دوستانه، نه KeyError
        raise RuleError("بازی هنوز شروع نشده؛ نقش‌ها پخش نشده‌اند.")
    if arg:
        res = g.night_action(uid, int(arg))
        tgt = g.s.players[int(arg)].name
        return _ok(f"✅ ثبت شد — هدف: *{tgt}*\n{res}",
                   ui.action_kb(g.s, p, g.legal_targets(uid), chosen=int(arg)),
                   private=True)
    chosen = g.chosen_target(uid)
    if ROLES[p.role].ability == "hunter":
        targets = [t for t in g.s.players
                   if t != uid and g.s.players[t].in_game]
        chosen = p.hunter_target
    else:
        targets = g.legal_targets(uid)
    return _ok(ui.action_panel(g.s, p, chosen),
               ui.action_kb(g.s, p, targets, chosen), private=True)


def h_night(chat, uid, name, arg):
    """سازگاری با /night <id> — بدون آرگومان همان پنل دکمه‌ای را می‌دهد."""
    return h_act(chat, uid, name, arg)


def h_dawn(chat, uid, name, arg):
    g = _g(chat)
    r = g.resolve_night()
    dead = "، ".join(g.s.players[u].name for u in r["killed"]) or "هیچ‌کس"
    ev_line = f"\n🌩️ رویداد شب: {g.s.night_event}" if g.s.night_event else ""
    # بهبود ۵: ردهایی که از اکشن واقعیِ دیشب ساخته شده‌اند
    traces = ("\n\n🔬 *ردهای دیشب:*\n" + "\n".join(f"  • {t}" for t in g.s.traces)) \
        if g.s.traces else ""
    txt = (f"☀️ *صبح روز {g.s.day}*{ev_line}\n{ui.DIV}\n⚰️ کشته‌شده: {dead}\n\n"
           + ui.evidence_card(r["evidence"]) + traces + "\n\n" + ui.status_board(g.s))
    return _ok(txt, ui.kb([[("💬 گفتگو", "discuss")], [ui.BACK, ui.HOME]]), anim=ui.ANIM["morning"])


def h_discuss(chat, uid, name, arg):
    g = _g(chat)
    g.open_discussion()
    return _ok("💬 *فاز گفتگو باز است.* بحث کنید، اتهام بزنید، دفاع کنید.",
               ui.kb([[("🗳️ شروع رای‌گیری", "vote")], [ui.BACK, ui.HOME]]))


def h_vote(chat, uid, name, arg):
    g = _g(chat)
    g.open_vote()
    return _ok("🗳️ *رای‌گیری آغاز شد* — چه کسی به بازجویی برود؟", ui.vote_kb(g.s), anim=ui.ANIM["vote"])


def h_castvote(chat, uid, name, arg):
    g = _g(chat)
    g.vote(uid, int(arg))
    who = "" if g.s.vote_anon else f" — {_name(name, uid)} به {g.s.players[int(arg)].name}"
    return _ok(f"✅ رای ثبت شد ({len(g.s.votes)} رای){who}.",
               ui.kb([[("📊 بستن رای‌گیری", "closevote")]]))


def h_closevote(chat, uid, name, arg):
    g = _g(chat)
    who = g.close_vote()
    if who is None:
        return _ok("🤷 تساوی/بدون رای — کسی بازداشت نشد. شب فرا می‌رسد.",
                   ui.kb([[("🌙 پایان شب", "dawn")]]), anim=ui.ANIM["night"])
    p = g.s.players[who]
    db.log_event(chat, who, "interrogation", "رای گروه")
    return _ok(f"🔦 *{p.name}* به اتاق بازجویی منتقل شد.\n"
               f"بازجو امشب سؤال می‌پرسد؛ حکم فردا صبح صادر می‌شود.\n"
               f"بقیه اکشن شبانه‌شان را دارند — بعد «🌙 پایان شب».",
               ui.officer_kb(who), anim=ui.ANIM["interrogation"])


# ================= بازجویی =================
def h_hints(chat, uid, name, arg):
    g = _g(chat)
    hs = g.officer_hints(uid)
    return _ok("🔦 *سرنخ‌های بازجویی (مبهم و غیرقطعی):*\n" + "\n".join(f"  • {h}" for h in hs), private=True)


def h_ask(chat, uid, name, arg):
    g = _g(chat)
    if not arg:
        # دکمه‌ی قبلی آیدیِ متهم را به‌جای متنِ سؤال می‌فرستاد؛ حالا متن می‌گیریم.
        return _ask_text(chat, uid, "ask")
    d = f"\n🛡️ دفاع متهم: «{g.s.defense_text}»" if g.s.defense_text else ""
    return _ok(f"🗣️ متهم: «{g.ask(uid, arg)}»{d}",
               ui.kb([[("💬 پرسش بعدی", "ask")],
                      [("🔒 حبس موقت", "verdict:1"),
                       ("🔓 آزادی", "verdict:0")]]), private=True)


def h_verdict(chat, uid, name, arg):
    g = _g(chat)
    if arg not in ("0", "1"):
        if g.s.suspect_uid is None:
            raise RuleError("کسی در بازجویی نیست.")
        return _ok("⚖️ *حکم تو چیست؟*", menus.verdict_kb(g.s))
    msg = g.officer_verdict(uid, arg == "1")
    db.log_event(chat, g.s.suspect_uid or 0, "verdict", "حبس موقت" if arg == "1" else "آزادی")
    anim = ui.ANIM["jail"] if arg == "1" else None
    # شبِ بازجویی قبلاً گذشته؛ روز از همین‌جا ادامه می‌دهد.
    return _ok(msg + "\n\n" + ui.status_board(g.s),
               ui.kb([[("💬 گفتگو", "discuss")], [ui.BACK, ui.HOME]]), anim=anim)


def h_clear(chat, uid, name, arg):
    g = _g(chat)
    if not arg:
        return _ok("🕊️ *کدام زندانی را تبرئه می‌کنی؟*",
                   menus.player_kb(g.s, "clear", only_custody=Custody.TEMP_JAIL))
    return _ok(g.clear_previous(uid, int(arg)) + "\n\n" + ui.status_board(g.s), ui.back_only())


# ================= هیئت منصفه =================
def h_jury(chat, uid, name, arg):
    g = _g(chat)
    formed = g.request_jury(uid)
    if not formed:
        return _ok("📝 درخواست هیئت منصفه ثبت شد؛ یک نفر دیگر هم لازم است.")
    return _ok("⚖️ *هیئت منصفه تشکیل شد!* رای بدهید.", ui.jury_kb())


def h_juryvote(chat, uid, name, arg):
    g = _g(chat)
    g.jury_vote(uid, arg == "1")
    return _ok(f"🗳️ رای هیئت منصفه ثبت شد ({len(g.s.jury_votes)}).",
               ui.kb([[("📊 نتیجه‌ی هیئت", "closejury")]]))


def h_closejury(chat, uid, name, arg):
    g = _g(chat)
    return _ok(g.close_jury() + "\n\n" + ui.status_board(g.s), ui.back_only())


# ================= وضعیت / پایان / پروفایل =================
def h_status(chat, uid, name, arg):
    return _ok(ui.status_board(_g(chat).s), ui.back_only())


def h_end(chat, uid, name, arg):
    g = _g(chat)
    if g.s.phase is not Phase.END:
        return _err("بازی هنوز تمام نشده؛ تا آخر بازی معلوم نمی‌شود قاتل کیست.")
    return _ok(g.ending_report(),
               ui.kb([[("🔁 همین ترکیب، دور جدید", "rematch")], [("🎮 بازی جدید", "new")], [ui.HOME]]),
               anim=ui.ANIM["court"])


def h_profile(chat, uid, name, arg):
    g, p = _player(chat, uid)
    return _ok(f"📊 *{p.name}*\n{ui.DIV}\n⭐ XP: {p.xp}\n🪙 سکه: {p.coins}\n🎖️ رتبه: {g.rank_of(p)}",
               ui.back_only(), private=True)


def h_help(chat, uid, name, arg):
    return _ok(ui.help_text(), ui.back_only())


def h_roles(chat, uid, name, arg):
    """کاتالوگ نقش‌ها = یک دکمه برای هر نقش؛ تپ → توانایی‌های همان نقش."""
    return _ok("🎭 *کاتالوگ نقش‌ها*\n" + ui.DIV +
               "\nروی هر نقش بزن تا تیم، کار شبانه و شرط بردش را ببینی.",
               menus.roles_kb())


# ================= اشتراک‌گذاری =================
def h_share(chat, uid, name, arg):
    g = _ensure(chat, uid, name)
    return _ok(ui.share_screen(chat, len(g.s.players)), ui.share_kb(chat))


def h_sharelink(chat, uid, name, arg):
    return _ok("🔗 لینک دعوت:\n`" + ui.share_links(chat)["join"] + "`", ui.back_only())


# ================= پنل ادمین (روی SQL) =================
def _admin(uid):
    # فهرست خالی = هیچ‌کس ادمین نیست (قبلاً یعنی «همه ادمین‌اند»).
    if uid not in ADMIN_IDS:
        raise RuleError("دسترسی ادمین لازم است.")


def h_admin(chat, uid, name, arg):
    _admin(uid)
    return _ok("🛠️ *پنل ادمین* (داده‌ها از پایگاه‌داده‌ی SQL)", ui.admin_menu())


def h_admin_games(chat, uid, name, arg):
    _admin(uid)
    return _ok(ui.admin_games_sql(db.q_active_games()), ui.back_only())


def h_admin_stats(chat, uid, name, arg):
    _admin(uid)
    return _ok(ui.admin_stats_sql(db.q_stats()), ui.back_only())


def h_admin_users(chat, uid, name, arg):
    """بدون آرگومان: فهرست کاربران از SQL. با آیدی: کارت کامل + خلاصه‌ی بازی‌ها."""
    _admin(uid)
    if not arg:
        return _ok(ui.admin_users_sql(db.q_users()),
                   menus.users_kb(db.q_users(), "admin_users"))
    t = int(arg)
    u = db.q_user(t)
    if not u:
        return _err("کاربری با این آیدی در پایگاه‌داده نیست.")
    return _ok(ui.admin_user_card_sql(u, db.q_user_games(t), db.q_user_events(t)), ui.back_only())


def h_admin_ban(chat, uid, name, arg):
    _admin(uid)
    if not arg:
        return _ok("🚫 *کدام کاربر مسدود شود؟*",
                   menus.users_kb(db.q_users(), "admin_ban"))
    t = int(arg)
    db.ban(t, True)
    db.log_event(chat, t, "ban", f"by {uid}")
    return _ok(f"🚫 کاربر `{t}` مسدود شد.", ui.back_only())



# ================= ایده ۱: تایمر =================
def h_tick(chat, uid, name, arg):
    g = _g(chat)
    msg = g.tick()
    if msg is None:
        rem = g.remaining()
        res = _ok(f"{t('timer')}: {rem if rem is not None else '—'} ثانیه | فاز: {g.s.phase.value}",
                  edit=True)
        res["advanced"] = False
        return res
    # advanced=True یعنی فاز واقعاً جلو رفت — آداپتور فقط این را پخش می‌کند.
    res = _ok(msg + "\n\n" + ui.status_board(g.s), ui.back_only())
    res["advanced"] = True
    return res


def h_dashboard(chat, uid, name, arg):            # ایده ۲۶ + بهبود ۳
    g = _g(chat)
    return _ok(ui.dashboard(g.s, g.remaining(), g.pending_actors(), g.next_step()),
               ui.dashboard_kb(g.s), edit=True)


# ================= ایده‌های ۲/۵/۹ =================
def h_defense(chat, uid, name, arg):
    g = _g(chat)
    if not arg:
        return _ask_text(chat, uid, "defense")
    return _ok(g.defense(uid, arg))


def _ask_text(chat, uid, cmd):
    """دکمه زده شد ولی متن لازم است → منتظر پیام بعدیِ همین کاربر می‌مانیم."""
    await_text(uid, chat, cmd)
    return _ok(menus.prompt_text(cmd), menus.prompt_kb(), private=True)


def h_will(chat, uid, name, arg):
    g, p = _player(chat, uid)
    if not arg:
        return _ask_text(chat, uid, "will")
    g.set_will(uid, arg)
    return _ok("📜 وصیت‌نامه ثبت شد؛ اگر کشته شوی صبح خوانده می‌شود.",
               menus.commands_menu(), private=True)


def h_note(chat, uid, name, arg):
    g, p = _player(chat, uid)
    if not arg:
        return _ask_text(chat, uid, "note")
    g.add_note(uid, arg)
    return _ok("📝 یادداشت خصوصی ثبت شد.",
               ui.kb([[("📓 دفترچه‌ی من", "notes")], [menus.BACK, menus.HOME]]), private=True)


def h_notes(chat, uid, name, arg):
    g, p = _player(chat, uid)
    found = "\n".join(f"  • {n}" for n in p.notes) or "  — هنوز چیزی نرسیده —"
    mine = "\n".join(f"  • {n}" for n in p.private_notes) or "  — خالی —"
    return _ok(f"🔎 *یافته‌های نقش تو:*\n{found}\n\n📝 *یادداشت‌های خودت:*\n{mine}",
               ui.back_only(), private=True)


# ================= ایده‌های ۶/۱۰/۱۱/۱۲ =================
def h_sos(chat, uid, name, arg):
    g = _g(chat)
    if not arg:
        return _ok("🚨 *رای اضطراری شهر* — علیه چه کسی؟\n"
                   "با ۸۰٪ رای، مستقیم به حبس موقت می‌رود. فقط یک بار در بازی.",
                   menus.player_kb(g.s, "sos", exclude=(uid,)))
    return _ok(g.sos(uid, int(arg)))


def h_lab(chat, uid, name, arg):
    g = _g(chat)
    if not arg:
        _need_case(g)
        return _ok("🧪 *کدام مدرک به آزمایشگاه برود؟*\nنتیجه دو شب دیگر می‌رسد.",
                   menus.evidence_kb(g.s, "lab"))
    return _ok(g.submit_lab(arg.upper()), menus.evidence_kb(g.s, "lab"))


def h_interp(chat, uid, name, arg):               # interp ← مدرک ← تفسیر
    g = _g(chat)
    _need_case(g)
    arg = (arg or "").upper()
    if not arg:
        return _ok("🧠 *تفسیر کدام مدرک؟*", menus.evidence_kb(g.s, "interp"))
    if ":" not in arg:                          # مدرک انتخاب شد → تفسیرها
        ev = next((e for e in g.s.case.evidence if e["code"] == arg), None)
        if not ev:
            raise RuleError("کد مدرک نامعتبر است.")
        return _ok(ui.evidence_card(ev) + "\n🗳️ کدام تفسیر را قبول داری؟",
                   menus.interp_kb(ev))
    code, idx = arg.split(":", 1)
    return _ok(g.vote_interp(uid, code, int(idx)), menus.evidence_kb(g.s, "interp"))


def h_expose(chat, uid, name, arg):
    g = _g(chat)
    if not arg:
        _need_case(g)
        return _ok("🔍 *اصالت کدام مدرک را بسنجم؟*\nاین کار اکشن شبانه‌ات را خرج می‌کند.",
                   menus.evidence_kb(g.s, "expose"), private=True)
    code = arg.upper()
    return _ok(f"🔍 اصالت مدرک {code}: {g.expose(uid, code)}",
               menus.evidence_kb(g.s, "expose"), private=True)


# ================= ایده‌های ۱۵/۱۶/۱۸/۱۹/۲۰/۲۵ =================
def h_top(chat, uid, name, arg):
    rows = db.q_top()
    body = "\n".join(f"  {i+1}. {r['name']} — ⭐{r['xp']} ({r['wins']}/{r['games']})"
                     for i, r in enumerate(rows)) or "  —"
    return _ok(f"🏆 *برترین‌ها*\n{ui.DIV}\n{body}", ui.back_only())


def h_league(chat, uid, name, arg):
    rows = db.q_league()
    body = "\n".join(f"  {i+1}. گروه `{r['chat_id']}` — 👥{r['n']} — ⭐{r['sx']}"
                     for i, r in enumerate(rows)) or "  —"
    return _ok(f"🌍 *لیگ گروه‌ها*\n{ui.DIV}\n{body}", ui.back_only())


def h_season(chat, uid, name, arg):
    rows = db.q_season()
    body = "\n".join(f"  {i+1}. {r['name']} — ⭐{r['xp']}" for i, r in enumerate(rows)) or "  —"
    return _ok(f"📅 *رتبه‌بندی این فصل*\n{ui.DIV}\n{body}", ui.back_only())


def h_missions(chat, uid, name, arg):
    body = "\n".join(f"  {'✅' if done else '⬜'} {title} (+{coin}🪙)"
                     for _k, title, coin, done in db.q_missions(uid))
    return _ok(f"🎯 *ماموریت‌های امروز*\n{ui.DIV}\n{body}", ui.back_only(), private=True)


def h_achv(chat, uid, name, arg):
    keys = db.q_achievements(uid)
    body = "\n".join(f"  {db.ACHIEVEMENTS[k]}" for k in keys if k in db.ACHIEVEMENTS) or "  — هنوز هیچ —"
    acc = db.q_accuracy(uid)
    acc_line = (f"\n🎯 دقت رای: {acc['hits']}/{acc['total']}" if acc and acc["total"] else "")
    return _ok(f"🏅 *دستاوردها*\n{ui.DIV}\n{body}{acc_line}", ui.back_only(), private=True)


# ================= ایده‌های ۲۱/۲۲/۲۳/۲۴/۲۷/۲۸ =================
def h_newtable(chat, uid, name, arg):             # ایده ۲۱: میز موازی در همان گروه
    for slot in range(1, 4):
        vid = chat * 100 + slot
        if vid not in GAMES:
            GAMES[vid] = Game(vid, seed=vid, owner=uid)
            GAMES[vid].join(uid, _name(name, uid))
            return _ok(f"🎲 *میز شماره {slot}* ساخته شد.\n\n" + ui.lobby_screen(GAMES[vid].s),
                       ui.lobby_kb(vid))
    return _err("هر گروه حداکثر ۳ میز هم‌زمان دارد.")


def h_spectate(chat, uid, name, arg):             # ایده ۲۲: تماشاچی بدون اسپویل
    g = _g(chat)
    tail = "\n".join(f"  • {l}" for l in g.s.log[-6:]) or "  —"
    return _ok(ui.status_board(g.s) + f"\n{ui.DIV}\n📺 آخرین رویدادها:\n{tail}",
               ui.back_only(), private=True)


def h_voteanon(chat, uid, name, arg):             # ایده ۲۳
    g = _g(chat)
    if uid != g.owner:
        raise RuleError("فقط میزبان می‌تواند حالت رای را عوض کند.")
    g.s.vote_anon = not g.s.vote_anon
    mode = "ناشناس 🕶️" if g.s.vote_anon else "علنی 📢"
    return _ok(f"🗳️ حالت رای‌گیری: {mode}")


def h_rematch(chat, uid, name, arg):              # ایده ۲۴
    roster = LAST_ROSTER.get(chat)
    if not roster:
        raise RuleError("بازی قبلی‌ای برای تکرار نیست.")
    _guard_replace(chat, uid)
    GAMES[chat] = Game(chat, seed=chat + len(roster), owner=roster[0][0])
    for u, n in roster:
        GAMES[chat].join(u, n)
    return _ok("🔁 *دور جدید با همان ترکیب!*\n\n" + ui.lobby_screen(GAMES[chat].s),
               ui.lobby_kb(chat))


def h_rolecard(chat, uid, name, arg):             # ایده ۲۷: کارت PNG
    g, p = _player(chat, uid)
    if not p.role:
        raise RuleError("بازی هنوز شروع نشده.")
    path = cards.render_role_card(p.role, p.name)
    res = _ok(ui.role_card(p.role, p.knows), private=True)
    res["photo"] = path
    return res


def h_tutorial(chat, uid, name, arg):             # ایده ۲۸
    return _ok(ui.tutorial_text(), ui.kb([[("📖 قوانین کامل", "help")], [ui.BACK, ui.HOME]]))


def h_blitz(chat, uid, name, arg):                # ایده ۳: لابی سریع
    _guard_replace(chat, uid)
    GAMES[chat] = Game(chat, seed=chat or 1, owner=uid, blitz=True)
    if uid:
        GAMES[chat].join(uid, _name(name, uid))
    return _ok("⚡ *حالت بلیتز* — همه‌ی مهلت‌ها نصف!\n\n" + ui.owner_panel(GAMES[chat].s),
               ui.owner_kb(chat))


def h_ready(chat, uid, name, arg):                # بهبود ۲
    g = _g(chat)
    msg = g.mark_ready(uid)
    left = g.not_ready()
    if left:
        names = "، ".join(g.s.players[u].name for u in left)
        tail = f"\n⏳ مانده: {names}"
    else:
        tail = "\n🟢 همه آماده‌اند — میزبان می‌تواند شروع کند."
    return _ok(msg + tail, ui.back_only(), private=True)


def h_remind(chat, uid, name, arg):               # بهبود ۷
    g = _g(chat)
    # در شب نه نام می‌بریم نه تعداد: هر دو می‌گویند چه کسی نقشِ اکشن‌دار دارد،
    # و تغییرِ عدد بین دو یادآوری، زمانِ اکشنِ آن نفر را لو می‌دهد.
    if g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
        return _ok("⏰ *یادآوری* — هر کسی اکشن شبانه دارد، «🌙 اکشن شبانه» را بزند.\n"
                   f"➡️ {g.next_step()}", ui.dashboard_kb(g.s))
    left = g.pending_actors()
    if not left:
        return _ok("✅ همه کارشان را کرده‌اند.", ui.back_only())
    names = "، ".join(g.s.players[u].name for u in left)
    return _ok(f"⏰ *یادآوری* — منتظر: {names}\n➡️ {g.next_step()}",
               ui.dashboard_kb(g.s))


def h_pause(chat, uid, name, arg):                # بهبود ۷
    g = _g(chat)
    if uid != g.owner:
        raise RuleError("فقط میزبان می‌تواند بازی را متوقف کند.")
    return _ok(g.pause(), ui.kb([[("▶️ ادامه", "resume")], [ui.BACK, ui.HOME]]))


def h_resume(chat, uid, name, arg):               # بهبود ۷
    g = _g(chat)
    if uid != g.owner:
        raise RuleError("فقط میزبان می‌تواند بازی را ادامه دهد.")
    return _ok(g.resume(), ui.dashboard_kb(g.s))


def h_host(chat, uid, name, arg):                 # بهبود ۷: انتقال میزبانی
    g = _g(chat)
    owner = g.s.players.get(g.owner)
    # میزبانِ حاضر خودش واگذار می‌کند؛ اگر از بازی بیرون است، هر بازیکنی می‌تواند بگیرد.
    if uid != g.owner and owner is not None and owner.in_game:
        raise RuleError("فقط میزبان فعلی می‌تواند میزبانی را واگذار کند.")
    if not arg:
        return _ok("👑 *میزبانی به چه کسی برسد؟*", menus.player_kb(g.s, "host"))
    return _ok(g.transfer_host(int(arg)), ui.back_only())


def h_balance(chat, uid, name, arg):              # بهبود ۸
    _admin(uid)
    return _ok(ui.balance_report_sql(db.q_balance(), db.q_balance_by_seats(),
                                     db.q_abandonment()), ui.back_only())


def h_hunter(chat, uid, name, arg):
    g = _g(chat)
    return _ok(g.set_hunter(uid, int(arg)), private=True)


def _need_case(g):
    if not g.s.case:
        raise RuleError("بازی هنوز شروع نشده؛ مدرکی وجود ندارد.")


# ================= همه‌ی فرمان‌ها = دکمه =================
def h_commands(chat, uid, name, arg):
    return _ok(menus.commands_screen(), menus.commands_menu())


def h_group(chat, uid, name, arg):
    keys = [k for k, _t, _i in menus.GROUPS]
    if arg not in keys:
        return _ok(menus.commands_screen(), menus.commands_menu())
    return _ok(f"*{menus.group_title(arg)}*", menus.group_kb(arg))


def h_roleinfo(chat, uid, name, arg):
    try:
        role = menus.ROLE_NAMES[int(arg)]
    except (ValueError, IndexError):
        return _ok("🎭 *کاتالوگ نقش‌ها* — یکی را بزن:", menus.roles_kb())
    return _ok(menus.role_detail(role), menus.role_detail_kb())


def h_abilities(chat, uid, name, arg):
    g, p = _player(chat, uid)
    return _ok(menus.abilities_text(g, p), menus.abilities_kb(g, p), private=True)


def h_cancel(chat, uid, name, arg):
    take_pending(uid)
    return _ok("✖️ باشه، بی‌خیال.", menus.commands_menu())


_ROUTES = {
    "start": h_start, "menu": h_menu, "back": h_menu, "new": h_new,
    "join": h_join, "leave": h_leave, "startgame": h_startgame, "myrole": h_myrole,
    "night": h_night, "dawn": h_dawn, "discuss": h_discuss, "vote": h_vote,
    "castvote": h_castvote, "closevote": h_closevote, "hints": h_hints, "ask": h_ask,
    "verdict": h_verdict, "clear": h_clear, "jury": h_jury, "juryvote": h_juryvote,
    "closejury": h_closejury, "status": h_status, "end": h_end, "profile": h_profile,
    "help": h_help, "roles": h_roles, "share": h_share, "sharelink": h_sharelink,
    "admin": h_admin, "admin_games": h_admin_games, "admin_users": h_admin_users,
    "admin_stats": h_admin_stats, "admin_ban": h_admin_ban,
    # نسخه ۲: ۳۰ ایده
    "tick": h_tick, "dashboard": h_dashboard, "defense": h_defense,
    "will": h_will, "note": h_note, "notes": h_notes, "sos": h_sos,
    "lab": h_lab, "interp": h_interp, "expose": h_expose,
    "top": h_top, "league": h_league, "season": h_season,
    "missions": h_missions, "achv": h_achv, "newtable": h_newtable,
    "spectate": h_spectate, "voteanon": h_voteanon, "rematch": h_rematch,
    "rolecard": h_rolecard, "tutorial": h_tutorial, "blitz": h_blitz,
    "hunter": h_hunter, "table": h_table, "act": h_act,
    "ready": h_ready, "remind": h_remind, "pause": h_pause,
    "commands": h_commands, "group": h_group, "roleinfo": h_roleinfo,
    "abilities": h_abilities, "cancel": h_cancel,
    "resume": h_resume, "host": h_host, "balance": h_balance,
}

# دستورهایی که به BotFather معرفی می‌شوند (زیرمجموعه‌ی امن برای منوی دستورها)
COMMANDS = ["start", "menu", "new", "join", "startgame", "myrole", "act",
            "dashboard", "status", "table", "notes", "help", "roles",
            "ready", "remind", "pause", "resume", "host",
            "share", "admin"]
ENDPOINTS = sorted(_ROUTES)
