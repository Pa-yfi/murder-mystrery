import pytest
from karagah import bot, ui, db
from karagah.bot import GAMES, handle
from karagah.cases import CASES
from karagah.engine import Game, RuleError
from karagah.models import Align, Custody, Phase
from karagah.roles import ROLES, balance_report, composition, validate_composition
from karagah import dialogue


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")          # دیتابیس تازه در حافظه برای هر تست
    GAMES.clear()
    yield
    GAMES.clear()


# ---------- کمکی ----------
def _game(n=6, seed=7) -> Game:
    g = Game(chat_id=1, seed=seed)
    for i in range(1, n + 1):
        g.join(i, f"بازیکن{i}")
    return g


def _officer(g): return g.s.officer_uid
def _first_free(g, exclude=()):
    return next(p.uid for p in g.s.alive_players()
                if p.custody is Custody.FREE and p.uid not in exclude and p.uid != g.s.officer_uid)


# ---------- محتوا ----------
def test_forty_cases_unique_and_complete():
    assert len(CASES) == 40
    assert len({c.title for c in CASES}) == 40
    for c in CASES:
        assert c.victim and c.place and c.weapon and c.motive and c.twist
        assert len(c.evidence) == 6
        assert all(len(e["interpretations"]) >= 2 for e in c.evidence)
        assert any(e["misleading"] for e in c.evidence)


@pytest.mark.parametrize("n", [4, 5, 6, 7, 8])
def test_role_division(n):
    assert validate_composition(n)
    c = composition(n)
    assert len(c) == n and c.count("بازجو") == 1
    rep = balance_report(n)
    assert rep[Align.KILLER.value] < rep[Align.CITY.value]


def test_player_bounds():
    for n in (3, 11):
        with pytest.raises(ValueError):
            composition(n)
    for n in range(4, 11):
        assert validate_composition(n)          # ۴..۱۰ همه معتبر


def test_role_info_access_is_specific():
    g = _game(8); g.start(1)
    for p in g.s.players.values():
        if ROLES[p.role].info == "team_ids":
            assert p.knows and p.align is Align.KILLER
        if p.role == "شهروند":
            assert p.knows == []


def test_dialogue_deterministic_and_no_llm():
    g = _game(6); g.start(2)
    p = list(g.s.players.values())[0]
    assert dialogue.answer(p, "کجا بودی؟", 1) == dialogue.answer(p, "کجا بودی؟", 1)
    hints = dialogue.interrogation_hints(p, 1)
    assert hints and not any("قاتل است" in h for h in hints)


# ---------- حذف سه‌مرحله‌ای ----------
def test_stage1_interrogation_one_night():
    g = _game(); g.start(3)
    g.resolve_night(); g.open_discussion(); g.open_vote()
    t = _first_free(g)
    for p in g.s.alive_players():
        if p.can_vote and p.uid != t:
            g.vote(p.uid, t)
    assert g.close_vote() == t
    assert g.s.players[t].custody is Custody.INTERROGATION
    assert len(g.officer_hints(_officer(g))) >= 3
    with pytest.raises(RuleError):
        g.officer_hints(t)


def test_stage2_temp_jail_needs_new_suspect():
    g = _game(); g.start(4); g.resolve_night()
    t = _first_free(g); g.send_to_interrogation(t)
    g.officer_verdict(_officer(g), True)
    assert g.s.players[t].custody is Custody.TEMP_JAIL
    with pytest.raises(RuleError):
        g.clear_previous(_officer(g), t)
    t2 = _first_free(g, exclude=(t,)); g.send_to_interrogation(t2)
    g.clear_previous(_officer(g), t)
    assert g.s.players[t].custody is Custody.FREE and g.s.players[t].cleared


def test_stage3_life_jail_no_reveal():
    g = _game(); g.start(5); g.resolve_night()
    t = _first_free(g); g.send_to_interrogation(t)
    g.officer_verdict(_officer(g), True)
    g.resolve_night()
    g.open_discussion(); g.open_vote(); g.close_vote()
    g.resolve_night()
    assert g.s.players[t].custody is Custody.LIFE_JAIL and not g.s.players[t].in_game
    if g.s.phase is not Phase.END:
        with pytest.raises(RuleError):
            g.reveal()


def test_jailed_cannot_vote_or_act():
    g = _game(); g.start(6); g.resolve_night()
    t = _first_free(g); g.send_to_interrogation(t)
    with pytest.raises(RuleError):
        g.night_action(t, _officer(g))
    g.officer_verdict(_officer(g), True); g.resolve_night()
    g.open_discussion(); g.open_vote()
    with pytest.raises(RuleError):
        g.vote(t, _officer(g))


def test_officer_release_clears():
    g = _game(); g.start(7); g.resolve_night()
    t = _first_free(g); g.send_to_interrogation(t)
    g.ask(_officer(g), "چرا دروغ گفتی؟")
    assert "آزاد" in g.officer_verdict(_officer(g), False)
    assert g.s.players[t].custody is Custody.FREE


def test_jury_after_one_night_acquits():
    g = _game(); g.start(8); g.resolve_night()
    t = _first_free(g); g.send_to_interrogation(t)
    with pytest.raises(RuleError):
        g.request_jury(_officer(g))
    g.s.players[t].custody_nights = 1
    voters = [p.uid for p in g.s.alive_players() if p.uid != t][:2]
    assert g.request_jury(voters[0]) is False
    assert g.request_jury(voters[1]) is True
    for u in [p.uid for p in g.s.alive_players() if p.can_vote]:
        g.jury_vote(u, True)
    assert "تبرئه" in g.close_jury()


def test_city_wins_when_all_killers_jailed():
    g = _game(4); g.start(9); g.resolve_night()
    for p in g.s.players.values():
        if p.align is Align.KILLER:
            p.custody = Custody.LIFE_JAIL
    g._check_win()
    assert g.s.winner.startswith("شهر")
    assert len(g.reveal()) == 4


def test_neutral_scapegoat_wins():
    g = _game(6); g.start(10)
    next(p for p in g.s.players.values() if p.role == "سپر بلا").custody = Custody.LIFE_JAIL
    g._check_win()
    assert "سپر بلا" in g.s.winner


# ---------- باگ اصلی اسکرین‌شات: «دستور ناشناخته» ----------
def test_unknown_command_returns_menu_not_error():
    r = handle("badcmd", 1, 1)
    assert r["ok"] and r["keyboard"]           # منو، نه خطا


def test_internal_keyerror_not_reported_as_unknown_command():
    """پروفایل/نقش قبل از ورود → پیام دوستانه، نه «دستور ناشناخته»."""
    handle("new", 50, 1, "Host")               # لابی هست ولی کاربر ۲ عضو نیست
    for cmd in ("profile", "myrole"):
        r = handle(cmd, 50, 999, "Ghost")
        assert r["ok"] is False
        assert "ناشناخته" not in r["text"]     # دیگر KeyError بلعیده نمی‌شود
        assert "ورود" in r["text"] or "بازی" in r["text"]


def test_start_always_shows_menu():
    for chat in (100, 200, 300):
        r = handle("start", chat, 5, "U")
        assert r["ok"] and r["keyboard"]["inline_keyboard"]
    # حتی با آرگومان خراب
    assert handle("start", 400, 5, "U", arg="join_xyz")["ok"]


# ---------- همه‌ی دکمه‌ها به اندپوینت واقعی وصل‌اند ----------
def _all_callbacks(keyboard):
    out = []
    for row in keyboard["inline_keyboard"]:
        for b in row:
            if "callback_data" in b:
                out.append(b["callback_data"])
    return out


def test_every_button_maps_to_real_endpoint():
    CB_MAP = {"vote": "castvote", "ver": "verdict", "jury": "juryvote", "ask": "ask"}
    g = _game(8); g.start(11); g.resolve_night()
    keyboards = [
        ui.main_menu(), ui.first_kb(1), ui.owner_kb(1), ui.back_only(),
        ui.share_kb(1), ui.admin_menu(), ui.vote_kb(g.s), ui.officer_kb(2),
        ui.jury_kb(),
        ui.kb([[ui.BACK, ui.HOME]]),
    ]
    for k in keyboards:
        for cb in _all_callbacks(k):
            if ":" in cb:
                endpoint = CB_MAP.get(cb.split(":", 1)[0], cb.split(":", 1)[0])
            else:
                endpoint = cb          # دکمه‌ی ساده = نام اندپوینت مستقیم
            assert endpoint in bot.ENDPOINTS, f"دکمه‌ی مرده: {cb} → {endpoint}"


def test_no_dead_menu_buttons():
    """منوی اصلی نباید callbackِ بدون هندلر داشته باشد (باگ rank/shop)."""
    for cb in _all_callbacks(ui.main_menu()):
        assert cb in bot.ENDPOINTS


# ---------- fuzz: هیچ اندپوینتی کرش نمی‌کند ----------
def test_every_endpoint_never_crashes():
    for cmd in bot.ENDPOINTS:
        for chat, uid, arg in [(1, 0, ""), (2, 5, "abc"), (3, 5, "999"), (4, 7, "join_5")]:
            try:
                r = handle(cmd, chat, uid, "X", arg)
            except Exception as e:
                raise AssertionError(f"{cmd} crashed: {e}")
            assert isinstance(r, dict) and r.get("text")


# ---------- اشتراک / دیپ‌لینک / میزبان ----------
def test_first_screen_has_group_and_invite():
    r = handle("start", 1000, 10, "Host")
    btns = [b for row in r["keyboard"]["inline_keyboard"] for b in row]
    assert any("startgroup" in b.get("url", "") for b in btns)
    assert any("share/url" in b.get("url", "") for b in btns)


def test_deeplink_owner_vs_newbie():
    handle("new", 1100, 10, "Host")
    assert 10 in GAMES[1100].s.players
    assert "پنل میزبان" in handle("start", 999, 10, "Host", arg="join_1100")["text"]
    r = handle("start", 998, 20, "Guest", arg="join_1100")
    assert "خوش آمدی" in r["text"]
    assert 20 in GAMES[1100].s.players
    assert handle("start", 998, 20, "Guest", arg="join_1100")["ok"]   # دوباره بدون خطا


def test_join_and_share_never_silent():
    assert handle("join", 1200, 30, "Solo")["ok"] and 30 in GAMES[1200].s.players
    assert handle("share", 1300, 31, "S2")["ok"]


# ---------- پنل ادمین روی SQL ----------
def test_admin_panel_uses_sql():
    handle("new", 600, 1, "Host")
    for i in range(2, 7):
        handle("join", 600, i, f"P{i}")
    handle("startgame", 600, 1, arg="3")       # save_game → SQL

    # داده باید در SQL باشد
    assert db.q_stats()["users"] >= 6
    assert any(r["chat_id"] == 600 for r in db.q_active_games())

    bot.ADMIN_IDS.clear(); bot.ADMIN_IDS.append(1)
    assert handle("admin", 600, 1)["ok"]
    assert handle("admin", 600, 2)["ok"] is False
    g = handle("admin_games", 600, 1)
    assert "600" in g["text"]
    u = handle("admin_users", 600, 1)
    assert "🆔" in u["text"]
    card = handle("admin_users", 600, 1, arg="2")
    assert "آیدی" in card["text"] and "XP" in card["text"]
    assert handle("admin_users", 600, 1, arg="99999")["ok"] is False
    assert "کاربران" in handle("admin_stats", 600, 1)["text"]
    # بن‌کردن از طریق SQL
    assert handle("admin_ban", 600, 1, arg="2")["ok"]
    assert db.is_banned(2)


def test_admin_requires_id_when_set():
    bot.ADMIN_IDS.clear(); bot.ADMIN_IDS.append(777)
    assert handle("admin", 1, 5)["ok"] is False
    assert handle("admin", 1, 777)["ok"] is True
    bot.ADMIN_IDS.clear()


# ---------- بازی کامل از طریق اندپوینت‌ها ----------
def test_full_endpoint_playthrough():
    chat = 42
    assert handle("start", chat, 1, "P1")["ok"]
    assert handle("new", chat, 1, "P1")["ok"]        # میزبان
    for i in range(2, 7):
        assert handle("join", chat, i, f"P{i}")["ok"]
    assert handle("startgame", chat, 1, arg="15")["ok"]
    g = GAMES[chat]; off = g.s.officer_uid
    assert handle("myrole", chat, 1)["private"]
    killer = next(p for p in g.s.players.values() if p.role == "قاتل")
    victim = next(p.uid for p in g.s.players.values()
                  if p.uid not in (killer.uid, off))
    assert handle("night", chat, killer.uid, arg=str(victim))["ok"]
    assert handle("dawn", chat)["anim"]
    assert handle("discuss", chat)["ok"]
    assert handle("vote", chat)["ok"]
    target = next(p.uid for p in g.s.alive_players() if p.uid != off)
    for p in g.s.alive_players():
        if p.can_vote and p.uid != target:
            handle("castvote", chat, p.uid, arg=str(target))
    assert handle("closevote", chat)["ok"]
    assert g.s.players[target].custody is Custody.INTERROGATION
    assert handle("hints", chat, off)["private"]
    assert handle("hints", chat, target)["ok"] is False
    assert "متهم" in handle("ask", chat, off, arg="کجا بودی؟")["text"]
    assert handle("end", chat)["ok"] is False        # قبل از پایان فاش نمی‌شود
    assert handle("verdict", chat, off, arg="1")["ok"]
    assert g.s.players[target].custody is Custody.TEMP_JAIL
    assert handle("status", chat)["ok"]
    assert handle("menu", chat, 1)["ok"]


def test_ui_screens_render():
    g = _game(8); g.start(20); g.resolve_night()
    for fn in (ui.lobby_screen, ui.status_board, ui.case_intro, ui.first_screen,
               ui.newbie_guide, ui.help_text):
        s = fn(g.s) if fn.__code__.co_argcount else fn()
        assert isinstance(s, str) and len(s) > 15
    assert all(k in ui.ANIM for k in ("night", "morning", "vote", "interrogation", "jail", "court"))


# ---------- نسخه ۱.۲: رکورد، دکمه‌ی گروهی، ویرایش درجا، قوانین ----------
def test_restart_recovery_restores_games():
    """ری‌استارت ربات وسط بازی → بازی از SQLite برمی‌گردد (مشکل «حفظ رکورد»)."""
    handle("new", 700, 1, "Host")
    for i in range(2, 7):
        handle("join", 700, i, f"P{i}")
    handle("startgame", 700, 1, arg="5")
    day, case = GAMES[700].s.day, GAMES[700].s.case.cid
    GAMES.clear()                                  # شبیه‌سازی کرش/ری‌استارت
    assert bot.restore_games() >= 1
    assert 700 in GAMES
    assert GAMES[700].s.day == day and GAMES[700].s.case.cid == case
    # و بعد از بازیابی، بازی ادامه‌پذیر است
    assert handle("status", 700, 1)["ok"]


def test_finished_game_cleaned_up():
    """بازی تمام‌شده از حافظه و اسنپ‌شات پاک می‌شود (نشت حافظه/لابی)."""
    handle("new", 710, 1, "Host")
    for i in range(2, 5):
        handle("join", 710, i, f"P{i}")
    handle("startgame", 710, 1, arg="2")
    g = GAMES[710]
    for p in g.s.players.values():
        if p.align is Align.KILLER:
            p.custody = Custody.LIFE_JAIL
    g._check_win()
    handle("status", 710, 1)                       # هر فرمانی → پاکسازی
    assert 710 not in GAMES
    GAMES.clear()
    assert bot.restore_games() == 0 or 710 not in GAMES


def test_lobby_has_metoo_button_and_edits_inplace():
    """دکمه‌ی «منم بازی می‌کنم» + ویرایش درجا به‌جای پیام جدید."""
    handle("new", 720, 1, "Host")
    r = handle("join", 720, 2, "P2")
    assert r["edit"] is True                       # پیام لابی ویرایش می‌شود
    btns = [b for row in r["keyboard"]["inline_keyboard"] for b in row]
    assert any("منم بازی" in b["text"] and b.get("callback_data") == "join" for b in btns)
    # روی پنل میزبان هم هست
    r2 = handle("new", 721, 1, "Host")
    btns2 = [b for row in r2["keyboard"]["inline_keyboard"] for b in row]
    assert any("منم بازی" in b["text"] for b in btns2)


def test_empty_name_gets_fallback():
    """باگ «👤 بی‌نام» در اسکرین‌شات: نام خالی → کارآگاه <id>."""
    handle("new", 730, 9, "")
    assert GAMES[730].s.players[9].name == "کارآگاه 9"


def test_no_self_vote_and_no_self_kill():
    g = _game(); g.start(6); g.resolve_night()
    g.open_discussion(); g.open_vote()
    voter = next(p.uid for p in g.s.alive_players() if p.can_vote)
    with pytest.raises(RuleError):
        g.vote(voter, voter)
    g2 = _game(); g2.start(7)
    killer = next(p for p in g2.s.players.values() if p.role == "قاتل")
    with pytest.raises(RuleError):
        g2.night_action(killer.uid, killer.uid)


def test_vote_edit_is_allowed():
    """رای دوباره = ویرایش رای (نه Double Vote)."""
    g = _game(); g.start(8); g.resolve_night()
    g.open_discussion(); g.open_vote()
    alive = [p.uid for p in g.s.alive_players() if p.can_vote]
    a, b, c = alive[0], alive[1], alive[2]
    g.vote(a, b); g.vote(a, c)
    assert g.s.votes[a] == c and list(g.s.votes).count(a) == 1


def test_host_migration_on_leave():
    handle("new", 740, 1, "Host")
    handle("join", 740, 2, "P2")
    handle("leave", 740, 1, "Host")
    assert GAMES[740].owner == 2                   # میزبانی منتقل شد


def test_join_after_start_friendly():
    handle("new", 750, 1, "Host")
    for i in range(2, 5):
        handle("join", 750, i, f"P{i}")
    handle("startgame", 750, 1, arg="1")
    r = handle("start", 99, 9, "Late", arg="join_750")
    assert r["ok"] is False and "شروع شده" in r["text"]


# ================= نسخه ۲: تست ۳۰ ایده =================
import time as _t


def test_phase_timer_auto_advances():           # ایده ۱
    g = _game(); g.start(3)
    assert g.s.deadline is not None            # شب مسلح شد
    assert g.remaining() >= 0
    g.s.deadline = _t.time() - 1               # مهلت گذشت
    assert "شب" in g.tick()
    assert g.s.phase is Phase.MORNING
    g.open_discussion()
    g.s.deadline = _t.time() - 1
    assert "رای‌گیری" in g.tick()
    g.s.deadline = _t.time() - 1
    assert "بسته شد" in g.tick()               # رای خالی → شب


def test_blitz_halves_rules():                  # ایده ۳
    from karagah.engine import Game as G
    g = G(2, seed=2, owner=1, blitz=True)
    assert g.temp_jail_nights == 1 and g.interrogation_nights >= 1
    r = handle("blitz", 810, 1, "Host")
    assert r["ok"] and "بلیتز" in r["text"] and GAMES[810].blitz


def test_night_events_deterministic():          # ایده ۴
    g = _game(8, seed=1); g.start(1)
    ev1 = []
    for _ in range(4):
        g.s.phase = Phase.NIGHT
        g.resolve_night()
        ev1.append(g.s.night_event)
    g2 = _game(8, seed=1); g2.start(1)
    ev2 = []
    for _ in range(4):
        g2.s.phase = Phase.NIGHT
        g2.resolve_night()
        ev2.append(g2.s.night_event)
    assert ev1 == ev2                           # قطعی


def test_storm_cancels_kill():                  # ایده ۴
    g = _game(); g.start(2)
    # شبی را پیدا کن که طوفان است
    import random as _r
    day = next(d for d in range(1, 60) if 0.12 <= _r.Random(g.s.chat_id*1000+d).random() < 0.22)
    g.s.day = day
    killer = next(p for p in g.s.players.values() if p.role == "قاتل")
    victim = next(p.uid for p in g.s.players.values() if p.uid != killer.uid)
    g.night_action(killer.uid, victim)
    r = g.resolve_night()
    assert r["killed"] == [] and g.s.players[victim].alive


def test_will_broadcast_on_death():             # ایده ۵
    g = _game(); g.start(4)
    killer = next(p for p in g.s.players.values() if p.role == "قاتل")
    victim = next(p for p in g.s.players.values() if p.uid != killer.uid)
    g.set_will(victim.uid, "قاتل کسی است که چای می‌خورد")
    # شبی بدون طوفان
    import random as _r
    day = next(d for d in range(1, 60)
               if not (0.12 <= _r.Random(g.s.chat_id*1000+d).random() < 0.22))
    g.s.day = day
    g.night_action(killer.uid, victim.uid)
    g.resolve_night()
    assert any("وصیت" in l and "چای" in l for l in g.s.log)


def test_sos_emergency_vote():                  # ایده ۶
    g = _game(); g.start(5); g.resolve_night()
    alive = [p.uid for p in g.s.alive_players() if p.can_vote]
    target = alive[-1]
    import math
    need = math.ceil(0.8 * len(alive))
    for u in alive[:need]:
        if u != target:
            msg = g.sos(u, target)
    assert g.s.players[target].custody is Custody.TEMP_JAIL or "تصویب" in msg
    with pytest.raises(RuleError):              # فقط یک بار در بازی
        g.sos(alive[0], alive[1])


def test_coroner_gets_death_details():          # ایده ۷
    g = _game(7, seed=3); g.start(6)
    g.s.fate_pair = None                        # ایزوله از ایده ۸
    cor = next(p for p in g.s.players.values() if p.role == "کالبدشکاف")
    killer = next(p for p in g.s.players.values() if p.role == "قاتل")
    victim = next(p.uid for p in g.s.players.values()
                  if p.uid not in (killer.uid, cor.uid))
    import random as _r
    day = next(d for d in range(1, 60)
               if not (0.12 <= _r.Random(g.s.chat_id*1000+d).random() < 0.22))
    g.s.day = day
    g.night_action(killer.uid, victim)
    g.resolve_night()
    assert any("🔬" in n for n in cor.notes)


def test_fate_pair_links_two_city():            # ایده ۸
    g = _game(8, seed=9); g.start(7)
    assert g.s.fate_pair is not None
    a, b = g.s.fate_pair
    assert g.s.players[a].align is Align.CITY and g.s.players[b].align is Align.CITY
    assert any("سرنوشت" in k for k in g.s.players[a].knows)


def test_notes_and_will_endpoints():            # ایده‌های ۵/۹
    handle("new", 820, 1, "Host")
    assert handle("will", 820, 1, arg="مواظب باغبان باشید")["private"]
    assert handle("note", 820, 1, arg="P3 مشکوک است")["ok"]
    r = handle("notes", 820, 1)
    assert "P3 مشکوک" in r["text"] and r["private"]


def test_lab_delayed_results():                 # ایده ۱۰
    g = _game(); g.start(8)
    assert "دو شب" in g.submit_lab("E1")
    with pytest.raises(RuleError):
        g.submit_lab("E1")                     # تکراری
    with pytest.raises(RuleError):
        g.submit_lab("E9")                     # نامعتبر
    g.resolve_night()                           # روز هنوز نرسیده
    g.s.day = 3
    g.s.phase = Phase.NIGHT
    g.resolve_night()
    assert any("آزمایشگاه" in l and "E1" in l for l in g.s.log)


def test_interp_voting():                       # ایده ۱۱
    g = _game(); g.start(9)
    msg = g.vote_interp(1, "E1", 0)
    assert "تفسیر غالب" in msg
    with pytest.raises(RuleError):
        g.vote_interp(1, "E1", 9)


def test_detective_expose():                    # ایده ۱۲
    g = _game(); g.start(10)
    det = next(p for p in g.s.players.values() if p.role == "کارآگاه")
    fake = next(e["code"] for e in g.s.case.evidence if e["misleading"])
    real = next(e["code"] for e in g.s.case.evidence if not e["misleading"])
    assert "جعلی" in g.expose(det.uid, fake)
    with pytest.raises(RuleError):              # یک اکشن در شب
        g.expose(det.uid, real)
    other = next(p for p in g.s.players.values() if p.role != "کارآگاه")
    with pytest.raises(RuleError):
        g.expose(other.uid, real)


def test_contradiction_detector():              # ایده ۱۳
    g = _game(); g.start(11); g.resolve_night()
    tgt = _first_free(g)
    g.send_to_interrogation(tgt)
    sus = g.s.players[tgt]
    sus.stress = 30                             # آرام
    a1 = g.ask(_officer(g), "کجا بودی؟")
    sus.stress = 90                             # پانیک → جواب عوض می‌شود
    a2 = g.ask(_officer(g), "کجا بودی؟")
    assert "تناقض" in a2


def test_defense_shown():                       # ایده ۲
    g = _game(); g.start(12); g.resolve_night()
    tgt = _first_free(g)
    g.send_to_interrogation(tgt)
    msg = g.defense(tgt, "من در آشپزخانه بودم")
    assert "دفاع" in msg
    with pytest.raises(RuleError):
        g.defense(_officer(g), "!")             # فقط متهم


def test_end_records_results_and_mvp():         # ایده‌های ۱۴-۲۰
    handle("new", 830, 1, "Host")
    for i in range(2, 5):
        handle("join", 830, i, f"P{i}")
    handle("startgame", 830, 1, arg="4")
    g = GAMES[830]
    for p in g.s.players.values():
        if p.align is Align.KILLER:
            p.custody = Custody.LIFE_JAIL
    g._check_win()
    assert g.s.mvp is not None                  # ایده ۱۷
    r = handle("end", 830, 1)
    assert "MVP" in r["text"] and "بازسازی" in r["text"]   # ایده ۱۴
    # ایده‌های ۱۵/۱۹/۲۰: ثبت در SQL
    assert db.q_top() and db.q_season()
    assert any(done for *_x, done in db.q_missions(1))
    assert handle("top", 830, 1)["ok"] and handle("season", 830, 1)["ok"]
    assert handle("league", 830, 1)["ok"] and handle("missions", 830, 1)["private"]
    assert handle("achv", 830, 1)["private"]
    # ایده ۲۴: دور دوباره با همان ترکیب
    r = handle("rematch", 830, 1)
    assert r["ok"] and len(GAMES[830].s.players) == 4


def test_parallel_tables():                     # ایده ۲۱
    handle("new", 840, 1, "Host")
    r1 = handle("newtable", 840, 2, "P2")
    r2 = handle("newtable", 840, 3, "P3")
    assert r1["ok"] and r2["ok"]
    assert 84001 in GAMES and 84002 in GAMES    # میزهای موازی
    handle("newtable", 840, 4, "P4")
    assert handle("newtable", 840, 5, "P5")["ok"] is False   # سقف ۳ میز


def test_spectate_no_secrets():                 # ایده ۲۲
    handle("new", 850, 1, "Host")
    for i in range(2, 5):
        handle("join", 850, i, f"P{i}")
    handle("startgame", 850, 1)
    r = handle("spectate", 850, 99, "Watcher")
    assert r["ok"] and r["private"]
    for role in ("قاتل", "کارآگاه", "سپر بلا"):
        assert f"→ {role}" not in r["text"]     # هیچ نقشی لو نمی‌رود


def test_voteanon_toggle_owner_only():          # ایده ۲۳
    handle("new", 860, 1, "Host")
    assert handle("voteanon", 860, 2, "P2")["ok"] is False
    r = handle("voteanon", 860, 1, "Host")
    assert "علنی" in r["text"] and GAMES[860].s.vote_anon is False


def test_dashboard_and_tick_endpoints():        # ایده‌های ۱/۲۶
    handle("new", 870, 1, "Host")
    for i in range(2, 5):
        handle("join", 870, i, f"P{i}")
    handle("startgame", 870, 1)
    r = handle("dashboard", 870, 1)
    assert r["ok"] and r["edit"]
    assert handle("tick", 870, 1)["ok"]


def test_rolecard_png():                        # ایده ۲۷
    handle("new", 880, 1, "Host")
    for i in range(2, 5):
        handle("join", 880, i, f"P{i}")
    handle("startgame", 880, 1)
    r = handle("rolecard", 880, 1)
    import os
    assert r["ok"] and r["private"] and os.path.exists(r["photo"])


def test_tutorial_and_strings():                # ایده‌های ۲۸/۳۰
    r = handle("tutorial", 890, 1)
    assert "آموزش" in r["text"] and "حبس ابد" in r["text"]
    from karagah.strings import t
    assert t("main_menu") and t("lobby", "en") == "🏛️ *Detective Lobby*"


def test_voice_map_exists():                    # ایده ۲۹
    assert set(ui.VOICE) == set(ui.ANIM)


def test_endpoint_count_v2():
    assert len(bot.ENDPOINTS) == 56


# ================= نسخه ۳: ۲۰ بهبود کیفیت و گیم‌پلی =================
def test_secret_role_ratio_balanced():          # ایده ۶ (پژوهش: ۲۰-۴۵٪)
    from karagah.roles import composition, ROLES
    for n in range(4, 11):
        c = composition(n)
        hidden = sum(1 for r in c if ROLES[r].align is not Align.CITY)
        k = sum(1 for r in c if ROLES[r].align is Align.KILLER)
        assert 0.20 <= hidden / n <= 0.45, f"n={n} نسبت خراب"
        assert k * 2 < n, f"n={n} قاتل‌ها اقلیت نیستند"


def test_role_cooldown_avoids_repeat():         # ایده ۵
    from karagah.roles import assign_with_cooldown
    import random as _r
    uids = [1, 2, 3, 4, 5, 6]
    last = {u: "قاتل" for u in uids}
    m = assign_with_cooldown(uids, 6, _r.Random(1), last)
    repeats = sum(1 for u in uids if m[u] == last[u])
    assert repeats <= 1                          # تقریباً هیچ تکراری


def test_mafia_parity_win():                     # ایده ۴
    g = _game(6); g.start(3)
    # بگذار فقط ۱ قاتل و ۱ شهر بمانند → برابری → برد قاتل
    alive = g.s.alive_players()
    killers = [p for p in alive if p.align is Align.KILLER]
    city = [p for p in alive if p.align is not Align.KILLER]
    for p in city[1:]:
        p.alive = False
    g._check_win()
    assert g.s.winner.startswith("قاتل")


def test_doctor_no_self_heal_no_repeat():        # ایده ۱۱
    g = _game(6); g.start(4)
    doc = next((p for p in g.s.players.values() if p.role == "پزشک"), None)
    if not doc:
        return
    with pytest.raises(RuleError):
        g.night_action(doc.uid, doc.uid)          # خودنجاتی ممنوع
    a = next(p.uid for p in g.s.alive_players() if p.uid != doc.uid)
    g.night_action(doc.uid, a)
    g.night_action(doc.uid, a)                    # ویرایش روی همان هدف در همان شب مجاز
    assert g.s.night_actions.get("_last_protect") == a
    g.resolve_night()                             # شب حل شد؛ هدف قبلی ثبت شد
    g.s.phase = Phase.NIGHT
    with pytest.raises(RuleError):
        g.night_action(doc.uid, a)                # دو شب پیاپی همان نفر ممنوع
    b = next(p.uid for p in g.s.alive_players() if p.uid not in (doc.uid, a))
    g.night_action(doc.uid, b)                    # نفر دیگر مجاز
    assert g.s.night_actions.get("_last_protect") == b


def test_investigator_records_last_target():     # ایده ۱۲
    g = _game(6); g.start(5)
    det = next(p for p in g.s.players.values() if p.role == "کارآگاه")
    other = next(p.uid for p in g.s.alive_players() if p.uid != det.uid)
    g.night_action(det.uid, other)
    assert g.s.night_actions.get(f"_inv_last:{det.uid}") == other


def test_hunter_last_shot():                     # ایده ۱۵
    g = _game(9, seed=4); g.start(6)
    hunter = next((p for p in g.s.players.values() if p.role == "شکارچی"), None)
    assert hunter
    victim = next(p.uid for p in g.s.alive_players() if p.uid != hunter.uid)
    g.set_hunter(hunter.uid, victim)
    # شکارچی امشب کشته می‌شود
    killer = next(p for p in g.s.players.values() if p.role == "قاتل")
    g.s.fate_pair = None
    import random as _r
    day = next(d for d in range(1, 80)
               if not (0.12 <= _r.Random(g.s.chat_id*1000+d).random() < 0.22))
    g.s.day = day
    g.night_action(killer.uid, hunter.uid)
    r = g.resolve_night()
    assert hunter.uid in r["killed"] and victim in r["killed"]   # هدفش را برد


def test_tie_break_sudden_death():               # ایده ۲۰
    g = _game(6); g.start(7); g.resolve_night()
    g.open_discussion(); g.open_vote()
    alive = [p for p in g.s.alive_players() if p.can_vote]
    a, b = alive[0], alive[1]
    # تساوی مصنوعی: نصف به a نصف به b
    g.s.votes = {alive[2].uid: a.uid, alive[3].uid: b.uid} if len(alive) >= 4 else {a.uid: b.uid, b.uid: a.uid}
    who = g.close_vote()
    assert who is None and g.s.tie_break is True   # مرگ ناگهانی فعال شد، فاز رای باز ماند


def test_input_sanitization():                   # ایده ۸
    from karagah.bot import _sanitize, _name
    assert "*" not in _sanitize("*bold* _hack_ `code`")
    assert _name("", 55) == "کارآگاه 55"
    handle("new", 950, 1, "*Ali*_[x]")
    nm = GAMES[950].s.players[1].name
    assert "*" not in nm and "[" not in nm


def test_callback_dedup():                       # ایده ۲
    from karagah.bot import is_dup_callback
    assert is_dup_callback(1, 1, "vote") is False   # اولین بار
    assert is_dup_callback(1, 1, "vote") is True    # بلافاصله دوباره → تکراری


def test_rate_limit_toggle():                    # ایده ۹
    import karagah.bot as B
    B.RATE_LIMIT_ENABLED = True
    B._LAST_CALL.clear()
    r1 = handle("roles", 960, 5)                  # roles در NO_RATE است → محدود نمی‌شود
    assert r1["ok"]
    handle("share", 960, 5)
    r2 = handle("share", 960, 5)                  # بلافاصله دوباره → محدود
    assert r2["ok"] is False and "آرام" in r2["text"]
    B.RATE_LIMIT_ENABLED = False


def test_audit_log_written():                    # ایده ۷
    db.reset(":memory:"); GAMES.clear()
    handle("new", 970, 1, "Host")
    handle("join", 970, 2, "P2")
    evs = db.q_user_events(1)
    assert any(e["kind"] == "new" for e in evs)


def test_per_chat_lock_exists():                 # ایده ۱
    from karagah.bot import _lock
    l1 = _lock(111); l2 = _lock(111); l3 = _lock(222)
    assert l1 is l2 and l1 is not l3


def test_serial_killer_solo_win():               # ایده ۱۸
    g = _game(10, seed=2); g.start(6)
    sk = next((p for p in g.s.players.values() if p.role == "جانی سریالی"), None)
    if not sk:
        return
    for p in g.s.players.values():
        if p.uid != sk.uid:
            p.alive = False
    g._check_win()
    assert "جانی سریالی" in (g.s.winner or "")


def test_nine_ten_player_games_run():            # ایده ۱۷
    for n in (9, 10):
        g = _game(n, seed=n); g.start(1)
        assert len(g.s.players) == n
        assert g.s.officer_uid in g.s.players


def test_hunter_endpoint():                       # ایده ۱۵ (اندپوینت)
    db.reset(":memory:"); GAMES.clear()
    handle("new", 980, 1, "Host")
    for i in range(2, 10):
        handle("join", 980, i, f"P{i}")
    handle("startgame", 980, 1, arg="6")
    g = GAMES[980]
    hunter = next((p for p in g.s.players.values() if p.role == "شکارچی"), None)
    if hunter:
        tgt = next(p.uid for p in g.s.alive_players() if p.uid != hunter.uid)
        r = handle("hunter", 980, hunter.uid, arg=str(tgt))
        assert r["private"]


def test_endpoint_count_v3():
    assert len(bot.ENDPOINTS) == 56
