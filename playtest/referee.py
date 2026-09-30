"""داور مستقل: پیش از هر سحر پیش‌بینی می‌کند، بعد با نتیجه‌ی ربات مقایسه می‌کند.

قواعد از روی متنِ نقش‌ها و مستندات نوشته شده‌اند، نه با صدا زدن موتور؛
داور فقط وضعیت را می‌خواند (نمای خدا)، هیچ‌وقت چیزی را عوض نمی‌کند.
"""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional, Set

from karagah.config import MAX_DAYS
from karagah.models import Align, Custody, Phase
from karagah.roles import ROLES, SURVIVORS, composition

VISIT_FREE = ("investigate", "expose", "watch")   # «از دور نگاه کردن» ملاقات نیست


class Referee:
    def __init__(self, game, agents, report):
        self.g, self.agents, self.r = game, {a.uid: a for a in agents}, report
        self.poison_due: Dict[int, int] = {}      # هدف → شبِ مرگ
        self.frame_until: Dict[int, int] = {}
        self.temp_nights: Dict[int, int] = {}     # زندانی موقت → شب‌های گذرانده
        self.track_custody = True
        self.track_intents = True                 # شلوغ‌کار دکمه‌ی اکشن را خارج از night_turn هم می‌زند
        self.watching = False                 # شلوغ‌کار شب‌ها را از مسیرِ دیگری هم می‌گذراند؛ خودش می‌شمارد
        self.intents: Dict[int, tuple] = {}       # uid → (ability, target) امشب
        self.before: Dict[int, tuple] = {}
        self.night_day = 0
        self.suspect_at_night: Optional[int] = None
        self.mode = ""                            # «دکمه در گروه» / «تایمر» / «پیوی»
        self.poisoner: Dict[int, int] = {}        # هدفِ سم → سم‌ساز (از دکمه‌هایی که زده شد)
        from karagah import engine as _engine
        _engine.NIGHT_OBSERVERS.append(self.on_resolve)
        self.rumors = [0, 0]                      # [شایعه‌ی درست، کل]

    @property
    def s(self):
        return self.g.s

    def name(self, uid) -> str:
        return self.s.players[uid].name

    # ── شروع بازی ──
    def check_start(self) -> None:
        n = len(self.s.players)
        got = Counter(p.role for p in self.s.players.values())
        if got != Counter(composition(n, self.g.scenario)):
            self.r.find("بالا", "نقش‌ها", f"پخش نقش در بازی {n} نفره با سناریو نمی‌خواند",
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
        self.watching = True                      # این شب را Session جلو می‌برد → intentها کامل‌اند
        from karagah.bot import GAMES
        cur = GAMES.get(self.g.s.chat_id, self.g)  # بعد از ری‌استارت، شبِ نیمه‌کاره اکشن‌های قبلی را دارد
        self.intents = {a: (ab, t) for ab, pairs in cur._committed_actions().items()
                        for a, t in pairs.items()}
        self.night_day = self.s.day
        self.suspect_at_night = self.s.suspect_uid
        self.before = {u: (p.alive, p.custody, p.custody_nights, p.in_game, p.cleared)
                       for u, p in self.s.players.items()}

    def intent(self, uid: int, ability: str, target: int) -> None:
        self.intents[uid] = (ability, target)

    def on_resolve(self, game, acts) -> None:
        """موتور درست پیش از حلِ شب صدا می‌زند (هر که شب را بسته باشد: دکمه، تایمر، آخرین تصمیم)."""
        if game.s.chat_id != self.g.s.chat_id:
            return
        if not self.watching and self.track_custody:
            # شبی که Session جلو نبرد (مثلاً شبِ بی‌کار که همان لحظه حل شد) هم یک شبِ بازداشت است
            for u, p in game.s.players.items():
                if p.custody is Custody.TEMP_JAIL and p.alive:
                    self.temp_nights[u] = self.temp_nights.get(u, 0) + 1
        if self.watching and self.track_intents:
            self.watching = False
            self.pre_dawn(acts)

    def pre_dawn(self, acts=None) -> None:
        """درست پیش از «پایان شب»: آنچه agentها زدند = آنچه موتور ثبت کرده؟"""
        acts = self.g._committed_actions() if acts is None else acts
        committed = {actor: (ab, t) for ab, pairs in acts.items()
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
        for who, t in acts.get("poison", {}).items():
            self.poison_due.setdefault(t, day + 2)
            self.poisoner.setdefault(t, who)
        for t in acts.get("frame", {}).values():
            self.frame_until[t] = day + 1
        alive_before = {u for u, b in self.before.items() if b[0] and b[3]}
        free_before = {u for u in alive_before if self.before[u][1] is Custody.FREE}

        # قاعده: بازداشتی (بازجویی یا حبس موقت) از حمله‌ی مستقیم در امان است
        attacked: List[int] = []
        for t in acts.get("kill", {}).values():
            if t not in protected and t not in attacked and t in free_before:
                attacked.append(t)
        if storm:
            attacked = []
        for t, due in list(self.poison_due.items()):
            if due > day:
                continue
            del self.poison_due[t]
            if t in protected:
                self.r.ok("سم: نجات پزشک در شبِ سررسید")
            elif t in alive_before and t not in attacked:
                attacked.append(t)
        expect = self._chain(attacked, alive_before)
        # حبس موقتِ دو‌شبه همین سحر ابد می‌شود؛ شکارچیِ حبس‌ابدی شلیک آخرش را دارد
        for u, b in self.before.items():
            if b[0] and b[3] and b[1] is Custody.TEMP_JAIL and not b[4] and u not in expect \
                    and b[2] + 1 >= self.g.temp_jail_nights:
                hunter = s.players[u]
                if hunter.role == "شکارچی" and hunter.hunter_target in alive_before:
                    expect += [x for x in self._chain([hunter.hunter_target], alive_before)
                               if x not in expect]

        died = {u for u in alive_before if not s.players[u].alive}
        if died == set(expect):
            if s.fate_pair and set(s.fate_pair) <= died:
                self.r.ok("زوج سرنوشت: مرگ همراه")
            if any(s.players[u].role == "شکارچی" and s.players[u].hunter_target in died for u in died):
                self.r.ok("شکارچی: شلیک آخر هنگام مرگ")
            if day == 1 and s.phase is Phase.END and not (s.winner or "").startswith("قاتل"):
                self.r.ok("سحر اول: پایانِ مشروع (مثلاً قاتل و جانی همدیگر را کشتند)")
            elif day == 1 and s.phase is Phase.END:
                self.r.find("متوسط", "تعادل", "بازی در همان سحرِ اول تمام شد — بدون هیچ روز و رایی",
                            f"{len(s.players)} نفره: {len(died)} نفر در شب اول مردند "
                            f"({'، '.join(self.name(u) for u in died)}) و قاتل‌ها به برابری رسیدند. "
                            "در ترکیب ۱۰ نفره دو قاتلِ مستقل (قاتل + جانی سریالی) + زوج سرنوشت + شلیک شکارچی "
                            "می‌توانند ۴ نفر را در یک شب ببرند؛ ۳ قاتل در برابر ۷ نفر فقط ۴ مرگ تا برابری فاصله دارند.", key="first-dawn-end")
        if died != set(expect) and self.track_intents:   # شلوغ‌کار اکشن‌ها را بیرون از intentها هم می‌زند
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
        if "⚰️ کشته‌شده" in announced and "frame" in acts:
            if "اثر انگشت روی صحنه" in announced:
                self.r.ok("همدست: ردِ پاپوش در پیام صبح")
            else:
                self.r.find("متوسط", "توانایی‌ها", "ردِ پاپوشِ همدست در پیام صبح نیامد",
                            f"شب {day}", key="frame-trace")
        # بازداشت
        for u, b in self.before.items():
            p = s.players[u]
            if b[1] is Custody.TEMP_JAIL and b[3] and self.track_custody:
                self.temp_nights[u] = self.temp_nights.get(u, 0) + 1
                want = Custody.LIFE_JAIL if self.temp_nights[u] >= self.g.temp_jail_nights else Custody.TEMP_JAIL
                if p.custody is not want and p.alive:
                    self.r.find("بالا", "بازداشت", "زمان‌بندی حبس موقت → حبس ابد اشتباه است",
                                f"{p.name}: {self.temp_nights[u]} شب — انتظار {want.value}، ربات {p.custody.value}")
                elif want is Custody.LIFE_JAIL:
                    self.r.ok("حبس موقت → حبس ابد بعد از ۲ شب")
                    self._hunter_on_life_jail(u)
        self.check_clues(acts, died, day)
        self.check_invariants("سحر")
        self.check_win("سحر")

    # ── صحنه‌ها (نسخه ۶): مکان‌های سناریو، جزئیاتِ هر روز تازه، متن و مشخصه‌ی ویژه‌ی سناریو ──
    def check_scenes(self, day) -> None:
        from karagah import scenes as SC
        from karagah.clues import keys_for
        s = self.s
        scen = SC.pack(s.scenario)
        allowed = set(SC.LOCATIONS[scen]) | {f"🕯️ {s.case.place}"}
        for c in s.clues:
            if c.get("place") not in allowed:
                self.r.find("بالا", "صحنه", "سرنخ در مکانی بیرون از سناریو پیدا شد",
                            f"{c['code']}: {c.get('place')} ({scen})", key="scene-foreign")
                break
            if SC.trait_text(scen, c["trait"], c["value"]) not in c["text"]:
                self.r.find("متوسط", "صحنه", "متنِ سرنخ با فضای سناریو نمی‌خواند", c["text"][:80],
                            key="scene-text")
                break
        else:
            if s.clues:
                self.r.ok(f"صحنه: سرنخ‌ها در مکان‌ها و با متنِ سناریوی {scen}")
        hist = SC.history(s)
        for loc, rows in hist.items():
            details = [d for _, d in rows]
            days = [d for d, _ in rows]
            if len(set(details)) != len(details):
                self.r.find("بالا", "صحنه", "یک مکان جزئیاتِ تکراری نشان داد", loc, key="scene-repeat")
            if len(set(days)) != len(days):
                self.r.find("متوسط", "صحنه", "یک مکان در یک روز دو جزئیات گرفت", loc, key="scene-twice")
        if hist and day >= 1 and not s.night_event.startswith("قطعی برق"):
            stale = [loc for loc, rows in hist.items() if rows and rows[-1][0] < day]
            if stale:
                self.r.find("متوسط", "صحنه", "مکانِ سرنخ‌داری امروز چیزِ تازه‌ای نشان نداد",
                            "، ".join(stale[:3]), key="scene-stale")
            else:
                self.r.ok("صحنه: هر مکانِ سرنخ‌دار امروز جزئیاتی تازه نشان داد")
        want = set(keys_for(scen))
        if any(set(p.traits) != want for p in s.players.values()):
            self.r.find("بالا", "صحنه", "مشخصه‌های بازیکن با سناریو نمی‌خواند", key="scene-traits")

    # ── سرنخ‌ها: راست‌ها به مجرمِ واقعی وصل‌اند، دروغ‌ها هرگز مجرمِ آن شب را نشان نمی‌دهند ──
    def check_clues(self, acts, died, day) -> None:
        s = self.s
        new = [c for c in s.clues if c["day"] == day and c["source"] != "case"]
        self.check_scenes(day)
        if s.night_event.startswith("قطعی برق"):
            if new:
                self.r.find("بالا", "سرنخ", "در قطعی برق سرنخ جمع شد", str([c["code"] for c in new]))
            else:
                self.r.ok("سرنخ: قطعی برق → هیچ سرنخی")
            return
        hidden = set(acts.get("hide", {}).values())
        killers = acts.get("kill", {})
        # نسخه ۹: هر سرنخ یک رویدادِ واقعیِ همین شب پشتش است؛ شبِ بی‌جنایت سرنخی ندارد
        crime = [c for c in new if c["source"] in ("kill", "sk", "poison")]
        attacked_tonight = bool(killers) or bool(acts.get("poison")) or any(
            u in self.poisoner for u in died)
        for c in new:
            src = c["source"]
            orphan = (src in ("herring", "witness") and not crime) or \
                     (src == "frame" and not acts.get("frame")) or \
                     (src == "reporter" and not acts.get("reveal")) or \
                     (src in ("kill", "sk") and not killers)
            if orphan:
                self.r.find("بحرانی", "سرنخ", "سرنخ بدون رویدادِ واقعی", f"شب {day} · {c['code']} ({src})",
                            key=f"clue-orphan:{src}")
            else:
                self.r.ok(f"سرنخ ({src}) ← رویدادِ واقعیِ همین شب")
        if not attacked_tonight and not acts.get("frame") and not acts.get("reveal"):
            if new:
                self.r.find("بحرانی", "سرنخ", "شبی که کسی حمله/پاپوش نکرد سرنخ ساخت",
                            f"شب {day}: {[c['code'] for c in new]}", key="clue-without-crime")
            else:
                self.r.ok("سرنخ: شبِ بی‌جنایت → بی‌سرنخ")

        def bad(title, c, why):
            self.r.find("بحرانی", "سرنخ", title, f"شب {day} · {c['code']} ({c['source']}): {c['text']} — {why}",
                        key=f"clue:{title}")

        for c in new:
            about = s.players.get(c["about"]) if c["about"] is not None else None
            src = c["source"]
            if src in ("kill", "sk", "poison", "witness", "reporter"):
                if not c["genuine"] or about is None or about.traits[c["trait"]] != c["value"]:
                    bad("سرنخِ «راست» با مشخصاتِ مجرم نمی‌خواند", c, "genuine/about/value")
                    continue
                if c["about"] in hidden:
                    bad("ضاربِ پنهان‌شده رد گذاشت", c, "قاچاقچی او را پنهان کرده بود")
                    continue
                if src in ("kill", "sk") and c["about"] not in killers:
                    bad("سرنخ به کسی وصل است که امشب حمله نکرد", c, "")
                    continue
                if src == "poison" and c["about"] not in self.poisoner.values():
                    bad("سرنخِ سم به کسی غیر از سم‌ساز وصل است", c, "")
                    continue
                self.r.ok(f"سرنخ راست ({src}) → مشخصه‌ی واقعیِ مجرم")
            elif src in ("frame", "herring"):
                if c["genuine"]:
                    bad("سرنخِ کاشته «راست» علامت خورده", c, "")
                    continue
                evil = [p for p in s.players.values() if p.in_game and p.align is Align.KILLER] + \
                    [s.players[u] for u in killers]
                hit = next((p for p in evil if p.traits[c["trait"]] == c["value"]), None)
                if hit is not None:
                    bad("سرنخِ دروغ به مجرمِ واقعی اشاره می‌کند", c, hit.name)
                    continue
                if src == "frame" and (about is None or c["about"] not in acts.get("frame", {}).values()
                                       or about.traits[c["trait"]] != c["value"]):
                    bad("پاپوش به کسی جز پاپوش‌خورده اشاره می‌کند", c, "")
                    continue
                self.r.ok(f"سرنخ دروغ ({src}) → مجرم را نشان نمی‌دهد")
        # هر قتلِ موفقِ ضاربِ پنهان‌نشده دقیقاً یک سرنخِ راست درباره‌ی همان ضارب
        for actor, tgt in killers.items():
            if tgt in died and actor not in hidden:
                n = sum(1 for c in new if c["source"] in ("kill", "sk") and c["about"] == actor)
                if n == 1:
                    self.r.ok("سرنخ: هر قتل یک رد")
                else:
                    self.r.find("بالا", "سرنخ", "قتل بدون سرنخ (یا با چند سرنخ)", f"شب {day}: {n}",
                                key="kill-clue-count")
        # پزشک قانونی راست/دروغِ همه‌ی سرنخ‌های امشب را درست می‌گوید
        for actor in acts.get("autopsy", {}):
            notes = "\n".join(s.players[actor].notes)
            wrong = [c["code"] for c in new
                     if f"{c['code']} {'✅ راست' if c['genuine'] else '❌ دروغ'}" not in notes]
            if wrong:
                self.r.find("بالا", "توانایی‌ها", "پزشک قانونی راست/دروغِ سرنخ‌ها را اشتباه گفت", str(wrong))
            elif new:
                self.r.ok("پزشک قانونی: راست/دروغِ سرنخ‌های امشب")
        # نتیجه‌ی آزمایشگاه همیشه با حقیقت می‌خواند
        for c in s.clues:
            if c["verified"] is not None and c["verified"] != c["genuine"]:
                self.r.find("بحرانی", "سرنخ", "تاییدِ سرنخ با حقیقت نمی‌خواند", c["code"], key="verify-wrong")
        # کالبدشکاف: روش و مشخصه‌ی راستِ ضارب
        for p in s.players.values():
            if p.role != "کالبدشکاف":
                continue
            for n in [x for x in p.notes if x.startswith(f"🔬 شب {day}:")]:
                if "ضارب:" in n:
                    tr, val = n.split("ضارب:")[1].strip().split(" = ")
                    culprits = list(killers) + list(self.poisoner.values())
                    if any(s.players[u].traits.get(k) == val for u in culprits
                           for k in s.players[u].traits if __import__("karagah.clues").clues.TRAITS[k][1] == tr):
                        self.r.ok("کالبدشکاف: مشخصه‌ی راستِ ضارب")
                    else:
                        self.r.find("بالا", "توانایی‌ها", "کالبدشکاف مشخصه‌ی غلط گفت", n)
        # بقال: شایعه ۷۰٪ درست (آمار در پایان)
        for p in s.players.values():
            if p.role == "بقال محله" and p.alive:
                for n in [x for x in p.notes if x.startswith(f"🏪 شایعه‌ی روز {day}")]:
                    knife = next((u for u, q in s.players.items() if q.in_game and q.align is Align.KILLER
                                  and self.g.ability_of(q) == "kill"), None)
                    if knife is None:
                        continue
                    import karagah.clues as CL
                    for k, tdef in CL.TRAITS.items():
                        nm = tdef[1]
                        if f"{nm}ِ قاتل «" in n:
                            val = n.split("«")[1].split("»")[0]
                            self.rumors[1] += 1
                            self.rumors[0] += int(s.players[knife].traits[k] == val)

    def _chain(self, start: List[int], alive_before) -> List[int]:
        """مرگ + زنجیره: زوج سرنوشت و شلیک آخر شکارچی (از متن نقش‌ها)."""
        out: List[int] = []
        queue = list(start)
        pair = self.s.fate_pair
        while queue:
            u = queue.pop(0)
            if u in out or u not in alive_before:
                continue
            out.append(u)
            if pair and u in pair:
                queue.append(pair[1] if u == pair[0] else pair[0])
            p = self.s.players[u]
            if p.role == "شکارچی" and p.hunter_target:
                queue.append(p.hunter_target)
        return out

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
        from karagah.l10n import fa_digits
        if line in text or fa_digits(line) in text:          # بازیکن رقمِ فارسی می‌بیند (نسخه ۸)
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
        """شرط برد از روی متن نقش‌ها و RULES.md (بخش «برد»)."""
        s = self.s
        alive = s.alive_players()
        if any(p.role == "سپر بلا" and p.custody is Custody.LIFE_JAIL and p.alive
               for p in s.players.values()):
            return "سپر بلا"
        if not alive:
            return "بدون برنده"
        k = [p for p in alive if p.align is Align.KILLER]
        sk = [p for p in alive if p.role == "جانی سریالی"]
        if not k and not sk:
            return "شهر"
        if sk and len(alive) <= 2 and (not k or len(alive) == 2):
            return "جانی سریالی"
        if k and not sk and len(k) >= len(alive) - len(k):
            return "قاتل‌ها"
        if s.day > MAX_DAYS:
            return "بدون برنده"
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
                            "متن نقش: جانی سریالی «در پایان باید تنها بازمانده باشد».", key="sk-alive-city-win")
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
        if p.role in SURVIVORS and p.in_game and w:
            return True                         # بقال/قاچاقچی: زنده ماندن تا پایان
        if w.startswith("سپر"):
            return p.role == "سپر بلا"
        if w.startswith("جانی"):
            return p.role == "جانی سریالی"
        if w.startswith("شهر"):
            return p.align is Align.CITY
        if w.startswith("قاتل"):
            return p.align is Align.KILLER
        return False
