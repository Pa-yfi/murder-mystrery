"""مدل‌های پایه‌ی بازی «کارآگاه» — نسخه‌ی پیشرفته مافیا + معمای قتل."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Align(str, Enum):
    KILLER = "قاتل‌ها"      # تیم قاتل
    CITY = "شهر"            # تیم شهروند/کارآگاه
    NEUTRAL = "خنثی"        # نقش‌های بی‌طرف (سپر بلا / پوشش قاتل)


class Custody(str, Enum):
    FREE = "آزاد"
    INTERROGATION = "بازجویی"   # ۱ شب
    TEMP_JAIL = "حبس موقت"      # ۲ شب
    LIFE_JAIL = "حبس ابد"       # حذف از بازی، بدون افشای نقش


class Phase(str, Enum):
    LOBBY = "لابی"
    NIGHT = "شب"
    MORNING = "صبح"             # اعلام جنازه + مدرک روز
    DISCUSSION = "گفتگو"
    VOTE = "رای‌گیری"
    INTERROGATION = "اتاق بازجویی"
    JURY = "هیئت منصفه"
    COURT = "دادگاه نهایی"
    END = "پایان"


@dataclass
class Player:
    uid: int
    name: str
    role: str = ""
    align: Align = Align.CITY
    alive: bool = True
    custody: Custody = Custody.FREE
    custody_nights: int = 0
    cleared: bool = False          # بازجو بی‌گناهی‌اش را تایید کرده
    jury_used: bool = False
    stress: int = 0                # ۰..۱۰۰ — روی دیالوگ قانون‌محور اثر می‌گذارد
    trust: int = 50
    suspicion: int = 0
    secrets: List[str] = field(default_factory=list)
    knows: List[str] = field(default_factory=list)   # اطلاعات اختصاصی نقش
    notes: List[str] = field(default_factory=list)
    xp: int = 0
    coins: int = 0
    will: str = ""                              # ایده ۵: وصیت‌نامه
    private_notes: List[str] = field(default_factory=list)   # ایده ۹
    qa: Dict[str, str] = field(default_factory=dict)         # ایده ۱۳: تناقض‌یاب
    hunter_target: Optional[int] = None                      # ایده ۱۵: هدف شلیک آخر
    role_assigned: str = ""
    ready: bool = False            # بهبود ۲: پیویِ ربات را باز کرده و آماده است
    missed: int = 0                # بهبود ۷: شب‌هایی که هیچ اکشنی نداده
    self_save_used: bool = False   # پزشک: نجاتِ خود فقط یک بار در کل بازی
    shared_notes: List[str] = field(default_factory=list)  # یادداشتِ سپرده به گروه
    notes_published: bool = False  # بعد از حبس موقت، سپرده‌ها علنی شدند
    recruited: bool = False        # شهروندِ بی‌نقش که دعوت قاتل را پذیرفت
    appearance: Dict[str, str] = field(default_factory=dict)  # قد، هیکل، مو، نشانه، لباس
    stance: str = ""               # ژستِ نمایشیِ انتخابیِ خودش در اتاق بازجویی

    @property
    def in_game(self) -> bool:
        return self.alive and self.custody != Custody.LIFE_JAIL

    @property
    def can_speak(self) -> bool:
        return self.in_game and self.custody != Custody.TEMP_JAIL

    @property
    def can_vote(self) -> bool:
        return self.can_speak and self.custody != Custody.INTERROGATION


@dataclass
class Evidence:
    code: str
    title: str
    kind: str
    interpretations: List[str]
    points_to: Optional[int] = None    # uid واقعی (مخفی)
    misleading: bool = False


@dataclass
class Case:
    cid: int
    title: str
    victim: str
    place: str
    weapon: str
    motive: str
    timeline: List[str]
    evidence: List[Dict]
    twist: str
    difficulty: int
    vehicle: Dict = field(default_factory=dict)   # خودروی دیده‌شده نزدیک صحنه


@dataclass
class GameState:
    chat_id: int
    phase: Phase = Phase.LOBBY
    day: int = 0
    case: Optional[Case] = None
    players: Dict[int, Player] = field(default_factory=dict)
    votes: Dict[int, int] = field(default_factory=dict)          # voter -> target
    jury_votes: Dict[int, bool] = field(default_factory=dict)
    officer_uid: Optional[int] = None
    suspect_uid: Optional[int] = None       # کسی که در بازجویی است
    pending_jail: List[int] = field(default_factory=list)        # حبس موقتی‌ها
    revealed_evidence: List[str] = field(default_factory=list)
    log: List[str] = field(default_factory=list)
    night_actions: Dict[str, int] = field(default_factory=dict)
    winner: Optional[str] = None
    winner_uids: List[int] = field(default_factory=list)   # برنده‌ها، صریح
    jury_requests: Dict[int, set] = field(default_factory=dict)
    deadline: Optional[float] = None            # ایده ۱: تایمر فاز
    night_event: str = ""                       # ایده ۴: رویداد شبانه
    fate_pair: Optional[tuple] = None           # ایده ۸: زوج سرنوشت
    sos_used: bool = False                      # ایده ۶: رای اضطراری شهر
    sos_votes: Dict[int, set] = field(default_factory=dict)
    lab_queue: Dict[str, int] = field(default_factory=dict)  # ایده ۱۰: آزمایشگاه
    interp_votes: Dict[str, Dict[int, int]] = field(default_factory=dict)  # ایده ۱۱
    defense_text: str = ""                      # ایده ۲: آخرین دفاع
    vote_history: List[tuple] = field(default_factory=list)  # ایده ۱۶: دقت رای
    vote_anon: bool = True                      # ایده ۲۳
    mvp: Optional[int] = None                   # ایده ۱۷
    tie_break: bool = False                     # ایده ۲۰: مرگ ناگهانی
    _protect_prev: Optional[int] = None         # ایده ۱۱: هدف نجاتِ شب قبل
    poison_queue: Dict[int, int] = field(default_factory=dict)   # uid → روزِ مرگ با سم
    framed: Dict[int, int] = field(default_factory=dict)         # uid → روزِ پاپوش‌دوزی
    hidden: List[int] = field(default_factory=list)              # مخفی‌شده‌های قاچاقچی
    traces: List[str] = field(default_factory=list)   # بهبود ۵: ردِ برخاسته از اکشنِ واقعی
    outbox: List[tuple] = field(default_factory=list)  # (uid, متن) — uid=0 یعنی گروه
    fake_clues: List[str] = field(default_factory=list)     # سرنخ‌های کاشته‌ی قاتل
    day_hints: List[str] = field(default_factory=list)      # سرنخ تازه‌ی هر روز
    hints_from: int = 0                                     # سرنخ‌های همین صبح از این ایندکس
    recruit_offer: Optional[int] = None                     # کسی که دعوت قاتل را گرفته
    plate_owner: Optional[int] = None    # پلاک به نام چه کسی است (قابل جعل)
    plate_swapped: bool = False          # قاتل یک بار می‌تواند پلاک را عوض کند
    plate_lookups: List[int] = field(default_factory=list)   # چه کسانی استعلام گرفتند
    plate_queries: Dict[int, int] = field(default_factory=dict)  # uid → شبِ استعلام
    plate_nights: List[tuple] = field(default_factory=list)  # (uid، شب) سهمیه‌ی استعلام
    inspect_days: List[tuple] = field(default_factory=list)  # (uid، روز) استعلام ظاهر
    witness_of: Optional[int] = None    # شاهدِ دیشب چه کسی را دیده (مخفی)
    death_cause: Dict[int, str] = field(default_factory=dict)  # uid → علتِ واقعیِ مرگ
    last_report_night: int = 0            # آخرین شبی که واقعاً حل شد
    # ── پرونده‌ی بازداشت (rules.md v2 — R07/R05) ──
    episode: int = 0                      # شماره‌ی پرونده‌ی بازداشت جاری
    room_qa: List[tuple] = field(default_factory=list)   # (پرسش، پاسخِ واقعیِ آدم)
    room_pending_q: str = ""              # پرسشی که منتظر جواب آدم است
    room_closed: bool = False             # گفتگو بسته شد
    hint_ack: bool = False                # بازجو سرنخ پایانی را باز کرد
    jury_panel: List[int] = field(default_factory=list)  # دقیقاً دو داور
    jury_locked: bool = False             # ارجاع شد؛ بازجو دیگر برنمی‌گردد
    # R07.4: رای‌گیری عمومیِ آزادی، وقتی متهمِ *تازه‌ای* وارد اتاق می‌شود
    release_ballots: Dict[int, Dict[int, bool]] = field(default_factory=dict)
    release_done: List[tuple] = field(default_factory=list)  # (اپیزود، زندانی)
    win_reason: str = ""                              # بهبود ۶: چرا این تیم برد
    paused: bool = False                        # بهبود ۷: بازی موقتاً متوقف
    paused_left: Optional[int] = None            # ثانیه‌های باقی‌ماندهی فاز هنگام توقف
    phase_before_jury: Optional[Phase] = None    # بعد از هیئت منصفه به همین فاز برگرد
    finalized: bool = False                     # نتیجه یک‌بار ثبت شد؛ دوباره XP نده

    def alive_players(self) -> List[Player]:
        return [p for p in self.players.values() if p.in_game]

    def by_align(self, a: Align) -> List[Player]:
        return [p for p in self.alive_players() if p.align == a]
