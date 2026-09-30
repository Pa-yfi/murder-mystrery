"""ایده ۲۷: کارت نقش تصویری (PNG) با Pillow — رنگ تیم + ایموجی + متن فارسی ساده."""
from __future__ import annotations
import os
import tempfile
from PIL import Image, ImageDraw

from .models import Align
from .roles import ROLES

TEAM_COLOR = {
    Align.CITY: (46, 96, 160),      # آبی شهر
    Align.KILLER: (150, 32, 32),    # سرخ قاتل
    Align.NEUTRAL: (120, 90, 30),   # طلایی خنثی
}


def render_role_card(role: str, player_name: str, out_dir: str | None = None) -> str:
    """کارت PNG می‌سازد و مسیر فایل را برمی‌گرداند."""
    r = ROLES[role]
    W, H = 640, 360
    bg = TEAM_COLOR[r.align]
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    # قاب و نوار
    d.rectangle([12, 12, W - 12, H - 12], outline=(255, 255, 255), width=4)
    d.rectangle([12, H - 90, W - 12, H - 12], fill=(0, 0, 0))
    # متن (فونت پیش‌فرض؛ نام نقش/تیم لاتین‌سازی نمی‌شود — تلگرام caption فارسی کامل دارد)
    d.text((30, 30), r.emoji, font_size=96)
    d.text((30, 150), role, fill=(255, 255, 255), font_size=48)
    d.text((30, 215), r.align.value, fill=(230, 230, 230), font_size=30)
    d.text((30, H - 72), player_name[:24], fill=(255, 215, 0), font_size=34)
    out_dir = out_dir or tempfile.gettempdir()
    path = os.path.join(out_dir, f"rolecard_{abs(hash((role, player_name))) % 10**8}.png")
    img.save(path, "PNG")
    return path
