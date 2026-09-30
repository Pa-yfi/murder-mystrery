"""بهبود ۸: سنجش تعادل — نرخ برد نقش، طول بازی، رهاشدگی."""
import pytest

from karagah import bot, db
from karagah.bot import GAMES, handle
from karagah.models import Align, Custody, Phase


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    yield
    GAMES.clear()


def _play_to_city_win(chat, n=6, case=3):
    handle("new", chat, 1, "Host")
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, arg=str(case))
    g = GAMES[chat]
    for p in g.s.players.values():
        if p.align is Align.KILLER:
            p.custody = Custody.LIFE_JAIL
    g._check_win()
    handle("status", chat, 1)          # → record_results
    return g


def test_outcome_row_per_player():
    g = _play_to_city_win(890)
    rows = db.conn().execute("SELECT * FROM outcomes").fetchall()
    assert len(rows) == len(g.s.players)
    assert {r["seats"] for r in rows} == {len(g.s.players)}


def test_win_rates_split_by_role():
    _play_to_city_win(891)
    rows = db.q_balance()
    assert rows
    by_role = {r["role"]: r for r in rows}
    # شهر برد → قاتل ۰٪ و کارآگاه ۱۰۰٪
    assert by_role["قاتل"]["pct"] == 0.0
    assert by_role["کارآگاه"]["pct"] == 100.0


def test_rates_aggregate_across_games():
    _play_to_city_win(892)
    _play_to_city_win(893, case=4)
    row = next(r for r in db.q_balance() if r["role"] == "قاتل")
    assert row["n"] == 2 and row["wins"] == 0


def test_duration_grouped_by_seat_count():
    _play_to_city_win(894, n=6)
    _play_to_city_win(895, n=8, case=6)
    seats = {r["seats"]: r for r in db.q_balance_by_seats()}
    assert set(seats) == {6, 8}
    assert all(r["avg_days"] is not None for r in seats.values())


def test_abandoned_game_counted_not_scored():
    handle("new", 896, 1, "Host")
    for i in range(2, 6):
        handle("join", 896, i, f"P{i}")
    handle("startgame", 896, 1, arg="5")
    handle("new", 896, 1, "Host")            # میزبان بازیِ در جریان را دور انداخت
    a = db.q_abandonment()
    assert a["abandoned"] == 1 and a["pct"] == 100.0
    assert db.q_balance() == []              # رهاشده در نرخ برد نمی‌آید


def test_finished_game_is_not_abandoned():
    _play_to_city_win(897)
    assert db.q_abandonment()["abandoned"] == 0


def test_balance_endpoint_requires_admin(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [])
    assert handle("balance", 898, 5)["ok"] is False
    monkeypatch.setattr(bot, "ADMIN_IDS", [5])
    assert handle("balance", 898, 5)["ok"] is True


def test_balance_report_renders(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [5])
    _play_to_city_win(899)
    text = handle("balance", 899, 5)["text"]
    assert "نرخ برد" in text and "رهاشدگی" in text and "قاتل" in text


def test_balance_report_handles_empty_history(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [5])
    assert "ثبت نشده" in handle("balance", 900, 5)["text"]
