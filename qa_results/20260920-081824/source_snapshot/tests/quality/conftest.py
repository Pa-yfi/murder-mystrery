import socket
import pytest
from karagah import bot, db


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    db.reset(":memory:")
    for cache in (bot.GAMES, bot.LAST_ROSTER, bot._ACTIVE_TABLE, bot._LAST_CALL, bot._LAST_CB):
        cache.clear()
    monkeypatch.setattr(bot, "ADMIN_IDS", [])
    monkeypatch.setattr(bot, "RATE_LIMIT_ENABLED", False)
    original_connect = socket.socket.connect
    def local_only(sock, address):
        if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
            return original_connect(sock, address)
        raise AssertionError("External network access forbidden")
    monkeypatch.setattr(socket.socket, "connect", local_only)
    yield
    bot.GAMES.clear()
    db.reset(":memory:")
