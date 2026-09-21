import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from karagah import bot, db, telegram_app
from .helpers import game, role_game, update, interrogate, GROUP


def test_private_role_routes_to_player_only():
    game()
    upd, transport = update(1)
    result = telegram_app._dispatch(upd, "myrole", "")
    assert result["ok"] and result["private"]
    asyncio.run(telegram_app._reply(upd, result))
    assert all(c.args[0] == 1 for c in transport.send_message.call_args_list)


@pytest.mark.parametrize("payload", ["SECRET_ROLE", "SECRET_HINT", "SECRET_NOTE", "SECRET_CONVERSATION"])
def test_failed_dm_never_falls_back_with_content(payload):
    sender = SimpleNamespace(send_message=AsyncMock(side_effect=[RuntimeError("blocked"), RuntimeError("blocked"), None]))
    upd, _ = update(1, GROUP, transport=sender)
    asyncio.run(telegram_app._reply(upd, {"text": payload, "private": True}))
    public = [c for c in sender.send_message.call_args_list if c.args[0] == GROUP]
    assert public and all(payload not in c.args[1] for c in public)
    assert all(not c.kwargs.get("reply_markup") for c in public)


@pytest.mark.parametrize("cmd", ["dashboard", "remind"])
def test_public_output_does_not_identify_pending_secret_roles(cmd):
    g = role_game("قاتل")
    result = bot.handle(cmd, GROUP, 5)
    pending_line = "\n".join(line for line in result["text"].splitlines() if "منتظر:" in line)
    assert g.s.players[1].name not in pending_line, "Public pending list exposes who has a hidden night action"
    if cmd == "dashboard":
        player_line = next(line for line in result["text"].splitlines() if g.s.players[1].name in line)
        assert "⏳" not in player_line


def test_human_officer_question_reaches_suspect_via_bot():
    g = role_game("بازجو"); interrogate(g)
    upd, transport = update(1)
    question = "Where were you at 22:30? HUMAN_QUESTION"
    asyncio.run(telegram_app.make_cmd("ask")(upd, SimpleNamespace(args=[question])))
    assert any(c.args[0] == 4 and question in c.args[1] for c in transport.send_message.call_args_list), "No human question relayed to actual suspect"


def test_interrogation_content_not_public():
    g = role_game("بازجو"); interrogate(g)
    response = bot.handle("ask", GROUP, 1, arg="Private question")
    assert response.get("private"), "Interrogation response is addressed to the group"


def test_private_note_not_copied_to_general_audit_history():
    game()
    secret = "PRIVATE_NOTE_SENTINEL"
    assert bot.handle("note", GROUP, 1, arg=secret)["ok"]
    assert all(secret not in row["detail"] for row in db.q_user_events(1))


def test_group_ready_does_not_claim_private_delivery():
    bot.handle("new", GROUP, 1)
    upd, _ = update(1, GROUP)
    telegram_app._dispatch(upd, "ready", "")
    assert not bot.GAMES[GROUP].s.players[1].ready


def test_deep_link_join_is_persisted_in_target_game():
    bot.handle("new", GROUP, 1)
    assert bot.handle("start", 2, 2, arg=f"join_{GROUP}")["ok"]
    bot.GAMES.clear(); bot.restore_games()
    assert 2 in bot.GAMES[GROUP].s.players


def test_old_callback_is_not_redirected_by_table_selection():
    first = role_game("قاتل")
    second = game(chat=GROUP - 1)
    second.s.players[1].role = "قاتل"
    bot._ACTIVE_TABLE[1] = GROUP - 1
    callback = SimpleNamespace(data="act:4", answer=AsyncMock(), message=SimpleNamespace(chat_id=1),
                               from_user=SimpleNamespace(id=1, first_name="Player 1"))
    # Callback originates from first game's action panel before table switch.
    upd, _ = update(1, callback=callback)
    asyncio.run(telegram_app.on_callback(upd, SimpleNamespace()))
    assert not second.s.night_actions, "Unversioned old button acted on newly selected game"


def test_timer_persists_transition_and_broadcasts():
    g = game(); g.s.deadline = 0
    sender = SimpleNamespace(send_message=AsyncMock())
    asyncio.run(telegram_app._timer_job(SimpleNamespace(bot=sender)))
    assert db.load_snapshots()[GROUP].s.phase == g.s.phase
    assert sender.send_message.call_count == 1


def test_public_progress_does_not_disclose_secret_action_count():
    # R11: repeated polling must not expose another player's secret action timing.
    g = role_game("قاتل")
    before = bot.handle("remind", GROUP, 5)["text"]
    g.night_action(1, 4)
    after = bot.handle("remind", GROUP, 5)["text"]
    assert before == after, "Public count changes when the only secret actor commits"
