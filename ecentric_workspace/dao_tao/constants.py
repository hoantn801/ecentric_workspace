# Copyright (c) 2026, eCentric and contributors
"""Hang so cua module Dao tao + Quiz truc tiep - KHONG import frappe.

Ma kieu cau hoi, ma pha cua phong, ma muc bao ve duoc ghi thang vao DB (JSON) va JS doc
lai: go sai o mot cho la mot kieu cau "khong ai nhan" - sua o DUNG MOT cho (day).
Thiet ke da chot: project doc `claude/dao-tao-ai.md` (Hoan, 07-12/11/2026).
"""

# --------------------------------------------------------------------------- DocType --
QUIZ = "EC Quiz"
SESSION = "EC Quiz Session"
PLAYER = "EC Quiz Player"
ANSWER = "EC Quiz Answer"
PROFILE = "EC Quiz Profile"
LESSON = "EC Training Lesson"
PROGRESS = "EC Training Progress"
TOPIC = "EC Training Topic"
VOTE = "EC Training Vote"
TICKET = "EC Training Ticket"
DRAW = "EC Training Draw"
DRAW_NUMBER = "EC Training Draw Number"

EMPLOYEE = "Employee"
DEPARTMENT = "Department"

# ------------------------------------------------------------------------------ Role --
#: "Ban dao tao". Hoan 12/11: chi Ban dao tao, team HR va Hoan duoc MO PHONG quiz / soan bai.
#: Patch chi tao role rong - ai vao Ban dao tao thi HR / admin gan.
ROLE_HOST = "EC Training Host"
#: Cac role duoc mo phong + soan bai hoc (team HR = HR Manager / HR User; Hoan = System Manager).
HOST_ROLES = (ROLE_HOST, "HR Manager", "HR User", "System Manager")
#: Xem + sua MOI bo quiz / phong (khong chi cua minh).
ADMIN_ROLES = ("System Manager",)

# ------------------------------------------------------------------------ Kieu cau hoi --
Q_SINGLE = "single"          # trac nghiem 1 dap an
Q_MULTI = "multi"            # chon nhieu
Q_TRUEFALSE = "truefalse"    # dung / sai
Q_SLIDER = "slider"          # thanh truot: dap an +- sai so du diem, lech xa hon duoc mot phan
Q_PIN = "pin"                # ghim tren anh / ban do: vung dung chu nhat hoac tron (toa do 0..1)
Q_ORDER = "order"            # sap xep
Q_MATCH = "match"            # ghep cap
Q_TYPE = "type"              # go dap an: nhieu cach viet, khong phan biet hoa thuong / dau cach
Q_POLL = "poll"              # binh chon - khong cham
Q_CLOUD = "cloud"            # dam may tu - khong cham
QUESTION_TYPES = (Q_SINGLE, Q_MULTI, Q_TRUEFALSE, Q_SLIDER, Q_PIN, Q_ORDER, Q_MATCH, Q_TYPE,
                  Q_POLL, Q_CLOUD)
OPTION_TYPES = (Q_SINGLE, Q_MULTI, Q_POLL)
UNSCORED_TYPES = (Q_POLL, Q_CLOUD)
#: Kieu co danh sach muc ma thu tu tren may phai XAO RIENG tung nguoi.
SHUFFLE_TYPES = (Q_SINGLE, Q_MULTI, Q_POLL, Q_ORDER, Q_MATCH)

PIN_RECT = "rect"
PIN_CIRCLE = "circle"

MEDIA_IMAGE = "image"
MEDIA_VIDEO = "video"
MEDIA_KINDS = (MEDIA_IMAGE, MEDIA_VIDEO)

# --------------------------------------------------------------------------- Gioi han --
MAX_QUESTIONS = 60
MAX_OPTIONS = 6
MIN_OPTIONS = 2
MAX_ORDER_ITEMS = 6
MAX_MATCH_PAIRS = 6
MAX_TYPE_ACCEPT = 10
MAX_TEXT = 240               # cau hoi
MAX_OPTION_TEXT = 90
MAX_EXPLAIN = 600
MAX_TYPE_ANSWER = 60
MAX_CLOUD_ANSWER = 30
TIME_CHOICES = (5, 10, 20, 30, 45, 60, 90, 120)
TIME_DEFAULT = 20
NICK_MAX = 16
NICK_MIN = 2
MAX_PLAYERS = 300
MAX_PRIZES = 12

# ------------------------------------------------------------------------- Cham diem --
#: Diem theo toc do (Hoan chot): tra loi ngay = 1.000, het gio = 500.
POINTS_MAX = 1000
POINTS_MIN = 500
STREAK_BONUS = 100           # moi cau dung lien tiep tu cau thu 2: +100
STREAK_BONUS_MAX = 500
LAST_DOUBLE = 2
#: Thanh truot: lech trong `tolerance` = du diem; lech toi 3x tolerance = giam dan tuyen tinh.
SLIDER_PARTIAL_SPAN = 3
#: Dung tu 60% -> du giai "Dung tu 60%".
PASS_RATIO = 0.6

# ------------------------------------------------------------------------ Kieu thi --
MODE_SOLO = "solo"           # ca nhan
MODE_TEAM = "team"           # ca nhan + duong dua phong ban
MODES = (MODE_SOLO, MODE_TEAM)
#: Phong duoi 4 nguoi gop vao "Van phong" (Hoan chot).
TEAM_MIN_SIZE = 4
TEAM_MERGED = "Văn phòng"
TEAM_UNKNOWN = "Chưa có phòng ban"

BOARD_EACH = "each"          # bang xep hang sau moi cau
BOARD_FIVE = "five"          # moi 5 cau
BOARD_END = "end"            # chi cuoi game
BOARD_MODES = (BOARD_EACH, BOARD_FIVE, BOARD_END)

# ------------------------------------------------------------------------ Bao ve --
GUARD_BASIC = "basic"        # dap an chi tren server + dang nhap + server bam gio, 1 lan tra loi
GUARD_STANDARD = "standard"  # + xao dap an, 1 nguoi 1 thiet bi, co tra loi nhanh, chan trinh duyet tu dong
GUARD_STRICT = "strict"      # + xao cau, chan copy, ghi nhan roi man hinh
GUARD_LEVELS = (GUARD_BASIC, GUARD_STANDARD, GUARD_STRICT)
#: Dung lien tuc duoi nguong nay -> gan co (khong tu tru diem).
FAST_MS = 800
FAST_STREAK = 3

FLAG_FAST = "fast"
FLAG_AUTOMATION = "automation"
FLAG_BLUR = "blur"
FLAG_DEVICE = "device"

# ----------------------------------------------------------------------- Pha cua phong --
PHASE_LOBBY = "lobby"
PHASE_QUESTION = "question"  # dang nhan cau tra loi
PHASE_LOCKED = "locked"      # het gio / nguoi dan khoa - chua cong bo dung sai
PHASE_REVEAL = "reveal"      # cong bo dap an + giai thich + diem cua tung nguoi
PHASE_BOARD = "board"        # bang xep hang giua game
PHASE_ENDED = "ended"        # ve dich - bang cuoi + giai
PHASE_CANCELLED = "cancelled"
PHASES = (PHASE_LOBBY, PHASE_QUESTION, PHASE_LOCKED, PHASE_REVEAL, PHASE_BOARD, PHASE_ENDED,
          PHASE_CANCELLED)
LIVE_PHASES = (PHASE_LOBBY, PHASE_QUESTION, PHASE_LOCKED, PHASE_REVEAL, PHASE_BOARD)
#: Phong bo quen (khong ai bam) qua so gio nay thi khong con hien "Quiz dang mo".
ROOM_STALE_HOURS = 6
#: 3 giay "chuan bi" truoc khi dong ho chay (cau hien tren may chieu truoc).
LEAD_IN_SEC = 3
#: Bu tre mang: nhan cau tra loi toi deadline + GRACE_MS.
GRACE_MS = 600
CODE_LEN = 6

ACT_START = "start"
ACT_LOCK = "lock"
ACT_REVEAL = "reveal"
ACT_BOARD = "board"
ACT_NEXT = "next"
ACT_END = "end"
ACT_CANCEL = "cancel"
HOST_ACTIONS = (ACT_START, ACT_LOCK, ACT_REVEAL, ACT_BOARD, ACT_NEXT, ACT_END, ACT_CANCEL)

QUIZ_DRAFT = "Draft"
QUIZ_READY = "Ready"
QUIZ_ARCHIVED = "Archived"
QUIZ_STATUSES = (QUIZ_DRAFT, QUIZ_READY, QUIZ_ARCHIVED)

# --------------------------------------------------------------------- Phan thuong --
SCOPE_PLAYER = "player"
SCOPE_TEAM = "team"
#: Ai nhan - theo nguoi choi.
RANK_1, RANK_2, RANK_3, RANK_4_10 = "rank1", "rank2", "rank3", "rank4_10"
RANK_PASS = "pass60"
RANK_CLIMB = "climb"         # leo hang nhanh nhat (tu hang sau cau 1 toi hang cuoi)
PLAYER_RANKS = (RANK_1, RANK_2, RANK_3, RANK_4_10, RANK_PASS, RANK_CLIMB)
#: Ai nhan - theo phong ban.
TEAM_1, TEAM_2, TEAM_MVP = "team1", "team2", "team_mvp"
TEAM_RANKS = (TEAM_1, TEAM_2, TEAM_MVP)
RANK_LABELS = {RANK_1: "Hạng 1", RANK_2: "Hạng 2", RANK_3: "Hạng 3", RANK_4_10: "Hạng 4–10",
               RANK_PASS: "Đúng từ 60%", RANK_CLIMB: "Leo hạng nhanh nhất",
               TEAM_1: "Đội nhất (mỗi thành viên)", TEAM_2: "Đội nhì (mỗi thành viên)",
               TEAM_MVP: "MVP mỗi đội"}
TICKETS_MAX_PER_PRIZE = 3
DEFAULT_PRIZES = (
    {"scope": SCOPE_PLAYER, "rank": RANK_1, "tickets": 3, "gift": "Trà sữa"},
    {"scope": SCOPE_PLAYER, "rank": RANK_2, "tickets": 2, "gift": ""},
    {"scope": SCOPE_PLAYER, "rank": RANK_3, "tickets": 1, "gift": ""},
    {"scope": SCOPE_PLAYER, "rank": RANK_PASS, "tickets": 1, "gift": ""},
)
GIFT_SUGGESTIONS = ("Trà sữa", "Voucher Grab 50k", "Voucher Shopee 100k", "Áo eCentric",
                    "Sổ tay eCentric", "Bình nước eCentric")

# ------------------------------------------------------------------------- Ve tuan --
#: Toi da 3 ve / nguoi / tuan, tinh CHUNG ve tu quiz + bai thuc hanh (mac dinh trong mockup).
TICKETS_PER_WEEK = 3
TICKET_QUIZ = "quiz"
TICKET_PRACTICE = "practice"
TICKET_LESSON_QUIZ = "lesson_quiz"
TICKET_MANUAL = "manual"
TICKET_SOURCES = (TICKET_QUIZ, TICKET_PRACTICE, TICKET_LESSON_QUIZ, TICKET_MANUAL)

DRAW_OPEN = "Open"
DRAW_DONE = "Done"
DRAW_CANCELLED = "Cancelled"
#: Tat job quay so tuan khan cap.
DRAW_KILL_SWITCH = "ec_training_draw_disabled"

# ------------------------------------------------------------------------- Bai hoc --
LESSON_DRAFT = "Draft"
LESSON_PUBLISHED = "Published"
LESSON_STATUSES = (LESSON_DRAFT, LESSON_PUBLISHED)
LEVELS = ("Cơ bản", "Trung bình", "Nâng cao")
TOPIC_TAGS = ("Viết & email", "Phân tích số liệu", "Slide & tài liệu", "Nghiên cứu",
              "Tự động hoá", "Livestream", "Khác")
TOOL_TAGS = ("Claude", "Claude Projects", "Claude Code", "Excel / Sheets", "ERP", "Khác")
MAX_LESSON_TEXT = 20000
MAX_PRACTICE = 4000
#: Binh chon: moi nguoi 3 phieu, tra lai khi chu de thanh bai hoc.
VOTES_PER_USER = 3
TOPIC_OPEN = "Open"
TOPIC_PLANNED = "Planned"
TOPIC_DONE = "Done"
TOPIC_REJECTED = "Rejected"
TOPIC_STATUSES = (TOPIC_OPEN, TOPIC_PLANNED, TOPIC_DONE, TOPIC_REJECTED)
#: Phieu cua chu de o cac trang thai nay duoc tra lai cho nguoi bau.
TOPIC_RELEASED = (TOPIC_DONE, TOPIC_REJECTED)

# ------------------------------------------------------------------------------ Trang --
ROUTE_LEARN = "dao-tao"
ROUTE_LESSON = "dao-tao/bai"
ROUTE_LESSON_ADMIN = "dao-tao/quan-ly"
ROUTE_QUIZ = "quiz"
ROUTE_QUIZ_EDIT = "quiz/soan"
ROUTE_QUIZ_PLAY = "quiz/choi"
ROUTE_QUIZ_HOST = "quiz/chieu"

REALTIME_ROOM = "ec_quiz_room"
NOTIFY_EVENT = "announcement"
#: Trang thai phong tren Redis - khoa: "ecq:room:<session>".
CACHE_PREFIX = "ecq:room:"
#: Ngan CO CHU Y: neu mot ban cu lot vao Redis (dua giua 2 request) thi chi ket toi da 3 giay.
CACHE_TTL = 3
#: The noi "Quiz dang mo": danh sach phong song, chung cho moi nguoi.
CACHE_CARD = "ecq:livecard"
CACHE_CARD_TTL = 15


def play_url(code):
    return "/%s?c=%s" % (ROUTE_QUIZ_PLAY, code)


def lesson_url(name):
    return "/%s?l=%s" % (ROUTE_LESSON, name)
