"""قراردادهای نسخه‌ی تازه: پیویِ نقش‌ها، جعبه‌ابزار قاتل، سرنخِ روزانه، و دکمه‌های زنده."""
import pytest

from karagah import bot, db, menus, ui
from karagah.bot import GAMES, handle
from karagah.models import Align, Custody, Phase
from karagah.roles import ROLES


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    bot._PENDING.clear()
    yield
    GAMES.clear()
    bot._PENDING.clear()


CHAT = 4242


def _started(n=10, case=5, chat=CHAT):
    handle("new", chat, 1, "Host")
    for i in range(2, n + 1):
        handle("join", chat, i, f"P{i}")
    handle("startgame", chat, 1, arg=str(case))
    return GAMES[chat]


def _cbs(kbd):
    return [b["callback_data"] for row in (kbd or {"inline_keyboard": []})["inline_keyboard"]
            for b in row if "callback_data" in b]


def _dm_to(res, uid):
    return [t for d, t, _k in res.get("dm", []) if d == uid]


def _role(g, name):
    return next(p for p in g.s.players.values() if p.role == name)


def _vote_out(g, chat=CHAT):
    handle("discuss", chat)
    handle("vote", chat)
    tgt = next(p.uid for p in g.s.alive_players()
               if p.can_vote and p.uid != g.s.officer_uid)
    for p in g.s.alive_players():
        if p.can_vote and p.uid != tgt:
            handle("castvote", chat, p.uid, arg=str(tgt))
    handle("closevote", chat)
    return tgt


# ---------- دکمه‌هایی که قبلاً هیچ کاری نمی‌کردند ----------
def test_abstain_button_actually_abstains():
    g = _started()
    handle("dawn", CHAT); handle("discuss", CHAT); handle("vote", CHAT)
    handle("castvote", CHAT, 2, arg="3")
    assert g.s.votes.get(2) == 3
    r = handle("castvote", CHAT, 2, arg="0")      # ⏭️ رای ممتنع
    assert r["ok"] and 2 not in g.s.votes


def test_hunter_button_without_argument_lists_targets():
    g = _started()
    h = next((p for p in g.s.players.values() if ROLES[p.role].ability == "hunter"), None)
    if h is None:
        pytest.skip("این ترکیب شکارچی ندارد")
    r = handle("hunter", CHAT, h.uid)
    assert r["ok"] and any(c.startswith("hunter:") for c in _cbs(r["keyboard"]))


def test_jury_button_always_answers_with_the_next_step():
    """قبلاً در فاز اشتباه فقط ⛔ می‌داد و کاربر فکر می‌کرد دکمه خراب است."""
    g = _started()
    r = handle("jury", CHAT, 2)                   # هنوز کسی در بازجویی نیست
    assert r["ok"] and r["keyboard"] and "رای‌گیری" in r["text"] + str(r["keyboard"])


def test_officer_can_refer_to_jury_instead_of_ruling():
    g = _started()
    handle("dawn", CHAT)
    _vote_out(g)
    handle("dawn", CHAT)                          # شبِ بازجویی گذشت
    r = handle("refer", CHAT, g.s.officer_uid)
    assert r["ok"] and g.s.phase is Phase.JURY
    assert _dm_to(r, 2)                           # برگه‌ی رای به پیوی رفت


# ---------- محرمانگیِ بازجو ----------
def test_officer_panel_never_lands_in_the_group():
    g = _started()
    handle("dawn", CHAT)
    tgt = _vote_out(g)
    r = handle("closevote", CHAT) if g.s.phase is Phase.VOTE else None
    grp = handle("status", CHAT)["text"]
    assert "اتاق بازجویی — فقط تو" not in grp
    # پنل فقط در dm و فقط برای بازجو
    handle("discuss", CHAT)


def test_officer_tools_are_private():
    g = _started()
    handle("dawn", CHAT)
    _vote_out(g)
    r = handle("hints", CHAT, g.s.officer_uid)
    assert r["ok"] and r["private"]
    assert handle("hints", CHAT, 2)["ok"] is False        # دیگران دسترسی ندارند


# ---------- پزشک: خودنجاتی یک بار ----------
def test_doctor_self_save_is_offered_once_then_withdrawn():
    g = _started(6, case=4)
    doc = next((p for p in g.s.players.values() if p.role == "پزشک"), None)
    if doc is None:
        pytest.skip("این ترکیب پزشک ندارد")
    assert doc.uid in g.legal_targets(doc.uid)            # بار اول در فهرست هست
    handle("act", CHAT, doc.uid, arg=str(doc.uid))
    handle("dawn", CHAT)
    assert doc.self_save_used
    g.s.phase = Phase.NIGHT
    assert doc.uid not in g.legal_targets(doc.uid)        # دیگر نیست
    other = next(p.uid for p in g.s.alive_players() if p.uid != doc.uid)
    assert handle("act", CHAT, doc.uid, arg=str(other))["ok"]


# ---------- جعبه‌ابزار قاتل ----------
def test_killer_can_choose_not_to_kill():
    g = _started()
    k = _role(g, "قاتل")
    handle("act", CHAT, k.uid, arg=str(next(
        u for u in g.legal_targets(k.uid))))
    r = handle("killer", CHAT, k.uid, arg="skip")
    assert r["ok"] and r["private"]
    handle("dawn", CHAT)
    assert not [p for p in g.s.players.values() if not p.alive]


def test_killer_plants_a_fake_fingerprint_that_misleads_the_detective():
    g = _started()
    k = _role(g, "قاتل")
    det = _role(g, "کارآگاه")
    innocent = next(p for p in g.s.alive_players()
                    if p.align is Align.CITY and p.uid not in (det.uid, k.uid))
    handle("killer", CHAT, k.uid, arg=f"plant:{innocent.uid}")
    handle("act", CHAT, det.uid, arg=str(innocent.uid))
    handle("dawn", CHAT)
    handle("discuss", CHAT); handle("vote", CHAT); handle("closevote", CHAT)
    handle("act", CHAT, det.uid, arg=str(innocent.uid))
    handle("dawn", CHAT)
    assert any("مشکوک" in n for n in det.notes)      # بی‌گناه، «مشکوک» دیده شد


def test_killer_fake_clue_appears_beside_the_real_ones():
    """سرنخ جعلی نباید جای سرنخ واقعی را بگیرد — باید کنارش بنشیند."""
    g = _started()
    k = _role(g, "قاتل")
    handle("killer", CHAT, k.uid, arg="clue:همسایه دیشب صدای جیغ شنید")
    r = handle("dawn", CHAT)
    today = g.today_hints()
    assert len(today) >= 2                       # سرنخ واقعی + سرنخ جعلی
    assert any("همسایه دیشب" in h for h in today)
    assert any("همسایه دیشب" not in h for h in today)   # واقعی هم هست
    assert all(h in r["text"] for h in today)    # همه در گزارش صبح


def test_threat_reaches_only_the_target_and_hides_the_sender():
    g = _started()
    k = _role(g, "قاتل")
    victim = next(p for p in g.s.alive_players() if p.align is Align.CITY)
    r = handle("killer", CHAT, k.uid, arg=f"threat:{victim.uid}")
    msgs = _dm_to(r, victim.uid)
    assert msgs and "بی‌امضا" in msgs[0]
    assert k.name not in msgs[0]                    # نام فرستنده لو نمی‌رود


def test_only_a_roleless_citizen_can_accept_the_recruitment():
    g = _started()
    k = _role(g, "قاتل")
    plain = next((p for p in g.s.alive_players() if p.role == "شهروند"), None)
    powered = _role(g, "کارآگاه")

    r = handle("killer", CHAT, k.uid, arg=f"recruit:{powered.uid}")
    assert "امکان پیوستن نداری" in _dm_to(r, powered.uid)[0]
    assert handle("recruit", CHAT, powered.uid, arg="1")["ok"] is False
    g.s.recruit_offer = None

    if plain is None:
        pytest.skip("این ترکیب شهروند ساده ندارد")
    r = handle("killer", CHAT, k.uid, arg=f"recruit:{plain.uid}")
    assert "می‌توانی بپذیری" in _dm_to(r, plain.uid)[0]
    assert handle("recruit", CHAT, plain.uid, arg="1")["ok"]
    assert plain.align is Align.KILLER and plain.recruited


def test_city_roles_cannot_open_the_killer_toolbox():
    g = _started()
    det = _role(g, "کارآگاه")
    assert handle("killer", CHAT, det.uid)["ok"] is False


# ---------- سناریو که ادامه پیدا می‌کند ----------
def test_every_day_brings_a_new_case_specific_clue():
    g = _started()
    seen = []
    for _ in range(4):                     # روز ۱ تا ۴
        handle("dawn", CHAT)
        seen.append(g.today_hint())
        if g.s.phase is Phase.END:
            break
        handle("discuss", CHAT); handle("vote", CHAT); handle("closevote", CHAT)
    assert len(seen) >= 3
    assert len(set(seen)) == len(seen)             # هیچ روزی تکرارِ روز قبل نیست
    assert any(g.s.case.place in h or g.s.case.weapon in h or g.s.case.victim in h
               for h in seen)                      # به همین پرونده گره خورده


def test_interrogation_hints_are_case_specific_and_shift_each_night():
    g = _started()
    handle("dawn", CHAT)
    _vote_out(g)
    off = g.s.officer_uid
    first = handle("hints", CHAT, off)["text"]
    # در همان شب پایدارند — وگرنه بازجو آن‌قدر دکمه می‌زند تا سرنخِ دلخواهش بیاید
    assert handle("hints", CHAT, off)["text"] == first
    # شبِ بعد سرنخ تازه است
    g.s.day += 1
    assert handle("hints", CHAT, off)["text"] != first
    assert g.s.case.place in first or g.s.case.weapon in first or \
           g.s.case.victim in first or g.s.case.motive in first


# ---------- یادداشتِ سپرده ----------
def test_shared_note_stays_hidden_until_temporary_jail():
    g = _started()
    handle("dawn", CHAT)
    tgt = _vote_out(g)
    p = g.s.players[tgt]
    handle("share_note", CHAT, tgt, arg="من پزشکم، مرا نکشید")
    assert p.shared_notes and not p.notes_published
    handle("dawn", CHAT)                                # شبِ بازجویی
    r = handle("verdict", CHAT, g.s.officer_uid, arg="1")   # 🔒 حبس موقت
    assert p.custody is Custody.TEMP_JAIL and p.notes_published
    assert any("صندوق امانات" in t for _d, t, _k in r["dm"])


# ---------- رای در پیوی ----------
def test_ballots_go_to_private_chats_not_the_group():
    g = _started()
    handle("dawn", CHAT); handle("discuss", CHAT)
    r = handle("vote", CHAT)
    voters = {p.uid for p in g.s.alive_players() if p.can_vote}
    assert {d for d, _t, _k in r["dm"]} == voters
    assert "پیوی" in r["text"]
    assert handle("castvote", CHAT, 2, arg="3")["private"] is True


def test_night_panels_are_pushed_to_each_role_privately():
    g = _started()
    handle("new", 4243, 1, "Host")
    for i in range(2, 11):
        handle("join", 4243, i, f"P{i}")
    r = handle("startgame", 4243, 1, arg="5")
    g2 = GAMES[4243]
    got = {d for d, _t, _k in r["dm"]}
    assert got == set(g2.s.players)                  # کارت نقش برای همه
    killer = next(p for p in g2.s.players.values() if p.role == "قاتل")
    assert any("جعبه‌ابزار" in t for t in _dm_to(r, killer.uid))


# ---------- ترتیب لابی ----------
def test_ready_works_before_join_too():
    handle("new", CHAT, 1, "Host")
    r = handle("ready", CHAT, 9, "Late")           # بدون «ورود» قبلی
    assert r["ok"] and GAMES[CHAT].s.players[9].ready


def test_lobby_screen_names_the_next_step():
    handle("new", CHAT, 1, "Host")
    assert "قدم ۱" in handle("join", CHAT, 2, "P2")["text"]
    for i in range(3, 6):
        handle("join", CHAT, i, f"P{i}")
    assert "قدم ۲" in ui.lobby_screen(GAMES[CHAT].s)
    for i in range(1, 6):
        handle("ready", CHAT, i, f"P{i}")
    assert "قدم ۳" in ui.lobby_screen(GAMES[CHAT].s)


# ---------- تابلوی زنده: ساعت‌شنی → ✅ ----------
def test_lobby_board_hourglass_flips_when_a_player_gets_ready():
    handle("new", CHAT, 1, "Host")
    for i in range(2, 6):
        handle("join", CHAT, i, f"P{i}")
    g = GAMES[CHAT]

    def waiting(txt):          # فقط سطرهای اسم، نه سطر راهنمای ⏳/✅
        return [l for l in txt.splitlines() if l.strip()[:1].isdigit() and "⏳" in l]

    assert len(waiting(ui.lobby_screen(g.s))) == 5
    r = handle("ready", CHAT, 3, "P3")
    assert r["refresh"], "ready باید تابلوی گروه را تازه کند"
    text, _kbd = r["refresh"]
    assert "✅ P3" in text and len(waiting(text)) == 4


def test_join_and_leave_republish_the_board():
    handle("new", CHAT, 1, "Host")
    assert handle("join", CHAT, 2, "P2")["board"] is True
    assert handle("leave", CHAT, 2, "P2")["board"] is True


def test_vote_board_tracks_who_voted_without_revealing_the_choice():
    g = _started()
    handle("dawn", CHAT); handle("discuss", CHAT)
    r = handle("vote", CHAT)
    assert r["board"] is True
    assert "⏳" in r["text"] and "🗳️" in r["text"]
    voter = next(p.uid for p in g.s.alive_players() if p.can_vote)
    other = next(p.uid for p in g.s.alive_players()
                 if p.can_vote and p.uid != voter)
    rv = handle("castvote", CHAT, voter, arg=str(other))
    assert rv["refresh"], "رای باید تابلوی گروه را تازه کند"
    text, _kbd = rv["refresh"]
    assert f"✅ {g.s.players[voter].name}" in text
    assert g.s.players[other].name not in text.split("📊")[0].split(
        f"✅ {g.s.players[voter].name}")[1][:3]   # به چه کسی رای داد لو نرود
    assert "رای ثبت شد" in text


def test_abstain_also_refreshes_the_board():
    g = _started()
    handle("dawn", CHAT); handle("discuss", CHAT); handle("vote", CHAT)
    voter = next(p.uid for p in g.s.alive_players() if p.can_vote)
    assert handle("castvote", CHAT, voter, arg="0")["refresh"]


# ---------- منو وسط بازی به قبل از بازی برنمی‌گردد ----------
def test_menu_does_not_offer_starting_a_new_game_mid_match():
    g = _started()
    r = handle("menu", CHAT, 2)
    cbs = _cbs(r["keyboard"])
    assert "new" not in cbs and "blitz" not in cbs, "منو نباید بازی در جریان را دور بیندازد"
    assert "surrender" in cbs
    # §۱۳.۵: سرصفحه‌ی مشترک — پرونده، دورِ جاری، فاز
    assert "دور ۱" in r["text"] and g.s.phase.value in r["text"]


def test_menu_returns_to_the_normal_one_in_lobby_and_after_the_end():
    handle("new", CHAT, 1, "Host")
    assert "new" in _cbs(handle("menu", CHAT, 1)["keyboard"])
    g = _started(chat=4344)
    for p in g.s.players.values():
        if p.align is Align.KILLER:
            p.alive = False
    g._check_win()
    assert "new" in _cbs(handle("menu", 4344, 1)["keyboard"])


def test_start_screen_mid_game_shows_the_in_game_menu():
    _started()
    assert "new" not in _cbs(handle("start", CHAT, 2)["keyboard"])


# ---------- تسلیم ----------
def test_surrender_asks_for_confirmation_first():
    g = _started()
    r = handle("surrender", CHAT, 4)
    assert r["ok"] and r["private"]
    assert "surrender:yes" in _cbs(r["keyboard"])
    assert g.s.players[4].in_game, "تا تایید نکرده نباید از بازی بیرون برود"


def test_surrender_removes_the_player_without_revealing_the_role():
    g = _started()
    role = g.s.players[4].role
    r = handle("surrender", CHAT, 4, arg="yes")
    assert r["ok"] and not g.s.players[4].in_game
    said = r["text"] + " ".join(t for _d, t, _k in r["dm"])
    assert role not in said, "نقشِ تسلیم‌شده نباید فاش شود"
    assert any("تسلیم شد" in t for _d, t, _k in r["dm"])


def test_surrender_clears_the_players_pending_night_action():
    g = _started()
    k = _role(g, "قاتل")
    tgt = next(iter(g.legal_targets(k.uid)))
    handle("act", CHAT, k.uid, arg=str(tgt))
    assert any(key.endswith(f":{k.uid}") for key in g.s.night_actions)
    handle("surrender", CHAT, k.uid, arg="yes")
    assert not any(key.endswith(f":{k.uid}") for key in g.s.night_actions)


def test_surrendering_host_hands_over_hosting():
    g = _started()
    assert g.owner == 1
    handle("surrender", CHAT, 1, arg="yes")
    assert g.owner != 1 and g.s.players[g.owner].in_game


def test_surrender_is_refused_in_the_lobby_and_after_the_end():
    handle("new", CHAT, 1, "Host")
    for i in range(2, 6):
        handle("join", CHAT, i, f"P{i}")
    assert handle("surrender", CHAT, 3)["ok"] is False


def test_surrendering_suspect_empties_the_interrogation_room():
    g = _started()
    handle("dawn", CHAT)
    tgt = _vote_out(g)
    assert g.s.suspect_uid == tgt
    handle("surrender", CHAT, tgt, arg="yes")
    assert g.s.suspect_uid is None


# ---------- غریبه نمی‌تواند بازی را بچرخاند ----------
@pytest.mark.parametrize("cmd,arg", [
    ("jury", ""), ("juryvote", "1"), ("castvote", "2"), ("dawn", ""),
    ("discuss", ""), ("vote", ""), ("closevote", ""), ("startgame", ""),
    ("surrender", "yes"), ("refer", ""), ("killer", "skip"),
])
def test_a_stranger_cannot_drive_the_game(cmd, arg):
    """قبلاً بعضی از این‌ها با KeyError کل فرمان را می‌ترکاندند."""
    g = _started()
    before = (g.s.phase, g.s.day, dict(g.s.votes), dict(g.s.jury_requests))
    r = handle(cmd, CHAT, 999, "غریبه", arg)
    assert r["ok"] is False
    assert "خطای داخلی" not in r["text"]
    assert (g.s.phase, g.s.day, dict(g.s.votes), dict(g.s.jury_requests)) == before


# ---------- هر نقش به داده‌ی خودش دسترسی دارد ----------
def test_every_role_info_kind_produces_a_real_archive():
    """هیچ info ای نباید فقط یک برچسب روی کارت نقش باشد."""
    seen = set()
    for n, case in ((10, 5), (9, 3), (8, 7), (7, 2), (6, 1)):
        chat = 5000 + n
        g = _started(n, case, chat)
        for p in g.s.players.values():
            r = handle("archive", chat, p.uid)
            kind = ROLES[p.role].info
            assert r["ok"] and r["private"], f"{p.role} بایگانی ندارد"
            assert len(r["text"]) > 80, f"بایگانی {p.role} تقریباً خالی است"
            assert "روز" in r["text"]
            seen.add(kind)
    assert seen >= {"hospital", "police_files", "forensic_files", "sightings",
                    "visit_log", "team_ids", "none"}


def test_doctor_archive_is_a_hospital_report():
    g = _started(6, case=4)
    doc = next((p for p in g.s.players.values() if p.role == "پزشک"), None)
    if doc is None:
        pytest.skip("این ترکیب پزشک ندارد")
    txt = handle("archive", CHAT, doc.uid)["text"]
    assert "درمانگاه" in txt
    assert "سهمیه‌ی نجاتِ خودت" in txt
    # محافظتِ ثبت‌شده رسید می‌گیرد
    other = next(u for u in g.legal_targets(doc.uid) if u != doc.uid)
    handle("act", CHAT, doc.uid, arg=str(other))
    handle("dawn", CHAT)
    assert g.s.players[other].name in handle("archive", CHAT, doc.uid)["text"]


def test_doctor_archive_is_not_an_alignment_oracle():
    """§۱۳ ST09: رتبه‌بندیِ «فشار عصبی» از هم‌ترازی می‌آمد و تیمِ بازیکن‌ها را لو می‌داد."""
    g = _started()
    doc = next((p for p in g.s.players.values() if p.role == "پزشک"), None)
    if doc is None:
        pytest.skip("این ترکیب پزشک ندارد")
    txt = handle("archive", CHAT, doc.uid)["text"]
    assert "فشار عصبی" not in txt
    for band in ("آرام", "بی‌قرار", "در آستانه‌ی فروپاشی"):
        assert band not in txt


def test_forensic_archive_does_not_hand_out_unearned_answers():
    """§۱۳ ST10: توییستِ پرونده و فهرستِ مدارکِ جعلی نباید مجانی باشند."""
    g = _started()
    fo = next((p for p in g.s.players.values()
               if ROLES[p.role].info == "forensic_files"), None)
    if fo is None:
        pytest.skip("این ترکیب نقشِ پزشکی قانونی ندارد")
    txt = handle("archive", CHAT, fo.uid)["text"]
    assert g.s.case.twist not in txt
    fake = [e["code"] for e in g.s.case.evidence if e["misleading"]]
    assert not any(f"• {c}" in txt for c in fake)
    # ولی نتیجه‌ی آزمایشی که خودش خرج کرده، می‌آید
    if ROLES[fo.role].ability == "autopsy":
        handle("act", CHAT, fo.uid, arg=str(next(iter(g.legal_targets(fo.uid)))))
        handle("dawn", CHAT)
        assert "🧪" in handle("archive", CHAT, fo.uid)["text"]


def test_coroner_reports_the_real_cause_not_the_case_weapon():
    """§۷.۳: «هر مرگ را با سلاحِ پرونده توصیف نکن.»"""
    g = _started()
    cor = next((p for p in g.s.players.values() if p.role == "کالبدشکاف"), None)
    k = _role(g, "قاتل")
    if cor is None:
        pytest.skip("این ترکیب کالبدشکاف ندارد")
    victim = next(u for u in g.legal_targets(k.uid) if u != cor.uid)
    handle("act", CHAT, k.uid, arg=str(victim))
    handle("dawn", CHAT)
    notes = " ".join(cor.notes)
    assert "حمله‌ی مستقیم" in notes
    assert g.s.case.weapon not in notes
    assert g.s.death_cause[victim] == "حمله‌ی مستقیم"


def test_officer_archive_holds_police_files_and_the_plate():
    g = _started()
    txt = handle("archive", CHAT, g.s.officer_uid)["text"]
    assert "پرونده‌های پلیس" in txt
    assert g.s.case.vehicle["plate"] in txt
    assert "سوابق کیفری" in txt


def test_plate_number_is_police_only_while_colour_and_model_are_public():
    g = _started()
    plate = g.s.case.vehicle["plate"]
    handle("dawn", CHAT)
    public = handle("dawn", CHAT)["text"] if False else " ".join(g.s.day_hints)
    assert g.s.case.vehicle["model"] in public
    assert g.s.case.vehicle["color"] in public
    assert plate not in public, "پلاک نباید علنی شود"
    for p in g.s.players.values():
        if ROLES[p.role].info != "police_files":
            assert plate not in handle("archive", CHAT, p.uid)["text"]


def test_only_police_can_look_up_the_plate_owner():
    """استعلام ثبت می‌شود؛ نتیجه سحر می‌رسد و فقط به خودِ پلیس."""
    g = _started()
    r = handle("plate", CHAT, g.s.officer_uid)
    assert r["ok"] and r["private"]
    assert g.s.players[g.s.plate_owner].name not in r["text"]   # هنوز نه
    owner = g.s.players[g.s.plate_owner].name
    d = handle("dawn", CHAT)
    got = _dm_to(d, g.s.officer_uid)
    assert got and owner in got[0]
    assert all(owner not in t for uid, t, _k in d["dm"] if uid != g.s.officer_uid)
    for p in g.s.players.values():
        if p.uid != g.s.officer_uid:
            assert handle("plate", CHAT, p.uid)["ok"] is False


def test_plate_inquiry_is_one_per_night():
    g = _started()
    assert handle("plate", CHAT, g.s.officer_uid)["ok"]
    assert handle("plate", CHAT, g.s.officer_uid)["ok"] is False   # در جریان
    handle("dawn", CHAT)
    assert handle("plate", CHAT, g.s.officer_uid)["ok"] is False   # همان شب


def test_undelivered_plate_result_is_not_inherited():
    """پلیسِ کشته‌شده نتیجه نمی‌گیرد و کسی جایش آن را نمی‌برد (§۱۲.۳)."""
    g = _started()
    handle("plate", CHAT, g.s.officer_uid)
    g.s.players[g.s.officer_uid].alive = False
    d = handle("dawn", CHAT)
    owner = g.s.players[g.s.plate_owner].name
    assert all(owner not in t for _u, t, _k in d["dm"])


def test_killer_can_forge_the_vehicle_registration_once():
    g = _started()
    k = _role(g, "قاتل")
    victim = next(p for p in g.s.alive_players()
                  if p.uid not in (k.uid, g.s.officer_uid))
    handle("plate", CHAT, g.s.officer_uid)          # پلیس قبلاً استعلام گرفته
    handle("dawn", CHAT)                             # و نتیجه‌اش را گرفته
    _vote_out(g)                                     # شبِ بعد: جعل سند ممکن است
    r = handle("killer", CHAT, k.uid, arg=f"plate:{victim.uid}")
    assert r["ok"] and g.s.plate_owner == victim.uid
    assert any("اصلاحیه" in t for _d, t, _k in r["dm"]), "پلیس باید خبردار شود"
    again = handle("killer", CHAT, k.uid, arg=f"plate:{k.uid}")
    assert again["ok"] is False                      # فقط یک بار
    # استعلام تازه حالا نام جعلی را می‌دهد
    handle("plate", CHAT, g.s.officer_uid)
    d = handle("dawn", CHAT)
    assert any(victim.name in t for t in _dm_to(d, g.s.officer_uid))


def test_grocer_hears_a_new_rumour_each_day():
    g = _started()
    grocer = next((p for p in g.s.players.values() if p.role == "بقال محله"), None)
    if grocer is None:
        pytest.skip("این ترکیب بقال ندارد")
    seen = []
    for _ in range(3):
        seen.append(handle("archive", CHAT, grocer.uid)["text"])
        g.s.day += 1
    assert len(set(seen)) == 3


def test_roleless_citizen_is_told_plainly_it_has_no_archive():
    g = _started()
    plain = next((p for p in g.s.players.values() if p.role == "شهروند"), None)
    if plain is None:
        pytest.skip("این ترکیب شهروند ساده ندارد")
    txt = handle("archive", CHAT, plain.uid)["text"]
    assert "پرونده‌ی اختصاصی ندارد" in txt


def test_archive_is_refused_before_the_game_starts():
    handle("new", CHAT, 1, "Host")
    for i in range(2, 6):
        handle("join", CHAT, i, f"P{i}")
    assert handle("archive", CHAT, 2)["ok"] is False


# ---------- منو وسط بازی فقط دکمه‌های بازی ----------
def test_command_hub_hides_non_game_groups_mid_match():
    g = _started()
    cbs = _cbs(handle("commands", CHAT, 2)["keyboard"])
    assert "group:play" in cbs and "group:clues" in cbs
    for hidden in ("group:progress", "group:table", "group:guide", "group:admin"):
        assert hidden not in cbs, f"{hidden} وسط بازی نباید دیده شود"


def test_command_hub_shows_everything_again_in_the_lobby():
    handle("new", CHAT, 1, "Host")
    cbs = _cbs(handle("commands", CHAT, 1)["keyboard"])
    for key, _t, _i in menus.GROUPS:
        assert f"group:{key}" in cbs


def test_pregame_buttons_are_stripped_from_in_game_group_pages():
    g = _started()
    actor = next(p for p in g.s.alive_players()
                 if ROLES[p.role].ability not in ("", "hunter"))
    cbs = _cbs(handle("group", CHAT, actor.uid, arg="play")["keyboard"])
    for bad in ("new", "blitz", "join", "leave", "startgame", "ready"):
        assert bad not in cbs, f"«{bad}» وسط بازی نباید در فهرست باشد"
    assert "act" in cbs and "dashboard" in cbs


def test_menus_are_built_from_this_actors_legal_actions():
    """§۱۳ ST03: نقشی که اکشن شبانه ندارد نباید دکمه‌ی آن را ببیند."""
    g = _started()
    idle = next((p for p in g.s.alive_players()
                 if ROLES[p.role].ability in ("", "hunter")
                 and p.uid != g.s.officer_uid), None)
    if idle is None:
        pytest.skip("همه‌ی نقش‌های این ترکیب اکشن شبانه دارند")
    assert "act" not in _cbs(handle("group", CHAT, idle.uid, arg="play")["keyboard"])
    assert "act" not in _cbs(handle("menu", CHAT, idle.uid)["keyboard"])


def test_only_the_officer_sees_police_and_interrogation_controls():
    """§۱۳ ST02: شهروند نباید دکمه‌ی پلیس/پلاک/بازجویی ببیند."""
    g = _started()
    civ = next(p for p in g.s.alive_players()
               if p.uid != g.s.officer_uid and p.align is Align.CITY)
    seen = set()
    for key, _t, _i in menus.visible_groups(g.s, g, civ):
        seen |= set(_cbs(menus.group_kb(key, g.s, g, civ)))
    for secret in ("plate", "hints", "ask", "verdict", "refer", "clear"):
        assert secret not in seen, f"«{secret}» نباید برای شهروند دیده شود"
    off = g.s.players[g.s.officer_uid]
    off_seen = set()
    for key, _t, _i in menus.visible_groups(g.s, g, off):
        off_seen |= set(_cbs(menus.group_kb(key, g.s, g, off)))
    assert {"plate", "hints", "verdict"} <= off_seen


def test_only_the_killer_team_sees_the_criminal_category():
    g = _started()
    civ = next(p for p in g.s.alive_players() if p.align is Align.CITY)
    k = _role(g, "قاتل")
    civ_groups = [key for key, _t, _i in menus.visible_groups(g.s, g, civ)]
    k_groups = [key for key, _t, _i in menus.visible_groups(g.s, g, k)]
    assert "dark" not in civ_groups
    assert "dark" in k_groups


def test_host_management_is_host_only_and_offers_no_new_game():
    g = _started()
    r = handle("manage", CHAT, 1)
    assert r["ok"] and r["private"]
    cbs = _cbs(r["keyboard"])
    assert "pause" in cbs and "host" in cbs
    for bad in ("new", "blitz", "newtable", "rematch", "startgame"):
        assert bad not in cbs
    other = next(p.uid for p in g.s.alive_players() if p.uid != 1)
    assert handle("manage", CHAT, other)["ok"] is False


def test_navigation_from_a_private_chat_keeps_the_live_match():
    """§۱۳ ST04: Home/Back در پیوی نباید منوی پیش از بازی را بیاورد."""
    from karagah.bot import route_chat
    g = _started()
    for cmd in ("menu", "back"):
        assert route_chat(cmd, 5, 5, private=True) == CHAT
    r = handle("menu", CHAT, 5)
    assert "new" not in _cbs(r["keyboard"])
    assert "دور ۱" in r["text"]


def test_cancel_returns_to_the_game_menu_not_the_lobby_hub():
    """§۱۳ ST05: لغو هم باید بافتِ بازی را حفظ کند."""
    g = _started()
    handle("note", CHAT, 3)
    cbs = _cbs(handle("cancel", CHAT, 3)["keyboard"])
    for bad in ("group:progress", "group:table", "group:guide", "group:admin"):
        assert bad not in cbs


def test_hidden_group_page_falls_back_to_the_hub_mid_match():
    g = _started()
    r = handle("group", CHAT, 2, arg="progress")
    assert r["ok"] and "group:progress" not in _cbs(r["keyboard"])


# ---------- ربات روز جاری را همه‌جا نگه می‌دارد ----------
def test_the_current_day_is_reported_everywhere():
    g = _started()
    for _ in range(2):
        handle("dawn", CHAT)
        handle("discuss", CHAT); handle("vote", CHAT); handle("closevote", CHAT)
    day = g.s.day
    fa = str(day).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
    for cmd in ("commands", "menu"):
        assert fa in handle(cmd, CHAT, 2)["text"] or str(day) in handle(cmd, CHAT, 2)["text"]
    assert str(day) in handle("status", CHAT, 2)["text"]
    assert fa in handle("archive", CHAT, 2)["text"]


def test_day_counter_advances_once_per_cycle():
    g = _started()
    days = [g.s.day]
    for _ in range(3):
        handle("dawn", CHAT)
        if g.s.phase is Phase.END:
            break
        handle("discuss", CHAT); handle("vote", CHAT); handle("closevote", CHAT)
        days.append(g.s.day)
    assert days == sorted(days), "روز نباید عقب برود"
    assert all(b - a == 1 for a, b in zip(days, days[1:])), f"پرش در شمارش روز: {days}"


# ---------- چرخه‌ی دسترسی: دادن، تعلیق، گرفتن (hints.md §۱۲.۳) ----------
def _police(g):
    return g.s.players[g.s.officer_uid]


def test_custody_suspends_new_queries_but_keeps_the_old_archive_readable():
    g = _started()
    pol = _police(g)
    fresh_txt = handle("archive", CHAT, pol.uid)["text"]
    assert "فریز" not in fresh_txt

    pol.custody = Custody.TEMP_JAIL
    r = handle("archive", CHAT, pol.uid)
    assert r["ok"], "بایگانی باید در بازداشت هم خواندنی بماند"
    assert "فریز" in r["text"] and "بازداشت" in r["text"]
    assert handle("plate", CHAT, pol.uid)["ok"] is False   # جستجوی تازه نه

    pol.custody = Custody.FREE                              # آزاد شد
    assert "فریز" not in handle("archive", CHAT, pol.uid)["text"]
    assert handle("plate", CHAT, pol.uid)["ok"]


def test_death_and_surrender_revoke_new_access_but_not_history():
    g = _started()
    pol = _police(g)
    pol.alive = False
    r = handle("archive", CHAT, pol.uid)
    assert r["ok"] and "فریز" in r["text"]
    assert handle("plate", CHAT, pol.uid)["ok"] is False

    g2 = _started(chat=4499)
    victim = next(p for p in g2.s.alive_players() if p.uid != g2.s.officer_uid)
    handle("surrender", 4499, victim.uid, arg="yes")
    r2 = handle("archive", 4499, victim.uid)
    assert r2["ok"] and "فریز" in r2["text"]


def test_a_paused_game_freezes_new_queries():
    g = _started()
    handle("pause", CHAT, 1)
    assert handle("plate", CHAT, g.s.officer_uid)["ok"] is False
    assert "فریز" in handle("archive", CHAT, g.s.officer_uid)["text"]
    handle("resume", CHAT, 1)
    assert handle("plate", CHAT, g.s.officer_uid)["ok"]


def test_host_transfer_grants_no_specialist_access():
    g = _started()
    plain = next(p for p in g.s.alive_players()
                 if ROLES[p.role].info not in ("police_files",))
    handle("host", CHAT, 1, arg=str(plain.uid))
    assert g.owner == plain.uid
    assert handle("plate", CHAT, plain.uid)["ok"] is False
    assert g.s.case.vehicle["plate"] not in handle("archive", CHAT, plain.uid)["text"]


def test_recruited_citizen_joins_the_team_without_the_killer_toolkit():
    """§۱۲.۲: عضویت در تیم، ابزار تخصصی نمی‌آورد."""
    g = _started()
    k = _role(g, "قاتل")
    plain = next((p for p in g.s.alive_players() if p.role == "شهروند"), None)
    if plain is None:
        pytest.skip("این ترکیب شهروند ساده ندارد")
    handle("killer", CHAT, k.uid, arg=f"recruit:{plain.uid}")
    assert handle("recruit", CHAT, plain.uid, arg="1")["ok"]
    assert plain.align is Align.KILLER              # هم‌تیمی شد
    for tool in ("skip", "plant:2", "clue:متن", "threat:2", "plate:2"):
        assert handle("killer", CHAT, plain.uid, arg=tool)["ok"] is False
    assert g.s.case.vehicle["plate"] not in handle("archive", CHAT, plain.uid)["text"]


def test_the_simulated_plate_is_never_mistakable_for_a_real_one():
    """§۱۲.۵: شناسه باید آشکارا ساختگی باشد."""
    g = _started()
    plate = g.s.case.vehicle["plate"]
    assert plate.startswith("SIM-") and "نمونه‌ی بازی" in plate
