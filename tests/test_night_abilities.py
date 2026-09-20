"""اکشن‌های شبانه باید واقعاً اثر کنند و اطلاعات فقط سحر برسد."""
import pytest

from karagah import db
from karagah.bot import GAMES
from karagah.engine import Game, RuleError
from karagah.models import Align, Custody, Phase


@pytest.fixture(autouse=True)
def fresh():
    db.reset(":memory:")
    GAMES.clear()
    yield
    GAMES.clear()


def _game(n=10, seed=3, case=5) -> Game:
    g = Game(chat_id=1, seed=seed)
    for i in range(1, n + 1):
        g.join(i, f"بازیکن{i}")
    g.start(case)
    return g


def _role(g, name):
    return next(p for p in g.s.players.values() if p.role == name)


def _other(g, *exclude):
    ex = {p.uid if hasattr(p, "uid") else p for p in exclude}
    return next(p.uid for p in g.s.alive_players() if p.uid not in ex)


# ---------- باگ ۵: کارآگاه در یک شب همه را استعلام می‌کرد ----------
def test_investigation_gives_no_instant_answer():
    g = _game()
    det = _role(g, "کارآگاه")
    tgt = _other(g, det)
    out = g.night_action(det.uid, tgt)
    assert "پاک" not in out and "مشکوک" not in out     # جواب لو نمی‌رود
    assert det.notes == []                             # هنوز چیزی ثبت نشده


def test_switching_target_yields_only_one_result():
    g = _game()
    det = _role(g, "کارآگاه")
    a = _other(g, det)
    b = _other(g, det, a)
    c = _other(g, det, a, b)
    for t in (a, b, c):
        g.night_action(det.uid, t)                     # مدام هدف را عوض می‌کند
    g.resolve_night()
    results = [n for n in det.notes if n.startswith("شب")]
    assert len(results) == 1                           # فقط آخرین انتخاب
    assert g.s.players[c].name in results[0]


def test_investigation_result_arrives_at_dawn():
    g = _game()
    det = _role(g, "کارآگاه")
    killer = _role(g, "قاتل")
    g.night_action(det.uid, killer.uid)
    g.resolve_night()
    assert any("مشکوک" in n for n in det.notes)


def test_detective_cannot_spend_night_twice():
    g = _game()
    det = _role(g, "کارآگاه")
    fake = next(e["code"] for e in g.s.case.evidence if e["misleading"])
    g.expose(det.uid, fake)
    with pytest.raises(RuleError):
        g.night_action(det.uid, _other(g, det))


# ---------- باگ ۶: توانایی‌ها ثبت می‌شدند ولی اثری نداشتند ----------
def test_poison_kills_two_nights_later():
    g = _game()
    poisoner = _role(g, "سم‌ساز")
    victim = g.s.players[_other(g, poisoner)]
    g.night_action(poisoner.uid, victim.uid)
    g.resolve_night()
    assert victim.alive                                # شب ۱: هنوز زنده
    g.s.phase, g.s.day = Phase.NIGHT, g.s.day + 1
    g.resolve_night()
    assert victim.alive                                # شب ۲: هنوز زنده
    g.s.phase, g.s.day = Phase.NIGHT, g.s.day + 1
    g.resolve_night()
    assert not victim.alive                            # شب ۳: سم کارش را کرد


def test_doctor_cures_poison():
    g = _game()
    poisoner = _role(g, "سم‌ساز")
    doc = _role(g, "پزشک")
    victim = g.s.players[_other(g, poisoner, doc)]
    g.night_action(poisoner.uid, victim.uid)
    g.resolve_night()
    g.s.phase, g.s.day = Phase.NIGHT, g.s.day + 1
    g.resolve_night()
    g.s.phase, g.s.day = Phase.NIGHT, g.s.day + 1
    g.night_action(doc.uid, victim.uid)          # دقیقاً شبِ سررسید سم
    g.resolve_night()
    assert victim.alive
    assert any("پادزهر" in l for l in g.s.log)


def test_frame_makes_innocent_look_guilty():
    g = _game()
    acc = _role(g, "همدست")
    det = _role(g, "کارآگاه")
    mark = next(p for p in g.s.alive_players()
                if p.align is Align.CITY and p.uid not in (det.uid, acc.uid))
    g.night_action(acc.uid, mark.uid)
    g.resolve_night()
    g.s.phase, g.s.day = Phase.NIGHT, g.s.day + 1
    g.night_action(det.uid, mark.uid)
    g.resolve_night()
    assert any(mark.name in n and "مشکوک" in n for n in det.notes)


def test_smuggler_hides_target_from_detective():
    """هیچ ترکیبی قاچاقچی ندارد، پس نقش را دستی می‌گذاریم."""
    g = _game()
    det = _role(g, "کارآگاه")
    smug = next(p for p in g.s.alive_players()
                if p.role == "کالبدشکاف")
    smug.role, smug.align = "قاچاقچی", Align.NEUTRAL
    killer = _role(g, "قاتل")
    g.night_action(smug.uid, killer.uid)
    g.night_action(det.uid, killer.uid)
    g.resolve_night()
    assert any(killer.name in n and "پاک" in n for n in det.notes)


def test_watcher_counts_visits():
    g = _game()
    watcher = _role(g, "نگهبان")
    killer = _role(g, "قاتل")
    victim = g.s.players[_other(g, watcher, killer)]
    g.night_action(killer.uid, victim.uid)
    g.night_action(watcher.uid, victim.uid)
    g.resolve_night()
    assert any("ملاقات" in n for n in watcher.notes)
    note = next(n for n in watcher.notes if "ملاقات" in n)
    assert "1 ملاقات" in note


def test_spy_learns_interrogation_target():
    g = Game(chat_id=2, seed=3)
    for i in range(1, 10):
        g.join(i, f"بازیکن{i}")
    g.start(5)
    spy = _role(g, "خبرچین")
    sus = next(p for p in g.s.alive_players() if p.uid not in (spy.uid, g.s.officer_uid))
    g.s.suspect_uid = sus.uid
    g.night_action(spy.uid, _other(g, spy))
    g.resolve_night()
    assert any(sus.name in n for n in spy.notes)
