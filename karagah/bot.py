"""لایه‌ی اندپوینت ربات — مستقل از شبکه، پس کاملاً تست‌پذیر.
هر هندلر یک dict برمی‌گرداند: {ok, text, keyboard?, anim?, private?}
اتصال به python-telegram-bot فقط با map کردن این هندلرها انجام می‌شود.
"""
from __future__ import annotations
import contextvars
import logging
from typing import Dict, List, Optional

from . import ui, db, cards, menus, config
from .strings import t
from .config import ADMIN_IDS
from .engine import Game, RuleError
from .models import Custody, Phase
from .roles import ROLES, SCENARIOS, scenario_name

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


# کنترل‌های جهت (RLO و …) و نویسه‌های نامرئی — در نام، متنِ اطرافش را وارونه/جعل می‌کنند.
# نیم‌فاصله (U+200C) برای فارسی لازم است و می‌ماند.
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e"
                                    "\u2066\u2067\u2068\u2069\ufeff\u00ad"), None)
NAME_MAX = 32


def _sanitize(text: str) -> str:
    """ایده ۸: خنثی‌سازی نویسه‌های Markdown برای جلوگیری از تزریق/خرابی رندر.
    نسخه ۸: کنترل‌های جهت/نامرئی حذف، فاصله‌ها یکی، حداکثر ۳۲ نویسه (نام در دکمه و جدول جا شود)."""
    if not text:
        return ""
    text = text.translate(_INVISIBLE)
    for ch in ("*", "_", "`", "[", "]", "(", ")", "~", ">", "#", "|", "{", "}", "<"):
        text = text.replace(ch, "")
    text = " ".join(text.split())
    return text[:NAME_MAX].strip()


def _clean(text: str, limit: int = 300) -> str:
    """متنِ آزادِ بازیکن (پرسش، جواب، دفاع، وصیت، یادداشت) پیش از ذخیره: بدون نویسه‌ی Markdown،
    تا هر جا بعداً نشان داده شود (صبح، پایان، پیوی بازجو) قالب‌بندیِ پیام را نشکند."""
    if not text:
        return ""
    for ch in ("*", "_", "`", "[", "]", "~", "|", "\\"):
        text = text.replace(ch, "")
    return text.strip()[:limit]


def is_dup_callback(chat: int, uid: int, cb: str) -> bool:
    """ایده ۲: اگر همان کاربر همان دکمه را در پنجره‌ی کوتاه دوباره زد → نادیده."""
    key = (chat, uid, cb)
    now = _time.time()
    last = _LAST_CB.get(key, 0)
    _LAST_CB[key] = now
    return (now - last) < DEDUP_WINDOW


def _upgrade(g: Game) -> Game:
    """اسنپ‌شاتِ نسخه‌های قبل فیلدهای تازه را ندارد؛ پیش‌فرض‌ها را پر کن."""
    from .models import GameState
    fresh = GameState(chat_id=g.s.chat_id)
    for k, v in vars(fresh).items():
        if not hasattr(g.s, k):
            setattr(g.s, k, v)
    if not hasattr(g, "last_event"):
        g.last_event = None
    now = _time.time()
    if not g.s.touched:
        g.s.touched = now                       # ساعتِ بی‌فعالیتی از لحظه‌ی بازیابی
    if g.s.phase is Phase.END and not g.s.ended_at:
        g.s.ended_at = now
    return g


def restore_games() -> int:
    """بعد از ری‌استارت، بازی‌ها را از SQLite برمی‌گرداند (تمام‌شده‌ها هم، تا افشا بماند)."""
    loaded = {c: _upgrade(g) for c, g in db.load_snapshots().items()}
    GAMES.update(loaded)
    if loaded:
        log.info("♻️ %d بازی از اسنپ‌شات بازیابی شد: %s", len(loaded), list(loaded))
    return len(loaded)


def _name(name: str, uid: int) -> str:
    n = _sanitize(name)
    return n if n else f"کارآگاه {uid}"


def _ok(text, keyboard=None, anim=None, private=False, edit=False, announce=False):
    """edit=True یعنی آداپتور به‌جای پیام جدید، همان پیام را ویرایش کند.
    announce=True یعنی این پیام «اعلامِ عمومیِ بازی» است: اگر دکمه در پیوی زده شده،
    آداپتور آن را به گروهِ بازی می‌فرستد (نه به همان پیوی) و به کاربر فقط تاییدیه می‌دهد."""
    return {"ok": True, "text": text, "keyboard": keyboard, "anim": anim,
            "private": private, "edit": edit, "announce": announce}


# ── صندوق خروجی: پیام به کسانی غیر از فرستنده (پرسش بازجو به متهم، نتیجه‌ی شب، کارت نقش) ──
_OUT: contextvars.ContextVar = contextvars.ContextVar("karagah_outbox", default=None)


def _post(dest: int, text: str, keyboard=None) -> None:
    """پیامی برای چت/کاربرِ دیگر؛ آداپتور بعد از پاسخِ اصلی می‌فرستد."""
    box = _OUT.get()
    if box is not None and dest:
        box.append({"chat": dest, "text": text, "keyboard": keyboard})


def _push_notes(g: Game) -> None:
    """یافته‌های تازه‌ی هر بازیکن (استعلام، نگهبانی، شایعه، جانشینی…) خودکار به پیویِ خودش."""
    for p in g.s.players.values():
        done = getattr(p, "notes_pushed", 0)
        if len(p.notes) > done:
            fresh = "\n".join(f"  • {n}" for n in p.notes[done:])
            _post(p.uid, f"🔔 *خبر تازه برای تو (محرمانه):*\n{fresh}",
                  ui.kb([[("📓 دفترچه‌ی من", "notes")]]))
            p.notes_pushed = len(p.notes)


def _err(msg):
    return {"ok": False, "text": f"⛔ {msg}", "keyboard": ui.back_only(), "edit": False}


def _private(chat: int, uid: int) -> bool:
    """در تلگرام، آیدیِ پیوی همان آیدیِ کاربر است (گروه‌ها منفی‌اند)."""
    return bool(uid) and chat == uid


def _is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


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
GLOBAL_CMDS = {"start", "menu", "back", "fullmenu", "help", "roles", "tutorial", "share",
               "balance",
               "sharelink", "top", "league", "season", "missions", "achv",
               "new", "blitz", "table",
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


# بعد از پایان بازی هم این‌ها باید از پیوی به همان بازی برسند (دفترچه، نقش، افشا…)
AFTER_END_CMDS = {"notes", "myrole", "end", "abilities", "profile", "rolecard",
                  "status", "dashboard", "spectate", "rematch"}


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
    if found:
        return 0                          # مبهم
    if cmd in AFTER_END_CMDS:             # بازی‌ات تازه تمام شده → همان را نشان بده
        ended = [c for c, g in GAMES.items() if uid in g.s.players]
        if ended:
            return ended[-1]
    return chat                           # هیچ بازی‌ای نداری → خطای عادی


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
_NO_RATE = {"status", "dashboard", "tick", "help", "roles", "menu", "back", "profile", "fullmenu"}


def handle(cmd: str, chat: int, uid: int = 0, name: str = "", arg: str = "") -> Dict:
    """تنها نقطه‌ی ورود؛ خروجی از صافیِ بومی‌سازی (رقم فارسی) رد می‌شود."""
    from .l10n import localize
    return localize(_handle(cmd, chat, uid, name, arg))


def _handle(cmd: str, chat: int, uid: int = 0, name: str = "", arg: str = "") -> Dict:
    """تنها نقطه‌ی ورود. هرگز استثنا پرت نمی‌کند و هرگز بی‌پاسخ نمی‌ماند.
    ایمن در برابر: ریس (قفل هر چت)، اسپم (نرخ‌محدود)، تزریق (پاکسازی)، دستور ناشناخته."""
    try:
        db.touch_user(uid, _sanitize(name))
    except Exception:                           # دیتابیس نباید پاسخ را بخواباند
        log.exception("touch_user failed")
    if cmd not in _ROUTES:                      # ایده ۳: دستور/کالبک نامعتبر
        return _ok(t("unknown"), ui.main_menu())
    if uid and cmd not in ("start", "menu", "back", "help") and db.is_banned(uid):
        return {"ok": False, "text": "🚫 حساب تو مسدود شده است.", "keyboard": None, "edit": False}
    # ایده ۹: نرخ‌محدودساز
    if RATE_LIMIT_ENABLED and uid and cmd not in _NO_RATE:
        key = (uid, cmd)
        now = _time.time()
        if now - _LAST_CALL.get(key, 0) < RATE_WINDOW:
            return {"ok": False, "text": "⏳ کمی آرام‌تر! چند لحظه صبر کن.",
                    "keyboard": None, "edit": True}
        _LAST_CALL[key] = now
    with _lock(chat):                           # ایده ۱: قفل هر چت
        token = _OUT.set([])
        try:
            res = _ROUTES[cmd](chat, uid, name, arg)
            idle_tick = cmd == "tick" and not (isinstance(res, dict) and res.get("advanced"))
            if not idle_tick:                        # تیکِ بی‌اتفاق (هر ۵ ثانیه، هر میز) دیسک را نمی‌کوبد
                db.log_event(chat, uid, cmd, arg[:40])   # ایده ۷: audit log
            if chat in GAMES and not idle_tick:
                g = GAMES[chat]
                if cmd != "tick":                   # تایمر «فعالیت» نیست؛ وگرنه هیچ میزی بی‌فعالیت نمی‌شد
                    g.s.touched = _time.time()
                _push_notes(g)
                db.save_game(g)
                if g.s.phase is Phase.END and not g.s.finalized:
                    # نتیجه فقط یک بار ثبت می‌شود؛ پرچم بعد از نوشتنِ موفق زده می‌شود
                    # تا شکستِ نوشتن، تلاشِ دوباره را خفه نکند.
                    db.record_results(g)
                    g.s.finalized = True
                    g.s.ended_at = _time.time()
                    LAST_ROSTER[chat] = [(p.uid, p.name) for p in g.s.players.values()]
                # بازیِ تمام‌شده هم ذخیره می‌ماند تا بعد از ری‌استارت افشای پایانی در دسترس باشد
                db.save_snapshot(chat, g)
            res = dict(res)
            res["outbox"] = list(_OUT.get() or [])
            return res
        except RuleError as e:
            return _err(str(e))
        except (ValueError, TypeError):
            return _err("ورودی نامعتبر است؛ یک عدد/آیدی درست بده.")
        except Exception:
            log.exception("handler %s failed", cmd)
            return _err(f"خطای داخلی هنگام اجرای «{cmd}». دوباره /start بزن.")
        finally:
            _OUT.reset(token)


# ================= منو و شروع =================
def h_start(chat, uid, name, arg):
    """/start همیشه یا لابیِ دعوت را باز می‌کند یا منوی اصلی را نشان می‌دهد."""
    if arg.startswith("ready_"):                # بهبود ۲: تاییدِ «پیویم باز است»
        try:
            target = int(arg[6:])
        except ValueError:
            return _ok(ui.first_screen(), ui.first_kb(chat, _private(chat, uid), _is_admin(uid)))
        if target not in GAMES:
            return _err("این لابی دیگر فعال نیست.")
        return h_ready(target, uid, name, "")
    if arg.startswith("join_"):                 # دیپ‌لینک دعوت
        try:
            target = int(arg[5:])
        except ValueError:
            return _ok(ui.first_screen(), ui.first_kb(chat, _private(chat, uid), _is_admin(uid)))
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
    live = _live_game(chat, uid)
    if live is not None:                        # وسط بازی: بازیِ جاری، نه منوی ربات
        return _live_panel(live, uid, _private(chat, uid))
    return _ok(ui.first_screen(_private(chat, uid)), ui.first_kb(chat, _private(chat, uid), _is_admin(uid)))


def _live_game(chat: int, uid: int) -> Optional[int]:
    """بازیِ جاری‌ای که این فراخوانی باید نشانش بدهد (گروه: همان گروه؛ پیوی: میزِ خودِ کاربر)."""
    g = GAMES.get(chat)
    if g and g.s.phase is not Phase.END and (not _private(chat, uid) or uid in g.s.players):
        return chat
    if _private(chat, uid):
        pinned = _ACTIVE_TABLE.get(uid)
        if pinned in GAMES and uid in GAMES[pinned].s.players and GAMES[pinned].s.phase is not Phase.END:
            return pinned
        found = games_of(uid)
        if found:
            return found[-1]
    return None


def _live_panel(game_chat: int, uid: int, private: bool) -> Dict:
    """🎮 بازیِ جاری: فاز، روز، مهلت و دکمه‌ی کارِ بعدی — به‌جای منوی ربات."""
    g = GAMES[game_chat]
    if g.s.phase is Phase.LOBBY:
        return _ok("🎮 *بازیِ جاری — لابی*\n" + ui.lobby_screen(g.s), ui.lobby_kb(game_chat))
    p = g.s.players.get(uid)
    head = f"🎮 *بازیِ جاری*\n{ui.clock_text(g)}\n{ui.DIV}\n"
    if private and p is not None:
        return _ok(head + ui.personal_panel(g, p), ui.personal_kb(g, p), private=True)
    return _ok(head + ui.dashboard(g.s, g.remaining(), g.pending_actors(), g.next_step()),
               ui.live_kb(g.s))


def h_menu(chat, uid, name, arg):
    live = _live_game(chat, uid)
    if live is not None:
        return _live_panel(live, uid, _private(chat, uid))
    return h_fullmenu(chat, uid, name, arg)


def h_fullmenu(chat, uid, name, arg):
    return _ok("🏠 *منوی اصلی*", ui.main_menu(_private(chat, uid), _is_admin(uid)))


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


def _no_private_table(chat, uid):
    """بازی در گروه انجام می‌شود؛ میزِ پیوی برای بقیه نامرئی است (بن‌بست A1)."""
    if _private(chat, uid):
        return _ok("👥 *بازی در گروه انجام می‌شود.*\nربات را به یک گروه اضافه کن و آنجا «🎮 شروع بازی» را بزن؛ "
                   "صبح، رای و حکم باید جلوی چشم همه باشد. نقش و اکشن شبانه‌ات به همین پیوی می‌آید.",
                   ui.add_to_group_kb())
    return None


def _confirm_wipe(chat, uid, arg, cmd):
    """بازیِ در جریان با یک تپ پاک نشود (بن‌بست A3)."""
    g = GAMES.get(chat)
    if g and g.s.phase not in (Phase.LOBBY, Phase.END) and uid == g.owner and arg != "confirm":
        return _ok("⚠️ *یک بازی در جریان است.* اگر ادامه بدهی، این بازی پاک می‌شود و آمارش «رها‌شده» ثبت می‌شود.",
                   ui.kb([[("🗑️ بله، پاکش کن و لابی تازه بساز", f"{cmd}:confirm")],
                          [("↩️ نه، برگرد به بازی", "dashboard")]]))
    return None


def h_new(chat, uid, name, arg):
    stop = _no_private_table(chat, uid) or _confirm_wipe(chat, uid, arg, "new")
    if stop:
        return stop
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


def _host_only(g: Game, uid: int, what: str) -> None:
    if uid and uid != g.owner:
        raise RuleError(f"فقط میزبان می‌تواند {what}.")


def _gate(g: Game, uid: int, step: str) -> None:
    """چه کسی و کِی می‌تواند فاز را جلو ببرد (RULES.md «جریان بازی»).
    uid=0 یعنی خودِ سیستم (تایمر/آزمون) و همیشه مجاز است."""
    if not uid:
        return
    if g.s.paused:
        raise RuleError("بازی متوقف است؛ میزبان اول «▶️ ادامه» را بزند.")
    p = g.s.players.get(uid)
    host = uid == g.owner
    if not host and not (p and p.in_game):
        raise RuleError("فقط میزبان یا بازیکنانِ داخل بازی می‌توانند بازی را جلو ببرند.")
    left = g.remaining() or 0
    full = config.PHASE_SECONDS.get(g.s.phase.value) or 0
    if g.blitz:
        full //= 2
    if host and step in ("closevote", "closejury") and full and left <= full // 2:
        return                                     # میزبان بعد از نیمه‌ی مهلت می‌تواند رای را ببندد (غایبِ دائمی)
    if step == "dawn":
        return                                     # شب را فقط «تصمیمِ همه» یا مهلت + فرصتِ اضافه می‌بندد (advance_night)
    if step in ("dawn", "closevote", "closejury") and g.pending_actors() and left > 0:
        waiting = {"dawn": "همه‌ی نقش‌های شبانه اکشن نداده‌اند",
                   "closevote": "همه رای نداده‌اند (ممتنع هم رای است)",
                   "closejury": "همه‌ی اعضای هیئت منصفه رای نداده‌اند"}[step]
        raise RuleError(f"⏳ هنوز {waiting}؛ {left} ثانیه تا پایان مهلت. "
                        "بعد از آن (یا وقتی همه تمام کردند) دوباره بزن.")
    if step == "vote" and not host and left > 0:
        raise RuleError(f"⏳ گفتگو هنوز {left} ثانیه وقت دارد؛ فقط میزبان می‌تواند زودتر رای‌گیری را باز کند.")


def h_startgame(chat, uid, name, arg):
    g = _g(chat)
    _host_only(g, uid, "بازی را شروع کند")
    asked = "force" in (arg or "").lower()
    case = (arg or "").replace("force", "").strip()
    try:
        g.start(int(case) if case else None, force=asked or not REQUIRE_READY)
    except RuleError as e:
        if "پیوی ربات" not in str(e):
            raise
        res = _err(str(e))                   # دکمه، نه «/startgame force» تایپی
        res["keyboard"] = ui.kb([[("⚡ شروع بدون آن‌ها", "startgame:force")],
                                 [("🔄 دوباره امتحان کن", "startgame")]])
        return res
    db.log_event(chat, uid, "start", g.s.case.title if g.s.case else "")
    for p in g.s.players.values():               # کارت نقش خودکار به پیوی هر نفر
        _post(p.uid, ui.role_card(p.role, p.knows), ui.kb([[("🌙 اکشن شبانه", "act")],
                                                          [("🎯 توانایی‌های من", "abilities")]]))
    return _ok(ui.case_intro(g.s) + "\n\n" + ui.status_board(g.s) +
               f"\n\n🎭 سناریو: {scenario_name(g.scenario)}"
               "\n🔐 نقش هر کس به پیوی‌اش رفت؛ اگر نرسید «🔐 نقش من» را بزن.",
               ui.kb([[("🔐 نقش من", "myrole")], [("🌙 پایان شب", "dawn")], [ui.BACK, ui.HOME]]),
               anim=ui.ANIM["night"], announce=True)


def h_scenario(chat, uid, name, arg):
    """انتخاب سناریو (مجموعه‌ی نقش‌ها) در لابی — فقط میزبان."""
    g = _g(chat)
    if not arg:
        rows = [[(("✅ " if k == g.scenario else "🎭 ") + nm, f"scenario:{k}")]
                for k, (nm, _d, _c) in SCENARIOS.items()]
        body = "\n".join(f"{'✅' if k == g.scenario else '▫️'} *{nm}* — {d}"
                         for k, (nm, d, _c) in SCENARIOS.items())
        return _ok(f"🎭 *سناریوی میز*\n{ui.DIV}\n{body}\n\nمیزبان یکی را انتخاب کند.",
                   ui.kb(rows + [[ui.BACK, ui.HOME]]))
    _host_only(g, uid, "سناریو را عوض کند")
    msg = g.set_scenario(arg)
    return _ok(msg + "\n\n" + ui.lobby_screen(g.s), ui.lobby_kb(chat), edit=True)


def h_myrole(chat, uid, name, arg):
    g, p = _player(chat, uid)
    if not p.role:
        return _err("بازی هنوز شروع نشده؛ نقش‌ها پخش نشده‌اند.")
    return _ok(ui.role_card(p.role, p.knows), ui.role_kb(p), private=True)


# ================= شب / روز =================
def h_act(chat, uid, name, arg):
    """پنل اکشن شبانه: بدون آرگومان = فهرست هدف‌ها با نام؛ با آرگومان = ثبت."""
    g, p = _player(chat, uid)
    if not p.role:      # هنوز نقشی پخش نشده → خطای دوستانه، نه KeyError
        raise RuleError("بازی هنوز شروع نشده؛ نقش‌ها پخش نشده‌اند.")
    if arg:
        res = g.night_action(uid, int(arg))
        tgt = g.s.players[int(arg)].name
        out = _ok(f"✅ ثبت شد — هدف: *{tgt}*\n{res}",
                  ui.action_kb(g.s, p, g.legal_targets(uid), chosen=int(arg)),
                  private=True)
        _dawn_if_all_decided(g, chat)
        return out
    chosen = g.chosen_target(uid)
    ab = g.ability_of(p)
    if ab == "hunter":
        targets = [t for t in g.s.players
                   if t != uid and g.s.players[t].in_game] if p.in_game else []
        chosen = p.hunter_target
    else:
        targets = g.legal_targets(uid)
    passed = g.passed(uid)
    return _ok(ui.action_panel(g.s, p, chosen, ab, targets if g.s.phase in
                               (Phase.NIGHT, Phase.INTERROGATION) and p.free else None, passed=passed),
               ui.action_kb(g.s, p, targets, chosen, passed=passed), private=True)


def h_pass(chat, uid, name, arg):
    """🙅 امشب کاری نمی‌کنم — شب منتظرِ این نفر نمی‌ماند."""
    g, p = _player(chat, uid)
    msg = g.night_pass(uid)
    out = _ok(msg, ui.action_kb(g.s, p, g.legal_targets(uid), passed=True), private=True)
    _dawn_if_all_decided(g, chat)
    return out


def _dawn_if_all_decided(g: Game, chat: int) -> None:
    """آخرین نقش تصمیم گرفت → صبح همین حالا در گروه، بی‌معطلیِ تایمر."""
    if not g.all_decided():
        return
    since = len(g.s.log)
    ev = g.advance_night()
    res = _morning(g, ev["result"], since)
    _post(chat, "🌅 همه‌ی نقش‌ها تصمیمشان را گرفتند؛ شب تمام شد.\n\n" + res["text"], res.get("keyboard"))


def _grace_notice(g: Game, ev: Dict) -> Dict:
    """مهلت شب تمام شد و هنوز کسی تصمیم نگرفته: یادآوری خصوصی + اعلامِ بی‌نام در گروه."""
    for u in ev["pending"]:
        p = g.s.players[u]
        _post(u, f"⏳ *شب منتظرِ توست!* {ev['left']} ثانیه فرصت داری: تصمیمت را بگیر "
                 "(هدف، «🙅 امشب کاری نمی‌کنم» یا برای بازجو «✅ بازجویی تمام شد»).",
              ui.personal_kb(g, p))
    return _ok(f"⏳ مهلت شب تمام شد، ولی هنوز همه‌ی نقش‌ها تصمیم نگرفته‌اند. {ev['left']} ثانیه فرصتِ اضافه؛ "
               "بعد از آن هر کس تصمیم نگرفته «کاری نکرد» حساب می‌شود.",
               ui.dashboard_kb(g.s), announce=True)


def h_night(chat, uid, name, arg):
    """سازگاری با /night <id> — بدون آرگومان همان پنل دکمه‌ای را می‌دهد."""
    return h_act(chat, uid, name, arg)


def _morning(g: Game, r: Dict, since: int = 0) -> Dict:
    """پیام صبح — یکی برای دکمه‌ی «پایان شب» و یکی برای تایمر؛ همیشه کامل.
    since: طول log پیش از حل شب؛ فقط رویدادهای همین شب اعلام می‌شوند."""
    dead = "، ".join(g.s.players[u].name for u in r["killed"]) or "هیچ‌کس"
    ev_line = f"\n🌩️ رویداد شب: {g.s.night_event}" if g.s.night_event else ""
    # بهبود ۵: ردهایی که از اکشن واقعیِ دیشب ساخته شده‌اند
    traces = ("\n\n🔬 *ردهای دیشب:*\n" + "\n".join(f"  • {t}" for t in g.s.traces)) \
        if g.s.traces else ""
    # رویدادهای عمومیِ همین شب؛ «💉 پادزهر» عمداً نه — نجات پزشک را فاش نمی‌کنیم
    wills = [l for l in g.s.log[since:] if l.startswith(("📜 وصیت", "🏹", "☠️", "⚰️", "⛓️", "⛈️"))]
    extra = ("\n\n📣 " + "\n📣 ".join(wills)) if wills else ""
    if g.s.phase is Phase.JURY:
        extra += (f"\n\n⚖️ *بازجو نمی‌تواند حکم بدهد؛ هیئت منصفه درباره‌ی "
                  f"{g.s.players[g.s.suspect_uid].name} تصمیم می‌گیرد.* تبرئه یا ادامه؟")
    txt = (f"☀️ *صبح روز {g.s.day}*{ev_line}\n{ui.DIV}\n⚰️ کشته‌شده: {dead}\n\n"
           + ui.clue_block(r.get("clues", [])) + ui.patrol_block(r.get("patrol", []))
           + traces + extra + "\n\n" + ui.status_board(g.s)
           + f"\n➡️ {g.next_step()}")
    return _ok(txt, ui.morning_kb(g.s, g.officer_can_judge()), anim=ui.ANIM["morning"], announce=True)


def h_dawn(chat, uid, name, arg):
    g = _g(chat)
    _gate(g, uid, "dawn")
    since = len(g.s.log)
    ev = g.advance_night(force=not uid)          # uid=0 = سیستم/آزمون
    if ev["kind"] == "grace":
        return _grace_notice(g, ev)
    return _morning(g, ev["result"], since)


def _discussion_open(g: Game) -> Dict:
    return _ok("💬 *فاز گفتگو باز است.* بحث کنید، اتهام بزنید، دفاع کنید.\n"
               f"➡️ {g.next_step()}",
               ui.kb([[("🗳️ شروع رای‌گیری", "vote")], [ui.BACK, ui.HOME]]), announce=True)


def h_discuss(chat, uid, name, arg):
    g = _g(chat)
    _gate(g, uid, "discuss")
    g.open_discussion()
    return _discussion_open(g)


def _vote_open(g: Game) -> Dict:
    return _ok("🗳️ *رای‌گیری آغاز شد* — چه کسی به بازجویی برود؟\n"
               "(رای دوباره = عوض کردن رای؛ «⏭️ ممتنع» هم رای حساب می‌شود.)",
               ui.vote_kb(g.s), anim=ui.ANIM["vote"], announce=True)


def h_vote(chat, uid, name, arg):
    g = _g(chat)
    _gate(g, uid, "vote")
    g.open_vote()
    return _vote_open(g)


def h_castvote(chat, uid, name, arg):
    g = _g(chat)
    target = int(arg)
    g.vote(uid, target)
    if target == 0:
        return _ok(f"⏭️ رای ممتنع ثبت شد ({len(g.s.votes)} رای).",
                   ui.kb([[("📊 بستن رای‌گیری", "closevote")]]))
    who = "" if g.s.vote_anon else f" — {_name(name, uid)} به {g.s.players[target].name}"
    return _ok(f"✅ رای ثبت شد ({len(g.s.votes)} رای){who}.",
               ui.kb([[("📊 بستن رای‌گیری", "closevote")]]))


def _vote_closed(g: Game, who: Optional[int]) -> Dict:
    if who is None and g.s.phase is Phase.VOTE:        # تساوی → دور دوم (مرگ ناگهانی)
        names = "، ".join(g.s.players[u].name for u in g.s.tie_leaders)
        return _ok(f"⚔️ *تساوی!* دور دوم (مرگ ناگهانی) فقط بین: {names}\n"
                   "دوباره رای بدهید؛ تساوی دوباره یعنی امروز کسی بازداشت نمی‌شود.",
                   ui.vote_kb(g.s), anim=ui.ANIM["vote"], announce=True)
    if who is None:
        if g.s.phase is Phase.END:
            return _ok(f"🏁 {g.s.win_reason}", ui.kb([[("🏁 پایان و افشای نقش‌ها", "end")]]),
                       announce=True)
        return _ok("🤷 کسی بازداشت نشد. شب فرا می‌رسد.",
                   ui.kb([[("🌙 پایان شب", "dawn")], [("📋 داشبورد", "dashboard")]]),
                   anim=ui.ANIM["night"], announce=True)
    p = g.s.players[who]
    return _ok(f"🔦 *{p.name}* به اتاق بازجویی منتقل شد.\n"
               f"بازجو امشب سؤال می‌پرسد (پرسش به خودِ متهم می‌رسد)؛ حکم فردا صبح صادر می‌شود.\n"
               f"متهم در بازداشت از حمله‌ی شبانه در امان است. بقیه اکشن شبانه‌شان را دارند.",
               ui.officer_kb(who), anim=ui.ANIM["interrogation"], announce=True)


def h_closevote(chat, uid, name, arg):
    g = _g(chat)
    _gate(g, uid, "closevote")
    who = g.close_vote()
    if who is not None:
        db.log_event(chat, who, "interrogation", "رای گروه")
    return _vote_closed(g, who)


# ================= بازجویی =================
def h_hints(chat, uid, name, arg):
    g = _g(chat)
    hs = g.officer_hints(uid)
    return _ok("🔦 *سرنخ‌های بازجویی (مبهم و غیرقطعی):*\n" + "\n".join(f"  • {h}" for h in hs),
               _officer_tools(g), private=True)


def _officer_tools(g: Game) -> Dict:
    sus = g.s.suspect_uid
    return ui.kb([[("💬 پرسش بعدی", "ask"), ("🔦 سرنخ‌ها", "hints")],
                  [("✅ بازجویی تمام شد", "pass")],
                  [("🔒 حبس موقت", f"verdict:{sus}:1"), ("🔓 آزادی", f"verdict:{sus}:0")]])


def h_ask(chat, uid, name, arg):
    """بازجویی دونفره: پرسش به پیوی متهم می‌رود و جوابش به پیوی بازجو برمی‌گردد."""
    g = _g(chat)
    if not arg:
        g._officer(uid, "می‌تواند استنطاق کند")     # خطای روشن پیش از گرفتن متن
        if not g.awaiting_verdict():
            raise RuleError("کسی در بازجویی نیست.")
        return _ask_text(chat, uid, "ask")
    arg = _clean(arg) or "؟"
    out = g.ask(uid, arg)
    sus = g.s.players[g.s.suspect_uid]
    _post(sus.uid, f"🔦 *بازجو از تو می‌پرسد:*\n«{_sanitize(arg)}»\n\n"
                   "با دکمه‌ی زیر جواب بده؛ فقط تو و بازجو این گفت‌وگو را می‌بینید.",
          ui.kb([[("🗣️ جواب بده", "answer")]]))
    d = f"\n🛡️ دفاع متهم: «{g.s.defense_text}»" if g.s.defense_text else ""
    return _ok(out + d, _officer_tools(g), private=True)


def h_answer(chat, uid, name, arg):
    """جواب متهم به پرسش بازجو."""
    g, p = _player(chat, uid)
    if not arg:
        if uid not in g.s.questions:
            raise RuleError("پرسشی بی‌جواب برای تو نیست.")
        return _ask_text(chat, uid, "answer")
    arg = _clean(arg) or "…"
    q, clash = g.answer(uid, arg)
    warn = "\n⚠️ *تناقض:* جوابش با دفعه‌ی قبل به همین پرسش فرق دارد!" if clash else ""
    _post(g.s.officer_uid, f"🗣️ *جواب {p.name}* به «{q}»:\n«{_sanitize(arg)}»{warn}", _officer_tools(g))
    return _ok("✅ جوابت به بازجو رسید.", ui.back_only(), private=True)


def _verdict_given(g: Game, msg: str, jailed: bool) -> Dict:
    anim = ui.ANIM["jail"] if jailed else None
    if g.s.phase is Phase.END:
        kb = ui.kb([[("🏁 پایان و افشای نقش‌ها", "end")]])
    else:
        kb = ui.kb([[("💬 گفتگو", "discuss")], [("📋 داشبورد", "dashboard")]])
    return _ok(msg + "\n\n" + ui.status_board(g.s), kb, anim=anim, announce=True)


def h_verdict(chat, uid, name, arg):
    g = _g(chat)
    if ":" in (arg or ""):                  # verdict:<uid>:<x> — دکمه به متهمِ مشخصی بسته است
        who, arg = arg.split(":", 1)
        if int(who) != g.s.suspect_uid:
            raise RuleError("این دکمه مالِ متهمِ قبلی است؛ از پیامِ امروز حکم بده.")
    if arg not in ("0", "1"):
        if not g.awaiting_verdict():
            raise RuleError("کسی در بازجویی نیست.")
        return _ok("⚖️ *حکم تو چیست؟*", menus.verdict_kb(g.s))
    sus = g.s.suspect_uid
    msg = g.officer_verdict(uid, arg == "1")
    db.log_event(chat, sus or 0, "verdict", "حبس موقت" if arg == "1" else "آزادی")
    # شبِ بازجویی قبلاً گذشته؛ روز از همین‌جا ادامه می‌دهد.
    return _verdict_given(g, msg, arg == "1")


def h_clear(chat, uid, name, arg):
    g = _g(chat)
    if not arg:
        return _ok("🕊️ *کدام زندانی را تبرئه می‌کنی؟*",
                   menus.player_kb(g.s, "clear", only_custody=Custody.TEMP_JAIL))
    return _ok(g.clear_previous(uid, int(arg)) + "\n\n" + ui.status_board(g.s), ui.back_only(),
               announce=True)


# ================= هیئت منصفه =================
def _jury_open(g: Game, auto: bool = False) -> Dict:
    sus = g.s.players[g.s.suspect_uid].name
    why = "بازجو حکم نداد/نمی‌تواند بدهد؛ " if auto else ""
    return _ok(f"⚖️ *هیئت منصفه برای {sus} تشکیل شد!* {why}رای بدهید: تبرئه یا ادامه؟\n"
               f"({g.jury_percent()}٪ تبرئه = آزادی)", ui.jury_kb(), announce=True)


def h_jury(chat, uid, name, arg):
    g = _g(chat)
    formed = g.request_jury(uid)
    if not formed:
        return _ok("📝 درخواست هیئت منصفه ثبت شد؛ یک نفر دیگر هم لازم است.", ui.back_only())
    return _jury_open(g)


def h_juryvote(chat, uid, name, arg):
    g = _g(chat)
    g.jury_vote(uid, arg == "1")
    return _ok(f"🗳️ رای هیئت منصفه ثبت شد ({len(g.s.jury_votes)}).",
               ui.kb([[("📊 نتیجه‌ی هیئت", "closejury")]]))


def _jury_closed(g: Game, msg: str) -> Dict:
    return _verdict_given(g, msg, "حبس موقت" in msg)


def h_closejury(chat, uid, name, arg):
    g = _g(chat)
    _gate(g, uid, "closejury")
    return _jury_closed(g, g.close_jury())


# ================= وضعیت / پایان / پروفایل =================
def h_status(chat, uid, name, arg):
    return _ok(ui.status_board(_g(chat).s), ui.back_only())


def h_end(chat, uid, name, arg):
    g = _g(chat)
    if g.s.phase is not Phase.END:
        return _err("بازی هنوز تمام نشده؛ تا آخر بازی معلوم نمی‌شود قاتل کیست.")
    return _ok(g.ending_report(),
               ui.kb([[("🔁 همین ترکیب، دور جدید", "rematch")], [("🎮 بازی جدید", "new")], [ui.HOME]]),
               anim=ui.ANIM["court"], announce=True)


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
    """تایمر همان پیامِ کاملی را می‌سازد که دکمه‌ی همان مرحله می‌ساخت
    (پیام صبح با کشته‌ها و مدرک، کیبورد رای، هیئت منصفه…)."""
    g = _g(chat)
    since = len(g.s.log)
    msg = g.tick()
    if msg is None:
        rem = g.remaining()
        res = _ok(f"{t('timer')}: {rem if rem is not None else '—'} ثانیه | فاز: {g.s.phase.value}",
                  ui.dashboard_kb(g.s), edit=True)
        res["advanced"] = False
        return res
    ev = g.last_event or {}
    kind = ev.get("kind")
    if kind == "grace":
        res = dict(_grace_notice(g, ev))
        res["text"] = f"{msg}\n\n{res['text']}"
        res["advanced"] = True
        return res
    if kind == "dawn":
        res = _morning(g, ev["result"], since)
    elif kind == "vote_open":
        res = _vote_open(g)
    elif kind == "vote_closed":
        res = _vote_closed(g, ev.get("who"))
    elif kind == "jury_open":
        res = _jury_open(g, auto=True)
    elif kind == "discussion":
        res = _discussion_open(g)
    elif kind in ("verdict", "jury_closed"):
        res = _verdict_given(g, ev.get("msg", msg), "حبس موقت" in ev.get("msg", ""))
    else:
        res = _ok(msg + "\n\n" + ui.status_board(g.s), ui.back_only(), announce=True)
    res = dict(res)
    res["text"] = f"{msg}\n\n{res['text']}"
    # advanced=True یعنی فاز واقعاً جلو رفت — آداپتور فقط این را پخش می‌کند.
    res["advanced"] = True
    return res


def gc(now: Optional[float] = None) -> Dict[str, int]:
    """نسخه ۸ (soak): ربات هفته‌ها روشن می‌ماند؛ بدون این، هر بازیِ تمام‌شده، قفل، نرخ‌محدودساز و
    اسنپ‌شات برای همیشه در حافظه و دیسک می‌ماند. صدا زده می‌شود از تایمر (هر چند ثانیه)."""
    now = _time.time() if now is None else now
    gone = []
    for chat, g in list(GAMES.items()):
        s = g.s
        last = getattr(s, "touched", 0) or 0
        ended = getattr(s, "ended_at", 0) or 0
        if s.phase is Phase.END and ended and now - ended > config.ENDED_TTL:
            gone.append(chat)
        elif last and now - last > config.IDLE_TTL and s.phase is not Phase.END:
            if s.phase is not Phase.LOBBY:
                db.record_abandoned(g)          # بازیِ رهاشده در آمار رهاشدگی بماند
            gone.append(chat)
    for chat in gone:
        GAMES.pop(chat, None)
        LAST_ROSTER.pop(chat, None)
        db.drop_snapshot(chat)
    for d, ttl in ((_LAST_CALL, RATE_WINDOW * 20), (_LAST_CB, 60)):
        for k in [k for k, t in d.items() if now - t > ttl]:
            d.pop(k, None)
    for chat in [c for c in _LOCKS if c not in GAMES]:
        lk = _LOCKS[chat]
        if lk.acquire(blocking=False):          # قفلی که کسی نگرفته
            _LOCKS.pop(chat, None)
            lk.release()
    for uid in [u for u, (c, _cmd) in _PENDING.items() if c not in GAMES]:
        _PENDING.pop(uid, None)
    for uid in [u for u, c in _ACTIVE_TABLE.items() if c not in GAMES]:
        _ACTIVE_TABLE.pop(uid, None)
    return {"games_evicted": len(gone), "games": len(GAMES)}


def migrate_chat(old: int, new: int) -> bool:
    """گروه به سوپرگروه تبدیل شد → تلگرام آیدیِ چت را عوض می‌کند؛ بازی نباید یتیم بماند."""
    g = GAMES.pop(old, None)
    if g is None:
        return False
    g.s.chat_id = new
    GAMES[new] = g
    if old in LAST_ROSTER:
        LAST_ROSTER[new] = LAST_ROSTER.pop(old)
    for u, c in list(_ACTIVE_TABLE.items()):
        if c == old:
            _ACTIVE_TABLE[u] = new
    for u, (c, cmd) in list(_PENDING.items()):
        if c == old:
            _PENDING[u] = (new, cmd)
    db.drop_snapshot(old)
    db.save_snapshot(new, g)
    log.info("chat %s migrated to %s", old, new)
    return True


def clock_view(chat: int) -> Optional[Dict]:
    """پیامِ ساعتِ فاز برای گروه: {"key", "text", "keyboard"} — آداپتور برای هر key یک پیام
    می‌فرستد و بعد همان را مدام ویرایش می‌کند. None یعنی ساعتی لازم نیست (لابی/پایان)."""
    g = GAMES.get(chat)
    if g is None or g.s.phase in (Phase.LOBBY, Phase.END):
        return None
    key = f"{g.s.phase.value}:{g.s.day}:{int(g.s.tie_break)}:{int(getattr(g.s, 'grace_day', -1) == g.s.day)}"
    from .l10n import fa_digits, localize_keyboard
    return {"key": key, "text": fa_digits(ui.clock_text(g, detail=True)),
            "keyboard": localize_keyboard(ui.live_kb(g.s))}


def h_dashboard(chat, uid, name, arg):            # ایده ۲۶ + بهبود ۳
    g = _g(chat)
    return _ok(ui.dashboard(g.s, g.remaining(), g.pending_actors(), g.next_step()),
               ui.dashboard_kb(g.s), edit=True)


# ================= ایده‌های ۲/۵/۹ =================
def h_defense(chat, uid, name, arg):
    g = _g(chat)
    if not arg:
        if uid != g.s.suspect_uid:
            raise RuleError("فقط متهمِ داخل بازجویی می‌تواند دفاع کند.")
        return _ask_text(chat, uid, "defense")
    return _ok(g.defense(uid, _clean(arg) or "…"), announce=True)   # «آخرین دفاع» برای کل شهر


def _ask_text(chat, uid, cmd):
    """دکمه زده شد ولی متن لازم است → منتظر پیام بعدیِ همین کاربر می‌مانیم."""
    await_text(uid, chat, cmd)
    return _ok(menus.prompt_text(cmd), menus.prompt_kb(), private=True)


def h_will(chat, uid, name, arg):
    g, p = _player(chat, uid)
    if not p.alive:
        raise RuleError("وصیت را باید پیش از مرگ نوشت.")
    if not arg:
        return _ask_text(chat, uid, "will")
    g.set_will(uid, _clean(arg) or "…")
    return _ok("📜 وصیت‌نامه ثبت شد؛ اگر کشته شوی صبح خوانده می‌شود.",
               menus.commands_menu(), private=True)


def h_note(chat, uid, name, arg):
    g, p = _player(chat, uid)
    if not arg:
        return _ask_text(chat, uid, "note")
    g.add_note(uid, _clean(arg) or "…")
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
        free = [p.uid for p in g.s.players.values() if not p.free]
        return _ok("🚨 *رای اضطراری شهر* — علیه چه کسی؟\n"
                   "فقط در روز؛ با ۸۰٪ رای، مستقیم به حبس موقت می‌رود. فقط یک بار در بازی.",
                   menus.player_kb(g.s, "sos", exclude=(uid, *free)))
    msg = g.sos(uid, int(arg))
    return _ok(msg, ui.back_only(), announce=g.s.sos_used and "تصویب" in msg)


def _in_game(chat, uid):
    g, p = _player(chat, uid)
    if not p.in_game:
        raise RuleError("تو دیگر در بازی نیستی.")
    return g


LAB_EXPRESS_COINS = 30


def h_lab(chat, uid, name, arg):
    """🧪 آزمایشگاه: روزی یک نمونه؛ نتیجه‌ی راست/دروغ برای همه. «⚡ فوری» با سکه یک شب زودتر."""
    g = _in_game(chat, uid)
    _need_case(g)
    arg = (arg or "").upper()
    if not arg:
        return _ok("🧪 *کدام سرنخ به آزمایشگاه برود؟*\nروزی یک نمونه؛ نتیجه (✅ راست / ❌ دروغ) برای همه اعلام می‌شود.",
                   menus.evidence_kb(g.s, "lab"))
    code, _, mode = arg.partition(":")
    if not mode:
        g.clue(code)
        return _ok(f"🧪 سرنخ {code} — عادی یا فوری؟\n⚡ فوری {LAB_EXPRESS_COINS} 🪙 از سکه‌های پروفایلت می‌گیرد "
                   f"(موجودی: {db.coins_of(uid)} 🪙).",
                   ui.kb([[("🧪 عادی", f"lab:{code}:N"), (f"⚡ فوری ({LAB_EXPRESS_COINS}🪙)", f"lab:{code}:X")],
                          [("🗂️ پرونده", "board")], [ui.BACK, ui.HOME]]))
    express = mode == "X"
    if express and not db.spend_coins(uid, LAB_EXPRESS_COINS):
        raise RuleError(f"سکه کافی نیست ({LAB_EXPRESS_COINS} 🪙 لازم است؛ با بازی کردن سکه جمع کن).")
    try:
        msg = g.submit_lab(code, express=express)
    except RuleError:
        if express:
            db.spend_coins(uid, -LAB_EXPRESS_COINS)     # پول برمی‌گردد
        raise
    return _ok(msg, ui.kb([[("🗂️ پرونده", "board")], [ui.BACK, ui.HOME]]), announce=True)


def h_interp(chat, uid, name, arg):               # 👍👎 «باورش داری؟»
    g = _in_game(chat, uid)
    _need_case(g)
    arg = (arg or "").upper()
    if not arg:
        return _ok("👍👎 *کدام سرنخ؟* باورت را ثبت کن؛ وقتی تکلیفش روشن شد، درست‌گوها XP می‌گیرند.",
                   menus.evidence_kb(g.s, "interp"))
    if ":" not in arg:
        c = g.clue(arg)
        from .clues import matches
        who = "، ".join(p.name for p in g.s.alive_players() if matches(p, c)) or "هیچ‌کسِ زنده"
        return _ok(ui.clue_line(c) + f"\n↳ جور با: {who}\n\nراست است یا کاشته؟", menus.interp_kb(c))
    code, idx = arg.split(":", 1)
    return _ok(g.vote_interp(uid, code, int(idx)), menus.evidence_kb(g.s, "interp"))


def h_expose(chat, uid, name, arg):
    g = _in_game(chat, uid)
    if not arg:
        _need_case(g)
        return _ok("🔍 *کدام سرنخ را راستی‌آزمایی کنم؟*\nاین کار اکشن شبانه‌ات را خرج می‌کند؛ نتیجه فقط به تو.",
                   menus.evidence_kb(g.s, "expose"), private=True)
    code = arg.upper()
    out = _ok(f"🔍 سرنخ {code}: {g.expose(uid, code)}",
              menus.evidence_kb(g.s, "expose"), private=True)
    _dawn_if_all_decided(g, chat)            # راستی‌آزمایی هم «تصمیمِ امشب» است
    return out


def h_board(chat, uid, name, arg):
    """🗂️ پرونده: همه‌ی سرنخ‌ها، مظنونان و «جور بودن» — عمومی."""
    g = _g(chat)
    _need_case(g)
    return _ok(ui.board(g.s), ui.kb([[("🧪 آزمایشگاه", "lab"), ("👍👎 باورش داری؟", "interp")],
                                     [("📋 داشبورد", "dashboard")], [ui.BACK, ui.HOME]]))


# ================= ایده‌های ۱۵/۱۶/۱۸/۱۹/۲۰/۲۵ =================
def h_top(chat, uid, name, arg):
    rows = db.q_top()
    body = "\n".join(f"  {i+1}. {r['name']} — ⭐{r['xp']} ({r['wins']}/{r['games']})"
                     for i, r in enumerate(rows)) or "  —"
    return _ok(f"🏆 *برترین‌ها*\n{ui.DIV}\n{body}", ui.back_only())


def h_league(chat, uid, name, arg):
    rows = db.q_league()
    body = "\n".join(f"  {['🥇', '🥈', '🥉'][i] if i < 3 else f'{i+1}.'} گروهِ {r['host'] or 'بی‌نام'} — 👥{r['n']} — ⭐{r['sx']}"
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
    return _ok(f"🗳️ حالت رای‌گیری: {mode}", ui.dashboard_kb(g.s))


def h_rematch(chat, uid, name, arg):              # ایده ۲۴
    roster = LAST_ROSTER.get(chat)
    if not roster:
        raise RuleError("بازی قبلی‌ای برای تکرار نیست.")
    _guard_replace(chat, uid)
    old = GAMES.get(chat)
    scen = old.scenario if old else "classic"
    GAMES[chat] = Game(chat, seed=chat + len(roster), owner=roster[0][0], scenario=scen)
    for u, n in roster:
        GAMES[chat].join(u, n)
    return _ok("🔁 *دور جدید با همان ترکیب!*\n\n" + ui.lobby_screen(GAMES[chat].s),
               ui.lobby_kb(chat))


def h_rolecard(chat, uid, name, arg):             # ایده ۲۷: کارت PNG
    g, p = _player(chat, uid)
    if not p.role:
        raise RuleError("بازی هنوز شروع نشده.")
    path = cards.render_role_card(p.role, p.name)
    res = _ok(ui.role_card(p.role, p.knows), ui.role_kb(p), private=True)
    res["photo"] = path
    return res


def h_tutorial(chat, uid, name, arg):             # ایده ۲۸
    return _ok(ui.tutorial_text(), ui.kb([[("📖 قوانین کامل", "help")], [ui.BACK, ui.HOME]]))


def h_blitz(chat, uid, name, arg):                # ایده ۳: لابی سریع
    stop = _no_private_table(chat, uid) or _confirm_wipe(chat, uid, arg, "blitz")
    if stop:
        return stop
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
    g, p = _player(chat, uid)
    if p.role != "شکارچی":
        raise RuleError("فقط شکارچی می‌تواند هدف شلیک آخر بگذارد.")
    if not arg:                                   # دکمه‌ی منو → همان پنل انتخاب هدف
        return h_act(chat, uid, name, "")
    return _ok(g.set_hunter(uid, int(arg)),
               ui.action_kb(g.s, p, [u for u in g.s.players if u != uid and g.s.players[u].in_game],
                            chosen=int(arg)), private=True)


def _need_case(g):
    if not g.s.case:
        raise RuleError("بازی هنوز شروع نشده؛ مدرکی وجود ندارد.")


# ================= همه‌ی فرمان‌ها = دکمه =================
def h_commands(chat, uid, name, arg):
    return _ok(menus.commands_screen(), menus.commands_menu(_is_admin(uid)))


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
    "start": h_start, "menu": h_menu, "back": h_menu, "fullmenu": h_fullmenu, "pass": h_pass,
    "new": h_new,
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
    "missions": h_missions, "achv": h_achv,
    "spectate": h_spectate, "voteanon": h_voteanon, "rematch": h_rematch,
    "rolecard": h_rolecard, "tutorial": h_tutorial, "blitz": h_blitz,
    "hunter": h_hunter, "table": h_table, "act": h_act,
    "ready": h_ready, "remind": h_remind, "pause": h_pause,
    "commands": h_commands, "group": h_group, "roleinfo": h_roleinfo,
    "abilities": h_abilities, "cancel": h_cancel,
    "resume": h_resume, "host": h_host, "balance": h_balance,
    # نسخه ۴
    "scenario": h_scenario, "answer": h_answer, "board": h_board,
}

# دستورهایی که به BotFather معرفی می‌شوند (زیرمجموعه‌ی امن برای منوی دستورها)
COMMANDS = ["start", "menu", "new", "join", "startgame", "scenario", "myrole", "act",
            "dashboard", "status", "table", "notes", "help", "roles",
            "ready", "remind", "pause", "resume", "host",
            "share", "admin"]
ENDPOINTS = sorted(_ROUTES)
