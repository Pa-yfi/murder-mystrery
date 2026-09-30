"""سناریوهای هدفمند: موقعیت‌هایی که بازیِ تصادفی به‌ندرت می‌سازد.

هر سناریو یک میز واقعی با agentها می‌سازد. «چیدمان صحنه» (مثلاً اینکه چه
کسی به بازجویی برود) تا جای ممکن هم با دکمه انجام می‌شود؛ جایی که لازم است
صحنه مستقیم چیده شود (مثل رساندن بازی به دو بازمانده) در کد گفته شده.
خودِ کاری که سنجیده می‌شود همیشه با تپ روی دکمه انجام می‌شود.

هر سناریو قاعده‌ی درست (RULES.md) را می‌سنجد: اگر ربات درست رفتار کند یک ✅
در جدول «بررسی‌ها» ثبت می‌شود، وگرنه یک یافته با شرح دقیق.
"""
from __future__ import annotations

import traceback
from typing import Callable, List, Optional

from karagah import bot, engine
from karagah.bot import GAMES
from karagah.models import Align, Custody, Phase
from karagah.roles import ROLES

from .agent import Agent, cb_is, cb_starts
from .game import Session
from .report import Report


class Scene:
    def __init__(self, report: Report, rb, n: int, seed: int, title: str, lobby=True,
                 scenario: str = "classic"):
        self.s = Session(n, seed, report, rb, "group", scenario)
        report.context = f"سناریو: {title} ({n} نفره، بذر {seed})"
        self.r = report
        self.ok = self.s.lobby() if lobby else True
        report.context = f"سناریو: {title} ({n} نفره، بذر {seed})"

    @property
    def g(self):
        return self.s.g

    @property
    def host(self) -> Agent:
        return self.s.host

    def role(self, name: str) -> Optional[Agent]:
        return next((a for a in self.s.agents if a.role == name), None)

    def others(self, *skip: Agent) -> List[Agent]:
        ids = {a.uid for a in skip if a}
        return [a for a in self.s.agents if a.uid not in ids and self.g.s.players[a.uid].in_game]

    def citizen(self, *skip: Agent) -> Agent:
        """یک بازیکنِ شهری (ترجیحاً بی‌اکشن، غیر از بازجو) برای نقش قربانی/متهم."""
        pool = [a for a in self.others(*skip) if ROLES[a.role].align is Align.CITY
                and a.uid != self.g.s.officer_uid]
        plain = [a for a in pool if not ROLES[a.role].ability]
        return (plain or pool)[0]

    # ── دکمه‌ها ──
    def act(self, a: Agent, target: Agent):
        panel = a.tap(cb_is("act"), ("dm",), depth=3, nav="act")
        hit = a.find(cb_is(f"act:{target.uid}"), ("dm",), 1)
        return a.press(*hit) if hit else panel

    def offered(self, a: Agent, target: Agent) -> bool:
        a.tap(cb_is("act"), ("dm",), depth=3, nav="act")
        return a.find(cb_is(f"act:{target.uid}"), ("dm",), 1) is not None

    def dawn(self, by: Optional[Agent] = None):
        """میزبان «پایان شب» را می‌زند؛ اگر هنوز منتظرِ اکشن است، تا پایان مهلت صبر می‌کند."""
        by = by or self.host
        m = by.tap(cb_is("dawn"), ("group",), depth=60)
        if m is not None and not m.ok and "⏳" in m.text:
            self.s.tg.clock.advance((self.g.remaining() or 0) + 1)
            m = by.tap(cb_is("dawn"), ("group",), depth=60)
        return m

    def discuss_and_vote(self):
        self.host.tap(cb_is("discuss"), ("group",), depth=60)
        return self.host.tap(cb_is("vote"), ("group",), depth=6)

    def close_vote(self):
        m = self.host.tap(cb_is("closevote"), ("group",), depth=10)
        if m is not None and not m.ok and "⏳" in m.text:
            self.s.tg.clock.advance((self.g.remaining() or 0) + 1)
            m = self.host.tap(cb_is("closevote"), ("group",), depth=10)
        return m

    def vote_all(self, target: Agent):
        for a in self.s.agents:
            p = self.g.s.players[a.uid]
            if p.can_vote and a.uid != target.uid:
                a.tap(cb_is(f"vote:{target.uid}"), ("group",), depth=60)
            elif p.can_vote:
                a.tap(cb_is("vote:0"), ("group",), depth=60)
        return self.close_vote()

    def no_vote_night(self):
        """روز بدون بازداشت: گفتگو → رای → همه ممتنع → شب."""
        self.discuss_and_vote()
        for a in self.s.agents:
            if self.g.s.players[a.uid].can_vote:
                a.tap(cb_is("vote:0"), ("group",), depth=60)
        return self.close_vote()

    def verdict(self, x: int):
        off = self.s.agent(self.g.s.officer_uid)
        sus = self.g.s.suspect_uid
        return off.tap(cb_is(f"ver:{sus}:{x}"), ("group",), depth=60)

    def interrogate(self, target: Agent):
        """از وضعیت فعلی تا جایی که target در بازجویی است (فقط با دکمه)."""
        if self.g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
            self.dawn()
        if self.g.awaiting_verdict() and self.g.s.phase is Phase.MORNING:
            self.verdict(0)
        self.discuss_and_vote()
        return self.vote_all(target)

    def stormy(self) -> bool:
        return self.g.s.night_event.startswith("طوفان")


def _try(report: Report, rb, title: str, fn: Callable[[Scene], Optional[bool]],
         n: int, seeds=range(1, 12), scenario: str = "classic") -> None:
    """سناریو را با بذرهای مختلف امتحان کن تا صحنه (بدون طوفان و …) جور شود.
    fn اگر False برگرداند یعنی «صحنه جور نشد، بذر بعدی»."""
    for seed in seeds:
        sc = Scene(report, rb, n, seed, title, scenario=scenario)
        try:
            if not sc.ok:
                continue
            if fn(sc) is not False:
                return
        except Exception as e:                         # خطای خودِ سناریو، نه ربات
            report.find("پایین", "playtest", f"سناریو «{title}» اجرا نشد",
                        f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=3)}")
            return
        finally:
            sc.s.tg.close()
    report.find("پایین", "playtest", f"سناریو «{title}» صحنه‌ی مناسب پیدا نکرد")


def _lobby_only(report: Report, rb, title: str, fn, n: int = 6) -> None:
    """لابی با همه‌ی آماده‌ها ولی بدون زدن «شروع» — برای سناریوهای پیش از بازی."""
    sc = Scene(report, rb, n, 1, title, lobby=False)
    try:
        s = sc.s
        for a in s.agents:
            a.read_docs(rb)
        s.tg.command(s.host.uid, "/new", s.group)
        for a in s.agents[1:]:
            a.tap(cb_is("join"), ("group",))
        for a in s.agents:
            a.tap(lambda b: "start=ready_" in b.get("url", ""), ("group",), depth=8)
        fn(sc)
    except Exception as e:
        report.find("پایین", "playtest", f"سناریو «{title}» اجرا نشد", f"{type(e).__name__}: {e}")
    finally:
        sc.s.tg.close()


# ───────────────────────── دسترسی ─────────────────────────
def p_early_dawn(sc: Scene):
    """قاتل اکشنش را می‌زند و فوراً «پایان شب» را می‌زند؛ غریبه «گفتگو» را می‌زند."""
    killer = sc.role("قاتل")
    victim = sc.citizen(killer)
    sc.act(killer, victim)
    m = killer.tap(cb_is("dawn"), ("group",), depth=60)
    if m and m.ok:
        sc.r.find("بالا", "دسترسی", "هر کسی — حتی خودِ قاتل — می‌تواند شب را زودتر ببندد",
                  "قاتل اکشنش را زد و «🌙 پایان شب» را زد، پیش از آنکه بقیه اکشن بدهند.",
                  key="phase-authz")
    else:
        sc.r.ok("دسترسی: شب تا اکشنِ همه یا پایان مهلت بسته نمی‌شود")
    sc.dawn()
    outsider = 999_001
    sc.s.tg.names[outsider] = "غریبه"
    grp = sc.s.tg.inbox(sc.s.group)
    msg = next((m for m in reversed(grp) for b in m.buttons() if b.get("callback_data") == "discuss"), None)
    if msg and sc.g.s.phase is Phase.MORNING and not sc.g.awaiting_verdict():
        sc.s.tg.press(outsider, msg, next(b for b in msg.buttons() if b.get("callback_data") == "discuss"))
        if sc.g.s.phase is Phase.DISCUSSION:
            sc.r.find("بالا", "دسترسی", "کسی که اصلاً در بازی نیست فاز را جلو می‌برد", key="outsider-phase")
        else:
            sc.r.ok("دسترسی: غریبه فاز را جلو نمی‌برد")


def p_non_host_start(sc: Scene):
    other = sc.s.agents[-1]
    hit = other.find(cb_is("startgame"), ("group",), 10)
    if hit:
        other.press(*hit)
    if sc.g.s.phase is Phase.NIGHT:
        sc.r.find("متوسط", "دسترسی", "هر عضو لابی — نه فقط میزبان — می‌تواند بازی را شروع کند",
                  key="start-authz")
    else:
        sc.r.ok("دسترسی: فقط میزبان بازی را شروع می‌کند")


def p_outsider_jury(sc: Scene):
    target = sc.citizen()
    sc.interrogate(target)
    if sc.g.s.suspect_uid != target.uid:
        return False
    sc.dawn()
    if sc.g.s.phase is not Phase.MORNING:
        return False
    outsider = 999_002
    sc.s.tg.names[outsider] = "غریبه"
    msg = sc.s.tg.command(outsider, "/dashboard", sc.s.group)
    b = next((x for x in msg.buttons() if x.get("callback_data") == "jury"), None)
    if b:
        r = sc.s.tg.press(outsider, msg, b)             # «خطای داخلی» را جدول خودش گزارش می‌کند
        if r and not r.ok and "خطای داخلی" not in r.text:
            sc.r.ok("هیئت منصفه: غریبه پیام قانون می‌گیرد")


def p_outsider_interp(sc: Scene):
    """غریبه در گروه «/interp» را از منوی دستورهای ربات می‌زند."""
    outsider = Agent(999_003, "غریبه", sc.s.tg, sc.s.rng)
    m = sc.s.tg.command(outsider.uid, "/interp", sc.s.group)
    if m.ok and outsider.find(cb_starts("interp:"), ("group",), 1):
        sc.r.find("پایین", "دسترسی", "کسی که در بازی نیست در رای تفسیر مدرک شرکت می‌کند",
                  key="outsider-interp")
    else:
        sc.r.ok("دسترسی: تفسیر/آزمایشگاه فقط برای بازیکن‌ها")


def p_ban(sc: Scene):
    bot.ADMIN_IDS.append(sc.host.uid)
    try:
        victim = next(a for a in sc.s.agents[1:] if ROLES[a.role].ability not in ("", "hunter"))
        sc.host.navigate("admin_ban")
        hit = sc.host.find(cb_is(f"admin_ban:{victim.uid}"), ("dm",), 1)
        if not hit:
            return False
        sc.host.press(*hit)
        m = victim.tap(cb_is("act"), ("dm",), depth=3, nav="act")
        if m and m.ok and victim.buttons_named(m, "act:"):
            sc.r.find("متوسط", "امنیت", "کاربرِ مسدودشده به بازی ادامه می‌دهد", key="ban-ignored")
        else:
            sc.r.ok("مسدودسازی: کاربر بسته‌شده دکمه‌ای نمی‌زند")
    finally:
        bot.ADMIN_IDS.remove(sc.host.uid)


def p_pause(sc: Scene):
    other = sc.s.agents[1]
    m = other.navigate("pause")
    if m and m.ok:
        sc.r.find("متوسط", "دسترسی", "غیرمیزبان بازی را متوقف کرد")
    sc.host.navigate("pause")
    if not sc.g.s.paused:
        sc.r.find("متوسط", "میزبانی", "دکمه‌ی «⏸️ توقف» بازی را متوقف نکرد")
        return None
    sc.s.tg.clock.advance(3600)
    sc.s.tg.timer_job()
    if sc.g.s.phase is not Phase.NIGHT:
        sc.r.find("بالا", "تایمر", "بازیِ متوقف با تایمر جلو رفت")
    m = sc.host.tap(cb_is("dawn"), ("group",), depth=60)
    if m and m.ok:
        sc.r.find("متوسط", "میزبانی", "بازیِ متوقف با دکمه جلو رفت", key="paused-advance")
    sc.host.navigate("resume")
    if sc.g.s.paused:
        sc.r.find("متوسط", "میزبانی", "«▶️ ادامه» کار نکرد")
    else:
        sc.r.ok("توقف/ادامه‌ی میزبان")


# ───────────────────────── بازجویی و بازداشت ─────────────────────────
def p_stale_verdict(sc: Scene):
    x = sc.citizen()
    sc.interrogate(x)
    if sc.g.s.suspect_uid != x.uid:
        return False
    old = next((m for m in reversed(sc.s.tg.inbox(sc.s.group))
                for b in m.buttons() if b.get("callback_data") == f"ver:{x.uid}:1"), None)
    sc.dawn()
    if sc.g.s.phase is not Phase.MORNING or not sc.g.officer_can_judge():
        return False
    sc.verdict(0)                                      # X آزاد شد
    y = sc.citizen(x)
    sc.discuss_and_vote()
    sc.vote_all(y)
    if sc.g.s.suspect_uid != y.uid or old is None:
        return False
    sc.dawn()
    if sc.g.s.phase is not Phase.MORNING or sc.g.s.suspect_uid != y.uid:
        return False
    off = sc.s.agent(sc.g.s.officer_uid)
    b = next(b for b in old.buttons() if b.get("callback_data") == f"ver:{x.uid}:1")
    sc.s.tg.press(off.uid, old, b)                    # دکمه‌ی حبسِ X روی پیام دیروز
    if sc.g.s.players[y.uid].custody is Custody.TEMP_JAIL:
        sc.r.find("بالا", "دکمه‌ها", "دکمه‌ی حکمِ کهنه روی متهمِ تازه اجرا می‌شود", key="stale-verdict")
    else:
        sc.r.ok("دکمه‌ی حکمِ کهنه اثری ندارد")


def p_suspect_immune(sc: Scene):
    """متهمِ داخل بازجویی در بازداشت است؛ قاتل نباید بتواند او را هدف بگیرد."""
    killer = sc.role("قاتل")
    x = sc.citizen(killer)
    sc.interrogate(x)
    if sc.g.s.suspect_uid != x.uid or not sc.g.s.players[killer.uid].free:
        return False
    if sc.offered(killer, x):
        sc.r.find("بالا", "قواعد", "متهمِ داخل بازجویی هدفِ قتل پیشنهاد می‌شود", key="suspect-killable")
    else:
        sc.r.ok("بازداشتی از حمله‌ی شبانه در امان است")


def p_officer_suspect(sc: Scene):
    """گروه بازجو را به بازجویی می‌فرستد: او نباید خودش حکم بدهد؛ هیئت منصفه خودکار تشکیل شود."""
    off = sc.s.agent(sc.g.s.officer_uid)
    sc.interrogate(off)
    if sc.g.s.suspect_uid != off.uid:
        return False
    sc.dawn()
    if sc.g.s.phase is Phase.END:
        return False
    m = off.tap(cb_is(f"ver:{off.uid}:0"), ("group",), depth=60)
    if m and m.ok and sc.g.s.players[off.uid].custody is Custody.FREE and not sc.g.s.players[off.uid].jury_used:
        sc.r.find("بحرانی", "بازجویی", "بازجو وقتی خودش متهم است، خودش را تبرئه می‌کند",
                  key="officer-self-acquit")
    elif sc.g.s.phase is Phase.JURY and sc.g.s.auto_jury:
        sc.r.ok("بازجوی متهم → هیئت منصفه‌ی خودکار")
    else:
        sc.r.find("بالا", "بازجویی", "وقتی بازجو خودش متهم است هیئت منصفه تشکیل نشد",
                  f"فاز {sc.g.s.phase.value}")


def p_dead_officer(sc: Scene):
    """قاتل بازجو را می‌کشد، در حالی که متهمی منتظر حکم است."""
    killer = sc.role("قاتل")
    off = sc.s.agent(sc.g.s.officer_uid)
    x = sc.citizen(killer)
    sc.interrogate(x)
    if sc.g.s.suspect_uid != x.uid or not sc.g.s.players[killer.uid].free:
        return False
    sc.act(killer, off)
    sc.dawn()
    if sc.stormy() or sc.g.s.players[off.uid].alive or sc.g.s.phase is Phase.END:
        return False
    m = off.tap(cb_is(f"ver:{x.uid}:1"), ("group",), depth=60)
    if m and m.ok:
        sc.r.find("بالا", "بازجویی", "بازجوی حذف‌شده هنوز حکم صادر می‌کند", key="dead-officer-verdict")
    if sc.g.s.phase is Phase.JURY:
        sc.r.ok("بازجوی کشته → هیئت منصفه‌ی خودکار")
        for a in sc.s.agents:
            hit = a.find(cb_is("jury:0"), ("group",), 6)
            if hit and sc.g.s.players[a.uid].can_vote:
                a.press(*hit)
        sc.host.tap(cb_is("closejury"), ("group",), depth=6)
        if sc.g.s.players[x.uid].custody is Custody.TEMP_JAIL:
            sc.r.ok("هیئت منصفه‌ی خودکار: تبرئه‌نکردن = حبس موقت")
        else:
            sc.r.find("بالا", "هیئت منصفه", "هیئت منصفه‌ی خودکار تبرئه نکرد ولی متهم حبس نشد",
                      sc.g.s.players[x.uid].custody.value)
    else:
        sc.r.find("بالا", "بازجویی", "بازجو کشته شد و هیئت منصفه تشکیل نشد", sc.g.s.phase.value)


def p_sos_suspect(sc: Scene):
    x = sc.citizen()
    sc.interrogate(x)
    if sc.g.s.suspect_uid != x.uid:
        return False
    for a in sc.s.agents:
        if sc.g.s.players[a.uid].can_vote and a.uid != x.uid:
            a.navigate("sos")
            hit = a.find(cb_is(f"sos:{x.uid}"), ("dm",), 1)
            if hit:
                a.press(*hit)
    if sc.g.s.players[x.uid].custody is Custody.TEMP_JAIL:
        sc.r.find("متوسط", "قواعد", "رای اضطراری وسط شب روی متهمِ داخل بازجویی اجرا می‌شود",
                  key="sos-suspect")
    else:
        sc.r.ok("رای اضطراری: فقط روز و فقط روی بازیکن آزاد")


def p_sos_lobby(sc: Scene):
    victim = sc.s.agents[-1]
    for a in sc.s.agents:
        if a is victim:
            continue
        a.navigate("sos")
        hit = a.find(cb_is(f"sos:{victim.uid}"), ("dm",), 1)
        if hit:
            a.press(*hit)
    if sc.g.s.players[victim.uid].custody is Custody.TEMP_JAIL:
        sc.r.find("بالا", "قواعد", "«🚨 رای اضطراری» در لابی کار می‌کند", key="sos-lobby")
    else:
        sc.r.ok("رای اضطراری در لابی رد شد")


def p_defense_visible(sc: Scene):
    x = sc.citizen()
    sc.interrogate(x)
    if sc.g.s.suspect_uid != x.uid:
        return False
    x.navigate("defense")
    x.say("من آن شب در بیمارستان کشیک بودم.")
    grp = "\n".join(m.text for m in sc.s.tg.inbox(sc.s.group))
    if "آخرین دفاع" in grp and "بیمارستان" in grp:
        sc.r.ok("آخرین دفاع متهم در گروه اعلام می‌شود")
    else:
        sc.r.find("پایین", "رابط", "«آخرین دفاعِ» متهم به گروه نمی‌رسد", key="defense-hidden")


def p_two_way_interrogation(sc: Scene):
    x = sc.citizen()
    sc.interrogate(x)
    if sc.g.s.suspect_uid != x.uid or not sc.g.officer_can_judge():
        return False
    off = sc.s.agent(sc.g.s.officer_uid)
    off.navigate("ask")
    off.say("ساعت یازده کجا بودی؟")
    hit = x.find(cb_is("answer"), ("dm",), 3)
    if not hit or "یازده" not in hit[0].text:
        sc.r.find("بالا", "بازجویی", "پرسش بازجو به پیوی متهم نرسید", key="ask-not-delivered")
        return None
    x.press(*hit)
    x.say("در کتابخانه بودم.")
    back = sc.s.tg.last(off.uid)
    if back and "کتابخانه" in back.text:
        sc.r.ok("بازجویی دونفره: پرسش → متهم → جواب → بازجو")
    else:
        sc.r.find("بالا", "بازجویی", "جواب متهم به بازجو نرسید", key="answer-not-delivered")
    bystander = sc.citizen(x)
    m = bystander.navigate("answer")
    if m is not None and m.ok:
        sc.r.find("متوسط", "بازجویی", "کسی غیر از متهم می‌تواند جواب بدهد", key="answer-authz")


# ───────────────────────── توانایی‌ها ─────────────────────────
def p_doctor_repeat(sc: Scene):
    doc = sc.role("پزشک")
    killer = sc.role("قاتل")
    if not doc:
        return False
    a = sc.citizen(doc, killer)
    b = sc.citizen(doc, killer, a)
    sc.act(doc, a)
    sc.dawn()
    sc.no_vote_night()                                 # شب ۲
    if sc.g.s.phase is not Phase.NIGHT or not sc.g.s.players[a.uid].in_game:
        return False
    first = sc.offered(doc, a)
    sc.act(doc, b)
    again = sc.offered(doc, a)
    if first or again:
        sc.r.find("متوسط", "توانایی‌ها", "پزشک دو شب پشت‌سرهم یک نفر را نجات می‌دهد", key="doctor-repeat")
    else:
        sc.r.ok("پزشک: منع دو شب پیاپی")


def p_doctor_self_once(sc: Scene):
    doc = sc.role("پزشک")
    if not doc:
        return False
    if not sc.offered(doc, doc):
        sc.r.find("متوسط", "توانایی‌ها", "پزشک حتی یک بار هم نمی‌تواند خودش را نجات دهد", key="doc-self")
        return None
    sc.act(doc, doc)
    sc.dawn()
    sc.no_vote_night()
    sc.no_vote_night() if sc.g.s.phase is Phase.MORNING else None
    if sc.g.s.phase is not Phase.NIGHT:
        return False
    sc.dawn()                                          # شبِ فاصله (قید دو شب پیاپی)
    sc.no_vote_night()
    if sc.g.s.phase is not Phase.NIGHT or not sc.g.s.players[doc.uid].in_game:
        return False
    if sc.offered(doc, doc):
        sc.r.find("متوسط", "توانایی‌ها", "پزشک بیش از یک بار خودش را نجات می‌دهد", key="doc-self-twice")
    else:
        sc.r.ok("پزشک: خودنجاتی فقط یک بار")


def p_detective_repeat(sc: Scene):
    det = sc.role("کارآگاه")
    killer = sc.role("قاتل")
    a = sc.citizen(det, killer)
    sc.act(det, a)
    sc.dawn()
    sc.no_vote_night()
    if sc.g.s.phase is not Phase.NIGHT or not sc.g.s.players[a.uid].in_game:
        return False
    if sc.offered(det, a):
        sc.r.find("پایین", "توانایی‌ها", "کول‌داونِ هدف کارآگاه عمل نمی‌کند", key="detective-repeat")
    else:
        sc.r.ok("کارآگاه: کول‌داون هدف")


def p_team_target(sc: Scene):
    killer, acc = sc.role("قاتل"), sc.role("همدست")
    if not acc:
        return False
    if sc.offered(killer, acc):
        sc.r.find("متوسط", "قواعد", "قاتل می‌تواند هم‌تیمی‌اش را بکشد", key="team-kill")
    else:
        sc.r.ok("قاتل هم‌تیمی را هدف نمی‌گیرد")


def p_poison_save(sc: Scene):
    poisoner, doc = sc.role("سم‌ساز"), sc.role("پزشک")
    if not (poisoner and doc):
        return False
    t = sc.citizen(poisoner, doc, sc.role("قاتل"))
    sc.act(poisoner, t)
    for night in range(3):
        if night == 2:
            sc.act(doc, t)                             # شبِ سررسید: پزشک می‌رسد
        sc.dawn()
        if sc.stormy() or sc.g.s.phase is Phase.END or not sc.g.s.players[t.uid].alive:
            return False
        if night < 2:
            sc.no_vote_night()
    sc.r.ok("سم: نجات پزشک در شبِ سررسید")


def p_heir(sc: Scene):
    """قاتل حبس ابد می‌گیرد؛ چاقو باید به همدست برسد و او شب بعد بتواند بکشد."""
    killer, acc = sc.role("قاتل"), sc.role("همدست")
    if not acc:
        return False
    sc.interrogate(killer)
    if sc.g.s.suspect_uid != killer.uid:
        return False
    sc.dawn()
    if sc.g.s.phase is not Phase.MORNING or not sc.g.officer_can_judge():
        return False
    sc.verdict(1)
    for _ in range(2):
        if sc.g.s.phase is Phase.END:
            return False
        sc.no_vote_night()
        sc.dawn()
    if sc.g.s.players[killer.uid].custody is not Custody.LIFE_JAIL or sc.g.s.phase is Phase.END:
        return False
    acc.read_dm()
    if not acc.heir:
        sc.r.find("بالا", "توانایی‌ها", "جانشینِ قاتل خبردار نشد", key="heir-note")
        return None
    sc.no_vote_night()
    victim = sc.citizen(acc)
    m = sc.act(acc, victim)
    if m and m.ok and "ثبت" in m.text:
        sc.r.ok("جانشینی قاتل: همدست چاقو را گرفت")
    else:
        sc.r.find("بالا", "توانایی‌ها", "جانشینِ قاتل نمی‌تواند بکشد", m.text if m else "", key="heir-kill")


def p_hunter_life_jail(sc: Scene):
    hunter = sc.role("شکارچی")
    if not hunter:
        return False
    victim = sc.citizen(hunter)
    hunter.tap(cb_is("act"), ("dm",), depth=3, nav="act")
    hit = hunter.find(cb_is(f"hunter:{victim.uid}"), ("dm",), 1)
    if not hit:
        return False
    hunter.press(*hit)
    sc.interrogate(hunter)
    if sc.g.s.suspect_uid != hunter.uid:
        return False
    sc.dawn()
    if sc.g.s.phase is not Phase.MORNING or not sc.g.officer_can_judge():
        return False
    sc.verdict(1)
    for _ in range(2):
        if sc.g.s.phase is Phase.END:
            return False
        sc.no_vote_night()
        sc.dawn()
    p, v = sc.g.s.players[hunter.uid], sc.g.s.players[victim.uid]
    if p.custody is not Custody.LIFE_JAIL:
        return False
    if v.in_game:
        sc.r.find("متوسط", "توانایی‌ها", "شلیک آخر شکارچی با حبس ابد اجرا نمی‌شود", key="hunter-lifejail")
    else:
        sc.r.ok("شکارچی: شلیک آخر با حبس ابد")


def p_hunter_button(sc: Scene):
    hunter = sc.role("شکارچی")
    other = next(a for a in sc.s.agents if a is not hunter)
    m = other.navigate("hunter")
    if m is not None and not m.ok and "ورودی نامعتبر" in m.text:
        sc.r.find("پایین", "دکمه‌ها", "دکمه‌ی «🏹 هدف شلیک آخر» به بن‌بست می‌رسد", key="hunter-button")
    if hunter:
        m = hunter.navigate("hunter")
        if m and m.ok and hunter.buttons_named(m, "hunter:"):
            sc.r.ok("دکمه‌ی شکارچی در منو فهرست هدف‌ها را می‌دهد")


# ───────────────────────── برد و امتیاز ─────────────────────────
def p_serial_killer_win(sc: Scene):
    sk = sc.role("جانی سریالی")
    if not sk:
        return False
    victim = sc.citizen(sk)
    # چیدمان صحنه: بقیه از بازی بیرون‌اند (رسیدن به این نقطه با بازی واقعی ده‌ها دور است)
    for p in sc.g.s.players.values():
        if p.uid not in (sk.uid, victim.uid):
            p.alive = False
    sc.act(sk, victim)
    sc.dawn()
    if not (sc.g.s.winner or "").startswith("جانی"):
        sc.r.find("بالا", "قواعد برد", "جانی سریالی در دوئل یک‌به‌یک برنده اعلام نشد", sc.g.s.winner or "—")
        return None
    sc.r.ok("شرط برد: جانی سریالی")
    xp = sc.g.s.players[sk.uid].xp
    if xp < 120:
        sc.r.find("بالا", "امتیاز", "جانی سریالی برنده می‌شود ولی امتیاز باخت می‌گیرد",
                  f"XP جانی: {xp}", key="xp-win:جانی سریالی")
    else:
        sc.r.ok("امتیاز: برنده‌ی خنثی XP برد می‌گیرد")


def p_sk_city_win(sc: Scene):
    sk = sc.role("جانی سریالی")
    if not sk:
        return False
    killers = [a for a in sc.s.agents if ROLES[a.role].align is Align.KILLER]
    # چیدمان صحنه: همه‌ی قاتل‌ها جز یکی از قبل حبس ابد گرفته‌اند
    for a in killers[1:]:
        sc.g.s.players[a.uid].custody = Custody.LIFE_JAIL
    last = killers[0]
    sc.interrogate(last)
    if sc.g.s.suspect_uid != last.uid:
        return False
    sc.dawn()
    if sc.g.s.phase is not Phase.MORNING or not sc.g.officer_can_judge():
        return False
    sc.verdict(1)
    for _ in range(2):
        if sc.g.s.phase is Phase.END:
            break
        sc.no_vote_night()
        sc.dawn()
    if sc.g.s.players[last.uid].custody is not Custody.LIFE_JAIL:
        return False
    if (sc.g.s.winner or "").startswith("شهر") and sc.g.s.players[sk.uid].in_game:
        sc.r.find("متوسط", "قواعد برد", "شهر برد در حالی که جانی سریالی زنده است", key="sk-alive-city-win")
    elif sc.g.s.players[sk.uid].in_game:
        sc.r.ok("جانی زنده ⇒ شهر هنوز نبرده")


def p_survivor_cowin(sc: Scene):
    """بقال محله اگر تا پایان در بازی بماند، کنار برنده می‌برد."""
    grocer = sc.role("بقال محله")
    if not grocer:
        return False
    for a in sc.s.agents:                          # چیدمان صحنه: قاتل‌ها حبس ابد
        if ROLES[a.role].align is Align.KILLER or a.role == "جانی سریالی":
            sc.g.s.players[a.uid].custody = Custody.LIFE_JAIL
    sc.dawn()
    if not (sc.g.s.winner or "").startswith("شهر"):
        return False
    m = sc.host.tap(cb_is("end"), ("group",), depth=10)
    if sc.g.s.players[grocer.uid].xp >= 120 and m and "کنار برنده" in m.text:
        sc.r.ok("بقال/قاچاقچی: برد با زنده ماندن")
    else:
        sc.r.find("متوسط", "قواعد برد", "بقالِ زنده کنار برنده حساب نشد", key="survivor-cowin")


def p_vote_edit_xp(sc: Scene):
    killer = sc.role("قاتل")
    voter = sc.citizen(killer)
    sc.dawn()
    if sc.g.s.phase is not Phase.MORNING:
        return False
    sc.discuss_and_vote()
    other = sc.citizen(killer, voter)
    for _ in range(4):
        voter.tap(cb_is(f"vote:{killer.uid}"), ("group",), depth=60)
        voter.tap(cb_is(f"vote:{other.uid}"), ("group",), depth=60)
    voter.tap(cb_is(f"vote:{killer.uid}"), ("group",), depth=60)
    sc.s.tg.clock.advance((sc.g.remaining() or 0) + 1)
    sc.close_vote()
    n = sum(1 for _d, v, t in sc.g.s.vote_history if v == voter.uid and t == killer.uid)
    if n > 1:
        sc.r.find("پایین", "امتیاز", "هر ویرایش رای یک «رای درست» جدا حساب می‌شود", key="vote-edit-xp")
    else:
        sc.r.ok("دقت رای: فقط رای نهایی هر دور")


def p_abstain_and_tie(sc: Scene):
    sc.dawn()
    if sc.g.s.phase is not Phase.MORNING:
        return False
    sc.discuss_and_vote()
    voters = [a for a in sc.s.agents if sc.g.s.players[a.uid].can_vote]
    if len(voters) < 5:
        return False
    a, b = voters[0], voters[1]
    voters[2].tap(cb_is(f"vote:{a.uid}"), ("group",), depth=60)
    voters[3].tap(cb_is(f"vote:{b.uid}"), ("group",), depth=60)
    r = voters[4].tap(cb_is("vote:0"), ("group",), depth=60)
    if r and r.ok:
        sc.r.ok("رای ممتنع ثبت می‌شود")
    else:
        sc.r.find("متوسط", "دکمه‌ها", "دکمه‌ی «⏭️ رای ممتنع» خطا می‌دهد", key="abstain")
    for v in voters[5:] + voters[:2]:
        v.tap(cb_is("vote:0"), ("group",), depth=60)
    m = sc.close_vote()
    if sc.g.s.phase is Phase.VOTE and m and "دور دوم" in m.text:
        kb = [x["callback_data"] for x in m.buttons() if x["callback_data"].startswith("vote:")]
        if set(kb) == {f"vote:{a.uid}", f"vote:{b.uid}", "vote:0"}:
            sc.r.ok("تساوی: دور دوم فقط بین نفرات مساوی")
        else:
            sc.r.find("متوسط", "رابط", "کیبورد دور دوم همه را نشان می‌دهد", str(kb), key="tie-kb")
        c = next(x for x in voters if x not in (a, b))
        r = c.find(cb_starts("vote:"), ("group",), 60)
        other = next((u.uid for u in voters if u not in (a, b, c)), None)
        if other:
            bad = sc.g
            try:
                bad.vote(c.uid, other)
                sc.r.find("متوسط", "قواعد", "در دور دوم می‌شود به غیرنامزد رای داد", key="tie-outsider")
            except engine.RuleError:
                sc.r.ok("تساوی: رای به غیرنامزد رد می‌شود")
    else:
        sc.r.find("متوسط", "رابط", "تساوی به دور دوم نرفت", m.text if m else "", key="tie-round")


# ───────────────────────── تایمر و پایداری ─────────────────────────
def p_morning_timer(sc: Scene):
    sc.dawn()
    if sc.g.s.phase is not Phase.MORNING:
        return False
    for _ in range(40):
        sc.s.tg.clock.advance(15)
        sc.s.tg.timer_job()
        if sc.g.s.phase is not Phase.MORNING:
            break
    if sc.g.s.phase is Phase.MORNING:
        sc.r.find("متوسط", "تایمر", "فاز صبح مهلت ندارد؛ میزِ بی‌میزبان تا ابد در صبح می‌ماند",
                  key="morning-no-timer")
    else:
        sc.r.ok("تایمر صبح: گفتگو خودکار باز شد")


def p_restart(sc: Scene):
    sc.dawn()
    phase = sc.g.s.phase
    GAMES.clear()                                      # ربات ری‌استارت شد
    n = bot.restore_games()
    g = GAMES.get(sc.s.group)
    if not g or g.s.phase is not phase:
        sc.r.find("بالا", "پایداری", "بازی بعد از ری‌استارت برنگشت", f"{n} بازی بازیابی شد")
        return None
    sc.s.ref.g = g
    sc.s.play()
    if g.s.phase is Phase.END:
        sc.r.ok("ری‌استارت وسط بازی و ادامه تا پایان")
        GAMES.clear()                                  # ری‌استارتِ دوم، بعد از پایان
        bot.restore_games()
        m = sc.host.tap(cb_is("end"), ("group",), depth=20)
        if m and m.ok and "پایان" in m.text:
            sc.r.ok("افشای پایانی بعد از ری‌استارت")
        else:
            sc.r.find("متوسط", "پایداری", "بعد از ری‌استارت، افشای بازیِ تمام‌شده در دسترس نیست",
                      key="reveal-after-restart")


def p_rematch(sc: Scene):
    sc.s.play()
    if sc.g.s.phase is not Phase.END:
        return False
    hit = sc.host.find(cb_is("rematch"), ("group",), 6)
    if not hit:
        sc.r.find("پایین", "رابط", "دکمه‌ی «🔁 همین ترکیب» بعد از پایان نبود")
        return None
    sc.host.press(*hit)
    g = sc.g
    if g.s.phase is not Phase.LOBBY or len(g.s.players) != len(sc.s.agents):
        sc.r.find("متوسط", "میزبانی", "دور دوباره همه‌ی بازیکن‌ها را برنگرداند")
        return None
    for a in sc.s.agents:
        a.tap(lambda b: "start=ready_" in b.get("url", ""), ("group",), depth=4)
    sc.host.tap(cb_is("startgame"), ("group",), depth=4)
    if g.s.phase is Phase.NIGHT and g.scenario == sc.s.scenario:
        sc.r.ok("دور دوباره با همان ترکیب و سناریو")
    else:
        sc.r.find("متوسط", "میزبانی", "دور دوباره شروع نشد", sc.s.tg.last(sc.s.group).text[:120])


def p_day_cap(sc: Scene):
    """اگر هیچ‌کس حذف نشود، بازی تا ابد نمی‌ماند (سقف روز)."""
    old = engine.MAX_DAYS
    engine.MAX_DAYS = 3
    try:
        for _ in range(8):
            if sc.g.s.phase is Phase.END:
                break
            if sc.g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
                sc.dawn()                              # هیچ‌کس اکشن نمی‌دهد
            else:
                sc.no_vote_night()
        if (sc.g.s.winner or "").startswith("بدون برنده"):
            sc.r.ok("سقف روز: بن‌بست بدون برنده")
        else:
            sc.r.find("متوسط", "جریان بازی", "سقف روز بازیِ بی‌حذف را تمام نکرد",
                      f"روز {sc.g.s.day}، برنده {sc.g.s.winner}", key="day-cap")
    finally:
        engine.MAX_DAYS = old


PROBES = [
    ("قاتل شب را زود می‌بندد", p_early_dawn, 6, "classic"),
    ("غریبه/مرده هیئت منصفه می‌خواهد", p_outsider_jury, 6, "classic"),
    ("غریبه در تفسیر مدرک", p_outsider_interp, 5, "classic"),
    ("کاربر مسدود", p_ban, 5, "classic"),
    ("توقف و ادامه", p_pause, 5, "classic"),
    ("دکمه‌ی حکمِ کهنه", p_stale_verdict, 7, "classic"),
    ("متهم در بازداشت در امان است", p_suspect_immune, 6, "classic"),
    ("بازجو خودش متهم است", p_officer_suspect, 6, "classic"),
    ("بازجو کشته می‌شود", p_dead_officer, 7, "classic"),
    ("رای اضطراری روی متهم", p_sos_suspect, 6, "classic"),
    ("آخرین دفاع متهم", p_defense_visible, 5, "classic"),
    ("بازجویی دونفره", p_two_way_interrogation, 6, "classic"),
    ("پزشک دو شب پیاپی", p_doctor_repeat, 5, "classic"),
    ("پزشک خودش را یک بار", p_doctor_self_once, 5, "classic"),
    ("کارآگاه دو شب پیاپی", p_detective_repeat, 5, "classic"),
    ("قاتل و هم‌تیمی", p_team_target, 7, "classic"),
    ("سم + پزشکِ سر موعد", p_poison_save, 10, "classic"),
    ("جانشینی قاتل", p_heir, 7, "classic"),
    ("شکارچی حبس ابد می‌گیرد", p_hunter_life_jail, 9, "classic"),
    ("دکمه‌ی شکارچی در منو", p_hunter_button, 9, "classic"),
    ("جانی سریالی تنها بازمانده", p_serial_killer_win, 10, "chaos"),
    ("جانی زنده، شهر برنده؟", p_sk_city_win, 10, "chaos"),
    ("بقال زنده کنار برنده", p_survivor_cowin, 8, "chaos"),
    ("ویرایش رای و XP", p_vote_edit_xp, 5, "classic"),
    ("ممتنع و مرگ ناگهانی", p_abstain_and_tie, 7, "classic"),
    ("صبح با تایمر", p_morning_timer, 5, "classic"),
    ("ری‌استارت وسط بازی", p_restart, 7, "court"),
    ("دور دوباره", p_rematch, 5, "court"),
    ("سقف روز", p_day_cap, 5, "classic"),
]


def run_probes(report: Report, rb) -> None:
    for title, fn, n, scen in PROBES:
        _try(report, rb, title, fn, n, scenario=scen)
    _lobby_only(report, rb, "رای اضطراری در لابی", p_sos_lobby)
    _lobby_only(report, rb, "غیرمیزبان بازی را شروع می‌کند", p_non_host_start)
