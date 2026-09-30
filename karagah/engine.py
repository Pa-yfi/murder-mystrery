"""موتور بازی — حلقه‌ی کامل، بدون LLM. تمام قواعد قطعی و تست‌پذیر.

قواعد کامل (با منطقِ هر کدام) در RULES.md آمده؛ این فایل همان‌ها را اجرا می‌کند.
"""
from __future__ import annotations
import random
from typing import Dict, List, Optional, Tuple

from .models import Align, Custody, GameState, Phase, Player
from .roles import (ROLES, DEFAULT_SCENARIO, KILL_HEIRS, SURVIVORS,
                    composition, scenario_name, validate_composition)
from .cases import CASES
from . import dialogue
from . import clues as C
from .roles import scenario_rules
import math
import time as _time
from .config import (MIN_PLAYERS, MAX_PLAYERS, INTERROGATION_NIGHTS,
                     TEMP_JAIL_NIGHTS, JURY_ACQUIT_PERCENT, JURY_MIN_REQUESTS,
                     PHASE_SECONDS, MAX_DAYS, NIGHT_GRACE_SECONDS)

MIN_P, MAX_P = MIN_PLAYERS, MAX_PLAYERS

# توانایی‌هایی که «دست به بدن» هدف می‌زنند؛ بازداشتی (در اتاق بازجویی یا سلول) در امان است
REACH_ABILITIES = ("kill", "poison", "frame", "hide", "protect")
# توانایی‌هایی که روی خودِ بازیکن معنا ندارند
NO_SELF = ("kill", "poison", "frame", "investigate")
# «از دور نگاه کردن» ملاقات نیست و ردی نمی‌گذارد
NO_VISIT = ("investigate", "expose", "watch")
DAY_PHASES = (Phase.MORNING, Phase.DISCUSSION, Phase.VOTE)


def _fa(n) -> str:
    """عدد فارسی — متنِ قانون همیشه از روی همین کانفیگ ساخته شود."""
    return str(n).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


class RuleError(Exception):
    pass


# ناظرهای «درست پیش از حلِ شب» (داورِ playtest) — fn(game, committed_actions)
NIGHT_OBSERVERS: List = []


class Game:
    def __init__(self, chat_id: int, seed: int = 0, owner: int = 0, blitz: bool = False,
                 scenario: str = DEFAULT_SCENARIO):
        self.s = GameState(chat_id=chat_id)
        self.owner = owner
        self.blitz = blitz                        # ایده ۳: حالت سریع
        self.s.scenario = scenario
        d = 2 if blitz else 1
        self.interrogation_nights = max(1, INTERROGATION_NIGHTS // d)
        self.temp_jail_nights = max(1, TEMP_JAIL_NIGHTS // d)
        self.rng = random.Random(seed)
        self.last_event: Optional[Dict] = None    # آخرین پیشرویِ تایمر، برای ساخت پیامِ گروه

    @property
    def scenario(self) -> str:
        return getattr(self.s, "scenario", DEFAULT_SCENARIO)

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
        """اگر مهلت فاز گذشته باشد، خودکار جلو می‌برد. خروجی: توضیح اتفاق.
        جزئیات (برای ساختن همان پیامِ کاملِ دکمه‌ها) در self.last_event می‌ماند."""
        self.last_event = None
        if self.s.paused:                 # بازیِ متوقف هرگز خودکار جلو نمی‌رود
            return None
        if self.s.deadline is None or _time.time() < self.s.deadline:
            return None
        ph = self.s.phase
        if ph in (Phase.NIGHT, Phase.INTERROGATION):
            ev = self.advance_night()
            self.last_event = ev
            if ev["kind"] == "grace":
                return f"⏳ مهلت شب تمام شد، ولی هنوز همه تصمیم نگرفته‌اند — {ev['left']} ثانیه فرصتِ اضافه."
            return "⏰ شب به پایان رسید."
        if ph is Phase.DISCUSSION:
            self.open_vote()
            self.last_event = {"kind": "vote_open"}
            return "⏰ گفتگو تمام شد؛ رای‌گیری آغاز شد."
        if ph is Phase.VOTE:
            who = self.close_vote()
            self.last_event = {"kind": "vote_closed", "who": who}
            return "⏰ رای‌گیری بسته شد." + (f" متهم: {self.s.players[who].name}" if who else "")
        if ph is Phase.MORNING:
            if self.awaiting_verdict():
                sus = self.s.players[self.s.suspect_uid]
                if not sus.jury_used:
                    self._form_jury(auto=True)
                    self.last_event = {"kind": "jury_open", "auto": True}
                    return f"⏰ حکمی برای {sus.name} صادر نشد؛ هیئت منصفه تصمیم می‌گیرد."
                msg = self._jail_suspect("⏰ هیئت منصفه تبرئه نکرد و بازجو حکمی نداد")
                self.last_event = {"kind": "verdict", "msg": msg}
                return msg
            self.open_discussion()
            self.last_event = {"kind": "discussion"}
            return "⏰ صبح تمام شد؛ گفتگو آغاز شد."
        if ph is Phase.JURY:
            msg = self.close_jury()
            self.last_event = {"kind": "jury_closed", "msg": msg}
            return "⏰ " + msg
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

    def set_scenario(self, key: str) -> str:
        from .roles import SCENARIOS
        if self.s.phase is not Phase.LOBBY:
            raise RuleError("سناریو فقط پیش از شروع بازی عوض می‌شود.")
        if key not in SCENARIOS:
            raise RuleError("چنین سناریویی نداریم.")
        self.s.scenario = key
        return f"🎭 سناریوی این میز: {scenario_name(key)}"

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
        if self.s.phase is not Phase.LOBBY:
            raise RuleError("بازی قبلاً شروع شده.")
        n = len(self.s.players)
        scenario = getattr(self.s, "scenario", DEFAULT_SCENARIO)
        if not (MIN_P <= n <= MAX_P):
            raise RuleError(f"تعداد بازیکن باید بین {_fa(MIN_P)} تا {_fa(MAX_P)} باشد.")
        if not validate_composition(n, scenario):
            raise RuleError("ترکیب نقش نامعتبر است.")
        if not force:
            missing = self.not_ready()
            if missing:
                names = "، ".join(self.s.players[u].name for u in missing)
                raise RuleError(
                    f"این بازیکن‌ها هنوز پیوی ربات را باز نکرده‌اند: {names}\n"
                    "هر کدام دکمه‌ی «✅ آماده‌ام» را بزنند (نقش محرمانه آنجا می‌رود). "
                    "میزبان می‌تواند با «⚡ شروع بدون آن‌ها» بی‌آن‌ها شروع کند.")
        from .scenes import CASE_POOL, pack
        pool = CASE_POOL[pack(scenario)]                 # پرونده‌ای که با فضای سناریو بخواند
        self.s.case = CASES[(case_id - 1) if case_id else self.rng.choice(pool) - 1]
        self.s.scene_log, self.s.scene_today = {}, {}
        self.s.day = 0                                   # سرنخ‌های اولِ پرونده مالِ «روز ۰» اند
        from .roles import assign_with_cooldown
        uids = list(self.s.players)
        mapping = assign_with_cooldown(uids, n, self.rng, getattr(self, "last_roles", {}), scenario)
        for p in self.s.players.values():
            p.role_assigned = mapping[p.uid]
            p.custody, p.custody_nights, p.alive = Custody.FREE, 0, True   # لابی هیچ اثری به بازی نمی‌برد
        for p, rname in ((self.s.players[u], mapping[u]) for u in uids):
            rd = ROLES[rname]
            p.role, p.align = rname, rd.align
            p.secrets = [f"راز: {self.s.case.twist}"]
        # پرونده‌ی ظاهریِ عمومیِ هر بازیکن (سرنخ‌ها به همین‌ها اشاره می‌کنند)
        for u, t in C.assign_traits(uids, self.rng, scenario).items():
            self.s.players[u].traits = t
        # اطلاعات اختصاصی هر نقش — همه‌ی اعضای تیم قاتل همدیگر را می‌شناسند (مثل مافیای استاندارد)
        killers = [p.uid for p in self.s.players.values() if p.align is Align.KILLER]
        boss = next(u for u in killers if self.s.players[u].role == "قاتل")
        for p in self.s.players.values():
            info = ROLES[p.role].info
            if p.align is Align.KILLER:
                p.knows = [f"هم‌تیمی: {self.s.players[u].name}" for u in killers if u != p.uid] or ["تنها هستی."]
                p.knows.append("🧤 سرنخ‌هایی که به تو اشاره کنند راست‌اند؛ با پاپوش و دروغ، شهر را به سمت دیگری ببر.")
            elif info == "forensic":
                p.knows = ["هر شب راست/دروغ بودنِ سرنخ‌های همان شب را خصوصی می‌فهمی."]
            elif info == "interrogation_hints":
                p.knows = ["تو بازجویی؛ حکم حبس موقت با توست."]
            elif info == "rumor":
                p.knows = [self._rumor(boss)]
            else:
                p.knows = []
        self.s.officer_uid = next(p.uid for p in self.s.players.values() if p.role == "بازجو")
        # ایده ۸: زوج سرنوشت — شکارچی بیرون می‌ماند تا زنجیره‌ی مرگ در یک شب از کنترل خارج نشود
        city = [p.uid for p in self.s.players.values()
                if p.align is Align.CITY and p.role != "شکارچی"]
        if len(city) >= 4 and len(self.s.players) >= 7:
            pair = tuple(self.rng.sample(city, 2))
            self.s.fate_pair = pair
            for u in pair:
                other = pair[1] if u == pair[0] else pair[0]
                self.s.players[u].knows.append(
                    f"🔗 سرنوشتت به {self.s.players[other].name} گره خورده؛ مرگ او مرگ توست.")
        # سرنخ‌های صحنه‌ی جرمِ پرونده: یکی/دو تا راست درباره‌ی قاتلِ واقعی، بقیه دروغ — به ترتیبِ تصادفی
        rules = scenario_rules(scenario)
        kinds = [True] * rules["start_true"] + [False] * rules["start_false"]
        self.rng.shuffle(kinds)
        for real in kinds:                               # مکان: صحنه‌ی اصلیِ پرونده (scenes.location_for)
            if real:
                C.true_clue(self.s, boss, self.rng, "case", "case")
            else:
                C.false_clue(self.s, boss, self.rng, "herring", "case",
                             avoid=[p.uid for p in self.s.players.values() if p.align is Align.KILLER])
        self.s.phase = Phase.NIGHT
        self.s.day = 1
        self._arm()
        self.s.log.append(f"پرونده #{self.s.case.cid}: {self.s.case.title} — سناریو {scenario_name(scenario)}")

    def _rumor(self, culprit: int) -> str:
        """بقال: یک مشخصه‌ی قاتل — ۷۰٪ درست."""
        rum = random.Random(self.s.chat_id * 7919 + self.s.day)
        k = rum.choice(list(self.s.players[culprit].traits))
        real = self.s.players[culprit].traits[k]
        v = real if rum.random() < 0.7 else rum.choice([x for x in C.TRAITS[k][2] if x != real])
        return f"🏪 شایعه‌ی روز {self.s.day}: می‌گویند {C.TRAITS[k][1]}ِ قاتل «{v}» است."

    # ---------------- توانایی‌ها ----------------
    def ability_of(self, p: Player) -> str:
        """توانایی شبانه‌ی مؤثر — جانشینِ قاتل «قتل» را به ارث می‌برد."""
        if not p.role:
            return ""
        if p.uid == getattr(self.s, "kill_heir", None) and p.in_game:
            return "kill"
        return ROLES[p.role].ability

    def _update_heir(self) -> None:
        """اگر قاتل از بازی بیرون رفته، چاقو به عضو بعدی تیم قاتل می‌رسد
        (همدست → سم‌ساز → خبرچین). جانشین و هم‌تیمی‌ها خصوصی خبردار می‌شوند؛
        برای شهر اعلام نمی‌شود چون حبس ابد نقش را فاش نمی‌کند."""
        s = self.s
        team = [p for p in s.players.values() if p.align is Align.KILLER and p.in_game]
        if any(ROLES[p.role].ability == "kill" for p in team):
            return
        cur = getattr(s, "kill_heir", None)
        if cur and s.players[cur].in_game:
            return
        order = sorted(team, key=lambda p: (KILL_HEIRS.index(p.role) if p.role in KILL_HEIRS else 9, p.uid))
        heir = order[0].uid if order else None
        if heir == cur:
            return
        s.kill_heir = heir
        if heir:
            h = s.players[heir]
            h.notes.append("🔪 قاتلِ تیم از بازی بیرون رفت؛ از امشب چاقو دست توست "
                           "(اکشن شبانه‌ات «قتل» شد).")
            for p in team:
                if p.uid != heir:
                    p.notes.append(f"🔪 چاقوی تیم حالا دست {h.name} است.")

    def check_night_action(self, uid: int, target: int) -> str:
        """قواعد اکشن شبانه در یک جا. خطا پرت می‌کند یا نام توانایی را می‌دهد.
        هم night_action و هم legal_targets از همین رد می‌شوند تا دکمه‌ها
        هیچ‌وقت با قواعد فرق نکنند."""
        s = self.s
        if s.phase not in (Phase.NIGHT, Phase.INTERROGATION):
            raise RuleError("الان شب نیست.")
        p = s.players.get(uid)
        if not p or not p.in_game:
            raise RuleError("تو از بازی خارج شده‌ای.")
        if p.custody in (Custody.INTERROGATION, Custody.TEMP_JAIL):
            raise RuleError("در بازداشتی؛ اکشن شبانه نداری.")
        ab = self.ability_of(p)
        if not ab or ab == "hunter":
            raise RuleError("نقش تو اکشن شبانه‌ی معمول ندارد.")
        t = s.players.get(target)
        if not t or not t.in_game:
            raise RuleError("هدف نامعتبر است.")
        if ab in NO_SELF and target == uid:
            raise RuleError("نمی‌توانی خودت را هدف بگیری.")
        if ab in REACH_ABILITIES and t.custody is not Custody.FREE:
            raise RuleError("این نفر در بازداشت است؛ امشب دست کسی به او نمی‌رسد.")
        if ab in ("kill", "poison", "frame") and p.align is Align.KILLER and t.align is Align.KILLER:
            raise RuleError("هم‌تیمی‌ات را نمی‌توانی هدف بگیری.")
        if ab == "protect":
            if target == uid and p.self_saved:
                raise RuleError("پزشک فقط یک بار در کل بازی می‌تواند خودش را نجات دهد.")
            if getattr(s, "_protect_prev", None) == target:
                raise RuleError("دو شب پیاپی نمی‌توانی یک نفر را نجات دهی.")
        if ab == "investigate":
            if getattr(s, "inv_prev", {}).get(uid) == target:
                raise RuleError("همین نفر را شب قبل استعلام کردی؛ کس دیگری را انتخاب کن.")
            if f"expose:{uid}" in s.night_actions:
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
        self.s.night_actions.pop(f"_pass:{uid}", None)  # «امشب کاری نمی‌کنم» را پس گرفت
        self.s.night_actions[f"{ab}:{uid}"] = target   # اکشن دوباره = ویرایش اکشن
        if ab == "protect":
            self.s.night_actions["_last_protect"] = target
        if ab == "investigate":
            self.s.night_actions[f"_inv_last:{uid}"] = target
            # نتیجه سحر می‌رسد. اگر همین‌جا جواب می‌دادیم، کارآگاه می‌توانست
            # هدف را پشت‌سرهم عوض کند و در یک شب همه را استعلام کند.
            return f"ثبت شد: {self.s.players[target].name} — نتیجه سحر به دفترچه‌ات می‌رسد."
        return "ثبت شد"

    def night_pass(self, uid: int) -> str:
        """«🙅 امشب کاری نمی‌کنم» — تصمیمِ آگاهانه؛ شب دیگر منتظرِ این نفر نمی‌ماند.
        اکشنِ ثبت‌شده‌ی امشبش (اگر بود) لغو می‌شود؛ تا سحر می‌تواند دوباره هدف بزند."""
        s = self.s
        if s.phase not in (Phase.NIGHT, Phase.INTERROGATION):
            raise RuleError("الان شب نیست.")
        p = s.players.get(uid)
        if not p or not p.in_game:
            raise RuleError("تو از بازی خارج شده‌ای.")
        if not p.free:
            raise RuleError("در بازداشتی؛ امشب اکشنی نداری.")
        if f"expose:{uid}" in s.night_actions:
            # نتیجه‌ی راستی‌آزمایی همان لحظه دیده شده؛ «پس گرفتن» یعنی دو اکشن در یک شب (راستی‌آزمایی + استعلام)
            raise RuleError("امشب با راستی‌آزماییِ سرنخ تصمیمت را گرفته‌ای و نتیجه‌اش را دیدی.")
        if self._officer_on_duty(uid):
            s.night_actions[f"_pass:{uid}"] = 1
            if self.ability_of(p) in ("", "hunter"):
                return "✅ بازجویی امشب تمام شد؛ حکم صبح با توست."
        if self.ability_of(p) in ("", "hunter"):
            raise RuleError("نقش تو اکشن شبانه ندارد؛ لازم نیست کاری بکنی.")
        for k in [k for k in s.night_actions if not k.startswith("_") and k.endswith(f":{uid}")]:
            del s.night_actions[k]
        if s.night_actions.get("_last_protect") is not None and self.ability_of(p) == "protect":
            s.night_actions.pop("_last_protect", None)
        s.night_actions[f"_pass:{uid}"] = 1
        return "🙅 ثبت شد: امشب کاری نمی‌کنی. تا سحر می‌توانی نظرت را عوض کنی."

    def _officer_on_duty(self, uid: int) -> bool:
        """شبِ بازجویی: بازجوی آزاد (که خودش متهم نیست) باید «✅ بازجویی تمام شد» بزند
        تا شب بسته شود — وگرنه آخرین نقش شب را پیش از اولین پرسش می‌بست."""
        s = self.s
        p = s.players.get(uid)
        return (s.phase is Phase.INTERROGATION and uid == s.officer_uid and p is not None
                and p.in_game and p.free and s.suspect_uid not in (None, uid))

    def passed(self, uid: int) -> bool:
        return f"_pass:{uid}" in self.s.night_actions

    def all_decided(self) -> bool:
        """شب: همه‌ی نقش‌های اکشن‌دار یا هدف زده‌اند یا گفته‌اند «کاری نمی‌کنم»."""
        return self.s.phase in (Phase.NIGHT, Phase.INTERROGATION) and not self.pending_actors()

    def advance_night(self, force: bool = False) -> Dict:
        """تنها راهِ بستنِ شب (دکمه‌ی سحر، تایمر، آخرین تصمیم). خروجی:
        {"kind": "dawn", "result": …} یا {"kind": "grace", "pending": […], "left": ثانیه}.
        قاعده: شب بسته نمی‌شود تا همه تصمیم بگیرند؛ اگر مهلت تمام شد، یک بار فرصتِ اضافه
        (و یادآوری به پیوی) داده می‌شود؛ بعد از آن، تصمیم‌نگرفته‌ها «کاری نکرد» حساب می‌شوند."""
        s = self.s
        if s.phase not in (Phase.NIGHT, Phase.INTERROGATION):
            raise RuleError("الان شب نیست.")
        pending = self.pending_actors()
        if pending and force:                      # فقط سیستم/آزمون (uid=0): بی‌انتظار
            for u in pending:
                s.night_actions[f"_pass:{u}"] = 0
            pending = []
        if pending:
            left = self.remaining() or 0
            if left > 0 or s.paused:
                raise RuleError(f"⏳ هنوز همه‌ی نقش‌های شبانه تصمیم نگرفته‌اند؛ {left} ثانیه تا پایان مهلت.")
            if getattr(s, "grace_day", -1) != s.day and NIGHT_GRACE_SECONDS > 0:
                s.grace_day = s.day
                sec = NIGHT_GRACE_SECONDS // 2 if self.blitz else NIGHT_GRACE_SECONDS
                s.deadline = _time.time() + sec
                s.log.append("⏳ مهلت شب تمام شد ولی هنوز کسی تصمیم نگرفته؛ فرصتِ اضافه.")
                return {"kind": "grace", "pending": pending, "left": sec}
            for u in pending:                      # فرصت هم تمام شد: «کاری نکرد»
                s.night_actions[f"_pass:{u}"] = 0
        return {"kind": "dawn", "result": self.resolve_night()}

    def pending_actors(self) -> List[int]:
        """چه کسانی هنوز کاری که این فاز از آن‌ها می‌خواهد انجام نداده‌اند."""
        if self.s.phase in (Phase.NIGHT, Phase.INTERROGATION):
            acted = {a for pairs in self._committed_actions().values() for a in pairs}
            acted |= {int(k.split(":", 1)[1]) for k in self.s.night_actions if k.startswith("_pass:")}
            # کسی که امشب هیچ هدفِ مجازی ندارد (بقیه بازداشت‌اند/هم‌تیمی‌اند) منتظرش نمی‌مانیم
            out = [p.uid for p in self.s.alive_players()
                   if p.free and self.ability_of(p) not in ("", "hunter")
                   and p.uid not in acted and self.legal_targets(p.uid)]
            off = self.s.officer_uid
            if off is not None and self._officer_on_duty(off) and f"_pass:{off}" not in self.s.night_actions \
                    and off not in out:
                out.append(off)                  # بازجو هنوز «بازجویی تمام شد» نزده
            return out
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
            return ("نقش‌های شبانه هدف بزنند یا «🙅 کاری نمی‌کنم»؛ وقتی همه تصمیم گرفتند، "
                    "صبح خودکار می‌رسد")
        if ph is Phase.MORNING:
            if self.awaiting_verdict():
                sus = self.s.players[self.s.suspect_uid].name
                if self.officer_can_judge():
                    return f"بازجو درباره‌ی {sus} حکم بدهد، یا ⚖️ هیئت منصفه"
                return f"بازجو نمی‌تواند حکم بدهد؛ ⚖️ هیئت منصفه درباره‌ی {sus} تصمیم می‌گیرد"
            return "«💬 گفتگو» را باز کنید"
        if ph is Phase.DISCUSSION:
            return "بحث کنید، بعد «🗳️ رای‌گیری»"
        if ph is Phase.VOTE:
            if self.s.tie_break:
                names = "، ".join(self.s.players[u].name for u in self.s.tie_leaders)
                return f"⚔️ دور دوم رای فقط بین: {names}"
            return "رای بدهید (یا ممتنع)، بعد «📊 بستن رای‌گیری»"
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
            if ab in NO_VISIT:
                continue
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

    def _deliver_night_info(self, acts: Dict[str, Dict[int, int]], night_suspect: Optional[int]) -> None:
        """اطلاعات اختصاصی نقش‌ها — سحر، یک‌بار، در دفترچه‌ی خودِ بازیکن."""
        day = self.s.day
        visits: Dict[int, int] = {}
        for ab, pairs in acts.items():
            if ab in NO_VISIT:
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
            who = self.s.players[night_suspect].name if night_suspect else "کسی"
            p.notes.append(f"📞 شب {day}: بازجو سراغ {who} رفته بود.")

        new = [c for c in self.s.clues if c["day"] == day and c["source"] != "case"]
        for actor in acts.get("autopsy", {}):   # پزشک قانونی: راست/دروغِ سرنخ‌های امشب
            p = self.s.players[actor]
            if new:
                verdicts = "، ".join(f"{c['code']} {'✅ راست' if c['genuine'] else '❌ دروغ'}" for c in new)
                p.notes.append(f"🧪 شب {day}: {verdicts}")
            else:
                p.notes.append(f"🧪 شب {day}: امشب سرنخی از صحنه‌ها جمع نشد.")

        for actor, tgt in acts.get("watch", {}).items():   # نگهبان: یک مشخصه‌ی یکی از ملاقات‌کننده‌ها
            if tgt in self.s.hidden:
                continue
            who = [a for ab, pairs in acts.items() if ab not in NO_VISIT
                   for a, t in pairs.items() if t == tgt]
            if who:
                v = self.s.players[random.Random(day * 131 + actor).choice(who)]
                k = random.Random(day * 17 + actor).choice(list(v.traits))
                self.s.players[actor].notes.append(
                    f"🛡️ یکی از ملاقات‌کننده‌های {self.s.players[tgt].name}: {C.TRAITS[k][1]} = {v.traits[k]}")

        # بقال محله: هر صبح یک شایعه درباره‌ی مشخصه‌ی قاتلِ فعلی (۷۰٪ درست)
        knife = self._knife_holder()
        for g in [p for p in self.s.alive_players() if p.role == "بقال محله"]:
            if knife is not None:
                g.notes.append(self._rumor(knife))

        for tgt, until in list(self.s.framed.items()):
            if until < day:
                del self.s.framed[tgt]

    def _eliminate(self, uids: List[int]) -> List[int]:
        """مرگ + زنجیره‌هایش (زوج سرنوشت، شلیک آخر شکارچی). فهرست همه‌ی مرده‌ها."""
        out: List[int] = []
        queue = list(uids)
        while queue:
            u = queue.pop(0)
            p = self.s.players[u]
            if u in out or not p.in_game:
                continue
            p.alive = False
            out.append(u)
            if self.s.fate_pair and u in self.s.fate_pair:
                a, b = self.s.fate_pair
                queue.append(b if u == a else a)
            shot = self._hunter_shot(p)
            if shot is not None:
                queue.append(shot)
        return out

    def _hunter_shot(self, p: Player) -> Optional[int]:
        """ایده ۱۵: شکارچی هنگام مرگ یا حبس ابد هدفِ از پیش تعیین‌شده‌اش را می‌برد."""
        if p.role != "شکارچی" or not p.hunter_target:
            return None
        t = self.s.players.get(p.hunter_target)
        if not t or not t.in_game:
            return None
        self.s.log.append(f"🏹 شلیک آخر {p.name}: {t.name} را با خود برد!")
        return t.uid

    def resolve_night(self) -> Dict:
        # فاز بازجویی هم یک شب است: متهم شب را در اتاق می‌گذراند
        # و بقیه اکشن شبانه‌شان را دارند.
        s = self.s
        if s.phase not in (Phase.NIGHT, Phase.INTERROGATION):
            raise RuleError("الان شب نیست.")
        night_suspect = s.suspect_uid
        for fn in list(NIGHT_OBSERVERS):
            fn(self, self._committed_actions())
        # ایده ۴: رویداد تصادفی شبانه (قطعی بر اساس seed+روز)
        ev_rng = random.Random(s.chat_id * 1000 + s.day)
        roll = ev_rng.random()
        r = scenario_rules(self.scenario)
        b1, b2, b3 = r["blackout"], r["blackout"] + r["storm"], r["blackout"] + r["storm"] + r["witness"]
        s.night_event = ("قطعی برق 🕯️" if roll < b1 else
                         "طوفان ⛈️" if roll < b2 else
                         "شاهد ناشناس 👁️" if roll < b3 else "")
        acts = self._committed_actions()
        # ترتیب شب (RULES.md): پنهان‌کاری → محافظت → پاپوش/سم → قتل → سمِ سررسیده → اطلاعات
        s.hidden = list(set(acts.get("hide", {}).values()))
        protected = set(acts.get("protect", {}).values())
        for doc, tgt in acts.get("protect", {}).items():
            if doc == tgt:
                s.players[doc].self_saved = True
        for who, tgt in acts.get("poison", {}).items():
            s.poison_queue.setdefault(tgt, s.day + 2)
            s.poison_by.setdefault(tgt, who)
        for tgt in acts.get("frame", {}).values():
            s.framed[tgt] = s.day + 1
        # حمله‌ی مستقیم امشب — طوفان فقط همین را لغو می‌کند؛ بازداشتی در امان است
        attacked: List[int] = []
        for tgt in acts.get("kill", {}).values():
            t = s.players[tgt]
            if tgt not in protected and tgt not in attacked and t.free:
                attacked.append(tgt)
        if s.night_event.startswith("طوفان") and attacked:
            s.log.append("⛈️ طوفان راه‌ها را بست؛ حمله‌ی امشب ناکام ماند.")
            attacked = []
        storm = s.night_event.startswith("طوفان")
        poisoned: List[int] = []
        # سمِ سررسیده ربطی به طوفان ندارد: دو شب پیش خورده شده.
        for tgt, due in list(s.poison_queue.items()):
            if due > s.day:
                continue
            del s.poison_queue[tgt]
            if tgt in protected:
                s.log.append(f"💉 پادزهر به موقع رسید: {s.players[tgt].name} نجات یافت.")
            elif s.players[tgt].in_game and tgt not in attacked:
                attacked.append(tgt)
                poisoned.append(tgt)
                s.log.append(f"☠️ {s.players[tgt].name} بر اثر سم از پا درآمد.")
        killed = self._eliminate(attacked)
        new_clues = self._make_clues(acts, killed, poisoned)
        # نسخه ۶: گشتِ صبحگاهی — هر مکانی که قبلاً سرنخ داشته امروز یک جزئیاتِ تازه نشان می‌دهد
        from . import scenes
        patrol = [] if s.night_event.startswith("قطعی برق") else \
            scenes.patrol(s, random.Random(s.chat_id * 53 + s.day))
        # ایده ۵: وصیت‌نامه‌ی کشته‌ها + ایده ۷: گزارش کالبدشکاف
        for uid in killed:
            w = s.players[uid].will
            if w:
                s.log.append(f"📜 وصیت {s.players[uid].name}: «{w}»")
        coroners = [p for p in s.players.values() if p.role == "کالبدشکاف" and p.in_game]
        for victim, (method, culprit) in self._death_causes(acts, killed, poisoned).items():
            for p in coroners:
                line = f"🔬 شب {s.day}: {s.players[victim].name} — {method}"
                if culprit is not None:
                    k = random.Random(s.day * 97 + victim).choice(list(s.players[culprit].traits))
                    line += f"؛ ضارب: {C.TRAITS[k][1]} = {s.players[culprit].traits[k]}"
                p.notes.append(line)
        # ایده ۱۰: نتیجه‌ی آزمایشگاه — واقعاً می‌گوید سرنخ راست است یا دروغ (برای همه)
        ready = [c for c, d in s.lab_queue.items() if d <= s.day]
        for code in ready:
            del s.lab_queue[code]
            c = next((x for x in s.clues if x["code"] == code), None)
            if c:
                c["verified"] = c["genuine"]
                s.log.append(f"🧪 نتیجه‌ی آزمایشگاه: سرنخ {code} "
                             + ("✅ راست است." if c["genuine"] else "❌ دروغ/کاشته است."))
        # پیشروی بازداشت‌ها (حبس موقت → حبس ابد) و شلیک شکارچیِ حبس‌ابدی
        for uid in self._advance_custody():
            shot = self._hunter_shot(s.players[uid])
            if shot is not None:
                killed += self._eliminate([shot])
        # متهمی که شب (با سمِ قدیمی یا زنجیره‌ی مرگ) مُرد، دیگر پرونده‌ی باز ندارد
        if s.suspect_uid is not None and not s.players[s.suspect_uid].alive:
            dead = s.players[s.suspect_uid]
            dead.custody, dead.custody_nights = Custody.FREE, 0
            s.log.append(f"⚰️ {dead.name} پیش از صدور حکم درگذشت؛ پرونده‌ی بازجویی بسته شد.")
            s.suspect_uid = None
            s.questions.clear()
        s._protect_prev = s.night_actions.get("_last_protect")
        s.inv_prev = dict(acts.get("investigate", {}))
        s.night_actions.clear()
        s.phase = Phase.MORNING
        # بهبود ۷: اکشنِ نداده پیش‌فرضش «هیچ‌کاری» است، ولی غیبت شمرده می‌شود.
        # فقط کسی که واقعاً می‌توانست اکشن بزند (آزاد، نه بازداشتی).
        acted = {a for pairs in acts.values() for a in pairs}
        for p in s.players.values():
            if p.free and self.ability_of(p) not in ("", "hunter"):
                p.missed = 0 if p.uid in acted else p.missed + 1
        afk = [p.name for p in s.alive_players() if p.missed >= 2]
        if afk:
            s.log.append("😴 چند شب بی‌حرکت: " + "، ".join(afk))
        self._build_traces(acts, killed)
        self._deliver_night_info(acts, night_suspect)
        self._update_heir()
        s.log.append(f"🌙 شب {s.day}: کشته‌ها — " + ("، ".join(s.players[u].name for u in killed) or "هیچ‌کس"))
        self._arm()
        self._check_win()
        # بازجو نمی‌تواند حکم بدهد (خودش متهم/زندانی/حذف است) → هیئت منصفه خودکار
        if s.phase is Phase.MORNING and self.awaiting_verdict() and not self.officer_can_judge():
            self._form_jury(auto=True)
        return {"killed": killed, "clues": new_clues, "patrol": patrol}

    def _knife_holder(self) -> Optional[int]:
        """قاتلِ فعلی تیم (قاتل یا جانشینش) — برای شایعه و سرنخ‌های دروغ."""
        for p in self.s.alive_players():
            if p.align is Align.KILLER and self.ability_of(p) == "kill":
                return p.uid
        k = [p.uid for p in self.s.alive_players() if p.align is Align.KILLER]
        return k[0] if k else None

    def _death_causes(self, acts, killed, poisoned) -> Dict[int, tuple]:
        """قربانی → (روش، ضارب) برای کالبدشکاف."""
        out: Dict[int, tuple] = {}
        for actor, tgt in acts.get("kill", {}).items():
            if tgt in killed and tgt not in out:
                sk = self.s.players[actor].role == "جانی سریالی"
                out[tgt] = ("زخم‌های متعدد و بی‌نظم (جانی سریالی)" if sk else "یک ضربه‌ی دقیقِ چاقو (تیم قاتل)",
                            actor)
        for tgt in poisoned:
            out[tgt] = ("سم؛ بوی بادام تلخ (سم‌ساز)", self.s.poison_by.get(tgt))
        for u in killed:
            out.setdefault(u, ("مرگِ همراه (زوج سرنوشت / شلیک شکارچی)", None))
        return out

    def _make_clues(self, acts, killed, poisoned) -> List[dict]:
        """سرنخ‌های امشب از روی کارِ واقعیِ بازیکن‌ها (RULES.md «سرنخ‌ها»):
        جنایتِ واقعی → سرنخ راست از مجرم؛ پاپوش → سرنخ دروغ با مشخصاتِ بی‌گناه؛
        ردِ گمراه‌کننده → سرنخ دروغ؛ شاهد → سرنخ راستِ اضافه؛ قطعی برق → هیچ سرنخی."""
        s = self.s
        rng = random.Random(s.chat_id * 31 + s.day * 7 + len(s.clues))
        if s.night_event.startswith("قطعی برق"):
            s.log.append("🕯️ برق رفت؛ صحنه‌ها تاریک ماند و امشب هیچ سرنخی جمع نشد.")
            return []
        # هر spec: (نوع، مجرم، منبع/پاپوش‌خورده، کلیدِ صحنه، یادداشت)
        # کلیدِ صحنه = قربانی: سرنخ‌های یک قتل (و پاپوش/ردِ گمراه‌کننده‌ی همان شب) در یک مکان پیدا می‌شوند،
        # تا از روی «کجا پیدا شد» نشود راست را از کاشته جدا کرد.
        specs = []
        attackers = []
        scenes_ = []                              # (کلید، یادداشت) صحنه‌های واقعیِ امشب
        for actor, tgt in acts.get("kill", {}).items():
            src = "sk" if s.players[actor].role == "جانی سریالی" else "kill"
            if actor in s.hidden:                 # قاچاقچی ردِ ضارب را پاک کرده
                continue
            name = s.players[tgt].name
            if tgt in killed:
                note = f"(کنارِ جسدِ {name})"
                specs.append(("true", actor, src, f"v{tgt}", note))
                attackers.append(actor)
                scenes_.append((f"v{tgt}", note))
            elif rng.random() < 0.5:
                note = f"(ردِ حمله‌ی ناکام به {name})"
                specs.append(("true", actor, src, f"v{tgt}", note))
                attackers.append(actor)
                scenes_.append((f"v{tgt}", note))
        for tgt in poisoned:
            who = s.poison_by.get(tgt)
            if who is not None and who not in s.hidden:
                note = f"(لیوانِ {s.players[tgt].name}؛ بوی بادام تلخ)"
                specs.append(("true", who, "poison", f"v{tgt}", note))
                attackers.append(who)
                scenes_.append((f"v{tgt}", note))
        culprit = next((a for a in attackers if s.players[a].align is Align.KILLER), None) \
            or self._knife_holder()
        for acc, tgt in acts.get("frame", {}).items():
            key, note = rng.choice(scenes_) if scenes_ else ("frame", "")
            specs.append(("frame", culprit, tgt, key, note))
        # ردِ گمراه‌کننده فقط کنارِ یک صحنه‌ی واقعی (شب بی‌جنایت سرنخ دروغ هم نمی‌سازد)
        if attackers and rng.random() < scenario_rules(self.scenario)["herring"]:
            key, note = rng.choice(scenes_) if scenes_ else ("herring", "")
            specs.append(("false", culprit, None, key, note))
        if s.night_event.startswith("شاهد") and attackers:
            a = rng.choice(attackers)
            specs.append(("true", a, "witness", "witness", "(👁️ به گفته‌ی یک شاهد ناشناس)"))
        # هر سرنخِ دروغ باید با **همه‌ی** مجرم‌های امشب (حتی ضاربِ پنهان) و کلِ تیم قاتل ناجور باشد؛
        # وگرنه «دروغ» تصادفاً به یک مجرمِ واقعی اشاره می‌کرد
        guilty = set(acts.get("kill", {})) | set(acts.get("poison", {})) | set(attackers)
        guilty |= {s.poison_by[t] for t in poisoned if s.poison_by.get(t) is not None}
        guilty |= {p.uid for p in s.players.values() if p.align is Align.KILLER and p.in_game}
        rng.shuffle(specs)                        # ترتیبِ کدها چیزی درباره‌ی راستی لو ندهد
        made = []
        for sp in specs:
            if sp[0] == "true":
                made.append(C.true_clue(s, sp[1], rng, sp[2], sp[3], sp[4]))
            elif sp[0] == "frame":
                c = C.false_clue(s, sp[1], rng, "frame", sp[3], framed=sp[2], avoid=guilty, note=sp[4])
                if c:
                    made.append(c)
            else:
                c = C.false_clue(s, sp[1], rng, "herring", sp[3], avoid=guilty, note=sp[4])
                if c:
                    made.append(c)
        # خبرنگار: اگر مصاحبه‌شونده امشب هدف حمله بود، سرنخِ تاییدشده از ضارب؛ وگرنه شمارِ ملاقات‌ها
        for rep_uid, tgt in acts.get("reveal", {}).items():
            hitters = [a for ab in ("kill", "poison") for a, t in acts.get(ab, {}).items()
                       if t == tgt and a not in s.hidden]
            name = s.players[tgt].name
            if hitters:
                c = C.true_clue(s, rng.choice(hitters), rng, "reporter", f"v{tgt}",
                                f"(📰 گزارش خبرنگار از {name})")
                c["verified"] = True
                made.append(c)
            else:
                n = sum(1 for ab, pairs in acts.items() if ab not in NO_VISIT
                        for a, t in pairs.items() if t == tgt and a != rep_uid)
                s.log.append(f"📰 خبرنگار: دیشب {n} نفر (جز خودش) به {name} سر زدند.")
        return made

    def _advance_custody(self) -> List[int]:
        """یک شب بازداشت می‌گذرد. خروجی: کسانی که همین حالا حبس ابد گرفتند."""
        life: List[int] = []
        for p in self.s.players.values():
            if not p.alive:
                continue
            if p.custody is Custody.INTERROGATION:
                p.custody_nights += 1         # حکم را بازجو (یا هیئت منصفه) صبح می‌دهد
            elif p.custody is Custody.TEMP_JAIL:
                p.custody_nights += 1
                if p.custody_nights >= self.temp_jail_nights and not p.cleared:
                    p.custody = Custody.LIFE_JAIL
                    p.custody_nights = 0
                    if p.uid in self.s.pending_jail:
                        self.s.pending_jail.remove(p.uid)
                    if p.role == "سپر بلا":
                        self.s.goat_jailed_alive = True
                    self.s.log.append(f"⛓️ {p.name} حبس ابد گرفت (نقشش فاش نمی‌شود).")
                    life.append(p.uid)
        return life

    # ---------------- روز / رای ----------------
    def awaiting_verdict(self) -> bool:
        """متهمی هست که شبِ بازجویی را گذرانده و هنوز حکم نگرفته."""
        sus = self.s.suspect_uid
        if sus is None:
            return False
        p = self.s.players[sus]
        return p.alive and p.custody is Custody.INTERROGATION

    def officer_can_judge(self) -> bool:
        """بازجو فقط وقتی حکم می‌دهد که آزاد و در بازی باشد و خودش متهم نباشد."""
        o = self.s.players.get(self.s.officer_uid)
        return bool(o and o.free and o.uid != self.s.suspect_uid)

    def open_discussion(self) -> None:
        if self.s.phase is not Phase.MORNING:
            raise RuleError("فاز اشتباه است.")
        if self.awaiting_verdict():
            raise RuleError("اول تکلیف متهم روشن شود: حکم بازجو یا ⚖️ هیئت منصفه.")
        self.s.phase = Phase.DISCUSSION
        self._arm()

    def open_vote(self) -> None:
        if self.s.phase is not Phase.DISCUSSION:
            raise RuleError("فاز اشتباه است.")
        self.s.phase = Phase.VOTE
        self._arm()
        self.s.votes.clear()
        self.s.tie_break = False
        self.s.tie_leaders = []

    def vote(self, voter: int, target: int) -> None:
        """target=0 یعنی رای ممتنع (در شمارش نیست، ولی «رای داده» حساب می‌شود)."""
        s = self.s
        if s.phase is not Phase.VOTE:
            raise RuleError("الان رای‌گیری نیست.")
        v = s.players.get(voter)
        if not v or not v.can_vote:
            raise RuleError("حق رای نداری.")
        if target == 0:
            s.votes[voter] = 0
            return
        t = s.players.get(target)
        if not t or not t.can_speak:
            raise RuleError("هدف نامعتبر است.")
        if voter == target:
            raise RuleError("نمی‌توانی به خودت رای بدهی.")
        if s.tie_break and target not in s.tie_leaders:
            names = "، ".join(s.players[u].name for u in s.tie_leaders)
            raise RuleError(f"دور دوم (مرگ ناگهانی) فقط بین: {names}")
        s.votes[voter] = target               # رای دوباره = ویرایش رای

    def close_vote(self) -> Optional[int]:
        """بیشترین رای → بازجویی (مرحله‌ی اول). رای‌ها فقط همین‌جا (نهایی) در تاریخچه ثبت می‌شوند."""
        s = self.s
        if s.phase is not Phase.VOTE:
            raise RuleError("فاز اشتباه است.")
        real = {v: t for v, t in s.votes.items() if t}
        for v, t in real.items():
            s.vote_history.append((s.day, v, t))   # ایده ۱۶ — یک رای در هر دور، نه هر ویرایش
        if not real:
            return self._to_night()
        tally: Dict[int, int] = {}
        for t in real.values():
            tally[t] = tally.get(t, 0) + 1
        top = max(tally.values())
        leaders = [u for u, c in tally.items() if c == top]
        if len(leaders) != 1:            # ایده ۲۰: تساوی → مرگ ناگهانی
            if not s.tie_break:
                s.tie_break = True
                s.tie_leaders = leaders
                s.votes.clear()
                self._arm()                     # مهلت تازه؛ وگرنه تیکِ بعدی دور دوم را می‌بلعد
                s.log.append("⚔️ تساوی! مرگ ناگهانی بین: "
                             + "، ".join(s.players[u].name for u in leaders))
                return None                     # فاز رای باز می‌ماند برای دور دوم
            return self._to_night()
        s.tie_break = False
        s.tie_leaders = []
        uid = leaders[0]
        self.send_to_interrogation(uid)
        return uid

    def _to_night(self) -> None:
        self.s.tie_break = False
        self.s.tie_leaders = []
        self.s.phase = Phase.NIGHT
        self.s.day += 1
        self._arm()
        self._check_win()                       # سقف روز
        return None

    # ---------------- مرحله ۱: بازجویی ----------------
    def send_to_interrogation(self, uid: int) -> None:
        p = self.s.players[uid]
        if not p.can_speak:
            raise RuleError("این بازیکن قابل بازجویی نیست.")
        if self.awaiting_verdict() and self.s.suspect_uid != uid:
            raise RuleError("متهم قبلی هنوز حکم نگرفته است.")
        p.custody = Custody.INTERROGATION
        p.custody_nights = 0
        p.cleared = False
        p.stress += 20
        self.s.suspect_uid = uid
        self.s.questions.pop(uid, None)
        self.s.phase = Phase.INTERROGATION
        self.s.day += 1                 # شبِ بازجویی آغاز شد
        self._arm()
        self.s.log.append(f"🔦 {p.name} به بازجویی رفت (فاصله: ۱ شب).")

    def _officer(self, officer_uid: int, verb: str) -> Player:
        if officer_uid != self.s.officer_uid:
            raise RuleError(f"فقط بازجو {verb}.")
        if not self.officer_can_judge():
            raise RuleError("بازجو الان نمی‌تواند کار کند (خودش متهم، زندانی یا بیرون از بازی است)؛ "
                            "حکم با ⚖️ هیئت منصفه است.")
        return self.s.players[officer_uid]

    def officer_hints(self, officer_uid: int) -> List[str]:
        self._officer(officer_uid, "دسترسی دارد")
        if not self.awaiting_verdict():
            raise RuleError("کسی در بازجویی نیست.")
        return dialogue.interrogation_hints(self.s.players[self.s.suspect_uid], self.s.day)

    def ask(self, officer_uid: int, question: str) -> str:
        """پرسش واقعاً به متهم می‌رسد (لایه‌ی ربات آن را به پیوی متهم می‌فرستد)؛
        بازجو فوراً فقط «واکنش بدنی» متهم را می‌بیند و جواب را خودِ متهم می‌نویسد."""
        self._officer(officer_uid, "می‌تواند استنطاق کند")
        if not self.awaiting_verdict():
            raise RuleError("کسی در بازجویی نیست.")
        sus = self.s.players[self.s.suspect_uid]
        sus.stress += 5
        self.s.questions[sus.uid] = question[:200]
        tell = dialogue.interrogation_hints(sus, self.s.day + len(sus.qa) + len(question), n=1)[0]
        return f"📨 پرسش به متهم ({sus.name}) رسید؛ منتظر جوابش باش.\n👀 واکنش فوری: {tell}"

    def answer(self, uid: int, text: str) -> Tuple[str, bool]:
        """جواب متهم به آخرین پرسش. خروجی: (پرسش، تناقض با جوابِ قبلی به همین پرسش؟)"""
        if uid != self.s.suspect_uid:
            raise RuleError("فقط متهمِ داخل بازجویی جواب می‌دهد.")
        q = self.s.questions.pop(uid, None)
        if q is None:
            raise RuleError("پرسشی بی‌جواب برای تو نیست.")
        p = self.s.players[uid]
        prev = p.qa.get(q)
        p.qa[q] = text[:300]
        return q, prev is not None and prev.strip() != text.strip()

    def _jail_suspect(self, why: str) -> str:
        p = self.s.players[self.s.suspect_uid]
        p.custody = Custody.TEMP_JAIL
        p.custody_nights = 0
        self.s.pending_jail.append(p.uid)
        self.s.suspect_uid = None
        self.s.questions.clear()                 # پرسشِ بی‌جوابِ متهمِ قبلی دیگر معنایی ندارد
        self.s.defense_text = ""
        msg = (f"{why}: 🔒 {p.name} به حبس موقت رفت ({_fa(self.temp_jail_nights)} شب). آزادی‌اش فقط با "
               "تایید بی‌گناهی توسط بازجو، آن هم وقتی متهم جدیدی وارد بازجویی شده باشد.")
        self.s.log.append(msg)
        self.s.phase = Phase.MORNING
        self._arm()
        self._check_win()
        return msg

    def officer_verdict(self, officer_uid: int, confirm: bool) -> str:
        """confirm=True → حبس موقت (۲ شب). confirm=False → آزادی + تایید بی‌گناهی."""
        self._officer(officer_uid, "حکم می‌دهد")
        if not self.awaiting_verdict():
            raise RuleError("کسی در بازجویی نیست.")
        p = self.s.players[self.s.suspect_uid]
        if p.custody_nights < self.interrogation_nights:
            raise RuleError("حکم بعد از گذشتن یک شب بازجویی صادر می‌شود.")
        if self.s.phase is not Phase.MORNING:
            raise RuleError("حکم فقط صبح صادر می‌شود.")
        if confirm:
            return self._jail_suspect("⚖️ حکم بازجو")
        p.custody = Custody.FREE
        p.cleared = True
        p.stress = max(0, p.stress - 15)
        msg = f"🔓 {p.name} آزاد شد؛ بازجو بی‌گناهی‌اش را تایید کرد."
        self.s.suspect_uid = None
        self.s.questions.clear()                 # پرسشِ بی‌جوابِ متهمِ قبلی دیگر معنایی ندارد
        self.s.defense_text = ""
        self.s.log.append(msg)
        self._arm()
        self._check_win()
        return msg

    # ---------------- مرحله ۲: حبس موقت + آزادسازی مشروط ----------------
    def clear_previous(self, officer_uid: int, uid: int) -> str:
        """آزادی از حبس موقت: فقط وقتی یک متهم *جدید* داخل بازجویی است."""
        self._officer(officer_uid, "می‌تواند تایید کند")
        if self.s.suspect_uid is None:
            raise RuleError("برای آزادی حبس موقت، باید متهم جدیدی وارد بازجویی شده باشد.")
        if self.s.suspect_uid == uid:
            raise RuleError("متهم فعلی نمی‌تواند خودش را تبرئه کند.")
        p = self.s.players.get(uid)
        if not p or p.custody is not Custody.TEMP_JAIL or not p.alive:
            raise RuleError("این بازیکن در حبس موقت نیست.")
        p.custody = Custody.FREE
        p.cleared = True
        p.custody_nights = 0
        if uid in self.s.pending_jail:
            self.s.pending_jail.remove(uid)
        msg = f"🕊️ {p.name} از حبس موقت آزاد شد (تایید بی‌گناهی توسط بازجو)."
        self.s.log.append(msg)
        return msg

    # ---------------- هیئت منصفه ----------------
    def _form_jury(self, auto: bool) -> None:
        target = self.s.players[self.s.suspect_uid]
        self.s.phase_before_jury = Phase.MORNING
        self.s.phase = Phase.JURY
        self.s.jury_votes.clear()
        self.s.auto_jury = auto
        target.jury_used = True
        self._arm()
        self.s.log.append(f"⚖️ هیئت منصفه برای {target.name} تشکیل شد"
                          + (" (به‌جای بازجو)." if auto else "."))

    def request_jury(self, uid: int) -> bool:
        """بعد از یک شب در بازجویی، بازیکنان می‌توانند هیئت منصفه تشکیل دهند.
        وکیل به‌تنهایی کافی است؛ بقیه حداقل ۲ نفر."""
        sus = self.s.suspect_uid
        if sus is None or not self.awaiting_verdict():
            raise RuleError("کسی در بازجویی نیست.")
        asker = self.s.players.get(uid)
        if not asker or not asker.can_vote:
            raise RuleError("فقط بازیکنانِ آزاد و داخل بازی می‌توانند هیئت منصفه بخواهند.")
        target = self.s.players[sus]
        if target.custody_nights < self.interrogation_nights:
            raise RuleError("هیئت منصفه فقط بعد از یک شب بازجویی ممکن است.")
        if self.s.phase is not Phase.MORNING:
            raise RuleError("هیئت منصفه فقط صبح تشکیل می‌شود.")
        if target.jury_used:
            raise RuleError("برای این متهم قبلاً هیئت منصفه تشکیل شده.")
        req = self.s.jury_requests.setdefault(sus, set())
        req.add(uid)
        need = 1 if asker.role == "وکیل" else JURY_MIN_REQUESTS
        if len(req) >= need:
            self._form_jury(auto=False)
            return True
        return False

    def jury_vote(self, uid: int, acquit: bool) -> None:
        if self.s.phase is not Phase.JURY:
            raise RuleError("هیئت منصفه فعال نیست.")
        p = self.s.players.get(uid)
        if not p or not p.can_vote:
            raise RuleError("حق رای در هیئت منصفه نداری.")
        self.s.jury_votes[uid] = acquit

    def jury_percent(self) -> int:
        """درصدِ تبرئه طبق سناریو (دادگاه سخت‌گیرتر: ۵۰٪)؛ اگر در .env عوض شده، همان مقدار."""
        if JURY_ACQUIT_PERCENT != 60:
            return JURY_ACQUIT_PERCENT
        return int(scenario_rules(getattr(self.s, "scenario", "classic")).get("jury", JURY_ACQUIT_PERCENT))

    def close_jury(self) -> str:
        if self.s.phase is not Phase.JURY:
            raise RuleError("فاز اشتباه است.")
        p = self.s.players[self.s.suspect_uid]
        yes = sum(1 for v in self.s.jury_votes.values() if v)
        total = max(1, len(self.s.jury_votes))
        self.s.phase = Phase.MORNING
        self.s.phase_before_jury = None
        auto, self.s.auto_jury = self.s.auto_jury, False
        if yes * 100 >= self.jury_percent() * total:
            p.custody = Custody.FREE
            p.cleared = True
            p.custody_nights = 0
            self.s.suspect_uid = None
            self.s.questions.clear()
            self.s.defense_text = ""
            msg = f"⚖️ هیئت منصفه {p.name} را تبرئه کرد ({_fa(yes)}/{_fa(total)})."
            self.s.log.append(msg)
        elif auto or not self.officer_can_judge():
            # هیئت منصفه به‌جای بازجو نشسته بود؛ تبرئه نکردن یعنی حبس موقت
            msg = self._jail_suspect(f"⚖️ هیئت منصفه تبرئه نکرد ({_fa(yes)}/{_fa(total)})")
        else:
            msg = "⚖️ هیئت منصفه رای به ادامه‌ی بازجویی داد؛ حکم نهایی با بازجوست."
            self.s.log.append(msg)
        self._arm()
        self._check_win()
        return msg

    # ---------------- پایان ----------------
    def _check_win(self) -> Optional[str]:
        """شرط‌های برد (RULES.md بخش «برد»):
        ۱. سپر بلا زنده حبس ابد بگیرد → سپر بلا تنها برنده.
        ۲. هیچ‌کس در بازی نماند → بدون برنده.
        ۳. نه قاتل مانده نه جانی سریالی → شهر.
        ۴. جانی سریالی با حداکثر یک نفرِ دیگر مانده → جانی.
        ۵. جانی در بازی نیست و قاتل‌ها ≥ بقیه → قاتل‌ها (برابری).
        ۶. به سقف روز رسیدیم → بن‌بست، بدون برنده.
        بقال محله و قاچاقچی اگر تا آخر در بازی بمانند، کنار برنده می‌برند."""
        s = self.s
        if s.phase is Phase.END:
            return s.winner
        alive = s.alive_players()
        k = [p for p in alive if p.align is Align.KILLER]
        sk = [p for p in alive if p.role == "جانی سریالی"]
        goat = any(p.role == "سپر بلا" and p.custody is Custody.LIFE_JAIL and p.alive
                   for p in s.players.values())
        if goat:
            s.winner = "سپر بلا 🎭"
            s.win_reason = ("🎭 سپر بلا زنده حبس ابد گرفت — شرط بردش دقیقاً همین بود؛ "
                            "شهر گناه را گردن او انداخت.")
        elif not alive:
            s.winner = "بدون برنده 🤝"
            s.win_reason = "🤝 هیچ‌کس در بازی نماند."
        elif not k and not sk:
            s.winner = "شهر 🕵️"
            s.win_reason = ("🕵️ هیچ قاتلی (و هیچ جانی‌ای) در بازی نماند (کشته یا حبس ابد) — "
                            "شهر همه را پیدا کرد.")
        elif sk and len(alive) <= 2 and (not k or len(alive) == 2):
            s.winner = "جانی سریالی 🩸"    # ایده ۱۸: تنها بازمانده یا دوئل یک‌به‌یک
            s.win_reason = ("🩸 جانی سریالی تنها بازمانده شد — شرط بردش تنهایی بود."
                            if len(alive) == 1 else
                            "🩸 جانی سریالی با یک نفر تنها ماند؛ در دوئل یک‌به‌یک، شب او می‌کشد و روز رای "
                            "مساوی می‌شود — برنده اوست.")
        elif k and not sk and len(k) >= len(alive) - len(k):   # ایده ۴: برد قاتل با برابری
            s.winner = "قاتل‌ها 🔪"
            s.win_reason = (f"🔪 قاتل‌ها {len(k)} نفر ماندند و بقیه {len(alive) - len(k)} نفر — "
                            "وقتی قاتل‌ها کم‌تر نباشند دیگر رای شهر جلودارشان نیست.")
        elif s.day > MAX_DAYS:
            s.winner = "بدون برنده ⌛"
            s.win_reason = (f"⌛ بازی به سقف {_fa(MAX_DAYS)} روز رسید و هیچ تیمی شرط بردش را کامل نکرد "
                            "— بن‌بست.")
        if s.winner:
            s.phase = Phase.END
            s.deadline = None
            self._payout()
        return s.winner

    def is_winner(self, p: Player) -> bool:
        """یک منبع برای برد/باخت — امتیاز، آمار و گزارش پایان همه از همین می‌خوانند."""
        w = self.s.winner or ""
        if p.role in SURVIVORS and p.in_game and w:
            return True                      # بقال/قاچاقچی: زنده ماندن تا پایان
        if w.startswith("سپر"):
            return p.role == "سپر بلا"
        if w.startswith("جانی"):
            return p.role == "جانی سریالی"
        if w.startswith("شهر"):
            return p.align is Align.CITY
        if w.startswith("قاتل"):
            return p.align is Align.KILLER
        return False

    def _payout(self) -> None:
        for p in self.s.players.values():
            win = self.is_winner(p)
            p.xp += 120 if win else 40
            p.coins += 60 if win else 20
            p.xp += 10 * len([n for n in p.notes if n.startswith("شب")])
        killers = {q.uid for q in self.s.players.values() if q.align is Align.KILLER}
        for p in self.s.players.values():        # ایده ۱۶: پاداش دقت رای
            hits = sum(1 for _, v, t in self.s.vote_history if v == p.uid and t in killers)
            p.xp += 15 * hits
            # نسخه ۵: هر «باور/شک» درست درباره‌ی سرنخی که تکلیفش روشن شد +۵
            p.xp += 5 * sum(1 for c in self.s.clues if c["verified"] is not None
                            and c["votes"].get(p.uid) == int(c["genuine"]))
        self.s.mvp = max(self.s.players, key=lambda u: self.s.players[u].xp)   # ایده ۱۷

    def reveal(self) -> List[Tuple[str, str, str]]:
        if self.s.phase is not Phase.END:
            raise RuleError("تا پایان بازی، هیچ نقشی فاش نمی‌شود.")
        return [(p.name, p.role, p.custody.value) for p in self.s.players.values()]

    # ---------------- ایده ۲: آخرین دفاع ----------------
    def defense(self, uid: int, text: str) -> str:
        if uid != self.s.suspect_uid or not self.awaiting_verdict():
            raise RuleError("فقط متهمِ داخل بازجویی می‌تواند دفاع کند.")
        self.s.defense_text = text[:300]
        return f"🗣️ آخرین دفاع {self.s.players[uid].name}: «{self.s.defense_text}»"

    # ---------------- ایده ۵/۹ ----------------
    def set_will(self, uid: int, text: str) -> None:
        p = self.s.players[uid]
        if not p.alive:
            raise RuleError("وصیت را باید پیش از مرگ نوشت.")
        p.will = text[:200]

    def add_note(self, uid: int, text: str) -> None:
        self.s.players[uid].private_notes.append(text[:200])

    # ---------------- ایده ۶: رای اضطراری شهر ----------------
    def sos(self, uid: int, target: int) -> str:
        if self.s.phase not in DAY_PHASES:
            raise RuleError("رای اضطراری فقط در روز (صبح، گفتگو یا رای‌گیری) ممکن است.")
        if self.s.sos_used:
            raise RuleError("سلاح مخفی شهر فقط یک بار در بازی قابل استفاده است.")
        v, t = self.s.players.get(uid), self.s.players.get(target)
        if not v or not v.can_vote or not t or not t.free or uid == target:
            raise RuleError("رای اضطراری نامعتبر است (هدف باید آزاد و در بازی باشد).")
        sup = self.s.sos_votes.setdefault(target, set())
        sup.add(uid)
        need = math.ceil(0.8 * len([p for p in self.s.alive_players() if p.can_vote]))
        if len(sup) >= need:
            self.s.sos_used = True
            t.custody = Custody.TEMP_JAIL
            t.custody_nights = 0
            t.cleared = False
            self.s.pending_jail.append(t.uid)
            self.s.sos_votes.clear()
            self.s.log.append(f"🚨 رای اضطراری شهر: {t.name} مستقیم به حبس موقت رفت!")
            return f"🚨 تصویب شد! {t.name} مستقیم به حبس موقت رفت."
        return f"🚨 رای اضطراری علیه {t.name}: {len(sup)}/{need}"

    # ---------------- ایده ۱۰: آزمایشگاه با تاخیر ----------------
    def clue(self, code: str) -> dict:
        c = next((x for x in self.s.clues if x["code"] == code), None)
        if c is None:
            raise RuleError("کد سرنخ نامعتبر است.")
        return c

    def submit_lab(self, code: str, express: bool = False) -> str:
        """آزمایشگاه: روزی یک نمونه؛ نتیجه (راست/دروغ) برای همه اعلام می‌شود.
        express: با سکه، یک شب زودتر (حداقل همان سحر)."""
        if not self.s.case:
            raise RuleError("بازی هنوز شروع نشده؛ سرنخی وجود ندارد.")
        c = self.clue(code)
        if c["verified"] is not None:
            raise RuleError("این سرنخ قبلاً تایید/رد شده است.")
        if code in self.s.lab_queue:
            raise RuleError("این سرنخ در صف آزمایشگاه است.")
        if self.s.lab_day == self.s.day:
            raise RuleError("آزمایشگاه امروز یک نمونه گرفته؛ فردا دوباره.")
        nights = max(0 if express else 1, scenario_rules(self.scenario)["lab_nights"] - (1 if express else 0))
        self.s.lab_queue[code] = self.s.day + max(nights, 0)
        self.s.lab_day = self.s.day
        when = "همین سحر" if nights == 0 else f"{_fa(nights)} شب دیگر"
        return f"🧪 سرنخ {code} به آزمایشگاه رفت؛ نتیجه {when} برای همه اعلام می‌شود."

    # ---------------- ایده ۱۱: «باورش داری؟» ----------------
    def vote_interp(self, uid: int, code: str, idx: int) -> str:
        """idx=1 یعنی «راست است»، idx=0 یعنی «دروغ/کاشته است». وقتی سرنخ تایید شد، درست‌گوها XP می‌گیرند."""
        if idx not in (0, 1):
            raise RuleError("فقط 👍 یا 👎.")
        c = self.clue(code)
        if c["verified"] is not None:
            raise RuleError("این سرنخ تکلیفش روشن شده است.")
        c["votes"][uid] = idx
        yes = sum(1 for v in c["votes"].values() if v)
        return f"🗳️ {code}: 👍 {_fa(yes)} باور دارند · 👎 {_fa(len(c['votes']) - yes)} شک دارند"

    # ---------------- ایده ۱۲: راستی‌آزمایی سرنخ توسط کارآگاه ----------------
    def expose(self, uid: int, code: str) -> str:
        p = self.s.players.get(uid)
        if not p or p.role != "کارآگاه" or not p.free:
            raise RuleError("فقط کارآگاهِ آزاد می‌تواند سرنخ را راستی‌آزمایی کند.")
        if self.s.phase not in (Phase.NIGHT, Phase.INTERROGATION):
            raise RuleError("راستی‌آزمایی فقط در شب ممکن است.")
        if f"investigate:{uid}" in self.s.night_actions or f"expose:{uid}" in self.s.night_actions:
            raise RuleError("امشب اکشنت را خرج کرده‌ای.")
        c = self.clue(code)
        self.s.night_actions[f"expose:{uid}"] = 0
        res = "راست ✅" if c["genuine"] else "دروغ ❌"
        p.notes.append(f"شب {self.s.day}: سرنخ {code} → {res}")
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
            crown = " 🏆" if self.is_winner(p) else ""
            rows.append(f"  {rd.emoji} {p.name} — {p.role} ({rd.align.value}) — {fate}{crown}")

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
        co = [p.name for p in self.s.players.values()
              if p.role in SURVIVORS and self.is_winner(p)]
        co_line = f"\n🤝 کنار برنده (زنده ماندند): {'، '.join(co)}" if co else ""

        mvp = self.s.players[self.s.mvp].name if self.s.mvp else "—"
        from .theme import ribbon
        return (ribbon("🏁", f"پایان — برنده: {self.s.winner}") + f"\n{'─' * 18}\n"
                f"{self.s.win_reason}{co_line}\n{'─' * 18}\n"
                "🎭 *نقش‌ها:* (🏆 = برنده)\n" + "\n".join(rows) +
                f"\n{'─' * 18}\n{justice}\n{votes}\n⭐ MVP: {mvp}\n\n"
                + self.reconstruction())

    def set_hunter(self, uid: int, target: int) -> str:
        """ایده ۱۵: شکارچی هدف شلیک آخرش را از قبل مشخص می‌کند."""
        p = self.s.players.get(uid)
        if not p or p.role != "شکارچی":
            raise RuleError("فقط شکارچی می‌تواند هدف شلیک آخر بگذارد.")
        if not p.in_game:
            raise RuleError("تو دیگر در بازی نیستی.")
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
