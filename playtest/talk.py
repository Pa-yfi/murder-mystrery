"""گفتگوی شبیه‌سازی‌شده سر میز: ادعا، بلوف، پاپوش و رای بر پایه‌ی باور.

هر agent فقط چیزهایی را می‌داند که یک آدمِ واقعی سر میز می‌داند:
  • اطلاعات عمومی: پرونده‌ی ظاهریِ همه، سرنخ‌های روی «🗂️ پرونده» و وضعیتِ تاییدشان، اعلام‌های گروه
  • اطلاعات خصوصیِ خودش: خط‌های دفترچه که ربات به پیوی‌اش فرستاده (agent.notes_seen) و هم‌تیمی‌هایش
  • پیام‌های چتِ گروه که بقیه نوشته‌اند (ادعاها و بلوف‌ها)

شهر: از سرنخ‌ها و ادعاها باور می‌سازد، دروغ‌گوی لو رفته را علامت می‌زند و به مظنون‌ترین نفر رای می‌دهد.
قاتل‌ها: ادعای دروغِ کارآگاه/پزشک قانونی می‌کنند، هم‌تیمی را «پاک» جا می‌زنند، سرنخِ کاشته را
«راست» و سرنخِ راست را «کاشته» می‌خوانند و همدست روی پاپوش‌خورده فشار می‌آورد.

حقیقت (نقش‌ها، راست/دروغ بودنِ سرنخ) فقط برای «آمار» خوانده می‌شود، نه برای تصمیمِ agentها.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from karagah.clues import TRAITS, matches
from karagah.models import Align, Custody
from karagah.roles import ROLES

TRAIT_BY_NAME = {v[1]: k for k, v in TRAITS.items()}
DET = "کارآگاه"
FOR = "پزشک قانونی"


@dataclass
class Claim:
    day: int
    speaker: int
    kind: str                      # det / clue / trait / accuse / vouch / reason / counter / chatter
    target: Optional[int] = None   # بازیکنِ موردِ ادعا
    code: str = ""                 # سرنخِ موردِ ادعا
    verdict: Optional[bool] = None  # مشکوک/راست = True
    trait: str = ""
    value: str = ""
    honest: bool = True            # فقط برای آمار
    caught: bool = False


@dataclass
class Mind:
    susp: Dict[int, float] = field(default_factory=dict)
    trust: Dict[int, float] = field(default_factory=dict)
    clue_p: Dict[str, float] = field(default_factory=dict)
    facts: List[tuple] = field(default_factory=list)     # (trait, value, weight) درباره‌ی قاتل
    liars: set = field(default_factory=set)
    dirty: set = field(default_factory=set)
    clean: set = field(default_factory=set)
    true_codes: set = field(default_factory=set)         # چیزی که خودش مطمئن است (پزشک قانونی/کارآگاه)
    false_codes: set = field(default_factory=set)
    parsed: int = 0


class TableTalk:
    def __init__(self, session):
        self.s = session
        self.rng = session.rng
        self.minds: Dict[int, Mind] = {a.uid: Mind() for a in session.agents}
        self.claims: List[Claim] = []
        self.det_claimers: Dict[int, int] = {}          # uid → روزِ اولین ادعای کارآگاهی
        self.for_claimers: set = set()
        self.bluffed: set = set()
        self.stats = {"messages": 0, "lies": 0, "lies_caught": 0, "honest_claims": 0,
                      "fake_detective": 0, "fake_forensic": 0, "frame_push": 0, "vouch": 0,
                      "counter_claims": 0, "lies_countered": 0, "city_votes": 0, "city_votes_on_killer": 0,
                      "bot_replied_to_chat": 0, "chat_swallowed": 0}

    # ─────────────────────────── کمکی‌ها ───────────────────────────
    @property
    def g(self):
        return self.s.g

    def name(self, uid: int) -> str:
        return self.g.s.players[uid].name

    def uid(self, name: str) -> Optional[int]:
        return next((p.uid for p in self.g.s.players.values() if p.name == name), None)

    def public_clues(self) -> List[dict]:
        """همان چیزی که «🗂️ پرونده» نشان می‌دهد: کد، مشخصه، مقدار، وضعیتِ تایید."""
        return [{k: c[k] for k in ("code", "day", "trait", "value", "verified")} for c in self.g.s.clues]

    def evil(self, uid: int) -> bool:                   # فقط برای آمار
        p = self.g.s.players[uid]
        return p.align is Align.KILLER or p.role == "جانی سریالی"

    def is_killer_agent(self, a) -> bool:
        return ROLES[a.role].align is Align.KILLER

    # ─────────────────────────── خواندنِ دفترچه ───────────────────────────
    def absorb_notes(self, a) -> None:
        m = self.minds[a.uid]
        for line in a.notes_seen[m.parsed:]:
            if x := re.match(r"شب \d+: (.+?) → (پاک|مشکوک)", line):
                u = self.uid(x.group(1))
                if u:
                    (m.clean if x.group(2) == "پاک" else m.dirty).add(u)
            if x := re.match(r"شب \d+: سرنخ (C\d+) → (راست|دروغ)", line):
                (m.true_codes if x.group(2) == "راست" else m.false_codes).add(x.group(1))
            if line.startswith("🧪 شب"):
                for code, v in re.findall(r"(C\d+) (✅|❌)", line):
                    (m.true_codes if v == "✅" else m.false_codes).add(code)
            if x := re.search(r"می‌گویند (.+?)ِ قاتل «(.+?)»", line):
                k = TRAIT_BY_NAME.get(x.group(1))
                if k:
                    m.facts.append((k, x.group(2), 0.7))
            if x := re.search(r"ضارب: (.+?) = (\S+)", line):
                k = TRAIT_BY_NAME.get(x.group(1))
                if k:
                    m.facts.append((k, x.group(2), 1.5))
            if x := re.search(r"ملاقات‌کننده‌های .+?: (.+?) = (\S+)", line):
                k = TRAIT_BY_NAME.get(x.group(1))
                if k:
                    m.facts.append((k, x.group(2), 0.5))
        m.parsed = len(a.notes_seen)

    # ─────────────────────────── باور ───────────────────────────
    def clue_belief(self, m: Mind, c: dict) -> float:
        if c["verified"] is not None:
            return 1.0 if c["verified"] else 0.0
        if c["code"] in m.true_codes:
            return 1.0
        if c["code"] in m.false_codes:
            return 0.0
        return m.clue_p.get(c["code"], 0.55)

    def score(self, a, uid: int) -> float:
        """مظنون بودنِ uid از نگاهِ a (فقط اطلاعات عمومی + دفترچه‌ی خودش + چت)."""
        m = self.minds[a.uid]
        p = self.g.s.players[uid]
        sc = 0.0
        for c in self.public_clues():
            if matches(p, c):
                b = self.clue_belief(m, c)
                sc += 2.0 * b if c["verified"] is not None or b in (0.0, 1.0) else b
                if b == 0.0:
                    sc -= 0.6                         # پاپوشِ لورفته: احتمالاً بی‌گناه است
        for k, v, w in m.facts:
            if p.traits.get(k) == v:
                sc += w
        sc += m.susp.get(uid, 0.0)
        if uid in m.dirty:
            sc += 8
        if uid in m.clean:
            sc -= 6
        if uid in m.liars:
            sc += 6
        return sc

    def ranking(self, a, pool: List[int]) -> List[int]:
        return sorted(pool, key=lambda u: (-self.score(a, u), self.rng.random()))

    # ─────────────────────────── گفتگو ───────────────────────────
    def post(self, a, text: str, claim: Optional[Claim]) -> None:
        """پیام واقعاً در گروه نوشته می‌شود؛ ربات نباید جواب بدهد (مگر منتظرِ متن باشد)."""
        tg = self.s.tg
        before = len(tg.inbox(self.s.group))
        from karagah import bot
        if bot._PENDING.get(a.uid):
            self.stats["chat_swallowed"] += 1       # مثل on_text: متن گروه جوابِ پرسشِ باز می‌شود
            return
        tg.chat(a.uid, f"{a.name}: {text}")
        after = tg.inbox(self.s.group)[before + 1:]
        if after:
            self.stats["bot_replied_to_chat"] += 1
            self.s.r.find("متوسط", "رابط", "ربات به گفتگوی عادیِ گروه جواب داد",
                          after[0].text[:120], key="bot-chat-reply")
        self.stats["messages"] += 1
        if claim:
            self.claims.append(claim)
            if claim.kind != "chatter":
                self.stats["lies" if not claim.honest else "honest_claims"] += 1
            self.hear(claim)

    def speakers(self):
        g = self.g
        return [a for a in self.s.agents if g.s.players[a.uid].can_speak]

    def day(self) -> None:
        """یک دور گفتگوی روز: اول نقش‌های اطلاعاتی، بعد بلوف‌ها، بعد استدلالِ شهروندها."""
        for a in self.s.agents:
            a.read_dm()
            self.absorb_notes(a)
        self.catch_liars()
        talkers = self.speakers()
        self.rng.shuffle(talkers)
        for a in talkers:
            if self.is_killer_agent(a):
                self.trick(a)
            else:
                self.honest(a)
        for a in talkers:
            if self.rng.random() < 0.5:
                self.reason(a)

    def honest(self, a) -> None:
        g, m, d = self.g, self.minds[a.uid], self.g.s.day
        alive = {p.uid for p in g.s.alive_players()}
        if a.role == DET:
            fresh = [u for u in m.dirty if u in alive]
            fakes = [u for u in self.det_claimers if u != a.uid and u in alive]
            if fakes:                                   # کارآگاهِ واقعی ادعای دروغ را می‌شکند
                f = fakes[0]
                if any(x.kind == "counter" and x.speaker == a.uid and x.target == f for x in self.claims):
                    fakes = []
            if fakes:
                self.stats["counter_claims"] += 1
                self.stats["lies_countered"] += 1
                self.post(a, f"🕵️ کارآگاه منم! {self.name(f)} دروغ می‌گوید.",
                          Claim(d, a.uid, "counter", f, verdict=True, honest=True))
                self.det_claimers.setdefault(a.uid, d)
            if fresh or (m.clean and self.rng.random() < 0.3):
                self.det_claimers.setdefault(a.uid, d)
                for u in fresh:
                    self.post(a, f"🕵️ کارآگاهم؛ {self.name(u)} مشکوک درآمد.",
                              Claim(d, a.uid, "det", u, verdict=True, honest=True))
                for u in list(m.clean)[:1]:
                    if u in alive:
                        self.post(a, f"🕵️ {self.name(u)} را استعلام کردم؛ پاک است.",
                                  Claim(d, a.uid, "det", u, verdict=False, honest=True))
            for code in m.true_codes | m.false_codes:
                self.clue_claim(a, code, code in m.true_codes, honest=True)
        elif a.role == FOR:
            if m.true_codes or m.false_codes:
                self.for_claimers.add(a.uid)
            known = m.true_codes | m.false_codes
            for c in [c for c in self.claims if c.kind == "clue" and c.speaker != a.uid and c.code in known
                      and (c.code in m.true_codes) != c.verdict and not c.caught]:
                if c.speaker in alive and not any(x.kind == "counter" and x.speaker == a.uid
                                                  and x.target == c.speaker for x in self.claims):
                    self.stats["counter_claims"] += 1
                    self.stats["lies_countered"] += int(not c.honest)
                    self.post(a, f"🧪 پزشک قانونی منم! {self.name(c.speaker)} درباره‌ی {c.code} دروغ می‌گوید.",
                              Claim(d, a.uid, "counter", c.speaker, code=c.code, verdict=True, honest=True))
            for code in m.true_codes | m.false_codes:
                self.clue_claim(a, code, code in m.true_codes, honest=True)
        elif m.facts and a.role in ("کالبدشکاف", "بقال محله", "نگهبان"):
            k, v, _ = m.facts[-1]
            if not any(c.speaker == a.uid and c.trait == k and c.value == v for c in self.claims):
                self.post(a, f"{ROLES[a.role].emoji} شنیده‌ام {TRAITS[k][1]}ِ قاتل «{v}» است.",
                          Claim(d, a.uid, "trait", trait=k, value=v, honest=True))

    def clue_claim(self, a, code: str, genuine: bool, honest: bool) -> None:
        if any(c.speaker == a.uid and c.code == code for c in self.claims):
            return
        who = "کارآگاه" if a.uid in self.det_claimers else "پزشک قانونی"
        self.post(a, f"🧪 ({who}) سرنخ {code} {'راست' if genuine else 'کاشته'} است.",
                  Claim(self.g.s.day, a.uid, "clue", code=code, verdict=genuine, honest=honest))

    def trick(self, a) -> None:
        """ترفندهای تیم قاتل — همه دروغ، همه قابلِ لو رفتن."""
        g, d = self.g, self.g.s.day
        team = {self.uid(n) for n in a.team} | {a.uid}
        alive = [p.uid for p in g.s.alive_players()]
        innocents = [u for u in alive if u not in team]
        if not innocents:
            return
        # ۱) سرنخِ راستی که به تیم می‌خورد → «کاشته است» (ادعای دروغِ پزشک قانونی)
        danger = [c for c in g.s.clues if c["verified"] is None
                  and any(matches(g.s.players[u], c) for u in team if u in g.s.players)]
        roll = self.rng.random()
        if danger and roll < 0.35 and a.uid not in self.bluffed:
            c = self.rng.choice(danger)
            self.bluffed.add(a.uid)
            self.for_claimers.add(a.uid)
            self.stats["fake_forensic"] += 1
            self.post(a, f"🧪 پزشک قانونی‌ام؛ سرنخ {c['code']} کاشته است، گولش را نخورید.",
                      Claim(d, a.uid, "clue", code=c["code"], verdict=False, honest=c["genuine"] is False))
            return
        # ۲) ادعای دروغِ کارآگاهی: یک بی‌گناه «مشکوک»، یک هم‌تیمی «پاک»
        pressured = any(c.kind == "det" and c.verdict and c.target in team and c.speaker not in team
                        for c in self.claims)
        if a.uid not in self.det_claimers and (pressured and roll < 0.7 or roll < 0.18):
            victim = self.ranking(a, innocents)[0]      # کسی که از قبل مشکوک به‌نظر می‌رسد
            self.det_claimers[a.uid] = d
            self.stats["fake_detective"] += 1
            self.post(a, f"🕵️ من کارآگاهم! {self.name(victim)} مشکوک درآمد.",
                      Claim(d, a.uid, "det", victim, verdict=True, honest=False))
            mates = [u for u in team if u != a.uid and u in alive]
            if mates:
                self.stats["vouch"] += 1
                self.post(a, f"🕵️ {self.name(mates[0])} را هم استعلام کردم؛ پاک است.",
                          Claim(d, a.uid, "det", mates[0], verdict=False, honest=False))
            return
        # ۳) همدست پاپوش‌خورده را هل می‌دهد
        framed = [c for c in g.s.clues if c["source"] == "frame" and c["verified"] is None
                  and c["about"] in innocents]
        if a.role == "همدست" and framed and roll < 0.8:
            c = framed[-1]
            self.stats["frame_push"] += 1
            self.post(a, f"👀 سرنخ {c['code']} را ببینید؛ فقط به {self.name(c['about'])} می‌خورد!",
                      Claim(d, a.uid, "accuse", c["about"], code=c["code"], verdict=True, honest=False))
            return
        # ۴) رای‌سازی: هم‌صدا شدن با مظنونِ عمومی
        top = self.ranking(a, innocents)[0]
        self.post(a, f"به نظرم {self.name(top)} مشکوک است.",
                  Claim(d, a.uid, "accuse", top, verdict=True, honest=False))

    def reason(self, a) -> None:
        """استدلالِ عمومی از روی پرونده (شهر) — راست یا غلط، صادقانه است."""
        if self.is_killer_agent(a):
            return
        pool = [p.uid for p in self.g.s.alive_players() if p.uid != a.uid]
        if not pool:
            return
        top = self.ranking(a, pool)[0]
        if self.score(a, top) <= 0:
            self.post(a, "هنوز چیزی دستم نیامده؛ منتظر آزمایشگاه بمانیم.", Claim(self.g.s.day, a.uid, "chatter"))
            return
        codes = [c["code"] for c in self.public_clues() if matches(self.g.s.players[top], c)
                 and self.clue_belief(self.minds[a.uid], c) > 0]
        why = f" ({'، '.join(codes[:3])} به او می‌خورد)" if codes else ""
        lines = [f"🗂️ مظنونِ من {self.name(top)} است{why}.",
                 f"🔎 سرنخ‌ها را کنار هم بگذارید{why}: {self.name(top)}!",
                 f"🤔 {self.name(top)}، دیشب کجا بودی؟{why}"]
        self.post(a, self.rng.choice(lines),
                  Claim(self.g.s.day, a.uid, "reason", top, verdict=True, honest=True))

    # ─────────────────────────── شنیدن ───────────────────────────
    def hear(self, c: Claim) -> None:
        """همه‌ی شنونده‌ها (جز گوینده) باورشان را به‌روز می‌کنند."""
        for a in self.s.agents:
            if a.uid == c.speaker or not self.g.s.players[a.uid].in_game:
                continue
            m = self.minds[a.uid]
            if self.is_killer_agent(a):
                continue                                  # قاتل‌ها حقیقت را می‌دانند
            t = m.trust.get(c.speaker, 1.0)
            if c.speaker in m.liars:
                t = 0.0
            if c.kind == "det":
                rivals = [u for u in self.det_claimers if u != c.speaker]
                if a.role == DET and c.speaker != a.uid:
                    m.liars.add(c.speaker)                # «کارآگاه منم» — دروغ است
                    continue
                if rivals:
                    t *= 0.4                              # دو مدعی: هیچ‌کدام کاملاً باورپذیر نیست
                if c.target is not None:
                    m.susp[c.target] = m.susp.get(c.target, 0) + (3.5 * t if c.verdict else -2.5 * t)
            elif c.kind == "counter":
                m.susp[c.target] = m.susp.get(c.target, 0) + 3 * t
                m.susp[c.speaker] = m.susp.get(c.speaker, 0) + 0.5    # هنوز معلوم نیست کدام راست می‌گوید
            elif c.kind == "clue":
                if a.role == FOR and c.speaker != a.uid and c.code in (m.true_codes | m.false_codes):
                    if (c.code in m.true_codes) != c.verdict:
                        m.liars.add(c.speaker)
                    continue
                old = m.clue_p.get(c.code, 0.55)
                m.clue_p[c.code] = old + (0.35 * t if c.verdict else -0.35 * t)
            elif c.kind == "trait":
                m.facts.append((c.trait, c.value, 0.6 * t))
            elif c.kind in ("accuse", "reason") and c.target is not None:
                m.susp[c.target] = m.susp.get(c.target, 0) + 0.4 * t

    def catch_liars(self) -> None:
        """آزمایشگاه/راستی‌آزمایی تکلیفِ سرنخ را روشن کرد → هر ادعای خلافش علنی لو می‌رود."""
        verified = {c["code"]: c["verified"] for c in self.g.s.clues if c["verified"] is not None}
        for c in self.claims:
            if c.kind != "clue" or c.caught or c.code not in verified:
                continue
            if verified[c.code] != c.verdict:
                c.caught = True
                if not c.honest:
                    self.stats["lies_caught"] += 1
                town = [a for a in self.speakers() if not self.is_killer_agent(a) and a.uid != c.speaker]
                if town and self.g.s.players[c.speaker].in_game:
                    self.post(self.rng.choice(town),
                              f"🚨 آزمایشگاه {c.code} را {'راست' if verified[c.code] else 'کاشته'} اعلام کرد؛ "
                              f"{self.name(c.speaker)} دروغ گفته بود!", None)
                for a in self.s.agents:
                    if not self.is_killer_agent(a):
                        self.minds[a.uid].liars.add(c.speaker)
                        # هر ادعای دیگرِ دروغ‌گو (مثلاً «X پاک است») بی‌اعتبار می‌شود
                        for o in self.claims:
                            if o.speaker == c.speaker and o.kind == "det" and o.target is not None:
                                m = self.minds[a.uid]
                                m.susp[o.target] = m.susp.get(o.target, 0) - (3.5 if o.verdict else -2.5)

    # ─────────────────────────── تصمیم‌ها ───────────────────────────
    def vote_choice(self, a, named: List[tuple]) -> Optional[dict]:
        """named: [(button, name)] — شهر به مظنون‌ترین، قاتل به مظنون‌ترین بی‌گناه (موج‌سواری)."""
        if not named:
            return None
        uids = {n: self.uid(n) for _, n in named}
        if self.is_killer_agent(a):
            pool = [(b, n) for b, n in named if n not in a.team] or named
            return max(pool, key=lambda x: (self.public_heat(uids[x[1]]), a.rng.random()))[0]
        b, n = max(named, key=lambda x: (self.score(a, uids[x[1]]), a.rng.random()))
        if self.score(a, uids[n]) <= 0.3 and a.rng.random() < 0.5:
            return None                                 # چیزی نمی‌داند → رای نمی‌دهد
        self.stats["city_votes"] += 1
        self.stats["city_votes_on_killer"] += int(self.evil(uids[n]))
        return b

    def public_heat(self, uid: int) -> float:
        """میانگینِ ظنِ شهر به uid — قاتل‌ها از چت می‌فهمند باد از کدام طرف می‌وزد."""
        city = [a for a in self.s.agents if not self.is_killer_agent(a)]
        return sum(self.score(a, uid) for a in city) / max(1, len(city))

    def acquit(self, a, sus: int) -> bool:
        if self.is_killer_agent(a):
            return self.name(sus) in a.team or self.public_heat(sus) < 2
        return self.score(a, sus) < 2.5

    def believes(self, a, code: str) -> bool:
        c = next(x for x in self.g.s.clues if x["code"] == code)
        if self.is_killer_agent(a):                     # قاتل وارونه «باور» ثبت می‌کند
            return not c["genuine"]
        return self.clue_belief(self.minds[a.uid], c) >= 0.5

    def kill_priority(self, a, names: List[str]) -> Optional[str]:
        """قاتل اول سراغ کسی می‌رود که علناً کارآگاه/پزشک قانونی بودنش را لو داده (و راست گفته)."""
        loud = [self.name(u) for u in list(self.det_claimers) + list(self.for_claimers)
                if self.g.s.players[u].role in (DET, FOR)]
        hit = [n for n in names if n in loud and n not in a.team]
        return hit[0] if hit else None

    def contested(self) -> set:
        """سرنخ‌های تاییدنشده‌ای که درباره‌شان ادعا شده (به‌خصوص ادعاهای متضاد) — اولویتِ آزمایشگاه."""
        open_ = {c["code"] for c in self.g.s.clues if c["verified"] is None}
        said: Dict[str, set] = {}
        for c in self.claims:
            if c.kind in ("clue", "accuse", "counter") and c.code in open_:
                said.setdefault(c.code, set()).add(c.verdict if c.kind == "clue" else "x")
        both = {k for k, v in said.items() if len(v) > 1}
        return both or set(said)

    def summary(self) -> dict:
        return dict(self.stats)
