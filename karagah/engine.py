"""موتور بازی — حلقه‌ی کامل، بدون LLM. تمام قواعد قطعی و تست‌پذیر."""
from __future__ import annotations
import random
from typing import Dict, List, Optional, Tuple

from .models import Align, Custody, GameState, Phase, Player
from .roles import ROLES, composition, validate_composition
from .cases import CASES
from . import dialogue
import math
import time as _time
from .config import (MIN_PLAYERS, MAX_PLAYERS, INTERROGATION_NIGHTS,
                     TEMP_JAIL_NIGHTS, JURY_ACQUIT_PERCENT, JURY_MIN_REQUESTS,
                     PHASE_SECONDS)

MIN_P, MAX_P = MIN_PLAYERS, MAX_PLAYERS


class RuleError(Exception):
    pass


class Game:
    def __init__(self, chat_id: int, seed: int = 0, owner: int = 0, blitz: bool = False):
        self.s = GameState(chat_id=chat_id)
        self.owner = owner
        self.blitz = blitz                        # ایده ۳: حالت سریع
        d = 2 if blitz else 1
        self.interrogation_nights = max(1, INTERROGATION_NIGHTS // d)
        self.temp_jail_nights = max(1, TEMP_JAIL_NIGHTS // d)
        self.rng = random.Random(seed)

    # ---------------- ایده ۱: تایمر فاز ----------------
    def _arm(self) -> None:
        sec = PHASE_SECONDS.get(self.s.phase.value)
        if self.blitz and sec:
            sec //= 2
        self.s.deadline = (_time.time() + sec) if sec else None

    def remaining(self) -> Optional[int]:
        if self.s.deadline is None:
            return None
        return max(0, int(self.s.deadline - _time.time()))

    def tick(self) -> Optional[str]:
        """اگر مهلت فاز گذشته باشد، خودکار جلو می‌برد. خروجی: توضیح اتفاق."""
        if self.s.deadline is None or _time.time() < self.s.deadline:
            return None
        if self.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
            self.resolve_night()
            return "⏰ شب به پایان رسید."
        if self.s.phase is Phase.DISCUSSION:
            self.open_vote()
            return "⏰ گفتگو تمام شد؛ رای‌گیری آغاز شد."
        if self.s.phase is Phase.VOTE:
            who = self.close_vote()
            return "⏰ رای‌گیری بسته شد." + (f" متهم: {self.s.players[who].name}" if who else "")
        self.s.deadline = None
        return None

    # ---------------- لابی ----------------
    def join(self, uid: int, name: str) -> Player:
        if self.s.phase is not Phase.LOBBY:
            raise RuleError("بازی شروع شده؛ منتظر دور بعدی بمان.")
        if uid in self.s.players:
            raise RuleError("قبلاً عضو شده‌ای.")
        if len(self.s.players) >= MAX_P:
            raise RuleError("ظرفیت لابی پر است (حداکثر ۸ نفر).")
        p = Player(uid=uid, name=name)
        self.s.players[uid] = p
        return p

    def leave(self, uid: int) -> None:
        if self.s.phase is not Phase.LOBBY:
            raise RuleError("در میانه‌ی بازی نمی‌توان خارج شد.")
        self.s.players.pop(uid, None)
        if uid == self.owner and self.s.players:      # مهاجرت میزبانی
            self.owner = next(iter(self.s.players))

    def start(self, case_id: Optional[int] = None) -> None:
        n = len(self.s.players)
        if not (MIN_P <= n <= MAX_P):
            raise RuleError("تعداد بازیکن باید بین ۴ تا ۸ باشد.")
        if not validate_composition(n):
            raise RuleError("ترکیب نقش نامعتبر است.")
        self.s.case = CASES[(case_id - 1) if case_id else self.rng.randrange(len(CASES))]
        from .roles import assign_with_cooldown
        uids = list(self.s.players)
        mapping = assign_with_cooldown(uids, n, self.rng, getattr(self, "last_roles", {}))
        for p in self.s.players.values():
            p.role_assigned = mapping[p.uid]
        for p, rname in ((self.s.players[u], mapping[u]) for u in uids):
            rd = ROLES[rname]
            p.role, p.align = rname, rd.align
            p.secrets = [f"راز: {self.s.case.twist}"]
        # اطلاعات اختصاصی هر نقش
        killers = [p.uid for p in self.s.players.values() if p.align is Align.KILLER]
        for p in self.s.players.values():
            info = ROLES[p.role].info
            if info == "team_ids":
                p.knows = [f"هم‌تیمی: {self.s.players[u].name}" for u in killers if u != p.uid] or ["تنها هستی."]
            elif info == "forensic":
                p.knows = [f"آزمایشگاه: {self.s.case.evidence[0]['title']}"]
            elif info == "interrogation_hints":
                p.knows = ["تو بازجویی؛ حکم حبس موقت با توست."]
            elif info == "rumor":
                p.knows = [f"شایعه: سلاح احتمالاً «{self.s.case.weapon}» بوده."]
            else:
                p.knows = []
        self.s.officer_uid = next(p.uid for p in self.s.players.values() if p.role == "بازجو")
        city = [p.uid for p in self.s.players.values() if p.align is Align.CITY]
        if len(city) >= 4 and len(self.s.players) >= 7:   # ایده ۸: زوج سرنوشت (فقط بازی بزرگ)
            pair = tuple(self.rng.sample(city, 2))
            self.s.fate_pair = pair
            for u in pair:
                other = pair[1] if u == pair[0] else pair[0]
                self.s.players[u].knows.append(
                    f"🔗 سرنوشتت به {self.s.players[other].name} گره خورده؛ مرگ او مرگ توست.")
        self.s.phase = Phase.NIGHT
        self.s.day = 1
        self._arm()
        self.s.log.append(f"پرونده #{self.s.case.cid}: {self.s.case.title}")

    # ---------------- شب ----------------
    def night_action(self, uid: int, target: int) -> str:
        if self.s.phase not in (Phase.NIGHT, Phase.INTERROGATION):
            raise RuleError("الان شب نیست.")
        p = self.s.players[uid]
        if not p.in_game:
            raise RuleError("تو از بازی خارج شده‌ای.")
        if p.custody in (Custody.INTERROGATION, Custody.TEMP_JAIL):
            raise RuleError("در بازداشتی؛ اکشن شبانه نداری.")
        ab = ROLES[p.role].ability
        if not ab or ab == "hunter":
            raise RuleError("نقش تو اکشن شبانه‌ی معمول ندارد.")
        if target not in self.s.players or not self.s.players[target].in_game:
            raise RuleError("هدف نامعتبر است.")
        if ab == "kill" and target == uid:
            raise RuleError("نمی‌توانی خودت را هدف بگیری.")
        if ab == "protect":
            if target == uid:
                raise RuleError("پزشک نمی‌تواند خودش را نجات دهد.")
            if getattr(self.s, "_protect_prev", None) == target and \
               f"protect:{uid}" not in self.s.night_actions:
                raise RuleError("دو شب پیاپی نمی‌توانی یک نفر را نجات دهی.")
        if ab == "investigate":
            if self.s.night_actions.get(f"_inv_last:{uid}") == target:
                raise RuleError("همین نفر را شب قبل استعلام کردی؛ کس دیگری را انتخاب کن.")
            if f"expose:{uid}" in self.s.night_actions:
                raise RuleError("امشب اکشنت را روی راستی‌آزمایی مدرک خرج کرده‌ای.")
        self.s.night_actions[f"{ab}:{uid}"] = target   # اکشن دوباره = ویرایش اکشن
        if ab == "protect":
            self.s.night_actions["_last_protect"] = target
        if ab == "investigate":
            self.s.night_actions[f"_inv_last:{uid}"] = target
            # نتیجه سحر می‌رسد. اگر همین‌جا جواب می‌دادیم، کارآگاه می‌توانست
            # هدف را پشت‌سرهم عوض کند و در یک شب همه را استعلام کند.
            return f"ثبت شد: {self.s.players[target].name} — نتیجه سحر به دفترچه‌ات می‌رسد."
        return "ثبت شد"

    def _committed_actions(self) -> Dict[str, Dict[int, int]]:
        """اکشن‌های واقعیِ امشب: {ability: {actor_uid: target}}.
        کلیدهای دفترچه‌ای (با _ شروع می‌شوند) کنار گذاشته می‌شوند."""
        out: Dict[str, Dict[int, int]] = {}
        for k, v in self.s.night_actions.items():
            if k.startswith("_") or ":" not in k:
                continue
            ab, actor = k.split(":", 1)
            out.setdefault(ab, {})[int(actor)] = v
        return out

    def _deliver_night_info(self, acts: Dict[str, Dict[int, int]]) -> None:
        """اطلاعات اختصاصی نقش‌ها — سحر، یک‌بار، در دفترچه‌ی خودِ بازیکن."""
        day = self.s.day
        visits: Dict[int, int] = {}
        for ab, pairs in acts.items():
            if ab in ("investigate", "expose", "watch"):
                continue                       # استعلام/راستی‌آزمایی/نگهبانی «ملاقات» نیست
            for tgt in pairs.values():
                visits[tgt] = visits.get(tgt, 0) + 1

        for actor, tgt in acts.get("investigate", {}).items():
            p, t = self.s.players[actor], self.s.players[tgt]
            if tgt in self.s.hidden:
                res = "پاک"                     # قاچاقچی ردش را پاک کرده
            elif self.s.framed.get(tgt, 0) >= day:
                res = "مشکوک"                   # پاپوشِ همدست
            else:
                res = "پاک" if t.align is Align.CITY else "مشکوک"
            p.notes.append(f"شب {day}: {t.name} → {res}")

        for actor, tgt in acts.get("watch", {}).items():
            p, t = self.s.players[actor], self.s.players[tgt]
            n = 0 if tgt in self.s.hidden else visits.get(tgt, 0)
            p.notes.append(f"🛡️ شب {day}: {t.name} — {n} ملاقات")

        for actor in acts.get("spy", {}):
            p = self.s.players[actor]
            sus = self.s.suspect_uid
            who = self.s.players[sus].name if sus else "کسی"
            p.notes.append(f"📞 شب {day}: بازجو سراغ {who} رفته بود.")

        for actor, tgt in acts.get("autopsy", {}).items():
            p = self.s.players[actor]
            code = self.s.case.evidence[min(day - 1, len(self.s.case.evidence) - 1)]["code"]
            ev = next(e for e in self.s.case.evidence if e["code"] == code)
            p.notes.append(f"🧪 شب {day}: مدرک {code} → "
                           + ("جعلی 🎭" if ev["misleading"] else "اصل ✅"))

        for actor in acts.get("reveal", {}):    # خبرنگار: مدرک اضافه برای کل شهر
            nxt = self.s.case.evidence[min(day, len(self.s.case.evidence) - 1)]
            if nxt["code"] not in self.s.revealed_evidence:
                self.s.revealed_evidence.append(nxt["code"])
                self.s.log.append(f"📰 خبرنگار مدرک {nxt['code']} را رو کرد.")

        for tgt, until in list(self.s.framed.items()):
            if until < day:
                del self.s.framed[tgt]

    def resolve_night(self) -> Dict:
        # فاز بازجویی هم یک شب است: متهم شب را در اتاق می‌گذراند
        # و بقیه اکشن شبانه‌شان را دارند.
        if self.s.phase not in (Phase.NIGHT, Phase.INTERROGATION):
            raise RuleError("الان شب نیست.")
        # ایده ۴: رویداد تصادفی شبانه (قطعی بر اساس seed+روز)
        ev_rng = random.Random(self.s.chat_id * 1000 + self.s.day)
        roll = ev_rng.random()
        self.s.night_event = ("قطعی برق 🕯️" if roll < 0.12 else
                              "طوفان ⛈️" if roll < 0.22 else
                              "شاهد ناشناس 👁️" if roll < 0.32 else "")
        acts = self._committed_actions()
        protected = set(acts.get("protect", {}).values())
        self.s.hidden = list(set(acts.get("hide", {}).values()))
        # سم: هدف دو شب بعد می‌میرد مگر پزشک همان شب نجاتش دهد
        for tgt in acts.get("poison", {}).values():
            self.s.poison_queue.setdefault(tgt, self.s.day + 2)
        # پاپوش‌دوزی همدست: مدرک فردا به این نفر اشاره می‌کند
        for tgt in acts.get("frame", {}).values():
            self.s.framed[tgt] = self.s.day + 1
        killed: List[int] = []
        for tgt in acts.get("kill", {}).values():
            if tgt not in protected and tgt not in killed:
                killed.append(tgt)
        for tgt, due in list(self.s.poison_queue.items()):
            if due > self.s.day:
                continue
            del self.s.poison_queue[tgt]
            if tgt in protected:
                self.s.log.append(f"💉 پادزهر به موقع رسید: {self.s.players[tgt].name} نجات یافت.")
            elif self.s.players[tgt].in_game and tgt not in killed:
                killed.append(tgt)
                self.s.log.append(f"☠️ {self.s.players[tgt].name} بر اثر سم از پا درآمد.")
        if self.s.night_event.startswith("طوفان"):
            killed = []                           # طوفان قتل امشب را لغو کرد
        # ایده ۸: زوج سرنوشت
        if self.s.fate_pair:
            a, b = self.s.fate_pair
            if a in killed and b not in killed and self.s.players[b].in_game:
                killed.append(b)
            elif b in killed and a not in killed and self.s.players[a].in_game:
                killed.append(a)
        # ایده ۱۵: شلیک آخر شکارچی
        extra = []
        for uid in list(killed):
            p = self.s.players[uid]
            if p.role == "شکارچی" and p.hunter_target and p.hunter_target in self.s.players:
                tgt = self.s.players[p.hunter_target]
                if tgt.in_game and p.hunter_target not in killed:
                    extra.append(p.hunter_target)
                    self.s.log.append(f"🏹 شلیک آخر {p.name}: {tgt.name} را با خود برد!")
        killed += extra
        for uid in killed:
            self.s.players[uid].alive = False
        # ایده ۵: وصیت‌نامه‌ی کشته‌ها + ایده ۷: گزارش کالبدشکاف
        for uid in killed:
            w = self.s.players[uid].will
            if w:
                self.s.log.append(f"📜 وصیت {self.s.players[uid].name}: «{w}»")
        if killed:
            for p in self.s.players.values():
                if p.role == "کالبدشکاف" and p.in_game:
                    p.notes.append(f"🔬 شب {self.s.day}: مرگ حوالی ۲۳:۱۵ با {self.s.case.weapon}.")
        # ایده ۱۰: تحویل نتایج آزمایشگاه سررسیدشده
        ready = [c for c, d in self.s.lab_queue.items() if d <= self.s.day]
        for c in ready:
            del self.s.lab_queue[c]
            self.s.log.append(f"🧪 نتیجه‌ی آزمایشگاه برای مدرک {c} رسید: منشأ مدرک مشخص شد، تفسیرها را محدود کنید.")
        # پیشروی بازداشت‌ها
        self._advance_custody()
        self.s._protect_prev = self.s.night_actions.get("_last_protect")
        self.s.night_actions.clear()
        self.s.phase = Phase.MORNING
        self.s.deadline = None
        ev = self.s.case.evidence[min(self.s.day - 1, len(self.s.case.evidence) - 1)]
        self.s.revealed_evidence.append(ev["code"])
        if self.s.night_event.startswith("شاهد"):     # شاهد ناشناس → مدرک اضافه
            nxt = self.s.case.evidence[min(self.s.day, len(self.s.case.evidence) - 1)]
            if nxt["code"] not in self.s.revealed_evidence:
                self.s.revealed_evidence.append(nxt["code"])
        self._deliver_night_info(acts)
        self.s.log.append(f"شب {self.s.day}: کشته‌ها={[self.s.players[u].name for u in killed]}")
        self._check_win()
        return {"killed": killed, "evidence": ev}

    def _advance_custody(self) -> None:
        for p in self.s.players.values():
            if p.custody is Custody.INTERROGATION:
                p.custody_nights += 1
                # بعد از یک شب اگر بازجو تصمیم نگرفته باشد، آزاد می‌شود
                if p.custody_nights >= 1 and p.uid == self.s.suspect_uid:
                    pass  # تصمیم بازجو در فاز بازجویی گرفته می‌شود
            elif p.custody is Custody.TEMP_JAIL:
                p.custody_nights += 1
                if p.custody_nights >= self.temp_jail_nights and not p.cleared:
                    p.custody = Custody.LIFE_JAIL
                    p.custody_nights = 0
                    if p.uid in self.s.pending_jail:
                        self.s.pending_jail.remove(p.uid)
                    self.s.log.append(f"⛓️ {p.name} حبس ابد گرفت (نقشش فاش نمی‌شود).")

    # ---------------- روز / رای ----------------
    def open_discussion(self) -> None:
        if self.s.phase is not Phase.MORNING:
            raise RuleError("فاز اشتباه است.")
        self.s.phase = Phase.DISCUSSION
        self._arm()

    def open_vote(self) -> None:
        if self.s.phase is not Phase.DISCUSSION:
            raise RuleError("فاز اشتباه است.")
        self.s.phase = Phase.VOTE
        self._arm()
        self.s.votes.clear()

    def vote(self, voter: int, target: int) -> None:
        if self.s.phase is not Phase.VOTE:
            raise RuleError("الان رای‌گیری نیست.")
        v, t = self.s.players.get(voter), self.s.players.get(target)
        if not v or not v.can_vote:
            raise RuleError("حق رای نداری.")
        if not t or not t.can_speak:
            raise RuleError("هدف نامعتبر است.")
        if voter == target:
            raise RuleError("نمی‌توانی به خودت رای بدهی.")
        self.s.votes[voter] = target          # رای دوباره = ویرایش رای
        self.s.vote_history.append((self.s.day, voter, target))   # ایده ۱۶

    def close_vote(self) -> Optional[int]:
        """بیشترین رای → بازجویی (مرحله‌ی اول)."""
        if self.s.phase is not Phase.VOTE:
            raise RuleError("فاز اشتباه است.")
        if not self.s.votes:
            self.s.phase = Phase.NIGHT
            self.s.day += 1
            self._arm()
            return None
        tally: Dict[int, int] = {}
        for t in self.s.votes.values():
            tally[t] = tally.get(t, 0) + 1
        top = max(tally.values())
        leaders = [u for u, c in tally.items() if c == top]
        if len(leaders) != 1:            # ایده ۲۰: تساوی → مرگ ناگهانی
            if not self.s.tie_break and len(leaders) >= 2:
                self.s.tie_break = True
                self.s.votes.clear()
                self.s.log.append(f"⚔️ تساوی! مرگ ناگهانی بین: "
                                  + "، ".join(self.s.players[u].name for u in leaders))
                return None                     # فاز رای باز می‌ماند برای دور دوم
            self.s.tie_break = False
            self.s.phase = Phase.NIGHT
            self.s.day += 1
            self._arm()
            return None
        self.s.tie_break = False
        uid = leaders[0]
        self.send_to_interrogation(uid)
        return uid

    # ---------------- مرحله ۱: بازجویی ----------------
    def send_to_interrogation(self, uid: int) -> None:
        p = self.s.players[uid]
        if not p.can_speak:
            raise RuleError("این بازیکن قابل بازجویی نیست.")
        p.custody = Custody.INTERROGATION
        p.custody_nights = 0
        p.cleared = False
        p.stress += 20
        self.s.suspect_uid = uid
        self.s.phase = Phase.INTERROGATION
        self.s.day += 1                 # شبِ بازجویی آغاز شد
        self._arm()
        self.s.log.append(f"🔦 {p.name} به بازجویی رفت (فاصله: ۱ شب).")

    def officer_hints(self, officer_uid: int) -> List[str]:
        if officer_uid != self.s.officer_uid:
            raise RuleError("فقط بازجو دسترسی دارد.")
        if not self.s.suspect_uid:
            raise RuleError("کسی در بازجویی نیست.")
        return dialogue.interrogation_hints(self.s.players[self.s.suspect_uid], self.s.day)

    def ask(self, officer_uid: int, question: str) -> str:
        if officer_uid != self.s.officer_uid:
            raise RuleError("فقط بازجو می‌تواند استنطاق کند.")
        sus = self.s.players[self.s.suspect_uid]
        sus.stress += 5
        ans = dialogue.answer(sus, question, self.s.day)
        prev = sus.qa.get(question)
        sus.qa[question] = ans
        if prev is not None and prev != ans:
            return ans + "\n⚠️ تناقض: جوابش با دفعه‌ی قبل فرق دارد!"
        return ans

    def officer_verdict(self, officer_uid: int, confirm: bool) -> str:
        """confirm=True → حبس موقت (۲ شب). confirm=False → آزادی + تایید بی‌گناهی."""
        if officer_uid != self.s.officer_uid:
            raise RuleError("فقط بازجو حکم می‌دهد.")
        if self.s.suspect_uid is None:
            raise RuleError("کسی در بازجویی نیست.")
        p = self.s.players[self.s.suspect_uid]
        if p.custody_nights < self.interrogation_nights:
            raise RuleError("حکم بعد از گذشتن یک شب بازجویی صادر می‌شود.")
        if confirm:
            p.custody = Custody.TEMP_JAIL
            p.custody_nights = 0
            self.s.pending_jail.append(p.uid)
            msg = f"🔒 {p.name} به حبس موقت رفت (۲ شب). آزادی‌اش فقط با تایید بی‌گناهی توسط بازجو، آن هم وقتی متهم جدیدی وارد بازجویی شده باشد."
        else:
            p.custody = Custody.FREE
            p.cleared = True
            p.stress = max(0, p.stress - 15)
            msg = f"🔓 {p.name} آزاد شد؛ بازجو بی‌گناهی‌اش را تایید کرد."
        self.s.suspect_uid = None
        self.s.defense_text = ""
        self.s.log.append(msg)
        # شب قبلاً گذشته؛ روز از همین صبح ادامه می‌دهد.
        if self.s.phase is Phase.INTERROGATION:
            self.s.phase = Phase.MORNING
        self._arm()
        self._check_win()
        return msg

    # ---------------- مرحله ۲: حبس موقت + آزادسازی مشروط ----------------
    def clear_previous(self, officer_uid: int, uid: int) -> str:
        """آزادی از حبس موقت: فقط وقتی یک متهم *جدید* داخل بازجویی است."""
        if officer_uid != self.s.officer_uid:
            raise RuleError("فقط بازجو می‌تواند تایید کند.")
        if self.s.suspect_uid is None:
            raise RuleError("برای آزادی حبس موقت، باید متهم جدیدی وارد بازجویی شده باشد.")
        if self.s.suspect_uid == uid:
            raise RuleError("متهم فعلی نمی‌تواند خودش را تبرئه کند.")
        p = self.s.players[uid]
        if p.custody is not Custody.TEMP_JAIL:
            raise RuleError("این بازیکن در حبس موقت نیست.")
        p.custody = Custody.FREE
        p.cleared = True
        p.custody_nights = 0
        self.s.pending_jail.remove(uid)
        msg = f"🕊️ {p.name} از حبس موقت آزاد شد (تایید بی‌گناهی توسط بازجو)."
        self.s.log.append(msg)
        return msg

    # ---------------- هیئت منصفه ----------------
    def request_jury(self, uid: int) -> bool:
        """بعد از یک شب در بازجویی، هم‌تیمی‌ها می‌توانند هیئت منصفه تشکیل دهند.
        وکیل به‌تنهایی کافی است؛ بقیه حداقل ۲ نفر."""
        sus = self.s.suspect_uid
        if sus is None:
            raise RuleError("کسی در بازجویی نیست.")
        target = self.s.players[sus]
        if target.custody_nights < self.interrogation_nights:
            raise RuleError("هیئت منصفه فقط بعد از یک شب بازجویی ممکن است.")
        if target.jury_used:
            raise RuleError("برای این متهم قبلاً هیئت منصفه تشکیل شده.")
        req = self.s.jury_requests.setdefault(sus, set())
        req.add(uid)
        need = 1 if self.s.players[uid].role == "وکیل" else JURY_MIN_REQUESTS
        if len(req) >= need:
            self.s.phase_before_jury = self.s.phase
            self.s.phase = Phase.JURY
            self.s.jury_votes.clear()
            target.jury_used = True
            return True
        return False

    def jury_vote(self, uid: int, acquit: bool) -> None:
        if self.s.phase is not Phase.JURY:
            raise RuleError("هیئت منصفه فعال نیست.")
        p = self.s.players[uid]
        if not p.can_vote:
            raise RuleError("حق رای در هیئت منصفه نداری.")
        self.s.jury_votes[uid] = acquit

    def close_jury(self) -> str:
        if self.s.phase is not Phase.JURY:
            raise RuleError("فاز اشتباه است.")
        p = self.s.players[self.s.suspect_uid]
        yes = sum(1 for v in self.s.jury_votes.values() if v)
        total = max(1, len(self.s.jury_votes))
        back = self.s.phase_before_jury or Phase.MORNING
        if yes * 100 >= JURY_ACQUIT_PERCENT * total:
            p.custody = Custody.FREE
            p.cleared = True
            p.custody_nights = 0
            self.s.suspect_uid = None
            msg = f"⚖️ هیئت منصفه {p.name} را تبرئه کرد."
        else:
            msg = f"⚖️ هیئت منصفه رای به ادامه‌ی بازجویی داد؛ حکم نهایی با بازجوست."
        # شبِ بازجویی قبلاً گذشته؛ به همان روز برمی‌گردیم.
        self.s.phase = Phase.MORNING if back is Phase.INTERROGATION else back
        self.s.phase_before_jury = None
        self.s.log.append(msg)
        return msg

    # ---------------- پایان ----------------
    def _check_win(self) -> Optional[str]:
        alive = self.s.alive_players()
        k = [p for p in alive if p.align is Align.KILLER]
        c = [p for p in alive if p.align is not Align.KILLER]
        jailed_neutral = [p for p in self.s.players.values()
                          if p.align is Align.NEUTRAL and p.role == "سپر بلا"
                          and p.custody is Custody.LIFE_JAIL]
        if jailed_neutral:
            self.s.winner = "سپر بلا 🎭"
        elif len(alive) == 1 and alive[0].role == "جانی سریالی":
            self.s.winner = "جانی سریالی 🩸"    # ایده ۱۸: تنها بازمانده
        elif not k:
            self.s.winner = "شهر 🕵️"
        elif len(k) >= len(c):         # ایده ۴: برد قاتل با برابری (parity)
            self.s.winner = "قاتل‌ها 🔪"
        if self.s.winner:
            self.s.phase = Phase.END
            self._payout()
        return self.s.winner

    def _payout(self) -> None:
        for p in self.s.players.values():
            win = (self.s.winner or "").startswith(p.align.value[:3]) or \
                  (p.role == "سپر بلا" and self.s.winner.startswith("سپر"))
            p.xp += 120 if win else 40
            p.coins += 60 if win else 20
            p.xp += 10 * len([n for n in p.notes if n.startswith("شب")])
        killers = {q.uid for q in self.s.players.values() if q.align is Align.KILLER}
        for p in self.s.players.values():        # ایده ۱۶: پاداش دقت رای
            hits = sum(1 for _, v, t in self.s.vote_history if v == p.uid and t in killers)
            p.xp += 15 * hits
        self.s.mvp = max(self.s.players, key=lambda u: self.s.players[u].xp)   # ایده ۱۷

    def reveal(self) -> List[Tuple[str, str, str]]:
        if self.s.phase is not Phase.END:
            raise RuleError("تا پایان بازی، هیچ نقشی فاش نمی‌شود.")
        return [(p.name, p.role, p.custody.value) for p in self.s.players.values()]

    # ---------------- ایده ۲: آخرین دفاع ----------------
    def defense(self, uid: int, text: str) -> str:
        if uid != self.s.suspect_uid:
            raise RuleError("فقط متهمِ داخل بازجویی می‌تواند دفاع کند.")
        self.s.defense_text = text[:300]
        return f"🗣️ آخرین دفاع {self.s.players[uid].name}: «{self.s.defense_text}»"

    # ---------------- ایده ۵/۹ ----------------
    def set_will(self, uid: int, text: str) -> None:
        self.s.players[uid].will = text[:200]

    def add_note(self, uid: int, text: str) -> None:
        self.s.players[uid].private_notes.append(text[:200])

    # ---------------- ایده ۶: رای اضطراری شهر ----------------
    def sos(self, uid: int, target: int) -> str:
        if self.s.sos_used:
            raise RuleError("سلاح مخفی شهر فقط یک بار در بازی قابل استفاده است.")
        v, t = self.s.players.get(uid), self.s.players.get(target)
        if not v or not v.can_vote or not t or not t.can_speak or uid == target:
            raise RuleError("رای اضطراری نامعتبر است.")
        sup = self.s.sos_votes.setdefault(target, set())
        sup.add(uid)
        need = math.ceil(0.8 * len([p for p in self.s.alive_players() if p.can_vote]))
        if len(sup) >= need:
            self.s.sos_used = True
            t.custody = Custody.TEMP_JAIL
            t.custody_nights = 0
            self.s.pending_jail.append(t.uid)
            self.s.sos_votes.clear()
            self.s.log.append(f"🚨 رای اضطراری شهر: {t.name} مستقیم به حبس موقت رفت!")
            return f"🚨 تصویب شد! {t.name} مستقیم به حبس موقت رفت."
        return f"🚨 رای اضطراری علیه {t.name}: {len(sup)}/{need}"

    # ---------------- ایده ۱۰: آزمایشگاه با تاخیر ----------------
    def submit_lab(self, code: str) -> str:
        if not self.s.case:
            raise RuleError("بازی هنوز شروع نشده؛ مدرکی وجود ندارد.")
        codes = {e["code"] for e in self.s.case.evidence}
        if code not in codes:
            raise RuleError("کد مدرک نامعتبر است (E1 تا E6).")
        if code in self.s.lab_queue:
            raise RuleError("این مدرک در صف آزمایشگاه است.")
        self.s.lab_queue[code] = self.s.day + 2
        return f"🧪 مدرک {code} به آزمایشگاه رفت؛ نتیجه دو شب دیگر می‌رسد."

    # ---------------- ایده ۱۱: رای تفسیر مدرک ----------------
    def vote_interp(self, uid: int, code: str, idx: int) -> str:
        if not self.s.case:
            raise RuleError("بازی هنوز شروع نشده؛ مدرکی وجود ندارد.")
        ev = next((e for e in self.s.case.evidence if e["code"] == code), None)
        if not ev or not (0 <= idx < len(ev["interpretations"])):
            raise RuleError("مدرک یا تفسیر نامعتبر.")
        self.s.interp_votes.setdefault(code, {})[uid] = idx
        tally = self.s.interp_votes[code]
        top = max(set(tally.values()), key=list(tally.values()).count)
        return f"🧠 تفسیر غالب {code}: «{ev['interpretations'][top]}» ({len(tally)} رای)"

    # ---------------- ایده ۱۲: راستی‌آزمایی مدرک توسط کارآگاه ----------------
    def expose(self, uid: int, code: str) -> str:
        p = self.s.players.get(uid)
        if not p or p.role != "کارآگاه" or not p.in_game:
            raise RuleError("فقط کارآگاه می‌تواند اصالت مدرک را بسنجد.")
        if self.s.phase not in (Phase.NIGHT, Phase.INTERROGATION):
            raise RuleError("راستی‌آزمایی فقط در شب ممکن است.")
        if f"investigate:{uid}" in self.s.night_actions or f"expose:{uid}" in self.s.night_actions:
            raise RuleError("امشب اکشنت را خرج کرده‌ای.")
        if not self.s.case:
            raise RuleError("بازی هنوز شروع نشده.")
        ev = next((e for e in self.s.case.evidence if e["code"] == code), None)
        if not ev:
            raise RuleError("کد مدرک نامعتبر است.")
        self.s.night_actions[f"expose:{uid}"] = 0
        res = "جعلی 🎭" if ev["misleading"] else "اصل ✅"
        p.notes.append(f"شب {self.s.day}: مدرک {code} → {res}")
        return res

    # ---------------- ایده ۱۴/۱۷: بازسازی و MVP ----------------
    def reconstruction(self) -> str:
        tail = self.s.log[-12:]
        return "🎬 بازسازی پرونده:\n" + "\n".join(f"  • {l}" for l in tail)

    def set_hunter(self, uid: int, target: int) -> str:
        """ایده ۱۵: شکارچی هدف شلیک آخرش را از قبل مشخص می‌کند."""
        p = self.s.players.get(uid)
        if not p or p.role != "شکارچی":
            raise RuleError("فقط شکارچی می‌تواند هدف شلیک آخر بگذارد.")
        t = self.s.players.get(target)
        if not t or not t.in_game or target == uid:
            raise RuleError("هدف نامعتبر است.")
        p.hunter_target = target
        return f"🏹 هدف شلیک آخر ثبت شد: {t.name}"

    def rank_of(self, p: Player) -> str:
        for th, name in [(1200, "کارآگاه افسانه‌ای 👑"), (800, "رئیس تحقیقات 🎖️"),
                         (450, "کلانتر ⭐"), (200, "بازرس 🔍")]:
            if p.xp >= th:
                return name
        return "کارآگاه تازه‌کار 🧢"
