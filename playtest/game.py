"""یک میز کامل: agentها از لابی تا افشای نقش‌ها، فقط با دکمه.

سه حالت پیشروی فاز (mode):
  group  — میزبان دکمه‌های فاز را روی پیام‌های گروه می‌زند (مسیر عادی)
  timer  — کسی «پایان شب/رای‌گیری» را نمی‌زند؛ مهلت‌ها با تایمر ۱۵ثانیه‌ای می‌گذرند
  dm     — میزبان دکمه‌های فاز را از منوی پیویِ خودش می‌زند (مسیرِ «🎛️ همه‌ی دکمه‌ها»)
"""
from __future__ import annotations

import random
import re
from typing import Dict, List, Optional

from karagah import bot, db
from karagah.bot import GAMES
from karagah.models import Align, Custody, Phase
from karagah.roles import ROLES, SCENARIOS, scenario_name

from .agent import Agent, cb_is, cb_starts
from .docs import Rulebook
from .referee import Referee
from .report import Report
from .table import Telegram

NAMES = ["آرش", "بهار", "کاوه", "دنیا", "سهراب", "مهسا", "نیما", "رویا", "پویا", "شیرین"]
QUESTIONS = ["ساعت یازده شب کجا بودی؟", "مقتول را از کی می‌شناختی؟", "چرا دیشب بیرون رفتی؟"]
MODE_FA = {"group": "دکمه در گروه", "timer": "تایمر", "dm": "دکمه از پیوی"}


def _reset_globals() -> None:
    db.reset(":memory:")
    GAMES.clear()
    from karagah import engine as _engine
    _engine.NIGHT_OBSERVERS.clear()        # داورِ جلسه‌ی قبلی دیگر گوش نمی‌دهد
    for d in (bot._PENDING, bot._ACTIVE_TABLE, bot._LAST_CB, bot._LAST_CALL, bot.LAST_ROSTER):
        d.clear()


class Session:
    def __init__(self, n: int, seed: int, report: Report, rb: Rulebook, mode: str = "group",
                 scenario: str = "classic", talk: bool = True):
        _reset_globals()
        self.n, self.seed, self.mode, self.r, self.rb = n, seed, mode, report, rb
        self.scenario = scenario
        self.group = -(1_000_000 + n * 1000 + seed * 10 + len(mode)
                       + 100_000 * list(SCENARIOS).index(scenario))
        self.tg = Telegram(self.group, report)
        self.rng = random.Random(seed * 1009 + n * 7 + len(mode))
        self.agents = [Agent(5000 + i, NAMES[i], self.tg, random.Random(seed * 31 + i))
                       for i in range(n)]
        self.by_uid = {a.uid: a for a in self.agents}
        self.host = self.agents[0]
        self.ref: Optional[Referee] = None
        self.stuck = ""
        self.lab_due: Dict[str, int] = {}
        self.talk_on = talk
        self.talk = None
        self.interrogated: set = set()
        self.jailed: set = set()
        report.context = f"{scenario_name(scenario)}، {n} نفره، بذر {seed}، {MODE_FA[mode]}"

    @property
    def g(self):
        return GAMES.get(self.group)

    def agent(self, uid: Optional[int]) -> Optional[Agent]:
        return self.by_uid.get(uid) if uid else None

    def uid_of(self, name: str) -> Optional[int]:
        return next((a.uid for a in self.agents if a.name == name), None)

    def group_since(self, mid: int) -> str:
        return "\n".join(m.text for m in self.tg.inbox(self.group) if m.mid > mid)

    def last_mid(self) -> int:
        return max((m.mid for box in self.tg.chats.values() for m in box), default=0)

    # ─────────────────────────── لابی ───────────────────────────
    def lobby(self, starter: Optional[Agent] = None) -> bool:
        for a in self.agents:
            a.read_docs(self.rb)                # قاعده: اول همه‌ی Markdownها
        if not all(a.ready_to_play for a in self.agents):
            self.r.find("بحرانی", "playtest", "agentی بدون خواندن مستندات سر میز نشست")
            return False
        self.tg.command(self.host.uid, "/new", self.group)
        for a in self.agents[1:]:
            m = a.tap(cb_is("join"), ("group",))
            if not (m and m.ok):
                self.r.find("بالا", "لابی", "دکمه‌ی «منم بازی می‌کنم» کار نکرد", m.text if m else "دکمه نبود")
        if self.scenario != "classic":               # میزبان سناریو را با دکمه انتخاب می‌کند
            other = self.agents[1]
            if other.tap(cb_is("scenario"), ("group",), depth=4):
                hit = other.find(cb_is(f"scenario:{self.scenario}"), ("group",), 2)
                r = other.press(*hit) if hit else None
                if r and r.ok:
                    self.r.find("متوسط", "دسترسی", "غیرمیزبان سناریو را عوض کرد", key="scenario-authz")
                else:
                    self.r.ok("سناریو: فقط میزبان")
            self.host.tap(cb_is("scenario"), ("group",), depth=6)
            hit = self.host.find(cb_is(f"scenario:{self.scenario}"), ("group",), 2)
            r = self.host.press(*hit) if hit else None
            if not (r and r.ok and scenario_name(self.scenario) in r.text):
                self.r.find("بالا", "لابی", "انتخاب سناریو با دکمه کار نکرد", r.text if r else "دکمه نبود")
            else:
                self.r.ok("سناریو: انتخاب با دکمه و نمایش نقش‌ها در لابی")
        m = self.host.tap(cb_is("startgame"), ("group",), depth=8)
        if m and m.ok:
            self.r.find("بالا", "لابی", "بازی بدون «✅ آماده‌ام» شروع شد", key="start-without-ready")
        else:
            self.r.ok("لابی: شروع قبل از آمادگی رد شد")
        for a in self.agents:
            m = a.tap(lambda b: "start=ready_" in b.get("url", ""), ("group",), depth=8)
            if not (m and m.ok and m.chat == a.uid):
                self.r.find("بالا", "لابی", "دکمه‌ی «✅ آماده‌ام» پیوی را تایید نکرد", m.text if m else "")
        starter = starter or self.host
        lobby = starter.find(cb_is("startgame"), ("group",), 8)
        m = starter.press(*lobby) if lobby else None
        if not self.g or self.g.s.phase is not Phase.NIGHT:
            self.r.find("بحرانی", "لابی", "بازی با همه‌ی آماده‌ها شروع نشد", m.text if m else "")
            return False
        for a in self.agents:
            if any("نقش تو:" in x.text for x in self.tg.inbox(a.uid)):
                self.r.ok("کارت نقش خودکار به پیوی")
            else:
                self.r.find("متوسط", "رابط", "کارت نقش خودکار به پیوی نرسید", a.name, key="auto-role-card")
            m = a.tap(cb_is("myrole"), ("group",), depth=4)
            if m and m.chat == a.uid:
                a.learn_role(m.text)
            else:
                self.r.find("بالا", "نقش‌ها", "دکمه‌ی «🔐 نقش من» نقش را به پیوی نفرستاد", m.text if m else "")
        self.ref = Referee(self.g, self.agents, self.r)
        self.ref.mode = MODE_FA[self.mode]
        self.ref.check_start()
        if self.talk_on:
            from .talk import TableTalk
            self.talk = TableTalk(self)
        return True

    # ─────────────────────────── حلقه ───────────────────────────
    def play(self) -> None:
        last, stall = None, 0
        handlers = {Phase.NIGHT: self.night, Phase.INTERROGATION: self.night,
                    Phase.MORNING: self.morning, Phase.DISCUSSION: self.discussion,
                    Phase.VOTE: self.vote, Phase.JURY: self.jury}
        for _ in range(150):
            g = self.g
            if g.s.phase is Phase.END:
                break
            self.check_dashboard()
            if g.s.suspect_uid:
                self.interrogated.add(g.s.suspect_uid)
            self.jailed |= {p.uid for p in g.s.players.values()
                            if p.custody in (Custody.TEMP_JAIL, Custody.LIFE_JAIL)}
            key = (g.s.phase, g.s.day, g.s.suspect_uid, len(g.s.votes))
            stall = stall + 1 if key == last else 0
            last = key
            if stall >= 4:
                self.stuck = f"{g.s.phase.value} روز {g.s.day}"
                self.r.find("بحرانی", "جریان بازی", "بازی گیر کرد و با دکمه‌ها جلو نرفت",
                            f"فاز {g.s.phase.value}، روز {g.s.day}؛ آخرین پاسخ‌ها:\n"
                            + "\n".join(f"  • {m.cause}: {m.text[:90]}" for m in self.tg.inbox(self.group)[-3:]),
                            key=f"stuck:{g.s.phase.value}:{self.mode}")
                return
            handlers[g.s.phase]()
        else:
            self.stuck = "بیش از ۱۵۰ قدم"
            self.r.find("بالا", "جریان بازی", "بازی بعد از ۱۵۰ قدم هنوز تمام نشده بود",
                        f"روز {self.g.s.day}، فاز {self.g.s.phase.value}. بازی سقف روز ندارد.",
                        key="endless")
            return
        self.finish()

    def check_dashboard(self) -> None:
        """میزبان «📋 داشبورد» گروه را نگاه می‌کند (دکمه‌ی 🔄 یا فرمان منوی ربات)."""
        m = self.host.tap(cb_is("dashboard"), ("group",), depth=1) \
            or self.tg.command(self.host.uid, "/dashboard", self.group)
        ph = re.search(r"فاز: ([^\*\n]+)\*", m.text)
        if not ph or ph.group(1).strip() != self.g.s.phase.value:
            self.r.find("متوسط", "رابط", "داشبورد فازِ اشتباه نشان می‌دهد",
                        f"داشبورد: {ph.group(1) if ph else '؟'} — واقعی: {self.g.s.phase.value}")
        pend = self.g.pending_actors()
        if self.g.s.phase is Phase.INTERROGATION:
            sus = self.g.s.suspect_uid
            if sus in pend:
                self.r.find("متوسط", "رابط", "متهمِ داخل بازجویی «منتظرِ اکشن شبانه» شمرده می‌شود",
                            "pending_actors فقط can_speak را می‌سنجد؛ متهم نمی‌تواند اکشن بزند "
                            "(check_night_action رد می‌کند) ولی در فهرست انتظار می‌ماند و سحر "
                            "شمارنده‌ی «شب‌های بی‌حرکت» (missed) او هم زیاد می‌شود — یعنی به‌خاطر "
                            "بازداشت، «😴 بی‌حرکت» اعلام می‌شود.", key="suspect-pending")

    def host_phase(self, cb: str, depth: int = 10) -> Optional["object"]:
        """میزبان دکمه‌ی فاز را می‌زند؛ اگر ربات گفت «هنوز منتظر…»، تا پایان مهلت صبر می‌کند."""
        def press():
            if self.mode == "dm":
                return self.host.navigate(cb)
            return self.host.tap(cb_is(cb), ("group",), depth=depth) or (
                self.check_dashboard() or self.host.tap(cb_is(cb), ("group",), depth=1))
        m = press()
        if m is not None and not m.ok and "⏳" in m.text:
            left = self.g.remaining() or 0
            self.tg.clock.advance(left + 1)
            m = press()
        return m

    # ─────────────────────────── شب ───────────────────────────
    def night(self) -> None:
        g = self.g
        for a in self.agents:
            a.read_dm()                                 # خبرهای محرمانه‌ی دیشب (جانشینی قاتل، …)
        killers = [p for p in g.s.alive_players() if p.align is Align.KILLER]
        if killers and not any(g.ability_of(p) in ("kill", "poison")
                               for p in g.s.alive_players()):
            self.r.find("متوسط", "تعادل", "تیم قاتل هنوز در بازی است ولی دیگر هیچ‌کس نمی‌تواند بکشد",
                        f"روز {g.s.day}: قاتل‌های باقی‌مانده {[p.role for p in killers]} هیچ‌کدام توانایی قتل "
                        "ندارند (قاتل حذف/زندانی شده و توانایی‌اش به همدست/خبرچین نمی‌رسد). از اینجا بازی "
                        "فقط با رای شهر تمام می‌شود و سقف روز هم ندارد؛ در دو بازی ۹ نفره که شهر رای نداد، "
                        "بازی ۳۸ روز بی‌هیچ مرگی ادامه یافت.", key="no-killer-can-kill")
        self.ref.begin_night()
        mark = self.last_mid()                          # صبح ممکن است با آخرین تصمیم همین حالا برسد
        day_before = g.s.day
        order = sorted(self.agents, key=lambda a: (self.ab(a) != "kill", self.rng.random()))
        order.sort(key=lambda a: ROLES[a.role].ability == "protect")     # پزشک آخر
        for a in order:
            if g.s.phase not in (Phase.NIGHT, Phase.INTERROGATION):
                break                                   # آخرین تصمیم شب را بست (بقیه هدفِ مجازی نداشتند)
            self.night_turn(a)
        if g.s.phase is Phase.INTERROGATION:
            self.officer_questions()
            self.officer_done()
        if g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
            if self.mode == "timer":
                self.run_timer()                        # مهلت → فرصتِ اضافه → صبح
            else:
                for _ in range(3):                      # «⏳ منتظر» → صبر؛ «فرصتِ اضافه» → صبر
                    m = self.host_phase("dawn")
                    if g.s.phase not in (Phase.NIGHT, Phase.INTERROGATION):
                        break
                    if m is not None and "فرصتِ اضافه" in m.text:
                        self.tg.clock.advance((g.remaining() or 0) + 1)
        elif not any("همه‌ی نقش‌ها تصمیمشان را گرفتند" in m.text
                     for m in self.tg.inbox(self.group) if m.mid > mark):
            self.r.find("بالا", "شب", "شب با آخرین تصمیم بسته شد ولی پیام صبح به گروه نرسید",
                        key="auto-dawn-silent")
        else:
            self.r.ok("شب: آخرین تصمیم → صبحِ خودکار در گروه")
        if g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
            return                                      # حلقه‌ی بعدی گیر را می‌گیرد
        announced = self.group_since(mark)
        self.ref.after_dawn(announced)
        for name in re.findall(r"اثر انگشت روی صحنه به \*(.+?)\*", announced):
            for a in self.agents:
                a.suspicion[name] = a.suspicion.get(name, 0) + 2
        self.check_lab(day_before)

    def run_timer(self) -> None:
        g, ph = self.g, self.g.s.phase
        for _ in range(40):
            self.tg.clock.advance(15)
            self.tg.timer_job()
            if g.s.phase is not ph:
                return

    def ab(self, a: Agent) -> str:
        """توانایی‌ای که خودِ agent فکر می‌کند دارد (جانشینی را از پیوی فهمیده)."""
        return "kill" if a.heir else ROLES[a.role].ability

    def night_turn(self, a: Agent) -> None:
        g = self.g
        p = g.s.players[a.uid]
        if not p.in_game:
            return
        ab = self.ab(a)
        if p.custody is Custody.INTERROGATION:
            m = a.navigate("defense")
            if m and "دفاع تو" in m.text:
                a.say("من بی‌گناهم؛ آن شب تا صبح خانه‌ی خواهرم بودم.")
                if g.s.defense_text:
                    self.r.ok("متهم: ثبت دفاع")
                else:
                    self.r.find("متوسط", "بازجویی", "دفاعِ متهم ثبت نشد", a.last.text if a.last else "")
            return
        if p.custody is Custody.TEMP_JAIL:
            return
        if a.rng.random() < 0.12:
            m = a.navigate("will")
            if m and "وصیت" in m.text:
                a.say(f"اگر مُردم، به {self.rng.choice(NAMES[:self.n])} شک کنید.")
        if not ab:
            return
        if a.role == "کارآگاه" and a.rng.random() < 0.15:
            if self.expose(a):
                return
        panel = a.tap(cb_is("act"), ("dm",), depth=3, nav="act")
        if panel is None or panel.chat != a.uid:
            self.r.find("بالا", "دکمه‌ها", "پنل «🌙 اکشن شبانه» باز نشد", a.role)
            return
        if ab == "hunter":
            btns = a.buttons_named(panel, "hunter:")
            if btns and p.hunter_target is None:
                b = a.rng.choice(btns)
                m = a.press(panel, b)
                if m and m.ok and p.hunter_target == int(b["callback_data"].split(":")[1]):
                    self.r.ok("شکارچی: ثبت هدف شلیک آخر")
                else:
                    self.r.find("بالا", "توانایی‌ها", "دکمه‌ی هدف شکارچی ثبت نشد", m.text if m else "")
            return
        btns = a.buttons_named(panel, "act:")
        if not btns:
            # قاعده: بازداشتی‌ها در امان‌اند، هم‌تیمی ممنوع، پزشک دو شب پیاپی نه — آیا واقعاً کسی نمانده؟
            others = [q for q in g.s.alive_players() if q.uid != a.uid]
            open_ = [q for q in others if q.free and not (
                ab in ("kill", "poison", "frame") and ROLES[a.role].align is Align.KILLER
                and q.align is Align.KILLER)]
            legal = g.legal_targets(a.uid)
            if legal and (open_ and ab in ("kill", "poison", "frame", "hide") or
                          ab not in ("kill", "poison", "frame", "hide", "protect") and others):
                self.r.find("متوسط", "دکمه‌ها", f"{a.role} در شب هیچ هدفِ مجازی نداشت", panel.text[:160])
            elif "هدفِ مجازی نداری" not in panel.text:
                self.r.find("پایین", "رابط", "پنل اکشن بی‌هدف توضیح نمی‌دهد چرا", key="no-target-why")
            else:
                self.r.ok("پنل اکشن: «هدفی نمانده» با توضیح")
            if a.uid in g.pending_actors():
                self.r.find("متوسط", "جریان بازی", "بازیکنِ بی‌هدف «منتظرِ اکشن» می‌ماند", key="no-target-pending")
            return
        b = self.pick(a, ab, btns)
        tgt = int(b["callback_data"].split(":")[1])
        self.ref.intent(a.uid, ab, tgt)                 # پیش از زدن: آخرین تصمیم خودش شب را می‌بندد
        m = a.press(panel, b)
        if not (m and m.ok and "ثبت شد" in m.text):
            self.ref.intents.pop(a.uid, None)
            self.r.find("بالا", "دکمه‌ها", "دکمه‌ی هدفِ پیشنهادیِ خودِ ربات رد شد",
                        f"{a.role} → {b['text']}: {m.text if m else '—'}", key=f"act-rejected:{ab}")
            return
        if ab == "investigate" and ("→ پاک" in m.text or "→ مشکوک" in m.text):
            self.r.find("بالا", "توانایی‌ها", "نتیجه‌ی استعلام پیش از سحر داده شد")
        # گاهی نظرش عوض می‌شود: دوباره انتخاب = ویرایش اکشن
        if a.rng.random() < 0.15 and len(btns) > 1 and g.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
            other = self.pick(a, ab, [x for x in a.buttons_named(m, "act:") if x is not None])
            prev = self.ref.intents.get(a.uid)
            self.ref.intent(a.uid, ab, int(other["callback_data"].split(":")[1]))
            m2 = a.press(m, other)
            if not (m2 and m2.ok) and prev:
                self.ref.intents[a.uid] = prev

    def pick(self, a: Agent, ab: str, btns: List[dict]) -> dict:
        names = [(b, a.name_of_button(b)) for b in btns]
        if ab in ("kill", "poison", "frame") and a.team is not None and ROLES[a.role].align is Align.KILLER:
            pool = [b for b, n in names if n not in a.team] or btns
            if self.talk and ab in ("kill", "poison"):
                loud = self.talk.kill_priority(a, [n for _, n in names])
                if loud and a.rng.random() < 0.75:
                    return next(b for b, n in names if n == loud)
            return a.rng.choice(pool)
        if ab == "protect" and a.rng.random() < 0.35:
            # «حدسِ خوش‌شانس»: پزشک گاهی دقیقاً هدفِ امشبِ قاتل را نجات می‌دهد تا مسیر نجات هم سنجیده شود
            kills = [t for u, (x, t) in self.ref.intents.items() if x in ("kill", "poison")]
            lucky = [b for b in btns if int(b["callback_data"].split(":")[1]) in kills]
            if lucky:
                return a.rng.choice(lucky)
        if ab == "investigate":
            pool = [b for b, n in names if n not in a.clean and n not in a.dirty] or btns
            return a.rng.choice(pool)
        return a.rng.choice(btns)

    def expose(self, a: Agent) -> bool:
        m = a.navigate("expose")
        evs = a.buttons_named(m, "expose:")
        if not evs:
            return False
        m = a.press(m, a.rng.choice(evs))
        if m and m.ok and ("راست ✅" in m.text or "دروغ ❌" in m.text):
            self.ref.intent(a.uid, "expose", 0)
            self.r.ok("کارآگاه: راستی‌آزمایی مدرک")
            return True
        return False

    def officer_done(self) -> None:
        """بازجو «✅ بازجویی تمام شد» را می‌زند؛ شبِ بازجویی تا آن وقت منتظرش می‌ماند."""
        g = self.g
        off = self.agent(g.s.officer_uid)
        if not off or not g._officer_on_duty(off.uid):
            return
        if off.uid not in g.pending_actors():
            self.r.find("بالا", "شب", "شبِ بازجویی منتظرِ بازجو نماند", key="officer-not-awaited")
        m = off.tap(cb_is("pass"), ("dm", "group"), depth=8, nav="pass")
        if m and m.ok and (g.passed(off.uid) or g.s.phase not in (Phase.NIGHT, Phase.INTERROGATION)):
            self.r.ok("بازجو: «✅ بازجویی تمام شد» شب را آزاد کرد")
        else:
            self.r.find("بالا", "دکمه‌ها", "دکمه‌ی «✅ بازجویی تمام شد» کار نکرد", m.text if m else "")

    def officer_questions(self) -> None:
        g = self.g
        off = self.agent(g.s.officer_uid)
        if not off:
            return
        m = off.tap(cb_is("hints"), ("group",), depth=8, nav="hints")
        if m and m.ok:
            if m.chat != off.uid:
                self.r.find("بالا", "امنیت", "سرنخ‌های بازجو در گروه دیده شد")
            else:
                self.r.ok("بازجو: سرنخ‌ها در پیوی")
        sus = self.agent(g.s.suspect_uid)
        q = self.rng.choice(QUESTIONS)
        for i in range(2):                              # دو بار همان سؤال → تناقض‌یاب
            m = off.tap(cb_is("ask"), ("dm", "group"), depth=6, nav="ask")
            if not (m and "پرسش از متهم" in m.text):
                return
            ans = off.say(q)
            if not ans.ok:
                self.r.find("متوسط", "بازجویی", "پرسشِ بازجو رد شد", ans.text,
                            key=f"ask-fail:{ans.text[:40]}")
                return
            # پرسش باید به پیوی متهم رسیده باشد، با دکمه‌ی «جواب بده»
            got = sus and sus.find(cb_is("answer"), ("dm",), 3)
            if not got or q not in got[0].text:
                self.r.find("بالا", "بازجویی", "پرسش بازجو به متهم نرسید", key="ask-not-delivered")
                return
            prompt = sus.press(*got)
            lie = ROLES[sus.role].align is not Align.CITY and i == 1
            said = "آن شب تنها بودم." if lie else "خانه بودم، همسایه‌ها دیدند."
            reply = sus.say(said)
            back = off.tg.last(off.uid)
            if reply.ok and back and "جواب" in back.text and said in back.text:
                self.r.ok("بازجویی دونفره: پرسش → متهم → جواب → بازجو")
                if lie and "تناقض" in back.text:
                    self.r.ok("تناقض‌یاب روی جواب واقعی متهم")
            else:
                self.r.find("بالا", "بازجویی", "جواب متهم به بازجو نرسید",
                            f"{reply.text[:80]} / {back.text[:80] if back else '—'}", key="answer-not-delivered")

    def check_lab(self, day: int) -> None:
        log = "\n".join(self.g.s.log)
        for code, due in list(self.lab_due.items()):
            if due <= day:
                del self.lab_due[code]
                c = next(x for x in self.g.s.clues if x["code"] == code)
                if f"نتیجه‌ی آزمایشگاه: سرنخ {code}" in log and c["verified"] is c["genuine"]:
                    self.r.ok("آزمایشگاه: نتیجه‌ی راست/دروغِ درست، سر موعد")
                else:
                    self.r.find("متوسط", "مدارک", "نتیجه‌ی آزمایشگاه سر موعد نرسید", code)

    # ─────────────────────────── صبح ───────────────────────────
    def morning(self) -> None:
        g = self.g
        sus = g.s.suspect_uid
        if sus is not None and g.s.players[sus].custody is Custody.INTERROGATION:
            if not g.s.players[sus].jury_used and self.rng.random() < 0.35:
                self.request_jury(sus)
                if g.s.phase is Phase.JURY:
                    return
            if g.s.suspect_uid is not None:
                self.verdict(g.s.suspect_uid)
        if g.s.phase is not Phase.MORNING:
            return
        m = self.host_phase("discuss", depth=6)
        if g.s.phase is Phase.MORNING and m is not None and not m.ok:
            self.r.find("متوسط", "جریان بازی", "«💬 گفتگو» صبح باز نشد", m.text)

    def request_jury(self, sus: int) -> None:
        g = self.g
        askers = [a for a in self.agents if g.s.players[a.uid].can_vote and a.uid != sus]
        self.rng.shuffle(askers)
        for a in askers[:2]:
            if g.s.phase is Phase.JURY:                  # وکیل به‌تنهایی کافی بود
                break
            self.check_dashboard()                       # دکمه‌ی ⚖️ روی داشبورد صبح
            m = a.tap(cb_is("jury"), ("group",), depth=2) or a.navigate("jury")
            if m and not m.ok:
                self.r.find("متوسط", "هیئت منصفه", "درخواست هیئت منصفه رد شد", m.text,
                            key=f"jury-req:{m.text[:40]}")
                return
        if g.s.phase is Phase.JURY:
            self.r.ok("هیئت منصفه: تشکیل با ۲ درخواست")
            self.jury()

    def verdict(self, sus: int) -> None:
        g = self.g
        off = self.agent(g.s.officer_uid)
        offp = g.s.players[off.uid]
        tp = g.s.players[sus]
        # پیش از حکم: اگر زندانیِ موقتی هست که بازجو فکر می‌کند بی‌گناه است
        jailed = [p for p in g.s.players.values() if p.custody is Custody.TEMP_JAIL]
        if jailed and offp.in_game and self.rng.random() < 0.4:
            m = off.navigate("clear")
            btns = off.buttons_named(m, "clear:")
            if btns:
                b = off.rng.choice(btns)
                who = int(b["callback_data"].split(":")[1])
                r = off.press(m, b)
                if r and r.ok and g.s.players[who].custody is Custody.FREE:
                    self.r.ok("بازجو: آزادی زندانی قبلی (با متهم جدید)")
                    self.ref.temp_nights.pop(who, None)
        if self.talk:
            guilty = (tp.name not in off.team and self.talk.score(off, sus) >= 2.5
                      if not self.talk.is_killer_agent(off) else tp.name not in off.team)
            confirm = off.uid != sus and guilty
        else:
            confirm = (off.uid != sus) and (tp.name in off.dirty or off.rng.random() < 0.55)
        x = 1 if confirm else 0
        m = off.tap(cb_is(f"ver:{sus}:{x}"), ("group",), depth=12)
        if m is None:
            m = off.tap(cb_is(f"verdict:{sus}:{x}"), ("dm",), depth=4)
        if m is None:
            m = off.navigate("verdict")
            if m and m.ok:
                m = off.tap(cb_is(f"verdict:{sus}:{x}"), ("dm",), depth=1)
        if m is None:
            return
        if m.ok:
            if not offp.in_game:
                self.r.find("بالا", "بازجویی", "بازجوی حذف‌شده هنوز حکم صادر می‌کند",
                            f"{off.name} ({'کشته' if not offp.alive else offp.custody.value}) حکم "
                            f"{'حبس' if confirm else 'آزادی'} {tp.name} را داد. officer_verdict فقط "
                            "آیدی را می‌سنجد نه اینکه بازجو هنوز در بازی است.", key="dead-officer-verdict")
            if off.uid == sus:
                self.r.find("بحرانی", "بازجویی", "بازجو وقتی خودش متهم است، خودش را تبرئه می‌کند",
                            f"رای گروه {off.name} (بازجو) را به بازجویی فرستاد؛ صبح بعد همان دکمه‌ی "
                            "«🔓 تایید بی‌گناهی» را زد و آزاد شد. هیچ مانعی در officer_verdict نیست.",
                            key="officer-self-acquit")
            if m.chat != self.group:
                self.r.find("متوسط", "رابط", "حکم بازجو فقط در پیوی خودش اعلام شد",
                            "دکمه‌ی حکم از پیوی زده شد؛ پاسخ غیرخصوصی است پس آداپتور آن را در همان پیوی "
                            "می‌فرستد و گروه نمی‌فهمد متهم آزاد شد یا زندانی.", key="verdict-dm")
            if confirm and tp.custody is Custody.TEMP_JAIL:
                self.ref.after_temp_jail(sus)
                self.r.ok("بازجو: حکم حبس موقت")
            elif not confirm and tp.custody is Custody.FREE:
                self.r.ok("بازجو: حکم آزادی")
            self.ref.check_invariants("حکم")
            self.ref.check_win("حکم")
        elif not offp.free or off.uid == sus:
            self.r.ok("بازجوی ناتوان/متهم حکم نمی‌دهد")

    # ─────────────────────────── گفتگو و رای ───────────────────────────
    def discussion(self) -> None:
        g = self.g
        if self.talk:
            self.talk.day()
        talkers = [a for a in self.agents if g.s.players[a.uid].can_speak]
        if talkers and self.rng.random() < (0.8 if self.talk else 0.35):
            self.interp(self.rng.choice(talkers))
        if talkers and self.rng.random() < (0.6 if self.talk else 0.25):
            self.lab(self.rng.choice(talkers))
        if talkers and self.rng.random() < 0.2:
            a = self.rng.choice(talkers)
            m = a.navigate("note")
            if m and "یادداشت" in m.text:
                r = a.say("به کسی که دیشب ساکت بود شک دارم.")
                if r.ok:
                    self.r.ok("یادداشت خصوصی")
        if not g.s.sos_used and self.rng.random() < 0.12:
            self.sos()
        if g.s.phase is not Phase.DISCUSSION:
            return
        if self.mode == "timer":
            self.run_timer()
        else:
            self.host_phase("vote", depth=4)

    def interp(self, a: Agent) -> None:
        m = a.navigate("interp")
        evs = a.buttons_named(m, "interp:")
        if not evs:
            return
        m = a.press(m, a.rng.choice(evs))
        opts = [b for b in a.buttons_named(m, "interp:") if b["callback_data"].count(":") == 2]
        if opts:
            pick = a.rng.choice(opts)
            if self.talk:                     # 👍 = راست (idx 1)، 👎 = کاشته (idx 0) طبق باورش
                code = opts[0]["callback_data"].split(":")[1]
                want = "1" if self.talk.believes(a, code) else "0"
                pick = next((b for b in opts if b["callback_data"].endswith(":" + want)), pick)
            r = a.press(m, pick)
            if r and r.ok and "باور دارند" in r.text:
                self.r.ok("رای تفسیر مدرک")

    def lab(self, a: Agent) -> None:
        m = a.navigate("lab")
        evs = a.buttons_named(m, "lab:")
        if not evs:
            return
        b = self.pick_lab(a, evs)
        r = a.press(m, b)                             # «عادی یا فوری؟»
        code = b["callback_data"].split(":")[1]
        hit = a.find(cb_is(f"lab:{code}:N"), ("dm", "group"), 2)
        r = a.press(*hit) if hit else None
        if r and r.ok and code not in self.lab_due:
            from karagah.roles import scenario_rules
            self.lab_due[code] = self.g.s.day + scenario_rules(self.scenario)["lab_nights"]

    def pick_lab(self, a: Agent, evs: List[dict]) -> dict:
        """سرنخی را به آزمایشگاه بفرست که بیشترین مظنون را جدا می‌کند (نیمی جور، نیمی نه)."""
        from karagah.clues import matches
        alive = self.g.s.alive_players()
        def split(b):
            c = self.g.clue(b["callback_data"].split(":")[1])
            k = sum(matches(p, c) for p in alive)
            return -abs(k - len(alive) / 2)
        if self.talk:                          # سرنخی که سرش دعواست اول (ادعاهای متناقض در چت)
            hot = self.talk.contested()
            pool = [b for b in evs if b["callback_data"].split(":")[1] in hot]
            if pool:
                return a.rng.choice(pool)
        return max(evs, key=lambda b: (split(b), a.rng.random()))

    def sos(self) -> None:
        g = self.g
        votes = {}
        for a in self.agents:
            for n, c in a.suspicion.items():
                votes[n] = votes.get(n, 0) + c
        cand = [p for p in g.s.alive_players() if p.can_speak]
        if not cand:
            return
        target = max(cand, key=lambda p: (votes.get(p.name, 0), self.rng.random()))
        backers = [a for a in self.agents if g.s.players[a.uid].can_vote and a.uid != target.uid]
        last = None
        for a in backers:
            m = a.navigate("sos")
            b = a.find(cb_is(f"sos:{target.uid}"), ("dm",), 1)
            if b:
                last = a.press(*b)
        if target.custody is Custody.TEMP_JAIL:
            self.r.ok("رای اضطراری ۸۰٪: مستقیم به حبس موقت")
            self.ref.after_temp_jail(target.uid)
            if last and last.chat != self.group:
                self.r.find("پایین", "رابط", "تصویب رای اضطراری فقط در پیوی آخرین رای‌دهنده اعلام شد",
                            "دکمه‌ی «🚨 رای اضطراری» در منوی پیوی است؛ پیامِ «تصویب شد» غیرخصوصی است "
                            "و در همان پیوی می‌ماند.", key="sos-dm")
            self.ref.check_win("رای اضطراری")

    def vote(self) -> None:
        g = self.g
        voters = [a for a in self.agents if g.s.players[a.uid].can_vote]
        self.rng.shuffle(voters)
        seen_kb = self.host.find(cb_starts("vote:"), ("group",), 60)
        if seen_kb is None:
            why = {"timer": "رای‌گیری را تایمر باز کرد و پیام تایمر («⏰ گفتگو تمام شد؛ رای‌گیری آغاز شد») "
                            "هیچ کیبوردی ندارد",
                   "dm": "میزبان «🗳️ رای‌گیری» را از منوی پیوی زد؛ پاسخ غیرخصوصی است، پس کیبورد رای "
                         "در پیوی میزبان افتاد نه در گروه"}.get(self.mode, "کیبورد رای فرستاده نشد")
            self.r.find("بالا", "رابط", f"رای‌گیری باز شد ولی گروه دکمه‌ی رای ندارد ({MODE_FA[self.mode]})",
                        why + "؛ بقیه نمی‌توانند رای بدهند و رای‌گیری خالی بسته می‌شود.",
                        key=f"no-vote-kb:{self.mode}")
        for a in voters:
            hit = a.find(cb_starts("vote:"), ("group",), 60)   # بالا اسکرول می‌کند
            if not hit:
                continue
            msg, _ = hit
            options = [b for b in msg.buttons() if b["callback_data"].startswith("vote:")
                       and b["callback_data"] != "vote:0"]
            if a.rng.random() < 0.08:
                r = a.press(msg, next(b for b in msg.buttons() if b["callback_data"] == "vote:0"))
                if r and not r.ok:
                    self.r.find("متوسط", "دکمه‌ها", "دکمه‌ی «⏭️ رای ممتنع» خطا می‌دهد",
                                f"پاسخ: «{r.text}». vote:0 به castvote با هدف ۰ می‌رود و موتور "
                                "«هدف نامعتبر است» برمی‌گرداند؛ ممتنع هیچ‌وقت ثبت نمی‌شود.", key="abstain")
                continue
            b = self.choose_vote(a, options)
            if b is None:
                continue
            r = a.press(msg, b)
            if r and not r.ok and "خودت" in r.text:
                self.r.find("پایین", "رابط", "کیبورد رای دکمه‌ی خودِ رای‌دهنده را هم نشان می‌دهد",
                            "vote_kb یک کیبورد مشترک برای همه است؛ زدن اسم خودت خطا می‌دهد.", key="self-vote")
        if self.mode == "timer":
            self.run_timer()
        else:
            m = self.host_phase("closevote")
            if m and "شب فرا می‌رسد" in m.text and g.s.phase is Phase.VOTE:
                self.r.find("متوسط", "رابط", "پیام تساوی می‌گوید «شب فرا می‌رسد» ولی دور دوم رای باز است",
                            "close_vote در اولین تساوی فاز را روی رای‌گیری نگه می‌دارد (مرگ ناگهانی) اما "
                            "h_closevote همان متن «کسی بازداشت نشد. شب فرا می‌رسد.» و دکمه‌ی «🌙 پایان شب» را "
                            "می‌دهد؛ زدن آن دکمه خطای «الان شب نیست» می‌دهد و کیبورد رای تازه هم فرستاده نمی‌شود.",
                            key="tie-message")
        self.ref.check_invariants("رای")

    def choose_vote(self, a: Agent, options: List[dict]) -> Optional[dict]:
        named = [(b, a.name_of_button(b)) for b in options if a.name_of_button(b) != a.name]
        if not named:
            return None
        if self.talk:
            return self.talk.vote_choice(a, named)
        if ROLES[a.role].align is Align.KILLER:
            pool = [b for b, n in named if n not in a.team] or [b for b, _ in named]
            return a.rng.choice(pool)
        dirty = [b for b, n in named if n in a.dirty]
        if dirty:
            return dirty[0]
        pool = [(b, a.suspicion.get(n, 0)) for b, n in named if n not in a.clean]
        if not pool:
            return a.rng.choice([b for b, _ in named])
        top = max(s for _, s in pool)
        return a.rng.choice([b for b, s in pool if s == top] if top and a.rng.random() < 0.6
                            else [b for b, _ in pool])

    def jury(self) -> None:
        g = self.g
        sus = g.s.suspect_uid
        yes = total = 0
        for a in self.agents:
            if not g.s.players[a.uid].can_vote:
                continue
            hit = a.find(cb_starts("jury:"), ("group",), 40)
            if not hit:
                self.r.find("بالا", "هیئت منصفه", "دکمه‌های رای هیئت منصفه در گروه نیست", key=f"no-jury-kb:{self.mode}")
                break
            if self.talk and sus:
                acquit = self.talk.acquit(a, sus)
            else:
                acquit = (sus and g.s.players[sus].name in a.team) or a.rng.random() < 0.5
            b = next(x for x in hit[0].buttons() if x["callback_data"] == f"jury:{1 if acquit else 0}")
            r = a.press(hit[0], b)
            if r and r.ok:
                total += 1
                yes += int(bool(acquit))
        if self.mode == "timer":
            self.run_timer()
        else:
            self.host_phase("closejury", depth=6)
        if g.s.phase is Phase.JURY:
            return
        freed = sus is not None and g.s.players[sus].custody is Custody.FREE
        from karagah.roles import scenario_rules
        pct = scenario_rules(self.scenario)["jury"]
        want = total and yes * 100 >= pct * total
        if bool(want) == freed:
            self.r.ok(f"هیئت منصفه: آستانه‌ی {pct}٪ ({self.scenario})")
        else:
            self.r.find("بالا", "هیئت منصفه", f"نتیجه‌ی هیئت منصفه با آستانه‌ی {pct}٪ نمی‌خواند",
                        f"{yes}/{total} تبرئه — آزاد شد؟ {freed}")

    # ─────────────────────────── پایان ───────────────────────────
    def finish(self) -> None:
        m = self.host.tap(cb_is("end"), ("group",), depth=4)
        if m is None:
            self.check_dashboard()
            m = self.host.tap(cb_is("end"), ("group",), depth=1)
        if m is None or not m.ok:
            self.r.find("بالا", "پایان", "دکمه‌ی «🏁 پایان و افشا» در دسترس نبود", m.text if m else "")
            return
        self.ref.check_end(m.text)
        self.ref.check_win("پایان")

    def summary(self) -> dict:
        g = self.g
        return {"players": self.n, "seed": self.seed, "mode": MODE_FA[self.mode],
                "scenario": scenario_name(self.scenario),
                "case": f"#{g.s.case.cid}" if g and g.s.case else "—",
                "winner": g.s.winner if g else None, "days": g.s.day if g else 0,
                "presses": self.tg.presses, "finished": bool(g and g.s.phase is Phase.END and not self.stuck),
                "stuck": self.stuck,
                "roles": {a.name: a.role for a in self.agents},
                "talk": self.talk.summary() if self.talk else None,
                "arrests": self.arrests(), "clues": self.clue_stats(),
                "rumors": list(self.ref.rumors) if self.ref else [0, 0],
                "winner_team": self.winner_team()}

    def winner_team(self) -> str:
        w = (self.g.s.winner or "") if self.g else ""
        return ("city" if "شهر" in w else "killers" if "قاتل" in w else
                "serial" if "جانی" in w else "scapegoat" if "سپر" in w else "none")

    def clue_stats(self) -> dict:
        g = self.g
        if not g:
            return {}
        cl = g.s.clues
        by = {}
        for c in cl:
            by[c["source"]] = by.get(c["source"], 0) + 1
        return {"total": len(cl), "true": sum(c["genuine"] for c in cl),
                "false": sum(not c["genuine"] for c in cl),
                "verified": sum(c["verified"] is not None for c in cl),
                "verified_right": sum(c["verified"] is c["genuine"] for c in cl if c["verified"] is not None),
                "by_source": by}

    def arrests(self) -> dict:
        """چند بار شهر درست آدم گرفت: بازجویی‌شده‌ها و زندانی‌ها در برابر نقشِ واقعی."""
        g = self.g
        if not g:
            return {}
        self.jailed |= {p.uid for p in g.s.players.values()
                        if p.custody in (Custody.TEMP_JAIL, Custody.LIFE_JAIL)}
        bad = lambda u: g.s.players[u].align is Align.KILLER or g.s.players[u].role == "جانی سریالی"
        return {"interrogated": len(self.interrogated),
                "interrogated_evil": sum(map(bad, self.interrogated)),
                "jailed": len(self.jailed), "jailed_evil": sum(map(bad, self.jailed))}


def run_session(n: int, seed: int, report: Report, rb: Rulebook, mode: str = "group",
                scenario: str = "classic", talk: bool = True) -> dict:
    s = Session(n, seed, report, rb, mode, scenario, talk)
    try:
        if s.lobby():
            s.play()
    finally:
        s.tg.close()
    out = s.summary()
    report.games.append(out)
    return out
