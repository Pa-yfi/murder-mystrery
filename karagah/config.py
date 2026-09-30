"""تنظیمات مرکزی پروژه — همه‌ی ماژول‌ها از اینجا کانفیگ می‌شوند."""
from __future__ import annotations
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

project_root = Path(__file__).resolve().parent.parent   # ریشه‌ی مخزن، یک پله بالاتر از بسته
env_path = project_root / ".env"

if load_dotenv is not None:
    load_dotenv(env_path, override=True)
    if not os.environ.get("BOT_TOKEN"):
        load_dotenv(override=True)

# --- تلگرام ---
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "KaragahBot")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x]

# --- قواعد بازی (قابل تنظیم بدون دست‌زدن به موتور) ---
MIN_PLAYERS = int(os.getenv("MIN_PLAYERS", 4))
MAX_PLAYERS = int(os.getenv("MAX_PLAYERS", 10))
INTERROGATION_NIGHTS = int(os.getenv("INTERROGATION_NIGHTS", 1))   # 🔦 بازجویی
TEMP_JAIL_NIGHTS = int(os.getenv("TEMP_JAIL_NIGHTS", 2))           # 🔒 حبس موقت
JURY_ACQUIT_PERCENT = int(os.getenv("JURY_ACQUIT_PERCENT", 60))    # ⚖️ درصد تبرئه
JURY_MIN_REQUESTS = int(os.getenv("JURY_MIN_REQUESTS", 2))         # وکیل = ۱
REVEAL_ROLE_ON_LIFE_JAIL = False   # ⛓️ هرگز؛ تا پایان بازی نقش فاش نمی‌شود

# --- تایمر فازها (ثانیه) — ایده ۱ ---
PHASE_SECONDS = {
    "شب": int(os.getenv("NIGHT_SECONDS", 60)),
    "گفتگو": int(os.getenv("DISCUSS_SECONDS", 180)),
    "رای‌گیری": int(os.getenv("VOTE_SECONDS", 90)),
    "اتاق بازجویی": int(os.getenv("NIGHT_SECONDS", 60)),   # شبِ بازجویی
    # نسخه ۴: صبح و هیئت منصفه هم مهلت دارند؛ میزِ بی‌میزبان دیگر گیر نمی‌کند
    "صبح": int(os.getenv("MORNING_SECONDS", 90)),
    "هیئت منصفه": int(os.getenv("JURY_SECONDS", 60)),
}
# مهلتِ شب تمام شد ولی نقشی هنوز تصمیم نگرفته → یک بار این‌قدر فرصتِ اضافه + یادآوری به پیوی‌اش
NIGHT_GRACE_SECONDS = int(os.getenv("NIGHT_GRACE_SECONDS", 30))
MAX_DAYS = int(os.getenv("MAX_DAYS", 20))
# نگه‌داری طولانی: میزِ تمام‌شده بعد از این‌قدر ثانیه از حافظه و اسنپ‌شات پاک می‌شود (افشا تا آن وقت در دسترس)،
# لابیِ بی‌فعالیت و بازیِ رهاشده هم بعد از IDLE_TTL.
ENDED_TTL = int(os.getenv("ENDED_TTL", 6 * 3600))
IDLE_TTL = int(os.getenv("IDLE_TTL", 24 * 3600))                  # سقف روز؛ بعدش «بن‌بست» (بدون برنده)
DEFENSE_SECONDS = int(os.getenv("DEFENSE_SECONDS", 30))    # ایده ۲
VOICE_DIR = os.getenv("VOICE_DIR", "assets/voice")         # ایده ۲۹
LANG = os.getenv("LANG_UI", "fa")                          # ایده ۳۰

# --- ذخیره‌سازی ---
DB_URL = os.getenv("DB_URL", "")   # خالی = حافظه (فاز ۱)
