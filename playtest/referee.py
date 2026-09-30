"""داور مستقل: پیش از هر سحر پیش‌بینی می‌کند، بعد با نتیجه‌ی ربات مقایسه می‌کند.

قواعد از روی متنِ نقش‌ها و مستندات نوشته شده‌اند، نه با صدا زدن موتور؛
داور فقط وضعیت را می‌خواند (نمای خدا)، هیچ‌وقت چیزی را عوض نمی‌کند.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Set

from karagah.models import Align, Custody, Phase
from karagah.roles import COMPOSITIONS, ROLES

VISIT_FREE = ("investigate", "expose", "watch")   # «از دور نگاه کردن» ملاقات نیست


class Referee:
    def __init__(self, game, agents, report):
        self.g, self.agents, self.r = game, {a.uid: a for a in agents}, report
        self.poison_due: Dict[int, int] = {}      # هدف → شبِ مرگ
        self.frame_until: Dict[int, int] = {}
        self.temp_nights: Dict[int, int] = {}     # زندانی موقت → شب‌های گذرانده
        self.intents: Dict[int, tuple] = {}       # uid → (ability, target) امشب
        self.before: Dict[int, tuple] = {}
        self.night_day = 0
        self.suspect_at_night: Optional[int] = None
        self.mode = ""                            # «دکمه در گروه» / «تایمر» / «پیوی»

    @property
    def s(self):
        return self.g.s

    def name(self, uid) -> str:
        return self.s.players[uid].name

    # ── شروع بازی ──
    def check_start(self) -> None:
        n = len(self.s.players)
        got = Counter(p.role for p in self.s.players.values())
        if got != Counter(COMPOSITIONS[n]):
            self.r.find("بالا", "نقش‌ها", f"پخش نقش در بازی {n} نفره با COMPOSITIONS نمی‌خواند",
                        f"{dict(got)}")
        else:
            self.r.ok("پخش نقش مطابق ترکیب")
        killers = {p.name for p in self.s.players.values() if p.align is Align.KILLER}
        for a in self.agents.values():
            p = self.s.players[a.uid]
            if a.role != p.role:
                self.r.find("بالا", "نقش‌ها", "کارت نقشِ پیوی با نقش واقعی فرق دارد",
                            f"{a.name}: کارت «{a.role}» — موتور «{p.role}»")
                continue
            if ROLES[p.role].info == "team_ids" and a.team != (killers - {a.name}):
                self.r.find("بالا", "نقش‌ها", "قاتل‌ها هم‌تیمی‌هایشان را درست نمی‌شناسند",
                            f"{a.name} می‌داند {a.team} — واقعی {killers - {a.name}}")
            if p.role == "خبرچین" and len(killers) > 1 and not a.team:
                self.r.find("متوسط", "نقش‌ها", "خبرچین هم‌تیمی‌هایش را نمی‌شناسد، ولی آن‌ها او را می‌شناسند",
                            "info خبرچین «watch_officer» است، پس کارت نقشش هیچ هم‌تیمی‌ای نشان نمی‌دهد؛ "
                            "در حالی که کارت قاتل و همدست «هم‌تیمی: خبرچین» را نشان می‌دهد. "
                            "یک‌طرفه بودنِ این دانش عمدی به نظر نمی‌رسد.", key="spy-team")
        self.r.ok("کارت نقش در پیوی")

    # ── شب ──
    def begin_night(self) -> None:
        self.intents = {}
        self.night_day = self.s.day
        self.suspect_at_night = self.s.suspect_uid
        self.before = {u: (p.alive, p.custody, p.custody_nights, p.in_game)
                       for u, p in self.s.players.items()}

    def intent(self, uid: int, ability: str, target: int) -> None:
        self.intents[uid] = (ability, target)

    def pre_dawn(self) -> None:
        """درست پیش از «پایان شب»: آنچه agentها زدند = آنچه موتور ثبت کرده؟"""
        committed = {actor: (ab, t) for ab, pairs in self.g._committed_actions().items()
                     for actor, t in pairs.items() if ab != "expose"}
        mine = {u: v for u, v in self.intents.items() if v[0] != "expose"}
        if committed != mine:
            self.r.find("بالا", "دکمه‌ها", "اکشنِ ثبت‌شده با دکمه‌ای که بازیکن زد فرق دارد",
                        f"دکمه‌ها: {mine} — موتور: {committed}", key="intent-mismatch")
        else:
            self.r.ok("دکمه‌ی اکشن شبانه → ثبت در موتور")

    def after_dawn(self, announced: str) -> None:
        s, day = self.s, self.night_day
        acts: Dict[str, Dict[int, int]] = {}
        for u, (ab, t) in self.intents.items():
            acts.setdefault(ab, {})[u] = t
        protected = set(acts.get("protect", {}).values())
        storm = s.night_event.startswith("طوفان")
        for t in acts.get("poison", {}).values():
            self.poison_due.setdefault(t, day + 2)
        for t in acts.get("frame", {}).values():
            self.frame_until[t] = day + 1
        alive_before = {u for u, b in self.before.items() if b[0] and b[3]}

        expect: List[int] = []
        for t in acts.get("kill", {}).values():
            if t not in protected and t not in expect:
                expect.append(t)
        if storm:
            expect = []
        for t, due in list(self.poison_due.items()):
            if due > day:
                continue
            del self.poison_due[t]
            if t in protected:
                self.r.ok("سم: نجات پزشک در شبِ سررسید")
            elif t in alive_before and t not in expect:
                expect.append(t)
        if s.fate_pair:
            a, b = s.fate_pair
            if a in expect and b not in expect and b in alive_before:
                expect.append(b)
            elif b in expect and a not in expect and a in alive_before:
                expect.append(a)
        for u in list(expect):
            p = s.players[u]
            if p.role == "شکارچی" and p.hunter_target in alive_before and p.hunter_target not in expect:
                expect.append(p.hunter_target)

        died = {u for u in alive_before if not s.players[u].alive}
        if died == set(expect):
            if s.fate_pair and set(s.fate_pair) <= died:
                self.r.ok("زوج سرنوشت: مرگ همراه")
            if any(s.players[u].role == "شکارچی" and s.players[u].hunter_target in died for u in died):
                self.r.ok("شکارچی: شلیک آخر هنگام مرگ")
            if day == 1 and s.phase is Phase.END:
                self.r.find("متوسط", "تعادل", "بازی در همان سحرِ اول تمام شد — بدون هیچ روز و رایی",
                            f"{len(s.players)} نفره: {len(died)} نفر در شب اول مردند "
                            f"({'، '.join(self.name(u) for u in died)}) و قاتل‌ها به برابری رسیدند. "
                            "در ترکیب ۱۰ نفره دو قاتلِ مستقل (قاتل + جانی سریالی) + زوج سرنوشت + شلیک شکارچی "
                            "می‌توانند ۴ نفر را در یک شب ببرند؛ ۳ قاتل در برابر ۷ نفر فقط ۴ مرگ تا برابری فاصله دارند.", key="first-dawn-end")
        if died != set(expect):
            detail = (f"شب {day}: انتظار مرگ {[self.name(u) for u in expect]} — "
                      f"ربات: {[self.name(u) for u in died]} | اکشن‌ها: "
                      + ", ".join(f"{self.name(u)}:{ab}→{self.name(t)}"
                                  for u, (ab, t) in self.intents.items() if t in s.players)
                      + (" | طوفان" if storm else ""))
            self.r.find("بحرانی", "توانایی‌ها", "مرگ‌های سحر با قواعد نقش‌ها نمی‌خواند", detail,
                        key=f"deaths:{day}:{sorted(died)}:{sorted(expect)}")
        else:
            for ab in ("kill", "protect", "poison"):
                if ab in acts:
                    self.r.ok({"kill": "قتل: مرگ در همان سحر",
                               "protect": "پزشک: هدفِ نجات‌یافته زنده ماند",
                               "poison": "سم: زمان‌بندی دو شب"}[ab])
            if storm and "kill" in acts:
                self.r.ok("طوفان: حمله لغو شد")
        # اعلامِ مرگ‌ها در گروه
        if "⚰️ کشته‌شده" not in announced:
            why = {"تایمر": "مهلت شب تمام شد و _timer_job فقط متن tick («⏰ شب به پایان رسید.» + تابلو) را "
                            "فرستاد؛ h_dawn که کشته‌ها، مدرک روز، رویداد شب و ردها را می‌سازد اصلاً اجرا نمی‌شود.",
                   "دکمه از پیوی": "«🌅 پایان شب» از منوی پیوی زده شد؛ پاسخ h_dawn غیرخصوصی است پس آداپتور "
                                   "آن را در همان پیوی می‌فرستد و گروه هیچ پیامی نمی‌گیرد."}.get(self.mode, "")
            self.r.find("بالا", "رابط", f"پیام صبح (کشته‌ها، مدرک روز، ردها) به گروه نرسید — {self.mode}",
                        f"{why}\nگروه بعد از شب {day} فقط این را دید: «{announced[:120]}»",
                        key=f"morning-missing:{self.mode}")
        else:
            self.r.ok("اعلام صبح در گروه")
        # اطلاعات نقش‌ها
        hidden = set(acts.get("hide", {}).values())
        visits = Counter(t for ab, pairs in acts.items() if ab not in VISIT_FREE
                         for t in pairs.values())
        for actor, tgt in acts.get("investigate", {}).items():
            if tgt in hidden:
                res = "پاک"
            elif self.frame_until.get(tgt, 0) >= day:
                res = "مشکوک"
            else:
                res = "پاک" if s.players[tgt].align is Align.CITY else "مشکوک"
            self._expect_note(actor, f"شب {day}: {self.name(tgt)} → {res}", "کارآگاه: نتیجه‌ی استعلام سحر")
        for actor, tgt in acts.get("watch", {}).items():
            n = 0 if tgt in hidden else visits.get(tgt, 0)
            self._expect_note(actor, f"🛡️ شب {day}: {self.name(tgt)} — {n} ملاقات", "نگهبان: شمارش ملاقات")
        for actor in acts.get("spy", {}):
            who = self.name(self.suspect_at_night) if self.suspect_at_night else "کسی"
            self._expect_note(actor, f"📞 شب {day}: بازجو سراغ {who} رفته بود.", "خبرچین: خبر بازجویی")
        for actor in acts.get("autopsy", {}):
            ev = s.case.evidence[min(day - 1, len(s.case.evidence) - 1)]
            res = "جعلی 🎭" if ev["misleading"] else "اصل ✅"
            self._expect_note(actor, f"🧪 شب {day}: مدرک {ev['code']} → {res}", "پزشک قانونی: اصالت مدرک")
        if "⚰️ کشته‌شده" in announced and "frame" in acts:
            if "اثر انگشت روی صحنه" in announced:
                self.r.ok("همدست: ردِ پاپوش در پیام صبح")
            else:
                self.r.find("متوسط", "توانایی‌ها", "ردِ پاپوشِ همدست در پیام صبح نیامد",
                            f"شب {day}", key="frame-trace")
        # بازداشت
        for u, b in self.before.items():
            p = s.players[u]
            if b[1] is Custody.TEMP_JAIL and b[3]:
                self.temp_nights[u] = self.temp_nights.get(u, 0) + 1
                want = Custody.LIFE_JAIL if self.temp_nights[u] >= self.g.temp_jail_nights else Custody.TEMP_JAIL
                if p.custody is not want and p.alive:
                    self.r.find("بالا", "بازداشت", "زمان‌بندی حبس موقت → حبس ابد اشتباه است",
                                f"{p.name}: {self.temp_nights[u]} شب — انتظار {want.value}، ربات {p.custody.value}")
                elif want is Custody.LIFE_JAIL:
                    self.r.ok("حبس موقت → حبس ابد بعد از ۲ شب")
                    self._hunter_on_life_jail(u)
        self.check_invariants("سحر")
        self.check_win("سحر")

    def _hunter_on_life_jail(self, u: int) -> None:
        p = self.s.players[u]
        if p.role != "شکارچی" or not p.hunter_target:
            return
        t = self.s.players[p.hunter_target]
        if t.in_game:
            self.r.find("متوسط", "توانایی‌ها", "شلیک آخر شکارچی با حبس ابد اجرا نمی‌شود",
                        f"متن نقش: «اگر حبس ابد بخورد یا کشته شود، یک نفر را با خود می‌برد». "
                        f"{p.name} حبس ابد گرفت و {t.name} (هدفش) هنوز در بازی است.",
                        key="hunter-lifejail")
        else:
            self.r.ok("شکارچی: شلیک آخر با حبس ابد")

    def _expect_note(self, uid: int, line: str, label: str) -> None:
        a = self.agents[uid]
        a.navigate("notes")
        text = a.last.text if a.last else ""
        a.learn_notes(text)
        if self.s.phase is Phase.END and "بازی فعالی" in text:
            self.r.find("متوسط", "رابط", "بعد از پایان بازی، دفترچه/نقش از پیوی باز نمی‌شود",
                        "route_chat فقط بازی‌های تمام‌نشده را پیدا می‌کند (games_of فاز END را کنار "
                        "می‌گذارد)؛ پس اگر بازی در همین سحر تمام شود، نتیجه‌ی آخرین استعلام/نگهبانیِ "
                        "بازیکن هرگز به دستش نمی‌رسد و «📓 دفترچه‌ی من» می‌گوید «بازی فعالی وجود ندارد».",
                        key="notes-after-end")
            text = "\n".join(self.s.players[uid].notes)     # نمای خدا برای سنجش خودِ توانایی
        if line in text:
            self.r.ok(label)
        else:
            self.r.find("بالا", "توانایی‌ها", f"{label} — نتیجه‌ی درست در دفترچه نیامد",
                        f"انتظار: «{line}»\nدفترچه:\n{text[-300:]}", key=f"note:{label}")

    # ── روز ──
    def after_temp_jail(self, uid: int) -> None:
        self.temp_nights[uid] = 0

    def check_invariants(self, when: str) -> None:
        s = self.s
        inter = [p for p in s.players.values() if p.custody is Custody.INTERROGATION and p.in_game]
        if len(inter) > 1 or (inter and s.suspect_uid != inter[0].uid):
            self.r.find("بالا", "بازداشت", "بازیکنی در «بازجویی» جا ماند و دیگر خارج نمی‌شود",
                        f"{when}: در بازجویی {[p.name for p in inter]} — suspect_uid="
                        f"{self.name(s.suspect_uid) if s.suspect_uid else None}. "
                        "وقتی حکمِ متهم داده نشود و روز به گفتگو/رای برود، رای بعدی متهم تازه را جایگزین "
                        "می‌کند و قبلی تا آخر بازی نه رای دارد نه اکشن.", key="stuck-interrogation")

    def expected_winner(self) -> Optional[str]:
        """شرط برد از روی متن نقش‌ها و PLAN.md."""
        s = self.s
        alive = s.alive_players()
        if any(p.role == "سپر بلا" and p.custody is Custody.LIFE_JAIL for p in s.players.values()):
            return "سپر بلا"
        if len(alive) == 1 and alive[0].role == "جانی سریالی":
            return "جانی سریالی"
        k = [p for p in alive if p.align is Align.KILLER]
        rest = [p for p in alive if p.align is not Align.KILLER]
        if not k:
            return "شهر"
        if len(k) >= len(rest):
            return "قاتل‌ها"
        return None

    def check_win(self, when: str) -> None:
        s = self.s
        want = self.expected_winner()
        got = s.winner
        if want is None and got is None:
            return
        if want and got and got.startswith(want[:3]):
            self.r.ok(f"شرط برد: {want}")
            if want == "شهر" and any(p.role == "جانی سریالی" for p in s.alive_players()):
                self.r.find("متوسط", "قواعد برد", "شهر برد در حالی که جانی سریالی زنده است",
                            "متن نقش: جانی سریالی «در پایان باید تنها بازمانده باشد». وقتی قاتل‌ها تمام "
                            "می‌شوند ولی جانی هنوز می‌کشد، بازی «برد شهر» اعلام می‌شود و تهدید باقی "
                            "مانده نادیده گرفته می‌شود.", key="sk-alive-city-win")
            return
        self.r.find("بالا", "قواعد برد", "برنده‌ی اعلام‌شده با شرط برد نمی‌خواند",
                    f"{when}: انتظار {want} — ربات {got} (فاز {s.phase.value})",
                    key=f"win:{want}:{got}")

    def check_end(self, text: str) -> None:
        s = self.s
        for p in s.players.values():
            if p.name not in text or p.role not in text:
                self.r.find("متوسط", "پایان", "افشای پایانی همه‌ی نقش‌ها را نشان نمی‌دهد", p.name)
                break
        else:
            self.r.ok("افشای نقش‌ها در پایان")
        # برد/باخت XP: برنده ۱۲۰ پایه می‌گیرد، بازنده ۴۰
        for p in s.players.values():
            won = self._won(p)
            if won and p.xp < 120:
                self.r.find("بالا", "امتیاز", f"«{p.role}» برنده شد ولی امتیاز باخت گرفت",
                            f"برنده: {s.winner}؛ {p.name} ({p.role}) فقط {p.xp} XP گرفت. "
                            "_payout و db.record_results برد را با "
                            "winner.startswith(align[:3]) می‌سنجند؛ «جانی سریالی» با «خنث» شروع نمی‌شود.",
                            key=f"xp-win:{p.role}")

    def _won(self, p) -> bool:
        w = self.s.winner or ""
        if w.startswith("سپر"):
            return p.role == "سپر بلا"
        if w.startswith("جانی"):
            return p.role == "جانی سریالی"
        if w.startswith("شهر"):
            return p.align is Align.CITY
        if w.startswith("قاتل"):
            return p.align is Align.KILLER
        return False
