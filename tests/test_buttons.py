"""هیچ فرمانی نباید فقط با تایپ در دسترس باشد."""
import pytest

from karagah import bot, db, menus, ui
from karagah.bot import GAMES, handle
from karagah.models import Custody, Phase
from karagah.roles import ROLES


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    bot._PENDING.clear()
    yield
    GAMES.clear()
    bot._PENDING.clear()


CHAT = 920


def _started(n=10, case=5, chat=CHAT):
    handle("new", chat, 1, "Host")
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, arg=str(case))
    return GAMES[chat]


def _cbs(kbd):
    return [b["callback_data"] for row in kbd["inline_keyboard"] for b in row
            if "callback_data" in b]


def _to_interrogation(g, chat=CHAT):
    handle("dawn", chat)
    handle("discuss", chat)
    handle("vote", chat)
    target = next(p.uid for p in g.s.alive_players()
                  if p.can_vote and p.uid != g.s.officer_uid)
    for p in g.s.alive_players():
        if p.can_vote and p.uid != target:
            handle("castvote", chat, p.uid, arg=str(target))
    handle("closevote", chat)
    return target


# ---------- پوشش: هر اندپوینت یک دکمه دارد ----------
def test_every_endpoint_is_reachable_by_a_button():
    direct = set(menus.all_buttons())
    indirect = set(menus.REACHES)
    missing = [e for e in bot.ENDPOINTS if e not in direct and e not in indirect]
    assert not missing, f"no button for: {missing}"


def test_every_button_points_at_a_real_endpoint():
    unknown = [cb for cb in menus.all_buttons() if cb not in bot._ROUTES]
    assert not unknown, f"dead button: {unknown}"


def test_indirect_reaches_are_real_endpoints_too():
    for endpoint, via in menus.REACHES.items():
        assert endpoint in bot._ROUTES, endpoint
        assert via in bot._ROUTES, via


def test_every_button_label_has_an_emoji_and_persian():
    for _key, _title, items in menus.GROUPS:
        for label, cb in items:
            assert any(ord(ch) > 0x2000 for ch in label), f"no emoji: {cb}"
            assert any("؀" <= ch <= "ۿ" for ch in label), f"no persian: {cb}"


def test_command_hub_opens_every_group():
    r = handle("commands", CHAT, 1)
    assert r["ok"]
    cbs = _cbs(r["keyboard"])
    for key, _title, _items in menus.GROUPS:
        assert f"group:{key}" in cbs


def test_each_group_page_renders_its_buttons():
    for key, title, items in menus.GROUPS:
        r = handle("group", CHAT, 1, arg=key)
        assert r["ok"] and title in r["text"]
        cbs = _cbs(r["keyboard"])
        for _label, cb in items:
            assert cb in cbs


def test_bad_group_falls_back_to_the_hub():
    r = handle("group", CHAT, 1, arg="nonsense")
    assert r["ok"] and "group:play" in _cbs(r["keyboard"])


def test_main_menu_links_to_the_hub():
    assert "commands" in _cbs(ui.main_menu())


# ---------- توانایی هر نقش، با دکمه ----------
def test_role_catalog_has_one_button_per_role():
    r = handle("roles", CHAT, 1)
    cbs = _cbs(r["keyboard"])
    assert len([c for c in cbs if c.startswith("roleinfo:")]) == len(ROLES)


@pytest.mark.parametrize("idx", range(len(ROLES)))
def test_every_role_card_opens_and_describes_its_night_job(idx):
    r = handle("roleinfo", CHAT, 1, arg=str(idx))
    name = menus.ROLE_NAMES[idx]
    assert r["ok"]
    assert name in r["text"]
    assert ROLES[name].align.value in r["text"]
    assert "کار شبانه" in r["text"]


def test_role_card_translates_the_ability_to_persian():
    idx = menus.ROLE_NAMES.index("سم‌ساز")
    text = handle("roleinfo", CHAT, 1, arg=str(idx))["text"]
    assert "دو شب بعد" in text
    assert "poison" not in text


def test_bad_role_index_shows_the_catalog():
    r = handle("roleinfo", CHAT, 1, arg="999")
    assert r["ok"] and any(c.startswith("roleinfo:") for c in _cbs(r["keyboard"]))


def test_my_abilities_is_private_and_offers_the_action_button():
    g = _started()
    killer = next(p for p in g.s.players.values() if p.role == "قاتل")
    r = handle("abilities", CHAT, killer.uid)
    assert r["ok"] and r["private"]
    assert "اکشن شبانه" in r["text"]
    assert "act" in _cbs(r["keyboard"])


def test_abilities_changes_with_the_phase():
    g = _started()
    plain = next(p for p in g.s.alive_players() if not ROLES[p.role].ability)
    night = handle("abilities", CHAT, plain.uid)["text"]
    handle("dawn", CHAT)
    handle("discuss", CHAT)
    handle("vote", CHAT)
    voting = handle("abilities", CHAT, plain.uid)["text"]
    assert night != voting
    assert "رای" in voting


def test_abilities_tells_a_jailed_player_they_are_out():
    g = _started()
    p = next(x for x in g.s.alive_players() if x.uid != g.s.officer_uid)
    p.custody = Custody.TEMP_JAIL
    assert "حبس موقت" in handle("abilities", CHAT, p.uid)["text"]


# ---------- انتخابگرها به‌جای تایپ آرگومان ----------
def test_lab_without_argument_offers_evidence_buttons():
    g = _started()
    cbs = _cbs(handle("lab", CHAT, 1)["keyboard"])
    for e in g.s.case.evidence:
        assert f"lab:{e['code']}" in cbs


def test_lab_button_submits_the_evidence():
    g = _started()
    code = g.s.case.evidence[0]["code"]
    assert handle("lab", CHAT, 1, arg=code)["ok"]
    assert code in g.s.lab_queue


def test_expose_without_argument_offers_evidence_buttons():
    _started()
    r = handle("expose", CHAT, 1)
    assert r["private"]
    assert any(c.startswith("expose:") for c in _cbs(r["keyboard"]))


def test_interp_is_a_two_step_picker():
    g = _started()
    code = g.s.case.evidence[1]["code"]
    assert f"interp:{code}" in _cbs(handle("interp", CHAT, 1)["keyboard"])
    second = _cbs(handle("interp", CHAT, 1, arg=code)["keyboard"])
    assert f"interp:{code}:0" in second and f"interp:{code}:2" in second
    assert handle("interp", CHAT, 1, arg=f"{code}:1")["ok"]
    assert g.s.interp_votes[code][1] == 1


def test_sos_without_argument_offers_player_buttons_excluding_self():
    _started()
    cbs = _cbs(handle("sos", CHAT, 2)["keyboard"])
    assert "sos:2" not in cbs
    assert any(c.startswith("sos:") for c in cbs)


def test_verdict_without_argument_offers_the_two_rulings():
    g = _started()
    _to_interrogation(g)
    cbs = _cbs(handle("verdict", CHAT, g.s.officer_uid)["keyboard"])
    assert "verdict:1" in cbs and "verdict:0" in cbs


def test_clear_without_argument_lists_only_jailed_players():
    g = _started()
    jailed = next(p for p in g.s.alive_players() if p.uid != g.s.officer_uid)
    jailed.custody = Custody.TEMP_JAIL
    cbs = _cbs(handle("clear", CHAT, g.s.officer_uid)["keyboard"])
    assert f"clear:{jailed.uid}" in cbs
    assert len([c for c in cbs if c.startswith("clear:")]) == 1


def test_host_without_argument_offers_players_instead_of_self_transfer():
    g = _started()
    r = handle("host", CHAT, 1)
    assert any(c.startswith("host:") for c in _cbs(r["keyboard"]))
    assert g.owner == 1


def test_admin_ban_without_argument_lists_users(monkeypatch):
    monkeypatch.setattr(bot, "ADMIN_IDS", [1])
    _started()
    r = handle("admin_ban", CHAT, 1)
    assert r["ok"]
    assert any(c.startswith("admin_ban:") for c in _cbs(r["keyboard"]))


# ---------- تنها جایی که تایپ لازم است ----------
@pytest.mark.parametrize("cmd", ["note", "will", "defense", "ask"])
def test_text_commands_prompt_instead_of_erroring(cmd):
    _started()
    r = handle(cmd, CHAT, 2)
    assert r["ok"] and r["private"]
    assert "cancel" in _cbs(r["keyboard"])
    assert bot._PENDING.get(2) == (CHAT, cmd)


def test_pending_text_is_consumed_once():
    _started()
    handle("note", CHAT, 2)
    assert bot.take_pending(2) == (CHAT, "note")
    assert bot.take_pending(2) is None


def test_cancel_clears_the_pending_prompt():
    _started()
    handle("note", CHAT, 2)
    assert handle("cancel", CHAT, 2)["ok"]
    assert bot.take_pending(2) is None


def test_note_text_is_stored_when_supplied():
    g = _started()
    handle("note", CHAT, 2, arg="سارا مشکوک است")
    assert "سارا مشکوک است" in g.s.players[2].private_notes


def test_ask_button_no_longer_sends_the_suspect_id_as_the_question():
    """دکمه‌ی قدیمی ask:<uid> آیدی را به‌جای متنِ سؤال می‌فرستاد."""
    cbs = _cbs(ui.officer_kb(4))
    assert "ask" in cbs
    assert not any(c.startswith("ask:") for c in cbs)


def test_interrogation_answer_is_private():
    g = _started()
    _to_interrogation(g)
    r = handle("ask", CHAT, g.s.officer_uid, arg="کجا بودی؟")
    assert r["ok"] and r["private"]
