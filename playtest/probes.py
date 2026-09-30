"""سناریوهای هدفمند: موقعیت‌هایی که بازیِ تصادفی به‌ندرت می‌سازد.

هر سناریو یک میز واقعی با agentها می‌سازد. «چیدمان صحنه» (مثلاً اینکه چه
کسی به بازجویی برود) تا جای ممکن هم با دکمه انجام می‌شود؛ جایی که لازم است
صحنه مستقیم چیده شود (مثل رساندن بازی به دو بازمانده) در کد گفته شده.
خودِ کاری که سنجیده می‌شود همیشه با تپ روی دکمه انجام می‌شود.
"""
from __future__ import annotations

import traceback
from typing import Callable, List, Optional

from karagah import bot
from karagah.bot import GAMES
from karagah.models import Align, Custody, Phase
from karagah.roles import ROLES

from .agent import Agent, cb_is
from .game import Session
from .report import Report


class Scene:
    def __init__(self, report: Report, rb, n: int, seed: int, title: str, lobby=True):
        self.s = Session(n, seed, report, rb, "group")
        report.context = f"سناریو: {title} ({n} نفره، بذر {seed})"
        self.r = report
        self.ok = self.s.lobby() if lobby else True

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
        by = by or self.host
        return by.tap(cb_is("dawn"), ("group",), depth=60)

    def discuss_and_vote(self):
        self.host.tap(cb_is("discuss"), ("group",), depth=60)
        return self.host.tap(cb_is("vote"), ("group",), depth=6)

    def vote_all(self, target: Agent):
        for a in self.s.agents:
            p = self.g.s.players[a.uid]
            if p.can_vote and a.uid != target.uid:
                a.tap(cb_is(f"vote:{target.uid}"), ("group",), depth=60)
        return self.host.tap(cb_is("closevote"), ("group",), depth=10)

    def no_vote_night(self):
        """روز بدون بازداشت: گفتگو → رای → بستن بی‌رای → شب."""
        self.discuss_and_vote()
        return self.host.tap(cb_is("closevote"), ("group",), depth=10)

    def verdict(self, x: int):
        off = self.s.agent(self.g.s.officer_uid)
        sus = self.g.s.suspect_uid
        return off.tap(cb_is(f"ver:{sus}:{x}"), ("group",), depth=60)

    def interrogate(self, target: Agent):
        """از وضعیت فعلی تا جایی که target در بازجویی است (فقط با دکمه)."""
        if self.g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
            self.dawn()
        if self.g.s.suspect_uid is not None and self.g.s.phase is Phase.MORNING:
            self.verdict(0)
        self.discuss_and_vote()
        return self.vote_all(target)

    def stormy(self) -> bool:
        return self.g.s.night_event.startswith("طوفان")


def _try(report: Report, rb, title: str, fn: Callable[[Scene], Optional[bool]],
         n: int, seeds=range(1, 12)) -> None:
    """سناریو را با بذرهای مختلف امتحان کن تا صحنه (بدون طوفان و …) جور شود.
    fn اگر False برگرداند یعنی «صحنه جور نشد، بذر بعدی»."""
    for seed in seeds:
        sc = Scene(report, rb, n, seed, title)
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
    killer = sc.role("قاتل")
    doc = sc.role("پزشک")
    victim = sc.citizen(killer, doc)
    sc.act(killer, victim)
    m = sc.dawn(by=killer)                             # قاتل خودش شب را می‌بندد
    if m and m.ok and sc.g.s.phase is Phase.MORNING:
        sc.r.find("بالا", "دسترسی", "هر کسی — حتی خودِ قاتل — می‌تواند شب را زودتر ببندد",
                  "قاتل هدفش را زد و بلافاصله «🌙 پایان شب» را در گروه زد؛ شب بسته شد پیش از آنکه "
                  "پزشک/کارآگاه اکشن بدهند و اکشن‌شان از دست رفت. h_dawn، h_discuss، h_vote، "
                  "h_closevote و h_closejury هیچ‌کدام نمی‌پرسند چه کسی دکمه را زده (میزبان؟ بازیکن "
                  "زنده؟ اصلاً عضو بازی؟). همین‌طور قاتل می‌تواند رای‌گیری را وقتی به نفعش است زود ببندد.",
                  key="phase-authz")
    outsider = 999_001
    sc.s.tg.names[outsider] = "غریبه"
    grp = sc.s.tg.inbox(sc.s.group)
    msg = next((m for m in reversed(grp) for b in m.buttons() if b.get("callback_data") == "discuss"), None)
    if msg and sc.g.s.phase is Phase.MORNING:
        sc.s.tg.press(outsider, msg, next(b for b in msg.buttons() if b.get("callback_data") == "discuss"))
        if sc.g.s.phase is Phase.DISCUSSION:
            sc.r.find("بالا", "دسترسی", "کسی که اصلاً در بازی نیست فاز را جلو می‌برد",
                      "یک عضوِ گروه که وارد لابی نشده «💬 گفتگو» را زد و فاز عوض شد.", key="outsider-phase")


def p_non_host_start(sc: Scene):
    other = sc.s.agents[-1]
    hit = other.find(cb_is("startgame"), ("group",), 10)
    if hit:
        other.press(*hit)
    if sc.g.s.phase is Phase.NIGHT:
        sc.r.find("متوسط", "دسترسی", "هر عضو لابی — نه فقط میزبان — می‌تواند بازی را شروع کند",
                  f"{other.name} (غیرمیزبان) «🎬 شروع بازی» را زد و بازی شروع شد. h_startgame "
                  "مالکیت را نمی‌سنجد.", key="start-authz")


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
        sc.s.tg.press(outsider, msg, b)                # جدول Telegram «خطای داخلی» را خودش گزارش می‌کند
    dead = next((a for a in sc.s.agents if not sc.g.s.players[a.uid].alive), None)
    if dead and not sc.g.s.players[target.uid].jury_used:
        msg = sc.s.tg.command(dead.uid, "/dashboard", sc.s.group)
        b = next((x for x in msg.buttons() if x.get("callback_data") == "jury"), None)
        if b:
            res = sc.s.tg.press(dead.uid, msg, b)
            if res and res.ok:
                sc.r.find("پایین", "دسترسی", "بازیکنِ مرده می‌تواند هیئت منصفه درخواست کند",
                          "request_jury نمی‌سنجد درخواست‌دهنده زنده/آزاد یا اصلاً عضو بازی است.",
                          key="dead-jury")


def p_outsider_interp(sc: Scene):
    """غریبه در گروه «/interp» را از منوی دستورهای ربات می‌زند و رای تفسیر می‌دهد."""
    outsider = Agent(999_003, "غریبه", sc.s.tg, sc.s.rng)
    sc.s.tg.command(outsider.uid, "/interp", sc.s.group)
    hit = outsider.find(lambda b: str(b.get("callback_data", "")).startswith("interp:"), ("group",), 1)
    if not hit:
        return None
    m = outsider.press(*hit)
    opts = [b for b in outsider.buttons_named(m, "interp:") if b["callback_data"].count(":") == 2]
    if opts:
        before = dict(sc.g.s.interp_votes.get(hit[1]["callback_data"].split(":")[1], {}))
        r = outsider.press(m, opts[0])
        if r and r.ok and outsider.uid not in before and \
                any(outsider.uid in v for v in sc.g.s.interp_votes.values()):
            sc.r.find("پایین", "دسترسی", "کسی که در بازی نیست در رای تفسیر مدرک و آزمایشگاه شرکت می‌کند",
                      "یک عضو گروه که وارد بازی نشده از منوی دستورها «/interp» زد و رایش شمرده شد. "
                      "h_interp و h_lab بازیکن بودن را نمی‌سنجند.", key="outsider-interp")


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
            sc.r.find("متوسط", "امنیت", "کاربرِ مسدودشده به بازی ادامه می‌دهد",
                      "ادمین از پنل «🚫 مسدودسازی» او را بست؛ db.is_banned() نوشته شده ولی handle() هرگز "
                      "صدایش نمی‌زند، پس هر دکمه‌ای هنوز کار می‌کند.", key="ban-ignored")
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
    if sc.g.s.phase is not Phase.MORNING:
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
        sc.r.find("بالا", "دکمه‌ها", "دکمه‌ی حکمِ کهنه روی متهمِ تازه اجرا می‌شود",
                  f"بازجو دکمه‌ی «🔒 حبس موقت» زیر پیامِ دیروز (متهم: {x.name}) را زد و {y.name} "
                  "(متهم امروز) به حبس موقت رفت. callback «ver:<uid>:<x>» آیدی متهم را دارد ولی "
                  "parse_callback فقط بخش آخر را نگه می‌دارد و h_verdict روی suspect_uid فعلی حکم می‌دهد.",
                  key="stale-verdict")
    else:
        sc.r.ok("دکمه‌ی حکمِ کهنه اثری ندارد")


def p_dead_suspect(sc: Scene):
    goat = sc.role("سپر بلا")
    killer = sc.role("قاتل")
    if not goat:
        return False
    sc.interrogate(goat)
    if sc.g.s.suspect_uid != goat.uid:
        return False
    sc.act(killer, goat)                               # قاتل متهمِ داخل بازجویی را می‌کشد
    sc.dawn()
    if sc.stormy() or sc.g.s.players[goat.uid].alive:
        return False
    r = sc.verdict(1)
    if r and r.ok:
        sc.r.find("بالا", "بازجویی", "برای متهمی که شب کشته شده حکم حبس صادر می‌شود",
                  "officer_verdict نمی‌سنجد متهم زنده است؛ مرده به حبس موقت می‌رود و "
                  "_advance_custody بعد از ۲ شب به او «حبس ابد» می‌دهد.", key="dead-suspect-verdict")
    for _ in range(3):
        if sc.g.s.phase is Phase.END:
            break
        sc.no_vote_night()
        sc.dawn()
    p = sc.g.s.players[goat.uid]
    if (sc.g.s.winner or "").startswith("سپر"):
        sc.r.find("بحرانی", "قواعد برد", "سپر بلای مرده با «حبس ابدِ پس از مرگ» برنده می‌شود",
                  f"{goat.name} (سپر بلا) در شبِ بازجویی کشته شد، صبح حکم حبس گرفت و دو شب بعد — در حالی که "
                  "مرده بود — «حبس ابد» شد؛ _check_win فقط custody را نگاه می‌کند نه alive، و بازی را به نام "
                  "سپر بلا تمام کرد.", key="dead-scapegoat-wins")
    elif p.custody is Custody.LIFE_JAIL and not p.alive:
        sc.r.find("متوسط", "بازداشت", "بازیکنِ مرده حبس ابد می‌گیرد", key="dead-life-jail")


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
    if sc.g.s.phase is Phase.INTERROGATION and sc.g.s.players[x.uid].custody is Custody.TEMP_JAIL:
        sc.r.find("متوسط", "قواعد", "رای اضطراری وسط شب روی متهمِ داخل بازجویی اجرا می‌شود",
                  "g.sos فاز را نمی‌سنجد؛ متهم وسط شبِ بازجویی به حبس موقت رفت ولی suspect_uid هنوز اوست "
                  "و custody_nights صفر شد، پس صبح بازجو «حکم بعد از گذشتن یک شب…» می‌گیرد.",
                  key="sos-suspect")


def p_sos_lobby(sc: Scene):
    """رای اضطراری پیش از شروع بازی (در لابی)."""
    victim = sc.s.agents[-1]
    backers = [a for a in sc.s.agents if a is not victim]
    for a in backers:
        a.navigate("sos")
        hit = a.find(cb_is(f"sos:{victim.uid}"), ("dm",), 1)
        if hit:
            a.press(*hit)
    p = sc.g.s.players[victim.uid]
    if p.custody is Custody.TEMP_JAIL:
        sc.r.find("بالا", "قواعد", "«🚨 رای اضطراری» در لابی کار می‌کند و بازیکن زندانی وارد بازی می‌شود",
                  f"پیش از شروع، {len(backers)} نفر رای اضطراری علیه {victim.name} دادند؛ او پیش از پخش "
                  "نقش‌ها به حبس موقت رفت و start() بازداشت را پاک نمی‌کند. g.sos فاز را نمی‌سنجد "
                  "(در شب، هیئت منصفه و حتی بعد از پایان هم کار می‌کند).", key="sos-lobby")
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
    if "آخرین دفاع" not in grp and sc.g.s.defense_text:
        sc.r.find("پایین", "رابط", "«آخرین دفاعِ» متهم هرگز به گروه نمی‌رسد",
                  "دفاع با دکمه‌ی پیوی فرستاده می‌شود و پاسخش («🗣️ آخرین دفاع …») در همان پیوی می‌ماند؛ "
                  "فقط بازجو آن را زیر جواب پرسش‌ها می‌بیند. ایده‌ی ۲ («آخرین دفاع») برای شهر دیده نمی‌شود.",
                  key="defense-hidden")


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
    sc.act(doc, b)                                     # اول کس دیگری را می‌زند…
    again = sc.offered(doc, a)                         # …بعد هدفِ دیشب دوباره پیشنهاد می‌شود؟
    if not first and again:
        m = sc.act(doc, a)
        if m and m.ok and "ثبت" in m.text:
            sc.r.find("متوسط", "توانایی‌ها", "قید «دو شب پیاپی» پزشک با عوض کردن هدف دور می‌خورد",
                      "شب دوم دکمه‌ی هدفِ دیشب نبود؛ پزشک اول کس دیگری را زد، بعد پنل دوباره هدفِ "
                      "دیشب را نشان داد و ثبت شد (شرط «protect:{uid} not in night_actions»).",
                      key="doctor-repeat")
    elif first:
        sc.r.find("متوسط", "توانایی‌ها", "پزشک دو شب پشت‌سرهم یک نفر را نجات می‌دهد", key="doctor-repeat-direct")
    else:
        sc.r.ok("پزشک: منع دو شب پیاپی")


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
        sc.r.find("پایین", "توانایی‌ها", "کول‌داونِ هدف کارآگاه عمل نمی‌کند",
                  "PLAN.md (بهبود ۱۲): «کول‌داون هدف کارآگاه». _inv_last داخل night_actions نگه داشته "
                  "می‌شود که سحر پاک می‌شود؛ شب بعد همان نفر دوباره پیشنهاد و پذیرفته می‌شود.",
                  key="detective-repeat")
    else:
        sc.r.ok("کارآگاه: کول‌داون هدف")


def p_poison_save(sc: Scene):
    poisoner, doc = sc.role("سم‌ساز"), sc.role("پزشک")
    if not (poisoner and doc):
        return False
    t = sc.citizen(poisoner, doc, sc.role("قاتل"), sc.role("جانی سریالی"))
    sc.act(poisoner, t)
    for night in range(3):
        if night == 2:
            sc.act(doc, t)                             # شبِ سررسید: پزشک می‌رسد
        sc.dawn()
        if sc.stormy() or sc.g.s.phase is Phase.END or not sc.g.s.players[t.uid].alive:
            return False                              # کسی دیگر او را کشت؛ بذر بعدی
        if night < 2:
            sc.no_vote_night()
    sc.r.ok("سم: نجات پزشک در شبِ سررسید")


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
    if sc.g.s.phase is Phase.END or not sc.g.s.players[hunter.uid].alive:
        return False
    sc.verdict(1)
    for _ in range(2):
        if sc.g.s.phase is Phase.END:
            return False
        sc.no_vote_night()
        sc.dawn()
    p, v = sc.g.s.players[hunter.uid], sc.g.s.players[victim.uid]
    if p.custody is not Custody.LIFE_JAIL or not v.alive:
        return False
    if v.in_game:
        sc.r.find("متوسط", "توانایی‌ها", "شلیک آخر شکارچی با حبس ابد اجرا نمی‌شود",
                  f"متن نقش: «اگر حبس ابد بخورد یا کشته شود، یک نفر را با خود می‌برد». {hunter.name} "
                  f"هدفش را {victim.name} گذاشت، حبس ابد گرفت و {victim.name} هنوز در بازی است؛ "
                  "شلیک فقط در مسیر مرگ شبانه (resolve_night) پیاده شده.", key="hunter-lifejail")
    else:
        sc.r.ok("شکارچی: شلیک آخر با حبس ابد")


def p_hunter_button(sc: Scene):
    a = sc.s.agents[1]
    m = a.navigate("hunter")
    if m is not None and not m.ok:
        sc.r.find("پایین", "دکمه‌ها", "دکمه‌ی «🏹 هدف شلیک آخر» در منوی دکمه‌ها به بن‌بست می‌رسد",
                  f"پاسخ: «{m.text}». h_hunter بدون آرگومان int('') می‌کند؛ باید مثل بقیه فهرست "
                  "بازیکن‌ها را نشان دهد (و برای غیرشکارچی بگوید «فقط شکارچی…»).", key="hunter-button")


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
    if sc.stormy():
        return False
    if not (sc.g.s.winner or "").startswith("جانی"):
        sc.r.find("بالا", "قواعد برد", "جانی سریالیِ تنها بازمانده برنده اعلام نشد", sc.g.s.winner or "—")
        return None
    sc.r.ok("شرط برد: جانی سریالی")
    xp = sc.g.s.players[sk.uid].xp
    if xp < 120:
        sc.r.find("بالا", "امتیاز", "جانی سریالی برنده می‌شود ولی امتیاز و آمارِ باخت می‌گیرد",
                  f"برنده «{sc.g.s.winner}» — XP جانی: {xp} (برنده ۱۲۰ می‌گیرد). _payout و "
                  "db.record_results برد را با winner.startswith(align.value[:3]) می‌سنجند؛ "
                  "«جانی…» با «خنث» شروع نمی‌شود، پس برد در جدول users/outcomes هم باخت ثبت می‌شود.",
                  key="xp-win:جانی سریالی")


def p_sk_city_win(sc: Scene):
    sk = sc.role("جانی سریالی")
    if not sk:
        return False
    killers = [a for a in sc.s.agents if ROLES[a.role].align is Align.KILLER]
    # چیدمان صحنه: دو قاتل از قبل حبس ابد گرفته‌اند؛ آخرین قاتل با رای و حکم واقعی می‌رود
    for a in killers[1:]:
        sc.g.s.players[a.uid].custody = Custody.LIFE_JAIL
    last = killers[0]
    sc.interrogate(last)
    if sc.g.s.suspect_uid != last.uid:
        return False
    sc.dawn()
    if sc.g.s.phase is Phase.END:
        return False
    sc.verdict(1)
    for _ in range(2):
        if sc.g.s.phase is Phase.END:
            break
        sc.no_vote_night()
        sc.dawn()
    if not (sc.g.s.winner or "").startswith("شهر"):
        return False
    if sc.g.s.players[sk.uid].in_game:
        sc.r.find("متوسط", "قواعد برد", "شهر برد در حالی که جانی سریالی زنده است",
                  "متن نقش جانی: «در پایان باید تنها بازمانده باشد». وقتی آخرین قاتل حبس ابد می‌گیرد، "
                  "بازی فوراً «برد شهر» اعلام می‌شود و جانیِ زنده (که هنوز هر شب می‌کشد) نادیده گرفته "
                  "می‌شود.", key="sk-alive-city-win")


def p_vote_edit_xp(sc: Scene):
    killer = sc.role("قاتل")
    voter = sc.citizen(killer)
    sc.dawn()
    if sc.g.s.phase is not Phase.MORNING:
        return False
    sc.discuss_and_vote()
    other = sc.citizen(killer, voter)
    for _ in range(4):                                 # نظرش را چند بار عوض می‌کند
        voter.tap(cb_is(f"vote:{killer.uid}"), ("group",), depth=60)
        voter.tap(cb_is(f"vote:{other.uid}"), ("group",), depth=60)
    voter.tap(cb_is(f"vote:{killer.uid}"), ("group",), depth=60)
    n = sum(1 for _d, v, t in sc.g.s.vote_history if v == voter.uid and t == killer.uid)
    if n > 1:
        sc.r.find("پایین", "امتیاز", "هر ویرایش رای یک «رای درست» جدا حساب می‌شود",
                  f"{voter.name} در یک رای‌گیری ۵ بار روی قاتل زد → {n} ردیف در vote_history؛ هر کدام "
                  "۱۵ XP و یک hit در جدول accuracy. با جابه‌جا کردن رای می‌شود XP ساخت.", key="vote-edit-xp")


# ───────────────────────── تایمر و پایداری ─────────────────────────
def p_morning_timer(sc: Scene):
    sc.dawn()
    if sc.g.s.phase is not Phase.MORNING:
        return False
    for _ in range(240):                               # یک ساعت، هر ۱۵ ثانیه tick
        sc.s.tg.clock.advance(15)
        sc.s.tg.timer_job()
    if sc.g.s.phase is Phase.MORNING:
        sc.r.find("متوسط", "تایمر", "فاز صبح مهلت ندارد؛ میزِ بی‌میزبان تا ابد در صبح می‌ماند",
                  "PHASE_SECONDS برای «صبح» (و «هیئت منصفه») مقداری ندارد و resolve_night مهلت را None "
                  "می‌کند؛ اگر کسی «💬 گفتگو» را نزند، تایمر یک ساعت بعد هم بازی را جلو نبرده بود.",
                  key="morning-no-timer")


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
    if g.s.phase is Phase.NIGHT:
        sc.r.ok("دور دوباره با همان ترکیب")
    else:
        sc.r.find("متوسط", "میزبانی", "دور دوباره شروع نشد", sc.s.tg.last(sc.s.group).text[:120])


PROBES = [
    ("قاتل شب را زود می‌بندد", p_early_dawn, 6),
    ("غریبه/مرده هیئت منصفه می‌خواهد", p_outsider_jury, 6),
    ("غریبه در تفسیر مدرک", p_outsider_interp, 5),
    ("کاربر مسدود", p_ban, 5),
    ("توقف و ادامه", p_pause, 5),
    ("دکمه‌ی حکمِ کهنه", p_stale_verdict, 7),
    ("متهمِ کشته‌شده حکم می‌گیرد", p_dead_suspect, 6),
    ("رای اضطراری روی متهم", p_sos_suspect, 6),
    ("آخرین دفاع متهم", p_defense_visible, 5),
    ("پزشک دو شب پیاپی", p_doctor_repeat, 5),
    ("کارآگاه دو شب پیاپی", p_detective_repeat, 5),
    ("سم + پزشکِ سر موعد", p_poison_save, 10),
    ("شکارچی حبس ابد می‌گیرد", p_hunter_life_jail, 9),
    ("دکمه‌ی شکارچی در منو", p_hunter_button, 4),
    ("جانی سریالی تنها بازمانده", p_serial_killer_win, 10),
    ("جانی زنده، شهر برنده", p_sk_city_win, 10),
    ("ویرایش رای و XP", p_vote_edit_xp, 5),
    ("صبح بدون تایمر", p_morning_timer, 5),
    ("ری‌استارت وسط بازی", p_restart, 7),
    ("دور دوباره", p_rematch, 5),
]


def run_probes(report: Report, rb) -> None:
    for title, fn, n in PROBES:
        _try(report, rb, title, fn, n)
    _lobby_only(report, rb, "رای اضطراری در لابی", p_sos_lobby)
    _lobby_only(report, rb, "غیرمیزبان بازی را شروع می‌کند", p_non_host_start)
