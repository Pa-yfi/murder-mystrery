import pytest
from karagah import bot, db
from karagah.engine import RuleError
from .helpers import game, role_game, GROUP


@pytest.mark.parametrize("target", ["", "abc", "-1", "0", str(2**80), "9" * 5000, "1:2", "[]"])
def test_invalid_action_input_is_a_controlled_rejection(target):
    role_game("قاتل")
    result = bot.handle("night", GROUP, 1, arg=target)
    # Empty input intentionally opens an action panel.
    assert isinstance(result, dict)
    assert result["ok"] is (target == "")


@pytest.mark.parametrize("case_id", [-1, 41, 2**80])
def test_invalid_case_does_not_start_or_index_from_end(case_id):
    bot.handle("new", GROUP, 1)
    for uid in range(2, 5):
        bot.handle("join", GROUP, uid)
    response = bot.handle("startgame", GROUP, 1, arg=f"force {case_id}")
    assert not response["ok"]
    assert "خطای داخلی" not in response["text"]


@pytest.mark.parametrize("uid", [2**63, -(2**63)-1])
def test_integer_overflow_is_controlled_at_entry(uid):
    response = bot.handle("help", GROUP, uid, "Oversize")
    assert not response["ok"]


def test_notes_have_bounded_total_storage_and_output():
    g = game()
    for i in range(101):
        bot.handle("note", GROUP, 1, arg=(f"{i}:" + "x" * 200))
    assert len(g.s.players[1].private_notes) <= 100, "No total note quota"
    response = bot.handle("notes", GROUP, 1)
    assert len(response["text"]) <= 3500, "No bounded rendering/pagination"


def test_notes_output_is_bounded_independently_of_storage_quota():
    g = game()
    for _ in range(30):
        g.add_note(1, "x" * 200)
    assert len(bot.handle("notes", GROUP, 1)["text"]) <= 3500


def test_repeated_questions_have_a_bounded_transcript():
    g = role_game("بازجو")
    from .helpers import interrogate
    interrogate(g)
    for i in range(101):
        bot.handle("ask", GROUP, 1, arg=f"question-{i}")
    assert len(g.s.players[4].qa) <= 100


def test_sql_like_player_name_cannot_change_schema():
    payload = "Robert'); DROP TABLE users;--"
    db.touch_user(1, payload)
    assert db.q_user(1)["name"] == payload
    assert db.q_stats()["users"] == 1


def test_duplicate_command_does_not_grow_ballot_history_without_bound():
    g = role_game("شهروند")
    g.resolve_night(); g.open_discussion(); g.open_vote()
    for _ in range(100):
        g.vote(1, 3)
    assert len(g.s.vote_history) == 1
