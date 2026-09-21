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


def _fa(n) -> str:
    """عدد فارسی — متنِ قانون همیشه از روی همین کانفیگ ساخته شود."""
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


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
        if self.s.paused:
            return self.s.paused_left
        if self.s.deadline is None:
            return None
        return max(0, int(self.s.deadline - _time.time()))

    # ---------------- بهبود ۷: توقف/ادامه ----------------
    def pause(self) -> str:
        if self.s.phase in (Phase.LOBBY, Phase.END):
            raise RuleError("بازی در جریان نیست.")
        if self.s.paused:
            raise RuleError("بازی همین حالا متوقف است.")
        self.s.paused_left = self.remaining()   # اول بخوان، بعد پرچم را بزن
        self.s.paused = True
        self.s.deadline = None            # تایمر دیگر فاز را جلو نمی‌برد
        self.s.log.append("⏸️ بازی موقتاً متوقف شد.")
        return "⏸️ بازی متوقف شد. با «▶️ ادامه» برگردید."

    def resume(self) -> str:
        if not self.s.paused:
            raise RuleError("بازی متوقف نیست.")
        self.s.paused = False
        left = self.s.paused_left
        self.s.paused_left = None
        self.s.deadline = (_time.time() + left) if left else None
        self.s.log.append("▶️ بازی ادامه یافت.")
        return f"▶️ ادامه! {left if left else '—'} ثانیه از این فاز مانده."

    def transfer_host(self, new_owner: int) -> str:
        """میزبان غایب → میزبانی به یک بازیکنِ داخل بازی منتقل می‌شود."""
        p = self.s.players.get(new_owner)
        if not p:
            raise RuleError("این نفر در بازی نیست.")
        if not p.in_game:
            raise RuleError("میزبان باید در بازی باشد.")
        self.owner = new_owner
        self.s.log.append(f"👑 میزبانی به {p.name} رسید.")
        return f"👑 میزبان جدید: {p.name}"

    def tick(self) -> Optional[str]:
        """اگر مهلت فاز گذشته باشد، خودکار جلو می‌برد. خروجی: توضیح اتفاق."""
        if self.s.paused:                 # بازیِ متوقف هرگز خودکار جلو نمی‌رود
            return None
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
            raise RuleError(f"ظرفیت لابی پر است (حداکثر {_fa(MAX_P)} نفر).")
        p = Player(uid=uid, name=name)
        self.s.players[uid] = p
        return p

    def leave(self, uid: int) -> None:
        if self.s.phase is not Phase.LOBBY:
            raise RuleError("در میانه‌ی بازی نمی‌توان خارج شد.")
        self.s.players.pop(uid, None)
        if uid == self.owner and self.s.players:      # مهاجرت میزبانی
            self.owner = next(iter(self.s.players))

    # ---------------- بهبود ۲: آمادگی پیش از شروع ----------------
    def mark_ready(self, uid: int) -> str:
        """فقط از راه دیپ‌لینکِ پیوی صدا می‌شود — یعنی ربات واقعاً می‌تواند
        به این بازیکن پیام خصوصی بدهد."""
        p = self.s.players.get(uid)
        if not p:
            raise RuleError("اول وارد لابی شو.")
        p.ready = True
        return f"✅ {p.name} آماده است."

    def not_ready(self) -> List[int]:
        return [p.uid for p in self.s.players.values() if not p.ready]

    def start(self, case_id: Optional[int] = None, force: bool = True) -> None:
        """force=False یعنی اول آمادگی همه را چک کن (لایه‌ی ربات)."""
        n = len(self.s.players)
        if not (MIN_P <= n <= MAX_P):
            raise RuleError(f"تعداد بازیکن باید بین {_fa(MIN_P)} تا {_fa(MAX_P)} باشد.")
        if not validate_composition(n):
            raise RuleError("ترکیب نقش نامعتبر است.")
        if not force:
            missing = self.not_ready()
            if missing:
                names = "، ".join(self.s.players[u].name for u in missing)
                raise RuleError(
                    f"این بازیکن‌ها هنوز پیوی ربات را باز نکرده‌اند: {names}\n"
                    "هر کدام دکمه‌ی «✅ آماده‌ام» را بزنند (نقش محرمانه آنجا می‌رود). "
                    "برای شروع بدون آن‌ها: /startgame force")
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
            elif info == "forensic_files":
                p.knows = [f"آزمایشگاه: {self.s.case.evidence[0]['title']}"]
            elif info == "police_files":
                p.knows = ["تو بازجویی؛ پرونده‌های پلیس و پلاک خودرو دست توست."]
            elif info == "rumor":
                p.knows = [f"شایعه: سلاح احتمالاً «{self.s.case.weapon}» بوده."]
            else:
                p.knows = []
        self.s.officer_uid = next(p.uid for p in self.s.players.values() if p.role == "بازجو")
        # مالک پلاک: نیمی از مواقع یکی از قاتل‌ها، نیمی از مواقع یک بی‌گناه.
        # اگر همیشه قاتل بود، استعلام پلاک بازی را یک‌شبه تمام می‌کرد.
        kl = [u for u in killers if u != self.s.officer_uid]
        others = [q.uid for q in self.s.players.values()
                  if q.uid not in killers and q.uid != self.s.officer_uid]
        pick = kl if (kl and self.rng.random() < 0.5) else (others or kl)
        self.s.plate_owner = self.rng.choice(pick) if pick else None
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
    def check_night_action(self, uid: int, target: int) -> str:
        """قواعد اکشن شبانه در یک جا. خطا پرت می‌کند یا نام توانایی را می‌دهد.
        هم night_action و هم legal_targets از همین رد می‌شوند تا دکمه‌ها
        هیچ‌وقت با قواعد فرق نکنند."""
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
            edit = f"protect:{uid}" in self.s.night_actions   # ویرایش همان اکشن
            if target == uid:
                # نجاتِ خود: یک بار در کل بازی. نجات دیگران بی‌سقف است.
                if p.self_save_used and not edit:
                    raise RuleError("خودت را یک بار نجات داده‌ای؛ از این به بعد فقط دیگران.")
            elif self.s._protect_prev == target and not edit:
                raise RuleError("دو شب پیاپی نمی‌توانی یک نفر را نجات دهی.")
        if ab == "investigate":
            if self.s.night_actions.get(f"_inv_last:{uid}") == target:
                raise RuleError("همین نفر را شب قبل استعلام کردی؛ کس دیگری را انتخاب کن.")
            if f"expose:{uid}" in self.s.night_actions:
                raise RuleError("امشب اکشنت را روی راستی‌آزمایی مدرک خرج کرده‌ای.")
        return ab

    def legal_targets(self, uid: int) -> List[int]:
        """هدف‌هایی که همین حالا برای این بازیکن مجازند — برای ساخت دکمه‌ها."""
        out = []
        for t in self.s.players:
            try:
                self.check_night_action(uid, t)
            except RuleError:
                continue
            out.append(t)
        return out

    def chosen_target(self, uid: int) -> Optional[int]:
        """هدفی که این بازیکن امشب ثبت کرده (برای نشان دادن ✅ روی دکمه)."""
        for ab, pairs in self._committed_actions().items():
            if uid in pairs:
                return pairs[uid]
        return None

    def night_action(self, uid: int, target: int) -> str:
        ab = self.check_night_action(uid, target)
        p = self.s.players[uid]
        self.s.night_actions[f"{ab}:{uid}"] = target   # اکشن دوباره = ویرایش اکشن
        if ab == "protect":
            self.s.night_actions["_last_protect"] = target
        if ab == "investigate":
            self.s.night_actions[f"_inv_last:{uid}"] = target
            # نتیجه سحر می‌رسد. اگر همین‌جا جواب می‌دادیم، کارآگاه می‌توانست
            # هدف را پشت‌سرهم عوض کند و در یک شب همه را استعلام کند.
            return f"ثبت شد: {self.s.players[target].name} — نتیجه سحر به دفترچه‌ات می‌رسد."
        return "ثبت شد"

    def pending_actors(self) -> List[int]:
        """چه کسانی هنوز کاری که این فاز از آن‌ها می‌خواهد انجام نداده‌اند."""
        if self.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
            acted = {a for pairs in self._committed_actions().values() for a in pairs}
            return [p.uid for p in self.s.alive_players()
                    if p.can_speak and ROLES[p.role].ability not in ("", "hunter")
                    and p.uid not in acted]
        if self.s.phase is Phase.VOTE:
            return [p.uid for p in self.s.alive_players()
                    if p.can_vote and p.uid not in self.s.votes]
        if self.s.phase is Phase.JURY:
            return [p.uid for p in self.s.alive_players()
                    if p.can_vote and p.uid not in self.s.jury_votes]
        return []

    def next_step(self) -> str:
        """یک جمله: الان نوبت چیست."""
        ph = self.s.phase
        if ph is Phase.LOBBY:
            n = len(self.s.players)
            return ("منتظر بازیکن بیشتر" if n < MIN_P else "میزبان «🎬 شروع بازی» را بزند")
        if ph in (Phase.NIGHT, Phase.INTERROGATION):
            return "نقش‌های شبانه اکشنشان را بدهند، بعد «🌙 پایان شب»"
        if ph is Phase.MORNING:
            sus = self.s.suspect_uid
            if sus is not None:
                return f"بازجو درباره‌ی {self.s.players[sus].name} حکم بدهد، یا ⚖️ هیئت منصفه"
            return "«💬 گفتگو» را باز کنید"
        if ph is Phase.DISCUSSION:
            return "بحث کنید، بعد «🗳️ رای‌گیری»"
        if ph is Phase.VOTE:
            return "رای بدهید، بعد «📊 بستن رای‌گیری»"
        if ph is Phase.JURY:
            return "هیئت منصفه رای بدهد، بعد «📊 نتیجه»"
        return "بازی تمام شده — «🏁 پایان» نقش‌ها را نشان می‌دهد"

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

    def _build_traces(self, acts: Dict[str, Dict[int, int]], killed: List[int]) -> None:
        """بهبود ۵: مدرکِ برخاسته از کارِ واقعیِ بازیکن‌ها — نه تزئین.

        هر «ملاقات» شبانه رد می‌گذارد. شمارش عمومی است (مبهم می‌ماند چون
        پزشک و نگهبان هم سر می‌زنند) ولی کسانی که یک‌جا بوده‌اند خصوصی
        همدیگر را می‌بینند؛ همین حرف‌زدنی می‌شود که می‌توان با آن دروغ گفت.
        """
        self.s.traces = []
        visitors: Dict[int, List[int]] = {}
        for ab, pairs in acts.items():
            if ab in ("investigate", "expose", "watch"):
                continue                   # از دور نگاه کردن ردی نمی‌گذارد
            for actor, tgt in pairs.items():
                visitors.setdefault(tgt, []).append(actor)

        for victim in killed:
            n = len(visitors.get(victim, []))
            if n:
                self.s.traces.append(
                    f"🐾 دیشب {n} نفر به {self.s.players[victim].name} سر زدند "
                    "(قاتل بین آن‌هاست — ولی پزشک و نگهبان هم سر می‌زنند).")

        # هم‌مکانی: هر دو نفری که یک هدف داشتند، خصوصی همدیگر را می‌بینند
        for tgt, who in visitors.items():
            alive_who = [u for u in who if self.s.players[u].in_game]
            if len(alive_who) < 2:
                continue
            name = self.s.players[tgt].name
            for a in alive_who:
                others = "، ".join(self.s.players[b].name for b in alive_who if b != a)
                self.s.players[a].notes.append(
                    f"👥 شب {self.s.day}: کنار {name} با {others} روبه‌رو شدی.")
            self.s.traces.append(
                f"👣 {len(alive_who)} نفر هم‌زمان نزدیک {name} بوده‌اند؛ "
                "می‌توانند شاهد هم باشند.")

        for tgt, until in self.s.framed.items():
            if until >= self.s.day:
                self.s.traces.append(
                    f"🖐️ اثر انگشت روی صحنه به *{self.s.players[tgt].name}* می‌خورد "
                    "— اثر انگشت را می‌شود کاشت.")

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
        for actor, tgt in acts.get("protect", {}).items():
            if actor == tgt:
                self.s.players[actor].self_save_used = True
        self.s.hidden = list(set(acts.get("hide", {}).values()))
        # سم: هدف دو شب بعد می‌میرد مگر پزشک همان شب نجاتش دهد
        for tgt in acts.get("poison", {}).values():
            self.s.poison_queue.setdefault(tgt, self.s.day + 2)
        # پاپوش‌دوزی همدست: مدرک فردا به این نفر اشاره می‌کند
        for tgt in list(acts.get("frame", {}).values()) + list(acts.get("plant", {}).values()):
            self.s.framed[tgt] = self.s.day + 1
        # حمله‌ی مستقیم امشب — طوفان فقط همین را لغو می‌کند
        killed: List[int] = []
        for tgt in acts.get("kill", {}).values():
            if tgt not in protected and tgt not in killed:
                killed.append(tgt)
        if self.s.night_event.startswith("طوفان") and killed:
            self.s.log.append("⛈️ طوفان راه‌ها را بست؛ حمله‌ی امشب ناکام ماند.")
            killed = []
        # سمِ سررسیده ربطی به طوفان ندارد: دو شب پیش خورده شده.
        for tgt, due in list(self.s.poison_queue.items()):
            if due > self.s.day:
                continue
            if tgt in protected:
                del self.s.poison_queue[tgt]
                self.s.log.append(f"💉 پادزهر به موقع رسید: {self.s.players[tgt].name} نجات یافت.")
            elif not self.s.players[tgt].in_game:
                del self.s.poison_queue[tgt]      # قبلاً از بازی بیرون رفته
            elif tgt not in killed:
                del self.s.poison_queue[tgt]
                killed.append(tgt)
                self.s.log.append(f"☠️ {self.s.players[tgt].name} بر اثر سم از پا درآمد.")
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
        # بهبود ۷: اکشنِ نداده پیش‌فرضش «هیچ‌کاری» است، ولی غیبت شمرده می‌شود.
        # از acts استفاده می‌کنیم چون night_actions همین بالا پاک شده.
        acted = {a for pairs in acts.values() for a in pairs}
        for p in self.s.players.values():
            if p.can_speak and ROLES[p.role].ability not in ("", "hunter"):
                p.missed = 0 if p.uid in acted else p.missed + 1
        afk = [p.name for p in self.s.alive_players() if p.missed >= 2]
        if afk:
            self.s.log.append("😴 چند شب بی‌حرکت: " + "، ".join(afk))
        self._build_traces(acts, killed)
        self._deliver_night_info(acts)
        self._new_day_hint(acts, killed)
        self._deliver_plate()        # نتیجه‌ی استعلامِ دیشبِ پلیس
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
        v = self.s.players.get(voter)
        if not v or not v.can_vote:
            raise RuleError("حق رای نداری.")
        if target == 0:                  # ممتنع: رای قبلی پس گرفته می‌شود
            self.s.votes.pop(voter, None)
            return
        t = self.s.players.get(target)
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
                self._arm()                     # مهلت تازه؛ وگرنه تیکِ بعدی دور دوم را می‌بلعد
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
        sus = self.s.players[self.s.suspect_uid]
        # سرنخ‌ها از واقعیتِ دیشب ساخته می‌شوند، نه از هوا: هر شب فرق می‌کنند.
        ev = (self.s.night_event or "").split()
        facts = {
            "visited": any(n.startswith(f"👥 شب {self.s.day - 1}") or
                           n.startswith(f"👥 شب {self.s.day}") for n in sus.notes),
            "was_visited": any(sus.name in tr for tr in self.s.traces),
            "framed": self.s.framed.get(sus.uid, 0) >= self.s.day,
            "blackout": bool(ev) and ev[0] == "قطعی",
            "storm": bool(ev) and ev[0] == "طوفان",
            "threatened": sus.stress >= 40,
        }
        return dialogue.interrogation_hints(sus, self.s.day, self.s.case, facts)

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
            self._publish_notes(p)      # صندوق امانات همین‌جا باز می‌شود
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
            self.s.win_reason = ("🎭 سپر بلا حبس ابد گرفت — شرط بردش دقیقاً همین بود؛ "
                                 "شهر گناه را گردن او انداخت.")
        elif len(alive) == 1 and alive[0].role == "جانی سریالی":
            self.s.winner = "جانی سریالی 🩸"    # ایده ۱۸: تنها بازمانده
            self.s.win_reason = "🩸 جانی سریالی تنها بازمانده شد — شرط بردش تنهایی بود."
        elif not k:
            self.s.winner = "شهر 🕵️"
            self.s.win_reason = ("🕵️ هیچ قاتلی در بازی نماند (کشته یا حبس ابد) — "
                                 "شهر همه را پیدا کرد.")
        elif len(k) >= len(c):         # ایده ۴: برد قاتل با برابری (parity)
            self.s.winner = "قاتل‌ها 🔪"
            self.s.win_reason = (f"🔪 قاتل‌ها {len(k)} نفر ماندند و بقیه {len(c)} نفر — "
                                 "وقتی قاتل‌ها کم‌تر نباشند دیگر رای شهر جلودارشان نیست.")
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
            self._publish_notes(t)      # صندوق امانات همین‌جا باز می‌شود
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

    # ---------------- بهبود ۶: پایانِ قابل‌فهم ----------------
    def ending_report(self) -> str:
        """چرا این تیم برد، چه کسی چه بود، و کدام تصمیم‌ها سرنوشت‌ساز شدند."""
        if self.s.phase is not Phase.END:
            raise RuleError("بازی هنوز تمام نشده.")
        rows = []
        for p in self.s.players.values():
            rd = ROLES[p.role]
            if not p.alive:
                fate = "💀 کشته شد"
            elif p.custody is Custody.LIFE_JAIL:
                fate = "⛓️ حبس ابد"
            elif p.custody is Custody.TEMP_JAIL:
                fate = "🔒 حبس موقت"
            else:
                fate = "🟢 زنده ماند"
            rows.append(f"  {rd.emoji} {p.name} — {p.role} ({rd.align.value}) — {fate}")

        wrong = [p.name for p in self.s.players.values()
                 if p.custody is Custody.LIFE_JAIL and p.align is Align.CITY]
        justice = ("⚖️ شهر بی‌گناه حبس ابد کرد: " + "، ".join(wrong)
                   if wrong else "⚖️ هیچ بی‌گناهی حبس ابد نگرفت.")

        killers = {p.uid for p in self.s.players.values() if p.align is Align.KILLER}
        sharp = []
        for p in self.s.players.values():
            hits = sum(1 for _, v, t in self.s.vote_history if v == p.uid and t in killers)
            if hits:
                sharp.append(f"{p.name} ({hits} رای درست)")
        votes = ("🎯 رای‌های درست روی قاتل‌ها: " + "، ".join(sharp)
                 if sharp else "🎯 هیچ‌کس رایِ درستی روی قاتل نداد.")

        mvp = self.s.players[self.s.mvp].name if self.s.mvp else "—"
        return (f"🏁 *پایان — برنده: {self.s.winner}*\n{'─' * 18}\n"
                f"{self.s.win_reason}\n{'─' * 18}\n"
                "🎭 *نقش‌ها:*\n" + "\n".join(rows) +
                f"\n{'─' * 18}\n{justice}\n{votes}\n⭐ MVP: {mvp}\n\n"
                + self.reconstruction())

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

    # ================= پیام خصوصی از دل موتور =================
    # موتور شبکه ندارد؛ فقط پیام را در صندوق می‌گذارد و لایه‌ی ربات خالی‌اش می‌کند.
    # uid=0 یعنی «این را در گروه بگو».
    def post(self, uid: int, text: str) -> None:
        self.s.outbox.append((uid, text))

    def drain(self) -> List[tuple]:
        out, self.s.outbox = list(self.s.outbox), []
        return out

    # ================= سرنخِ تازه‌ی هر روز =================
    def _new_day_hint(self, acts: Dict[str, Dict[int, int]], killed: List[int]) -> None:
        """سرنخ روزِ تازه از سه چیز ساخته می‌شود: پرونده، کارِ واقعیِ دیشب،
        و رویداد شب. پس روز دوم و سوم و چهارم هرگز متنِ تکراری نمی‌گیرند."""
        from .cases import day_clue
        facts = {
            "visits": sum(len(v) for ab, v in acts.items()
                          if ab not in ("investigate", "expose", "watch")),
            "killed": [self.s.players[u].name for u in killed],
            "event": self.s.night_event,
            "framed": [self.s.players[u].name for u, d in self.s.framed.items()
                       if d >= self.s.day],
        }
        self.s.hints_from = len(self.s.day_hints)     # سرنخ‌های همین صبح از اینجا
        self.s.day_hints.append(day_clue(self.s.case, self.s.day, facts))
        if self.s.day == 1 and self.s.case.vehicle:
            # رنگ و مدل برای همه؛ پلاک فقط در پرونده‌ی پلیس می‌ماند.
            from .cases import vehicle_clue
            self.s.day_hints.append(vehicle_clue(self.s.case))
        self.s.day_hints += self.s.fake_clues      # سرنخ‌های جعلیِ قاتل، بی‌نشان
        self.s.fake_clues = []

    def today_hints(self) -> List[str]:
        """همه‌ی سرنخ‌های همین صبح — واقعی و جعلی، به همان ترتیب و بی‌نشان."""
        return self.s.day_hints[self.s.hints_from:]

    def today_hint(self) -> str:
        return self.s.day_hints[-1] if self.s.day_hints else ""

    # ================= جعبه‌ابزار قاتل (همه از پیوی) =================
    def _killer(self, uid: int) -> Player:
        p = self.s.players.get(uid)
        if not p or p.align is not Align.KILLER or not p.in_game:
            raise RuleError("فقط تیم قاتل به این کار دسترسی دارد.")
        # عضویت در تیم، ابزارِ تخصصی نمی‌آورد: شهروندی که دعوت را پذیرفته
        # هم‌تیمی هست ولی جعبه‌ابزار ندارد (hints.md §۱۲.۲).
        if p.recruited or not ROLES[p.role].ability:
            raise RuleError("تو به تیم پیوسته‌ای، ولی ابزار شبانه‌ی تخصصی نداری.")
        if self.s.phase not in (Phase.NIGHT, Phase.INTERROGATION):
            raise RuleError("این کار فقط در شب ممکن است.")
        if p.custody in (Custody.INTERROGATION, Custody.TEMP_JAIL):
            raise RuleError("در بازداشتی؛ امشب کاری از تو برنمی‌آید.")
        return p

    def skip_kill(self, uid: int) -> str:
        """امشب نکشتن هم یک انتخاب است — نه جسدی، نه ردی."""
        p = self._killer(uid)
        if ROLES[p.role].ability != "kill":
            raise RuleError("تصمیمِ قتل با نقشِ قاتل است.")
        self.s.night_actions.pop(f"kill:{uid}", None)
        self.s.night_actions[f"_skip:{uid}"] = 1
        return "🚫 امشب کسی را نمی‌کشی. سکوت هم یک حرکت است."

    def plant_print(self, uid: int, target: int) -> str:
        """اثر انگشت جعلی: مدرکِ فردا به این نفر اشاره می‌کند و کارآگاه «مشکوک» می‌بیند."""
        self._killer(uid)
        t = self.s.players.get(target)
        if not t or not t.in_game or target == uid:
            raise RuleError("هدف نامعتبر است.")
        self.s.night_actions[f"plant:{uid}"] = target
        return f"🖐️ اثر انگشت جعلی روی {t.name} کاشته شد؛ فردا مدرک به او اشاره می‌کند."

    def plant_clue(self, uid: int, text: str) -> str:
        """سرنخ جعلی: صبح کنار سرنخ‌های واقعی خوانده می‌شود و از آن‌ها جدا نیست."""
        self._killer(uid)
        text = text.strip()[:120]
        if len(text) < 3:
            raise RuleError("متن سرنخ خیلی کوتاه است.")
        self.s.fake_clues.append(f"🕯️ {text}")
        return "🧾 سرنخ جعلی کاشته شد؛ فردا صبح میان سرنخ‌های واقعی خوانده می‌شود."

    def threaten(self, uid: int, target: int) -> str:
        """تهدید: هدف فقط می‌فهمد تهدید شده، نه اینکه از طرف کیست."""
        self._killer(uid)
        t = self.s.players.get(target)
        if not t or not t.in_game or target == uid:
            raise RuleError("هدف نامعتبر است.")
        t.stress += 20
        self.post(target,
                  "😈 *پیامی بی‌امضا به دستت رسید:*\n"
                  "«می‌دانم دیشب کجا بودی. فردا در گروه اسم مرا نیاور — "
                  "وگرنه شب بعد نوبت توست.»\n\n"
                  "_نمی‌دانی از طرف کیست. می‌توانی در گروه بگویی، یا نگویی._")
        return f"😈 تهدید برای {t.name} فرستاده شد — بدون نام تو."

    def offer_recruit(self, uid: int, target: int) -> str:
        """دعوت به همکاری: فقط «شهروند»ِ بی‌قدرت می‌تواند بپذیرد.

        هر کسی که نقش ویژه دارد هم پیام را می‌بیند — همین باعث می‌شود دعوت
        خودش یک سرنخ باشد و فرستادنش برای قاتل ریسک داشته باشد.
        """
        self._killer(uid)
        t = self.s.players.get(target)
        if not t or not t.in_game or target == uid:
            raise RuleError("هدف نامعتبر است.")
        if t.align is Align.KILLER:
            raise RuleError("او همین حالا هم هم‌تیمی توست.")
        if self.s.recruit_offer is not None:
            raise RuleError("یک دعوت در جریان است؛ اول جوابش بیاید.")
        self.s.recruit_offer = target
        body = ("🤝 *پیشنهادی در تاریکی:*\n"
                "«فرستنده‌ی این پیام قاتل است. با من باش تا تا آخر زنده بمانی.»\n")
        if t.role == "شهروند" and not t.recruited:
            self.post(target, body + "\nتو نقش ویژه‌ای نداری — *می‌توانی بپذیری یا رد کنی.*")
        else:
            self.post(target, body + "\n⚖️ تو نقشِ ویژه داری؛ *امکان پیوستن نداری.* "
                                     "ولی حالا می‌دانی قاتل سراغ تو آمده.")
        return f"🤝 دعوت برای {t.name} فرستاده شد."

    def answer_recruit(self, uid: int, accept: bool) -> str:
        if self.s.recruit_offer != uid:
            raise RuleError("دعوتی برای تو در جریان نیست.")
        p = self.s.players[uid]
        self.s.recruit_offer = None
        if not accept:
            return "🚪 دعوت را رد کردی. کسی خبردار نمی‌شود."
        if p.role != "شهروند" or p.recruited:
            raise RuleError("نقش تو اجازه‌ی پیوستن نمی‌دهد.")
        p.align = Align.KILLER
        p.recruited = True
        mates = [q.name for q in self.s.players.values()
                 if q.align is Align.KILLER and q.uid != uid]
        p.knows.append("🔪 به تیم قاتل پیوستی. هم‌تیمی: " + ("، ".join(mates) or "—"))
        for q in self.s.players.values():
            if q.align is Align.KILLER and q.uid != uid:
                self.post(q.uid, f"🤝 {p.name} دعوت را پذیرفت؛ حالا هم‌تیمی توست.")
        self.s.log.append("🕯️ شایعه‌ای در شهر: دیشب کسی طرف عوض کرد.")
        return "🔪 پذیرفتی. حالا با تیم قاتل می‌بری — ولی اکشن شبانه نداری."

    # ================= یادداشتِ سپرده به گروه =================
    def share_note(self, uid: int, text: str) -> str:
        """یادداشت در صندوق امانات می‌ماند و *فقط* وقتی این بازیکن به حبس موقت
        برود در گروه خوانده می‌شود — پس سپردنش یک شرط‌بندی است."""
        p = self.s.players[uid]
        if not p.in_game:
            raise RuleError("از بازی بیرونی.")
        p.shared_notes.append(text.strip()[:200])
        return ("📥 یادداشتت در صندوق امانات ماند.\n"
                "اگر به حبس موقت بروی، همان لحظه در گروه خوانده می‌شود.")

    def _publish_notes(self, p: Player) -> None:
        if p.notes_published or not p.shared_notes:
            return
        p.notes_published = True
        body = "\n".join(f"  • {n}" for n in p.shared_notes)
        self.post(0, f"📂 *صندوق امانات {p.name} باز شد:*\n{body}")
        self.s.log.append(f"📂 یادداشت‌های سپرده‌ی {p.name} علنی شد.")

    # ================= بازجو: حبس موقت یا هیئت منصفه =================
    def officer_refer_jury(self, officer_uid: int) -> str:
        """بعد از گفتگو با متهم، بازجو می‌تواند به‌جای حکم دادن پرونده را به
        هیئت منصفه بسپارد — مسیر دومِ هم‌ارزِ حکمِ خودش."""
        if officer_uid != self.s.officer_uid:
            raise RuleError("فقط بازجو می‌تواند پرونده را ارجاع دهد.")
        if self.s.suspect_uid is None:
            raise RuleError("کسی در بازجویی نیست.")
        t = self.s.players[self.s.suspect_uid]
        if t.custody_nights < self.interrogation_nights:
            raise RuleError("ارجاع بعد از گذشتن یک شب بازجویی ممکن است.")
        if t.jury_used:
            raise RuleError("برای این متهم قبلاً هیئت منصفه تشکیل شده.")
        self.s.phase_before_jury = self.s.phase
        self.s.phase = Phase.JURY
        self.s.jury_votes.clear()
        t.jury_used = True
        self.s.log.append(f"⚖️ بازجو پرونده‌ی {t.name} را به هیئت منصفه سپرد.")
        return f"⚖️ پرونده‌ی {t.name} به هیئت منصفه رفت؛ حالا شهر رای می‌دهد."

    def jury_state(self) -> str:
        """چرا دکمه‌ی هیئت منصفه الان کار می‌کند یا نمی‌کند — به زبان آدمیزاد."""
        if self.s.phase is Phase.JURY:
            return "هیئت منصفه باز است؛ رای بده: تبرئه یا ادامه‌ی بازجویی."
        sus = self.s.suspect_uid
        if sus is None:
            return "هنوز کسی در بازجویی نیست. اول با رای‌گیری یک متهم بفرستید."
        t = self.s.players[sus]
        if t.jury_used:
            return f"برای {t.name} یک بار هیئت منصفه تشکیل شده؛ حکم با بازجوست."
        if t.custody_nights < self.interrogation_nights:
            return (f"{t.name} همین حالا وارد بازجویی شد. بعد از «🌅 پایان شب» "
                    "می‌توانید هیئت منصفه بخواهید.")
        have = len(self.s.jury_requests.get(sus, set()))
        return (f"برای {t.name} {_fa(have)} درخواست ثبت شده؛ با "
                f"{_fa(JURY_MIN_REQUESTS)} درخواست (یا یک وکیل به‌تنهایی) تشکیل می‌شود.")

    # ================= تسلیم =================
    def surrender(self, uid: int) -> str:
        """بازیکن وسط بازی کنار می‌کشد.

        مثل مرگ عمل می‌کند نه مثل «خروج»: نقشش تا پایان فاش نمی‌شود، وگرنه
        هر کس می‌توانست با تسلیم شدن نقشش را به شهر اعلام کند. اکشنِ ثبت‌شده‌ی
        امشبش هم پاک می‌شود تا از آن سوءاستفاده نشود.
        """
        p = self.s.players.get(uid)
        if not p:
            raise RuleError("تو در این بازی نیستی.")
        if self.s.phase in (Phase.LOBBY, Phase.END):
            raise RuleError("بازی در جریان نیست؛ برای بیرون رفتن «🚪 خروج از لابی» را بزن.")
        if not p.in_game:
            raise RuleError("همین حالا هم از بازی بیرونی.")
        p.alive = False
        p.custody = Custody.FREE
        for k in [k for k in self.s.night_actions if k.endswith(f":{uid}")]:
            del self.s.night_actions[k]
        self.s.votes.pop(uid, None)
        self.s.jury_votes.pop(uid, None)
        if self.s.suspect_uid == uid:          # متهم رفت → اتاق بازجویی خالی شد
            self.s.suspect_uid = None
            if self.s.phase is Phase.INTERROGATION:
                self.s.phase = Phase.MORNING
        if uid == self.owner:                  # میزبانی به یک بازیکنِ زنده برسد
            nxt = next((q.uid for q in self.s.alive_players()), None)
            if nxt:
                self.owner = nxt
                self.s.log.append(f"👑 میزبانی به {self.s.players[nxt].name} رسید.")
        self.s.log.append(f"🏳️ {p.name} تسلیم شد و از بازی کنار کشید.")
        self.post(0, f"🏳️ *{p.name} تسلیم شد.*\nنقشش تا پایان بازی فاش نمی‌شود.")
        self._check_win()
        return "🏳️ تسلیم شدی. نقشت تا پایان بازی فاش نمی‌شود."

    # ================= چرخه‌ی دسترسیِ سرویس‌های محرمانه =================
    def _may_query(self, uid: int) -> Player:
        """اجازه‌ی یک *جستجوی تازه*. (خواندن بایگانیِ قبلی جدا حساب می‌شود.)

        قاعده‌ی hints.md §۱۲.۳: بازداشت دسترسی را معلق می‌کند؛ مرگ، حبس ابد
        و تسلیم آن را می‌گیرند؛ بازیِ متوقف هم جلوی جستجوی تازه را می‌گیرد.
        آنچه قبلاً تحویل داده شده هرگز پس گرفته نمی‌شود.
        """
        p = self.s.players.get(uid)
        if not p:
            raise RuleError("تو در این بازی نیستی.")
        if self.s.phase is Phase.LOBBY:
            raise RuleError("پس از شروع بازی و دریافت نقش فعال می‌شود.")
        if not p.alive or p.custody is Custody.LIFE_JAIL:
            raise RuleError("از بازی بیرون رفته‌ای؛ فقط بایگانیِ قبلی‌ات خواندنی است.")
        if p.custody in (Custody.INTERROGATION, Custody.TEMP_JAIL):
            raise RuleError("در بازداشتی؛ تا آزادی درخواست تازه‌ای ثبت نمی‌شود. "
                            "بایگانیِ قبلی‌ات باز است.")
        if self.s.paused:
            raise RuleError("بازی متوقف است؛ سهمیه‌ات دست‌نخورده می‌ماند.")
        return p

    # ================= پلاک خودرو =================
    # رنگ و مدل علنی است؛ پلاک فقط در پرونده‌ی پلیس. استعلامِ پلاک یک سرنخِ
    # قوی می‌دهد — به همین دلیل قاتل هم می‌تواند یک بار پلاک را جعل کند،
    # دقیقاً مثل اثر انگشت. هیچ سرنخی در این بازی غیرقابل‌دستکاری نیست.
    def plate_lookup(self, uid: int) -> str:
        """استعلام را ثبت می‌کند؛ نتیجه سحر می‌رسد، نه همین حالا.

        جوابِ فوری یعنی بازجو در یک شب پرونده را می‌بندد. تأخیرِ یک شب همان
        چیزی است که به قاتل فرصتِ جعل سند می‌دهد (hints.md §۱۲.۵).
        """
        # ترتیب مهم است: اول فاز/زنده‌بودن، بعد نقش. در لابی هنوز نقشی پخش
        # نشده و ROLES[""] با KeyError کل فرمان را می‌ترکاند.
        self._may_query(uid)
        p = self.s.players[uid]
        if not p.role or ROLES[p.role].info != "police_files":
            raise RuleError("استعلام پلاک فقط از پرونده‌ی پلیس ممکن است.")
        if self.s.plate_owner is None:
            raise RuleError("هنوز پلاکی ثبت نشده است.")
        if self.s.plate_query is not None:
            raise RuleError("یک استعلام در جریان است؛ نتیجه‌اش سحر می‌رسد.")
        if self.s.day in self.s.plate_nights:
            raise RuleError("امشب استعلامت را خرج کرده‌ای؛ شب بعد دوباره.")
        self.s.plate_query = uid
        self.s.plate_nights.append(self.s.day)
        if uid not in self.s.plate_lookups:
            self.s.plate_lookups.append(uid)
        return (f"🔎 استعلام پلاک `{self.s.case.vehicle['plate']}` ثبت شد.\n"
                "نتیجه سحرِ فردا به همین پیوی می‌رسد.")

    def _deliver_plate(self) -> None:
        """سحر: نتیجه‌ی استعلام دیشب.

        اگر استعلام‌کننده دیگر در بازی نیست، نتیجه تحویل *نمی‌شود* و کسی
        آن را ارث نمی‌برد (hints.md §۱۲.۳: «officer unavailable»).
        """
        uid = self.s.plate_query
        if uid is None:
            return
        self.s.plate_query = None
        p = self.s.players.get(uid)
        if not p or not p.in_game:
            self.s.log.append("🚗 استعلام پلاک بی‌تحویل ماند.")
            return
        owner = self.s.players.get(self.s.plate_owner)
        if owner is None:
            return
        p.notes.append(f"🚗 روز {_fa(self.s.day)}: مالک ثبت‌شده‌ی پلاک → {owner.name}")
        self.post(uid,
                  "🔎 *نتیجه‌ی استعلام پلاک* — پرونده‌ی انتظامی، محرمانه\n"
                  f"خودرو: {self.s.case.vehicle['model']} {self.s.case.vehicle['color']}\n"
                  f"شناسه‌ی پلاکِ ساختگیِ بازی: `{self.s.case.vehicle['plate']}`\n"
                  f"مالک ثبت‌شده در زمان واقعه: *{owner.name}*\n\n"
                  "⚠️ مالکیت، رانندگیِ آن شب را ثابت نمی‌کند؛ سند هم قابل جعل است. "
                  "این یک سرنخ است، نه حکم.")

    def swap_plate(self, uid: int, target: int) -> str:
        """قاتل یک بار در بازی سند خودرو را به نام دیگری می‌زند."""
        self._killer(uid)
        if self.s.plate_swapped:
            raise RuleError("یک بار پلاک را جعل کرده‌ای؛ بیش از این نمی‌شود.")
        t = self.s.players.get(target)
        if not t or not t.in_game:
            raise RuleError("هدف نامعتبر است.")
        self.s.plate_owner = target
        self.s.plate_swapped = True
        for u in self.s.plate_lookups:      # هر کس قبلاً استعلام گرفته، خبردار شود
            self.post(u, "🚗 *اصلاحیه‌ی راهنمایی و رانندگی:* سند خودروی پرونده "
                         "دوباره ثبت شده. استعلام قبلی‌ات دیگر معتبر نیست.")
        return f"🚗 سند خودرو به نام {t.name} خورد؛ استعلام پلاک حالا او را نشان می‌دهد."

    # ================= بایگانی اختصاصی هر نقش =================
    def archive(self, uid: int) -> Tuple[str, List[str]]:
        """داده‌ی اختصاصیِ هر نقش — همان چیزی که کارت نقش وعده می‌دهد.

        از وضعیت واقعیِ بازی ساخته می‌شود، پس هر روز تازه است. هیچ نقشی
        دستِ خالی برنمی‌گردد: حتی شهروند هم می‌فهمد دقیقاً چه چیزی ندارد.
        """
        p = self.s.players.get(uid)
        if not p:
            raise RuleError("تو در این بازی نیستی.")
        if not self.s.case:
            raise RuleError("بازی هنوز شروع نشده است.")
        # §۱۲.۳: بایگانی همیشه خواندنی است — حتی برای کشته و تسلیم‌شده —
        # ولی وقتی دسترسی معلق/گرفته شده، *داده‌ی زنده‌ی تازه* نمی‌آید.
        try:
            self._may_query(uid)
            frozen = ""
        except RuleError as e:
            frozen = f"🔒 {e}\n{'─' * 18}\n"
        kind = ROLES[p.role].info
        day, c = self.s.day, self.s.case
        L: List[str] = []

        if kind == "hospital":          # 💉 پزشک
            title = "🏥 *پرونده‌ی درمانگاه*"
            L.append(f"🛏️ سهمیه‌ی نجاتِ خودت: "
                     + ("سوخته ✔️" if p.self_save_used else "دستِ نخورده"))
            hurt = sorted((q for q in self.alive_in_game()), key=lambda q: -q.stress)[:3]
            L.append("📈 بالاترین فشار عصبی (از پذیرش‌های امروز):")
            L += [f"   • {q.name} — {self._stress_band(q)}" for q in hurt]
            dead = [q.name for q in self.s.players.values() if not q.alive]
            L.append("⚰️ فوتی‌ها: " + ("، ".join(dead) if dead else "—"))
            L.append(f"🧾 علت مرگ در پرونده: {c.weapon}")

        elif kind == "forensic_files":  # 🧪 پزشک قانونی / 🔬 کالبدشکاف
            title = "🔬 *گزارش کالبدشکافی*"
            L.append(f"🕰️ ساعت تقریبی مرگ: {self._death_hour()}")
            L.append(f"🔪 ابزار: {c.weapon}")
            L.append(f"📍 محل کشف: {c.place}")
            L.append(f"🧬 یافته: {c.twist}")
            fake = [e["code"] for e in c.evidence
                    if e["misleading"] and e["code"] in self.s.revealed_evidence]
            L.append("🎭 مدارکی که آزمایشگاه جعلی خواند: "
                     + ("، ".join(fake) if fake else "— هنوز هیچ —"))

        elif kind == "police_files":    # 🔦 بازجو
            title = "👮 *پرونده‌های پلیس*"
            L.append(f"🚗 پلاک خودروی صحنه: `{c.vehicle['plate']}`")
            L.append(f"   ({c.vehicle['model']} {c.vehicle['color']})")
            L.append("   «🚗 استعلام مالک» را بزن تا نام مالک ثبت‌شده بیاید.")
            L.append("")
            L.append("🗂️ سوابق کیفری:")
            for q in self.alive_in_game():
                L.append(f"   • {q.name} — {self._record_of(q)}")
            jailed = [q.name for q in self.s.players.values()
                      if q.custody is not Custody.FREE]
            L.append("🔒 بازداشتی‌ها: " + ("، ".join(jailed) if jailed else "—"))

        elif kind == "sightings":       # 🕵️ کارآگاه
            title = "🕵️ *دفتر مشاهدات*"
            L.append(f"🚗 خودروی نزدیک صحنه: *{c.vehicle['model']} {c.vehicle['color']}*")
            L.append("   پلاک در پرونده‌ی پلیس است، نه دست تو.")
            checked = [n for n in p.notes if n.startswith("شب")]
            L.append("🔎 استعلام‌های خودت:")
            L += [f"   • {n}" for n in checked] or ["   — هنوز هیچ —"]

        elif kind == "visit_log":       # 🛡️ نگهبان
            title = "🛡️ *دفتر نگهبانی*"
            L += [f"   • {n}" for n in p.notes if n.startswith("🛡️")] or \
                 ["   — هنوز شبی را زیر نظر نگرفته‌ای —"]
            L.append("👥 هم‌مکانی‌هایی که دیده‌ای:")
            L += [f"   • {n}" for n in p.notes if n.startswith("👥")] or ["   —"]

        elif kind == "press_archive":   # 📰 خبرنگار
            title = "📰 *بایگانی تحریریه*"
            L.append("🗞️ مدارکی که تا امروز رو شده:")
            L += [f"   • {e['code']} — {e['title']}" for e in c.evidence
                  if e["code"] in self.s.revealed_evidence] or ["   —"]
            L.append("🔔 با «🌙 اکشن شبانه» یک مدرک اضافه برای کل شهر رو می‌کنی.")

        elif kind == "court_records":   # ⚖️ وکیل
            title = "⚖️ *دفتر ثبت دادگاه*"
            for q in self.s.players.values():
                mark = ("تبرئه‌شده" if q.cleared else
                        q.custody.value if q.custody is not Custody.FREE else "بی‌سابقه")
                L.append(f"   • {q.name} — {mark}"
                         + (" (یک‌بار هیئت منصفه داشته)" if q.jury_used else ""))
            L.append("")
            L.append("🔑 امتیاز تو: به‌تنهایی می‌توانی هیئت منصفه بخواهی.")

        elif kind == "police_radio":    # 📞 خبرچین
            title = "📞 *بی‌سیم پلیس*"
            L += [f"   • {n}" for n in p.notes if n.startswith("📞")] or \
                 ["   — هنوز چیزی نشنیده‌ای —"]
            sus = self.s.suspect_uid
            L.append("🔦 همین حالا در اتاق بازجویی: "
                     + (self.s.players[sus].name if sus else "کسی نیست"))

        elif kind == "rumor":           # 🏪 بقال محله
            title = "🏪 *شایعه‌های امروز*"
            L.append(self.daily_rumor())
            L.append("_۷۰٪ شایعه‌ها درست‌اند؛ ۳۰٪ نه. کدام کدام است، معلوم نیست._")

        elif kind == "team_ids":        # 🔪 تیم قاتل
            title = "🔪 *پرونده‌ی تیم*"
            L += [f"   • {k}" for k in p.knows] or ["   • تنها هستی."]
            L.append(f"🚗 خودروی صحنه: {c.vehicle['model']} {c.vehicle['color']}")
            L.append("   پلیس پلاکش را دارد — می‌توانی یک بار سند را به نام دیگری بزنی.")

        else:                           # شهروند / سپر بلا / شکارچی / جانی / قاچاقچی
            title = "🗂️ *بایگانی تو*"
            L.append("این نقش پرونده‌ی اختصاصی ندارد — و همین خودش اطلاعات است:")
            L.append("هر کس ادعا کند گزارشِ محرمانه دارد، یا نقشش را لو می‌دهد یا دروغ می‌گوید.")
            L.append("")
            L.append("📓 چیزی که *داری*: یادداشت‌های خودت و هرچه در گروه شنیده‌ای.")
            if p.knows:
                L += [f"   • {k}" for k in p.knows]

        L.append("")
        if frozen:
            # دسترسی معلق یا گرفته شده: همین‌ها آخرین چیزی است که رسیده.
            L.append(f"🧊 این نسخه در روز {_fa(day)} فریز شده؛ تازه نمی‌شود.")
            return title, [frozen.rstrip()] + L
        L.append(f"📅 روز {_fa(day)} — این پرونده هر روز تازه می‌شود.")
        L.append("_گزارش‌ها لحظه‌ی ثبت را می‌گویند، نه تضمینِ همین حالا را._")
        return title, L

    def alive_in_game(self) -> List[Player]:
        return [q for q in self.s.players.values() if q.in_game]

    def _stress_band(self, q: Player) -> str:
        s = dialogue.stress_of(q)
        return "آرام" if s < 35 else ("بی‌قرار" if s < 70 else "در آستانه‌ی فروپاشی")

    def _death_hour(self) -> str:
        tl = self.s.case.timeline
        return tl[2].split("—")[0].strip() if len(tl) > 2 else "۲۳:۱۵"

    def _record_of(self, q: Player) -> str:
        """سابقه‌ی کیفریِ ساختگی ولی قطعی — به نقش گره نخورده، پس لو نمی‌دهد."""
        recs = ["بی‌سابقه", "یک شکایت مالی", "نزاع خیابانی (مختومه)",
                "چک برگشتی", "بی‌سابقه", "تخلف رانندگی مکرر", "بی‌سابقه"]
        return recs[dialogue._h(q.uid, self.s.chat_id) % len(recs)]

    def daily_rumor(self) -> str:
        """شایعه‌ی تازه‌ی هر روز — ۷۰٪ درست، قطعی بر اساس روز."""
        rng = random.Random(self.s.chat_id * 7919 + self.s.day)
        alive = self.alive_in_game()
        if not alive or not self.s.case:
            return "امروز کسی حرفی نزد."
        true_one = rng.random() < 0.70
        killers = [q for q in alive if q.align is Align.KILLER]
        pool = killers if (true_one and killers) else alive
        who = rng.choice(pool)
        shapes = [
            f"«دیشب {who.name} را بیرون از خانه دیدند.»",
            f"«می‌گویند {who.name} با مقتول دعوا داشته.»",
            f"«{who.name} درباره‌ی {self.s.case.motive} چیزی می‌دانسته.»",
            f"«کسی {who.name} را نزدیک {self.s.case.place} دیده.»",
        ]
        return "🗣️ " + shapes[rng.randrange(len(shapes))]
