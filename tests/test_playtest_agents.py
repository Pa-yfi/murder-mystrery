"""playtest: بازیکن‌های شبیه‌سازی از کمینه تا بیشینه، فقط با دکمه.

این تست یافته‌های باگ را «قبول» نمی‌کند و رد هم نمی‌کند — آن‌ها در گزارش‌اند.
فقط تضمین می‌کند خودِ agentها سالم‌اند: مستندات را می‌خوانند، هر میز از لابی
تا افشای نقش‌ها با دکمه جلو می‌رود و داور توانایی‌ها را واقعاً می‌سنجد.
"""
import pytest

from karagah import bot, config, engine
from karagah.bot import GAMES
from playtest.docs import read_all
from playtest.game import run_session
from playtest.probes import run_probes
from playtest.report import Report


@pytest.fixture(autouse=True)
def restore():
    time_mods = (bot._time, engine._time)
    yield
    bot._time, engine._time = time_mods
    bot.RATE_LIMIT_ENABLED = False
    bot.REQUIRE_READY = False
    GAMES.clear()


def test_agents_read_every_markdown_first():
    rb = read_all()
    assert "README.md" in rb.files and "PLAN.md" in rb.files
    assert not any(p.startswith(".") for p in rb.files)


@pytest.mark.parametrize("n", range(config.MIN_PLAYERS, config.MAX_PLAYERS + 1))
def test_every_table_size_plays_to_the_end_with_buttons(n):
    report = Report()
    g = run_session(n, seed=1, report=report, rb=read_all(), mode="group")
    assert g["finished"], (g, [f["title"] for f in report.sorted()])
    assert g["presses"] > 10 * n                   # واقعاً با دکمه بازی شد
    assert not [f for f in report.sorted() if f["area"] == "playtest"]
    assert report.checks.get("کارت نقش در پیوی") == 1
    assert report.checks.get("دکمه‌ی اکشن شبانه → ثبت در موتور", 0) >= 1


def test_probes_run_without_harness_errors():
    report = Report()
    run_probes(report, read_all())
    broken = [f for f in report.sorted() if f["area"] == "playtest"]
    assert not broken, broken
