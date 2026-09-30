"""ایده ۲۷: کارت نقش تصویری (PNG) با Pillow — رنگ تیم + متن فارسیِ درست.

نسخه ۵: فونت پیش‌فرض Pillow حروف فارسی ندارد و همه‌چیز «جعبه» می‌شد. حالا:
  • یک فونتِ دارای حروف فارسی پیدا می‌شود (assets/fonts، ویندوز: Tahoma/Arial/Segoe UI، لینوکس: DejaVu/Noto/Vazirmatn)
  • متن با arabic-reshaper به هم چسبانده و با python-bidi راست‌به‌چپ چیده می‌شود
  • ایموجی (که هیچ فونتی رنگی‌اش نمی‌کشد) جایش را به نشانِ رنگیِ تیم می‌دهد
"""
from __future__ import annotations
import os
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .models import Align
from .roles import ROLES

TEAM_COLOR = {
    Align.CITY: (46, 96, 160),      # آبی شهر
    Align.KILLER: (150, 32, 32),    # سرخ قاتل
    Align.NEUTRAL: (120, 90, 30),   # طلایی خنثی
}
TEAM_BADGE = {Align.CITY: "شهر", Align.KILLER: "قاتل‌ها", Align.NEUTRAL: "خنثی"}

_ROOT = Path(__file__).resolve().parent.parent
FONT_CANDIDATES = [
    _ROOT / "assets" / "fonts" / "Vazirmatn-Regular.ttf",
    Path("C:/Windows/Fonts/tahoma.ttf"), Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
    Path("/usr/share/fonts/truetype/vazirmatn/Vazirmatn-Regular.ttf"),
    Path("/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"), Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
]


def find_font() -> Optional[str]:
    for f in FONT_CANDIDATES:
        if f.exists():
            return str(f)
    return None


def _has_raqm() -> bool:
    try:
        from PIL import features
        return bool(features.check("raqm"))
    except Exception:
        return False


RAQM = _has_raqm()


def rtl(text: str) -> str:
    """اگر Pillow با libraqm ساخته شده، خودش حروف را می‌چسباند و راست‌به‌چپ می‌چیند (با direction=rtl)؛
    وگرنه با arabic-reshaper + python-bidi آماده‌اش می‌کنیم."""
    if RAQM:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except ImportError:                       # بدون کتابخانه: دست‌کم حروف دیده می‌شوند
        return text[::-1]


def _font(path: Optional[str], size: int):
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size=size)


def render_role_card(role: str, player_name: str, out_dir: str | None = None) -> str:
    """کارت PNG می‌سازد و مسیر فایل را برمی‌گرداند."""
    r = ROLES[role]
    W, H = 640, 360
    bg = TEAM_COLOR[r.align]
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    path = find_font()
    big, mid, small = _font(path, 56), _font(path, 30), _font(path, 34)
    # قاب، نوار پایین و نشانِ رنگیِ تیم (به‌جای ایموجی)
    d.rectangle([12, 12, W - 12, H - 12], outline=(255, 255, 255), width=4)
    d.rectangle([12, H - 90, W - 12, H - 12], fill=(0, 0, 0))
    d.ellipse([W - 130, 36, W - 40, 126], fill=(255, 255, 255))
    d.ellipse([W - 118, 48, W - 52, 114], fill=bg)
    # متن راست‌چین
    kw = {"direction": "rtl", "language": "fa"} if RAQM else {}

    def right(y, text, font, fill, x_end=W - 150):
        t = rtl(text)
        w = d.textlength(t, font=font, **kw)
        d.text((x_end - w, y), t, font=font, fill=fill, **kw)
    right(40, role, big, (255, 255, 255))
    right(120, "تیم: " + TEAM_BADGE[r.align], mid, (230, 230, 230))
    right(170, "کارآگاه — کارت محرمانه", mid, (210, 210, 210))
    right(H - 72, player_name[:24], small, (255, 215, 0), x_end=W - 40)
    out_dir = out_dir or tempfile.gettempdir()
    out = os.path.join(out_dir, f"rolecard_{abs(hash((role, player_name))) % 10**8}.png")
    img.save(out, "PNG")
    return out
