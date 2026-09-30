"""آداپتور تلگرام — توکن از متغیر محیطی BOT_TOKEN خوانده می‌شود (هرگز داخل کد ننویس).

اجرا:
    pip install python-telegram-bot python-dotenv
    export BOT_TOKEN="123456:AA..."     # یا در فایل .env
    python -m karagah.telegram_app       # یا: python run.py
"""
from __future__ import annotations
import asyncio
import logging
import os
import os.path as osp

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.error import InvalidToken
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                          MessageHandler, ContextTypes, filters)

try:
    from . import bot as botmod
    from .bot import (handle, ENDPOINTS, COMMANDS, restore_games,
                      is_dup_callback, route_chat, take_pending)
    from .config import BOT_TOKEN as CONFIG_BOT_TOKEN
except ImportError:
    import bot as botmod
    from bot import (handle, ENDPOINTS, COMMANDS, restore_games,
                     is_dup_callback, route_chat, take_pending)
    from config import BOT_TOKEN as CONFIG_BOT_TOKEN

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("karagah.telegram")

TOKEN = CONFIG_BOT_TOKEN

# نگاشت callback_data کوتاه → اندپوینت
CB_MAP = {"vote": "castvote", "ver": "verdict", "jury": "juryvote", "ask": "ask"}


def parse_callback(data: str):
    """callback_data → (اندپوینت، آرگومان). بازیکن‌های شبیه‌سازی (playtest) هم
    از همین تابع رد می‌شوند تا دکمه‌ها دقیقاً مثل تلگرام واقعی تفسیر شوند."""
    if ":" in data:                       # اکشن پارامتری: vote:5 ، ver:5:1 ، ask:5
        head, rest = data.split(":", 1)
        # ver:<متهم>:<حکم> کامل به h_verdict می‌رسد تا دکمه‌ی کهنه روی متهمِ تازه اجرا نشود
        return CB_MAP.get(head, head), rest
    return data, ""                       # دکمه‌ی ساده = نام اندپوینت (بدون نگاشت)


def _kb(k):
    if not k:
        return None
    rows = []
    for row in k["inline_keyboard"]:
        r = []
        for b in row:
            if "url" in b:
                r.append(InlineKeyboardButton(b["text"], url=b["url"]))
            else:
                # style: danger 🔴 / success 🟢 / primary 🔵 (Bot API ≥ 9.4؛ کلاینت قدیمی نادیده می‌گیرد)
                r.append(InlineKeyboardButton(b["text"], callback_data=b["callback_data"],
                                              style=b.get("style")))
        rows.append(r)
    return InlineKeyboardMarkup(rows)


async def _send_photo_or_voice(update: Update, res: dict):
    """ایده ۲۷/۲۹: اگر پاسخ photo دارد یا انیمیشن فاز فایل صوتی دارد، بفرست."""
    bot = update.get_bot()
    chat = update.effective_user.id if res.get("private") else update.effective_chat.id
    # صدای فازِ یک اعلام عمومی همراه خودِ اعلام به گروه می‌رود
    voice_chat = res.get("_target") if res.get("announce") and res.get("_target") \
        else update.effective_chat.id
    if res.get("photo") and osp.exists(res["photo"]):
        try:
            with open(res["photo"], "rb") as f:
                await bot.send_photo(chat, f, caption="🔐 کارت نقش تو")
        except Exception as e:
            log.warning("photo failed: %s", e)
    anim = res.get("anim")
    if anim:
        try:
            from .config import VOICE_DIR
            from .ui import ANIM, VOICE
        except ImportError:
            from config import VOICE_DIR
            from ui import ANIM, VOICE
        for key, frames in ANIM.items():
            if frames is anim and key in VOICE:
                vp = osp.join(VOICE_DIR, VOICE[key])
                if osp.exists(vp):
                    try:
                        with open(vp, "rb") as f:
                            await bot.send_voice(voice_chat, f)
                    except Exception as e:
                        log.warning("voice failed: %s", e)
                break


async def _send(bot, dest: int, text: str, keyboard=None) -> bool:
    """Markdown، و اگر خراب شد متن ساده. True یعنی رسید."""
    kb = _kb(keyboard)
    for pm in ("Markdown", None):
        try:
            if pm:
                await bot.send_message(dest, text, parse_mode=pm, reply_markup=kb)
            else:
                await bot.send_message(dest, text, reply_markup=kb)
            return True
        except Exception as e:
            log.warning("send to %s failed (%s): %s", dest, pm or "plain", e)
    return False


async def _flush_outbox(bot, res: dict) -> None:
    """پیام‌هایی که هندلر برای دیگران گذاشته (پرسش بازجو به متهم، نتیجه‌ی شب، کارت نقش)."""
    for m in res.get("outbox") or []:
        await _send(bot, m["chat"], m["text"], m.get("keyboard"))


ANIM_DELAY = 0.6        # ثانیه بین فریم‌های ایموجیِ متحرک


async def _animate(bot, chat: int, frames) -> None:
    """ایموجیِ متحرک: یک پیام کوتاه که چند فریم عوض می‌شود (🌆→🌃→🌌→🔪) و بعد پاک می‌شود."""
    if not frames or not chat:
        return
    try:
        msg = await bot.send_message(chat, frames[0])
        for f in frames[1:]:
            await asyncio.sleep(ANIM_DELAY)
            await msg.edit_text(f)
        await asyncio.sleep(ANIM_DELAY)
        await msg.delete()
    except Exception as e:                        # انیمیشن تزئین است؛ هرگز جلوی پیام اصلی را نگیرد
        log.debug("animation skipped: %s", e)


async def _reply(update: Update, res: dict):
    if res.get("anim") and not res.get("private"):
        dest = res.get("_target") if res.get("announce") and res.get("_target") else update.effective_chat.id
        await _animate(update.get_bot(), dest, res["anim"])
    await _deliver(update, res)
    await _flush_outbox(update.get_bot(), res)


async def _deliver(update: Update, res: dict):
    """هرگز بی‌صدا نماند: اگر Markdown یا پیوی خطا داد، ساده و در همان چت بفرست.
    اگر res["edit"] و پیام callback داریم → همان پیام ویرایش می‌شود (چت شلوغ نمی‌شود).
    اعلامِ عمومیِ بازی (announce) که از پیوی زده شده، به گروهِ بازی می‌رود نه همان پیوی."""
    kb = _kb(res.get("keyboard"))
    bot = update.get_bot()
    q = update.callback_query
    target = res.get("_target")
    here = update.effective_chat.id
    if res.get("announce") and target and target != here and not res.get("private"):
        if await _send(bot, target, res["text"], res.get("keyboard")):
            await _send(bot, here, "📣 در گروهِ بازی اعلام شد.")
            return
    if res.get("edit") and q and q.message and not res.get("private"):
        for pm in ("Markdown", None):
            try:
                await q.edit_message_text(res["text"], parse_mode=pm, reply_markup=kb)
                return
            except Exception as e:
                if "not modified" in str(e).lower():
                    return                      # همان محتوا؛ ویرایش لازم نیست
        # اگر ویرایش نشد (پیام پاک شده و ...) → به ارسال عادی برگرد
    private = bool(res.get("private"))
    dest = update.effective_user.id if private else update.effective_chat.id
    for attempt in ("md", "plain"):
        try:
            if attempt == "md":
                await bot.send_message(dest, res["text"], parse_mode="Markdown", reply_markup=kb)
            else:
                await bot.send_message(dest, res["text"], reply_markup=kb)
            return
        except Exception as e:
            log.warning("send failed (%s): %s", attempt, e)
    # پیوی شکست خورد. متن محرمانه (نقش/سرنخ) هرگز نباید در گروه بیفتد —
    # فقط یک تذکر بی‌محتوا می‌فرستیم.
    if private:
        try:
            await bot.send_message(
                update.effective_chat.id,
                "⚠️ نتوانستم پیام خصوصی‌ات را بفرستم. اول در پیوی ربات را /start کن، بعد دوباره امتحان کن.")
        except Exception as e:
            log.warning("private notice failed: %s", e)
        return
    log.error("delivery failed for chat %s", update.effective_chat.id)


AMBIGUOUS = ("🎲 در چند بازی هستی. اول با /table میز فعالت را انتخاب کن.")


def _dispatch(update: Update, cmd: str, arg: str) -> dict:
    """در پیوی، chat_id بازی گروه نیست — اول میز کاربر را پیدا کن."""
    chat = update.effective_chat.id
    uid = update.effective_user.id
    private = update.effective_chat.type == "private"
    target = route_chat(cmd, chat, uid, private)
    if not target:
        return {"ok": False, "text": AMBIGUOUS, "keyboard": None,
                "private": True, "edit": False}
    res = handle(cmd, target, uid, update.effective_user.first_name or "", arg)
    res["_target"] = target            # اعلامِ عمومی به همین چتِ بازی می‌رود
    return res


def make_cmd(name: str):
    async def h(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        arg = " ".join(ctx.args) if ctx.args else ""
        res = _dispatch(update, name, arg)
        await _reply(update, res)
        await _send_photo_or_voice(update, res)
    return h


async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()          # همیشه چرخ لودینگ تلگرام را قطع کن
    except Exception:
        pass
    data = q.data or "menu"
    if is_dup_callback(q.message.chat_id if q.message else 0, q.from_user.id, data):
        return                                 # ایده ۲: تپ تکراری نادیده
    cmd, arg = parse_callback(data)
    res = _dispatch(update, cmd, arg)
    await _reply(update, res)
    await _send_photo_or_voice(update, res)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """متن ساده فقط وقتی معنا دارد که ربات منتظر آن باشد (یادداشت/وصیت/پرسش/دفاع).
    وگرنه کاربر را به تابلوی دکمه‌ها می‌بریم تا مجبور به تایپ دستور نشود."""
    uid = update.effective_user.id
    private = update.effective_chat.type == "private"
    text = (update.effective_message.text or "").strip()
    if not private and not botmod._PENDING.get(uid):
        return        # گفتگوی عادیِ گروه مالِ بازیکن‌هاست؛ ربات وسط بحث منو نمی‌فرستد
    pending = take_pending(uid)
    if pending and text:
        chat, cmd = pending
        res = handle(cmd, chat, uid, update.effective_user.first_name or "", text)
        res["_target"] = chat
    else:
        res = _dispatch(update, "commands", "")
    await _reply(update, res)


async def on_unknown(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """هر متن/دستور ناشناخته → منوی اصلی، نه سکوت."""
    res = _dispatch(update, "menu", "")
    await _reply(update, res)


async def _post_init(app):
    n = restore_games()
    if n:
        log.info("♻️ %d بازی ناتمام بازیابی شد.", n)
    await app.bot.set_my_commands([BotCommand(c, c) for c in COMMANDS])
    log.info("دستورها ثبت شد: %s", ", ".join(COMMANDS))


async def _timer_job(ctx: ContextTypes.DEFAULT_TYPE):
    """ایده ۱: هر ۱۵ ثانیه، فازهای منقضی‌شده را خودکار جلو می‌برد.

    از handle() رد می‌شود، نه مستقیم از موتور — وگرنه قفل چت، ذخیره‌ی
    اسنپ‌شات و ثبت نتیجه‌ی پایان بازی دور زده می‌شود.
    """
    from .bot import GAMES
    for chat in list(GAMES):
        try:
            res = handle("tick", chat)
            if res.get("advanced"):
                # همان پیام کاملِ دکمه‌ها: کشته‌ها و مدرک صبح، کیبورد رای، هیئت منصفه…
                await _send(ctx.bot, chat, res["text"], res.get("keyboard"))
            await _flush_outbox(ctx.bot, res)
        except Exception as e:
            log.warning("timer tick %s: %s", chat, e)


def main():
    botmod.RATE_LIMIT_ENABLED = True          # ایده ۹: ضد اسپم فقط در محیط واقعی
    botmod.REQUIRE_READY = True               # بهبود ۲: بدون پیویِ باز، بازی شروع نشود
    if not TOKEN or TOKEN == "your_telegram_bot_token_here":
        raise SystemExit("⛔ BOT_TOKEN تنظیم نشده یا هنوز مقدار نمونه را دارد. در فایل .env توکن واقعی BotFather را جایگزین کن.")
    app = ApplicationBuilder().token(TOKEN).post_init(_post_init).concurrent_updates(True).build()
    for name in ENDPOINTS:
        app.add_handler(CommandHandler(name, make_cmd(name)))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.COMMAND, on_unknown))   # /هرچیزِ نامعلوم → منو
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    if app.job_queue:
        app.job_queue.run_repeating(_timer_job, interval=15, first=15)
    else:
        # بی‌صدا رد نشو: بدون job-queue، مهلت فازها هرگز خودکار جلو نمی‌رود.
        log.warning("⚠️ JobQueue نصب نیست → تایمر خودکار فازها کار نمی‌کند. "
                    'نصب کن: pip install "python-telegram-bot[job-queue]"')
    log.info("🕵️ ربات کارآگاه بالا آمد.")
    try:
        app.run_polling(drop_pending_updates=True)
    except InvalidToken:
        raise SystemExit("⛔ توکن تلگرام نامعتبر است. در فایل .env مقدار BOT_TOKEN را با توکن واقعی جایگزین کن.")


if __name__ == "__main__":
    main()
