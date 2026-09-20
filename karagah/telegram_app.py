"""آداپتور تلگرام — توکن از متغیر محیطی BOT_TOKEN خوانده می‌شود (هرگز داخل کد ننویس).

اجرا:
    pip install python-telegram-bot python-dotenv
    export BOT_TOKEN="123456:AA..."     # یا در فایل .env
    python -m karagah.telegram_app       # یا: python run.py
"""
from __future__ import annotations
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
                r.append(InlineKeyboardButton(b["text"], callback_data=b["callback_data"]))
        rows.append(r)
    return InlineKeyboardMarkup(rows)


async def _send_photo_or_voice(update: Update, res: dict):
    """ایده ۲۷/۲۹: اگر پاسخ photo دارد یا انیمیشن فاز فایل صوتی دارد، بفرست."""
    bot = update.get_bot()
    chat = update.effective_user.id if res.get("private") else update.effective_chat.id
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
                            await bot.send_voice(update.effective_chat.id, f)
                    except Exception as e:
                        log.warning("voice failed: %s", e)
                break


async def _reply(update: Update, res: dict):
    """هرگز بی‌صدا نماند: اگر Markdown یا پیوی خطا داد، ساده و در همان چت بفرست.
    اگر res["edit"] و پیام callback داریم → همان پیام ویرایش می‌شود (چت شلوغ نمی‌شود)."""
    kb = _kb(res.get("keyboard"))
    bot = update.get_bot()
    q = update.callback_query
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
    return handle(cmd, target, uid, update.effective_user.first_name or "", arg)


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
    arg = ""
    if ":" in data:                       # اکشن پارامتری: vote:5 ، ver:5:1 ، ask:5
        head, rest = data.split(":", 1)
        cmd = CB_MAP.get(head, head)
        arg = rest.split(":")[-1] if head == "ver" else rest
    else:                                 # دکمه‌ی ساده = نام اندپوینت (بدون نگاشت)
        cmd = data
    res = _dispatch(update, cmd, arg)
    await _reply(update, res)
    await _send_photo_or_voice(update, res)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """متن ساده فقط وقتی معنا دارد که ربات منتظر آن باشد (یادداشت/وصیت/پرسش/دفاع).
    وگرنه کاربر را به تابلوی دکمه‌ها می‌بریم تا مجبور به تایپ دستور نشود."""
    uid = update.effective_user.id
    pending = take_pending(uid)
    text = (update.effective_message.text or "").strip()
    if pending and text:
        chat, cmd = pending
        res = handle(cmd, chat, uid, update.effective_user.first_name or "", text)
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
                await ctx.bot.send_message(chat, res["text"])
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
