# Copyright (c) 2026, eCentric and contributors
"""Hang so AI Live (app eCentric AI Live tren may phat): ten DocType, role, gioi han, thong bao."""
import re

BRAND_CONFIG = "EC AI Live Brand Config"
MACHINE = "EC AI Live Machine"
COST_LOG = "EC AI Live Cost Log"

#: Quan tri cau hinh AI Live (key, may phat): giong quan tri AI Video.
ADMIN_ROLES = ("EC AI Video Admin", "System Manager")
#: Xem chi phi AI Live: ai co quyen trang /ai-video.
VIEW_ROLES = ("EC AI Content", "EC AI Video Admin", "System Manager")

MODES = ("full", "lite")
BREAK_SECS = (20, 25, 30, 35)
DEFAULT_BREAK_SEC = 20

BRAND_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")
MACHINE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,39}$")
SESSION_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Khoa (Password) tra ve cho may phat. Ten truong DocType = ten khoa trong JSON.
KEY_FIELDS = ("claude_key", "minimax_key", "kie_key", "plenx_key",
              "shopee_partner_key", "shopee_access_token", "shopee_refresh_token")
PLAIN_FIELDS = ("gpu_url", "mode", "break_sec", "kit_folder", "minimax_group", "daily_cost_cap_usd",
                "shopee_partner_id", "shopee_shop_id")
#: Shopee Open Platform: chi luu va tra cho may phat; chua goi API Shopee (chua co tai lieu live).
#: Cai dat app sua duoc va dong bo lai len ERP (JSON).
SETTING_FIELDS = {"templates": "templates_json", "playlist": "playlist_json", "cooldowns": "cooldowns_json"}
MAX_SETTING_BYTES = 200 * 1024
MAX_COST_ITEMS = 50
MAX_USD = 10000.0

MACHINE_EMAIL = "ailive-%s@machines.ecentric.local"


class Msg:
    NOT_MACHINE = "Tài khoản này không phải máy phát AI Live (hoặc máy đã bị tắt)."
    WRONG_MACHINE = "Mã máy không khớp với token."
    BRAND_NOT_ALLOWED = "Máy này chưa được giao brand %s."
    BAD_BRAND = "Mã brand không hợp lệ (chữ thường, số, - _; 2–40 ký tự): %s"
    BAD_MACHINE = "Mã máy không hợp lệ (chữ, số, - _; 2–40 ký tự)."
    BAD_MODE = "Chế độ phải là full (Đầy đủ) hoặc lite (Tiết kiệm)."
    BAD_BREAK = "Khoảng nghỉ phải là 20, 25, 30 hoặc 35 giây."
    BAD_JSON = "Dữ liệu %s không phải JSON hợp lệ."
    TOO_BIG = "Dữ liệu %s quá lớn (tối đa 200 KB)."
    BAD_COST = "Dữ liệu chi phí không hợp lệ: %s"
    NEED_ADMIN = "Chỉ quản trị AI Video được làm việc này."
    NEED_VIEW = "Cần quyền EC AI Content."
    UNKNOWN_BRAND = "Chưa có cấu hình brand %s."
    UNKNOWN = "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT."


class AiLiveError(Exception):
    """Loi nghiep vu AI Live - thong diep tieng Viet hien thang cho nguoi dung."""


class AiLivePermission(AiLiveError):
    pass


# ------------------------------------------------------------------ Bo live + kho host (fix10b) ---
KIT = "EC AI Live Kit"


class KitStatus:
    DRAFT = "Nháp"
    SENDING = "Đang gửi"
    BUILDING = "Đang dựng"
    DONE = "Xong"
    ERROR = "Lỗi"


PRODUCT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
HOST_RE = re.compile(r"^H_[A-Z0-9_]{3,40}$")
PLATFORM_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{0,40}$")
AUDIO_EXT = (".mp3", ".wav", ".m4a")
BG_EXT = {".mp4": "video", ".webm": "video", ".mov": "video", ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image"}
MAX_PRODUCTS = 60
MAX_AUDIO_PER_GROUP = 6
MAX_FAQ_TOPICS = 30
FAQ_COPIES = (2, 5)
#: Nhom video cua 1 SP: khoa trong bolive.json (products[].groups)
PRODUCT_AUDIO_GROUPS = ("main_free", "main_hold")
GENERIC_GROUPS = ("greet", "thanks", "answer", "cho", "race_call", "race_commentary", "race_winner", "race_claim")
#: fix10e: 4 nhom clip dua vit (W20) - may live doc generic.race_* trong bolive.json; khong co thi van dua (host noi realtime).
#: So ban nen co moi loai clip chung (min, max) - chi de goi y tren trang, khong chan luu.
GENERIC_COUNTS = {"greet": (3, 5), "thanks": (3, 3), "answer": (2, 2), "cho": (3, 3),
                  "race_call": (2, 2), "race_commentary": (3, 4), "race_winner": (2, 2), "race_claim": (1, 2)}
MAX_SCRIPT_CHARS = 200
#: Loi goi y cho clip chung (team sua tren trang roi thu am / TTS). {brand} = ten brand.
GENERIC_SCRIPTS = {
    "greet": ("Dạ em chào cả nhà mới vào phiên live của nhà {brand} ạ, mọi người xem live vui vẻ nha.",
              "Em chào các anh chị vừa ghé phiên live nha, có gì thắc mắc cứ để lại bình luận cho em ạ.",
              "Chào mừng mọi người đến với phiên live hôm nay của {brand}, nhiều ưu đãi lắm, ở lại với em nha.",
              "Dạ em chào các bạn mới vào nè, nhớ bấm theo dõi kênh để không bỏ lỡ ưu đãi nha.",
              "Em chào cả nhà, cảm ơn mọi người đã ghé live, mình cùng xem sản phẩm hôm nay nha."),
    "thanks": ("Dạ em cảm ơn anh chị đã quan tâm ạ, mọi người đợi em chút xíu, em giới thiệu lại ngay nha.",
               "Cảm ơn cả nhà đã hỏi nha, em sẽ nói lại phần này ngay sau đây, mọi người chờ em một chút ạ.",
               "Dạ em ghi nhận câu hỏi rồi ạ, lát nữa em giới thiệu lại kỹ hơn cho mình nha."),
    "answer": ("Dạ câu này anh chị nhắn tin cho shop để được tư vấn kỹ hơn nha, shop phản hồi ngay ạ.",
               "Dạ phần này em chưa có thông tin chính xác, mình để lại tin nhắn cho shop để được hỗ trợ nha."),
    "cho": ("Dạ em xem câu hỏi của mình chút nha.",
            "Dạ để em đọc kỹ câu hỏi nha, mọi người chờ em một xíu.",
            "Dạ có câu hỏi nè, em xem ngay cho mình ạ."),
    # fix10e - dua vit (W20): khong ten khach, khong gia; binh luan trung tinh (ket qua hien tren bang).
    "race_call": ("Đua vịt có thưởng đây cả nhà ơi! Comment chữ vịt để tham gia, một phút nữa mình xuất phát nha.",
                  "Cả nhà ơi sắp đua vịt rồi nè! Comment chữ vịt để có vịt của mình, quà xịn từ {brand} đang chờ nha."),
    "race_commentary": ("Xuất phát rồi! Các bạn vịt đang bơi rất là hăng nha… Ai đang dẫn đầu vậy ta, nhìn lên bảng nào!",
                        "Sát nút quá cả nhà ơi, chưa biết ai về nhất đâu nha!",
                        "Vịt nào cũng cố gắng hết sức luôn, mọi người cổ vũ vịt của mình đi nào!",
                        "Sắp tới đích rồi đó cả nhà, căng thẳng quá đi, cùng xem nha!"),
    "race_winner": ("Về đích rồi! Chúc mừng các bạn có tên trên màn hình nha!",
                    "Kết quả có rồi nè cả nhà! Chúc mừng các bạn trúng giải, tên đang hiện trên bảng đó nha!"),
    "race_claim": ("Bạn nào trúng giải nhắn tin cho shop để nhận quà nha.",
                   "Các bạn trúng giải nhớ nhắn tin cho shop để shop gửi quà nha, chưa trúng thì lát mình đua tiếp nè."),
}

#: Studio anh host: model -> nhan, credit PlenX moi anh (None = chua co bang gia, khong uoc tinh).
IMAGE_MODELS = (("nano-banana-full", "Nano Banana Full 2K (PlenX)", 10),
                ("nano-banana-pro", "Nano Banana Pro", None),
                ("gpt-image", "GPT Image", None),
                ("seedream", "Seedream", None))
HOST_IMAGE_N = 4
MAX_REFS = 4
MAX_PROMPT = 2000

#: Bo motion de xuat cho host moi (17/10, tinh tu H_BOO3HGI9JF 81 clip va H_FAQ_GREEN 22 clip): 20 clip noi.
MOTION_PROPOSAL = ((10, 10), (8, 5), (6, 3), (4, 2))
MOTION_DURS = (4, 6, 8, 10)
MAX_MOTION_CLIPS = 60
#: Uoc tinh: PlenX ~3 credit/giay video (1080p), x1,5 cho lan gen lai do QC; 80 d/credit (goi 399.000d / 5.000).
PX_CREDIT_PER_S = 3
QC_FACTOR = 1.5
VND_PER_PX_CREDIT = 80
#: Lipsync (giong AI Video): ~$0.012/giay neu chay fal; may GPU rieng thi gan nhu khong ton.
LS_USD_PER_S = 0.012
HOST_LABELS_KEY = "ec_ai_live_host_labels"
#: Tien to batch_id tren may chay video (tach lo Bo live / Studio anh / bo motion).
BATCH_KIT, BATCH_HOST_IMAGE, BATCH_MOTION = "kit_", "hi_", "ms_"


class KitMsg:
    NOT_FOUND = "Không tìm thấy Bộ live %s."
    BAD_PRODUCT = "Dòng sản phẩm %d: %s"
    BAD_FAQ = "Chủ đề FAQ %d: %s"
    BAD_FILE = "File không hợp lệ hoặc không phải của bạn: %s"
    NEED_HOST = "Chưa chọn host (host phải có trong Kho host)."
    NEED_BRAND = "Chưa chọn brand."
    NOTHING = "Bộ live chưa có voice nào để dựng."
    BUSY = "Bộ live đang dựng, đợi xong rồi gửi lại."
    BAD_HOST = "Mã host không hợp lệ."
    BAD_MODEL = "Model ảnh không hợp lệ."
    BAD_PLAN = "Bộ motion không hợp lệ (mỗi loại 0–20 clip, tổng 1–60, độ dài 4/6/8/10 giây)."
    NEED_PROMPT = "Chưa nhập mô tả ảnh host."
    BAD_PICK = "Ảnh này chưa xong hoặc không thuộc lượt tạo hiện tại."


# ------------------------------------------------------------------ Giam sat live (fix10c) ---
HEALTH = "EC AI Live Health"
HEALTH_SAMPLE = "EC AI Live Health Sample"
ALERT_LOG = "EC AI Live Alert"
ALERT_SETTINGS = "EC AI Live Alert Settings"


class Level:
    OK = "ok"
    INFO = "info"
    WARN = "warn"
    CRIT = "critical"
    OFF = "offline"
    #: Ngoai gio live, khong len song: o xam, khong bao dong.
    IDLE = "idle"


#: Thu tu muc canh bao (cao hon = nang hon). offline xep ngang critical.
LEVEL_RANK = {Level.IDLE: -1, Level.OK: 0, Level.INFO: 1, Level.WARN: 2, Level.CRIT: 3, Level.OFF: 3}
APP_ALERT_LEVELS = (Level.INFO, Level.WARN, Level.CRIT)
#: Trang thai live do app gui; 3 trang thai dau = dang len song (mat tin hieu luc nay la su co).
ON_AIR_STATES = ("preflight", "live", "ending")
LIVE_STATES = ON_AIR_STATES + ("idle", "stopped", "error")

LIVE_RE = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")
ALERT_CODE_RE = re.compile(r"^[a-z0-9_.-]{1,40}$")
HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
MAX_HB_LIVES = 8
MAX_HB_ALERTS = 20
MAX_ALERT_TEXT = 200
MAX_SLOTS = 14
MAX_THUMB_BYTES = 200 * 1024
THUMB_DIR = "ai_live_thumbs"
THUMB_KINDS = ("obs", "phone", "platform", "stream")  # fix10d: platform = xem truoc Seller Center / LIVE Manager (extension),
#                                                       stream = khung hinh luong cong khai TikTok

#: Mau so lieu toi da 1 dong / 60 s moi live; giu 24 gio. Lich su canh bao giu 14 ngay.
SAMPLE_EVERY_S = 60
SAMPLE_KEEP_HOURS = 24
ALERT_KEEP_DAYS = 14
#: Mac dinh (doi duoc trong EC AI Live Alert Settings).
DEAD_MAN_MIN = 2
DEDUPE_MIN = 10
ESCALATE_MIN = 5
#: O tren tuong chuyen vang khi qua 75 s chua co tin hieu (app gui moi 30 s).
STALE_WARN_S = 75
#: Nguong hien mau o (app cung tu bao dong theo nguong rieng).
FPS_MIN = 25.0
DROP_PCT_MAX = 2.0
GPU_MAX = 90.0
VRAM_MAX = 95.0
TZ_OFFSET_H = 7  # gio Viet Nam, khong doi mua

#: Zalo Bot Platform (bot.zaloplatforms.com): API kieu Telegram. CAN XAC NHAN tren bot that -> de doi trong cai dat.
ZALO_API_BASE = "https://bot-api.zaloplatforms.com"
ZALO_SEND_PATH = "/bot{token}/sendMessage"
TEAMS_FORMATS = ("workflows", "messagecard")
HTTP_TIMEOUT = 10
#: Tat may quet: site_config ec_ai_live_monitor_disabled = 1
KILL_SWITCH = "ec_ai_live_monitor_disabled"
MONITOR_LINK = "/ai-video#/monitor"


class MonMsg:
    BAD_HB = "Dữ liệu tín hiệu máy không hợp lệ: %s"
    NO_KEY = "Không tìm thấy live %s."
    NO_THUMB = "Chưa có ảnh."
    NO_CHANNEL = "Chưa cấu hình Teams hoặc Zalo trong EC AI Live Alert Settings."
    TEST_TEXT = "Tin thử từ màn Giám sát AI Live: kênh báo động hoạt động bình thường."
    OFFLINE = "Mất tín hiệu %d phút (mất điện, mất mạng hoặc app tắt) trong giờ live"
    BACK = "Đã có tín hiệu lại"
    ESCALATED = "Kéo dài hơn %d phút"


#: Ten hien thi cua ma canh bao do may chu tu sinh (app gui text rieng cho ma cua no).
SERVER_CODES = {"offline": "Mất tín hiệu", "back": "Có tín hiệu lại"}


# ------------------------------------------------------------------ Phien live + Lich live (fix10d) ---
SESSION = "EC AI Live Session"
SESSION_SLOT = "EC AI Live Session Slot"
COMMAND = "EC AI Live Command"

PLATFORMS = ("TikTok", "Shopee")
#: Ma phien live = ma live tren app (lives.<id>) -> cung luat voi LIVE_RE.
DEFAULT_MAX_LIVES = 2
MAX_SESSIONS = 300
MAX_SESSION_SLOTS = 40
TIKTOK_USER_RE = re.compile(r"^@?[A-Za-z0-9_.]{2,24}$")
PHONE_SERIAL_RE = re.compile(r"^[A-Za-z0-9_.:-]{3,64}$")
WATCH_URL_RE = re.compile(r"^https://[^\s]{4,400}$")
#: Man "Xem nhu khach": thu tu nguon anh phia khach + nhan; anh qua 2 phut -> "mat hinh".
VIEWER_SOURCES = ("platform", "stream", "phone")
VIEWER_STALE_S = 120
OBS_PORT_RANGE = (1024, 65535)


class SessionStatus:
    ON_AIR = "on_air"
    SCHEDULED = "scheduled"
    OFF = "off"
    PROBLEM = "problem"


#: Lenh tu trang ERP cho app tren may phat (app hoi pull_commands moi ~10 s).
CMD_ACTIONS = ("pause_ai", "resume_ai", "skip_clip", "play_faq", "start_race", "stop_race")  # fix10e: dua vit
CMD_QUEUED, CMD_SENT, CMD_DONE, CMD_FAILED, CMD_EXPIRED = "Queued", "Sent", "Done", "Failed", "Expired"
CMD_TTL_S = 120
CMD_PULL_MAX = 20
CMD_KEEP_DAYS = 7
MAX_CMD_ARG = 120
MAX_CMD_RESULT = 140                 # cot Data cua Frappe = varchar(140)

#: Gioi han khoi "detail" app gui kem tin hieu (chi luu ban moi nhat).
DETAIL_LIMITS = {"next": 10, "queue": 20, "recent": 30, "greeted": 20}
MAX_DETAIL_TEXT = 160
DETAIL_COUNTERS = ("comments", "answered", "greeted", "faq", "ai")


class SessMsg:
    BAD_ID = "Mã phiên live không hợp lệ (chữ, số, . _ -; tối đa 40 ký tự)."
    BAD_PLATFORM = "Sàn phải là TikTok hoặc Shopee."
    NEED_TIKTOK = "Phiên TikTok cần username kênh."
    BAD_TIKTOK = "Username TikTok không hợp lệ: %s"
    BAD_PORT = "Cổng OBS phải từ 1024 đến 65535."
    PORT_TAKEN = "Cổng OBS %s đã dùng cho phiên %s trên cùng máy."
    BAD_SLOT = "Khung giờ %d: %s"
    SLOT_OVERLAP = "Khung giờ %d trùng với khung %d của chính phiên này."
    CAPACITY = "Máy %s chỉ chạy tối đa %d live cùng lúc – %s trùng giờ với: %s."
    NOT_FOUND = "Không tìm thấy phiên live %s."
    BAD_CMD = "Lệnh không hợp lệ."
    NO_MACHINE = "Phiên live chưa gán máy phát."
    CMD_NOT_FOUND = "Không tìm thấy lệnh %s."
    BAD_WEEK = "Tuần không hợp lệ (dùng ngày thứ Hai, dạng YYYY-MM-DD)."
    BRAND_OFF = "Brand %s chưa giao cho máy %s."
    BAD_URL = "Link xem phiên phải bắt đầu bằng https://"
    BAD_SERIAL = "Mã điện thoại (adb serial) không hợp lệ."
    NOT_ON_MACHINE = "Phiên live %s không thuộc máy %s (hoặc chưa tạo trên ERP)."
    BAD_SLOTS = "Danh sách khung giờ không hợp lệ (cần mảng JSON, gửi [] để xoá hết khung)."

#: Tong ket cuoi phien (app gui khi phien ket thuc) - lich su phien, giu 400 ngay.
SESSION_LOG = "EC AI Live Session Log"
SUMMARY_REASONS = ("schedule_end", "manual", "error", "restart", "other")
LOG_KEEP_DAYS = 400
MAX_HISTORY_DAYS = 90


# ------------------------------------------------------------------ Dua vit (fix10e, W20) ---
RACE = "EC AI Live Race"
RACE_WINNER = "EC AI Live Race Winner"
RACE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")
#: Trang thai trao giai: ma app (W20) -> nhan luu tren ERP (Select). Ma la -> "Chua trao".
PRIZE_STATUS = {"chua_trao": "Chưa trao", "da_trao": "Đã trao", "khong_lien_lac": "Không liên lạc được"}
PRIZE_DEFAULT = "chua_trao"
#: Ket qua cuoc dua (app gui status: done | not_enough | cancelled | cancelled_<ly do> | aborted_restart).
RACE_OUTCOMES = {"done": "Đã đua xong", "not_enough": "Chưa đủ người", "cancelled": "Đã huỷ",
                 "aborted_restart": "Huỷ do app khởi động lại"}
RACE_BY = {"app": "Bấm trên app", "schedule": "Lịch giờ cố định", "every": "Mỗi X phút", "erp": "Lệnh từ ERP"}
MAX_RACE_TIERS = 10
MAX_RACE_WINNERS = 100
MAX_RACE_TEXT = 140
MAX_RACE_NOTE = 500
MAX_PNG_BYTES = 3 * 1024 * 1024
RACE_LIST_MAX = 500
RACE_DEFAULT_DAYS = 7
RACE_MAX_DAYS = 366
RACE_BULK_MAX = 500
#: Tham so lenh start_race (ghi de 1 lan tren app) - cung khoang voi cai dat W20.
RACE_ARG_RANGES = {"regSeconds": (20, 300), "raceSeconds": (20, 60), "minEntrants": (2, 100)}
RACE_ANNOUNCE = ("ascending", "descending")
RACE_EXCLUDE = ("none", "today", "week")
MAX_KEYWORD = 30
MAX_TIER_LABEL = 40
MAX_TIER_PRIZE = 120


class RaceMsg:
    BAD_RACE = "Kết quả đua vịt không hợp lệ: %s"
    BAD_ID = "Mã cuộc đua không hợp lệ."
    OTHER_MACHINE = "Cuộc đua %s thuộc máy khác."
    BAD_PNG = "Ảnh kết quả phải là PNG ≤ 3 MB."
    BAD_STATUS = "Trạng thái trao giải phải là: Chưa trao, Đã trao hoặc Không liên lạc được."
    NO_ITEMS = "Chưa chọn người thắng nào."
    TOO_MANY = "Tối đa %d người thắng mỗi lần cập nhật."
    BAD_DATE = "Ngày không hợp lệ (dạng YYYY-MM-DD)."
    BAD_ARG = "Tham số đua vịt không hợp lệ: %s"
    NOT_FOUND = "Không tìm thấy cuộc đua %s."


# ------------------------------------------------------------------ May im lang (W17, fix10f) ---
#: Bang con cua EC AI Live Alert Settings: kenh Teams / Zalo theo nhom brand.
ALERT_CHANNEL = "EC AI Live Alert Channel"
#: Trang thai app ca may (eC Live >= 1.0.20). 'stopping' = tat app dung cach -> im lang khong phai su co.
APP_RUNNING = "running"
APP_STOPPING = "stopping"
APP_STATES = (APP_RUNNING, APP_STOPPING)
#: Mac dinh (doi duoc trong EC AI Live Alert Settings).
MACHINE_OFFLINE_MIN = 3
MACHINE_REPEAT_MIN = 5
NIGHT_REPEAT_MIN = 15
NIGHT_START = "01:00"
NIGHT_END = "07:00"
#: boot_at moi lech hon chung nay so voi luc mat lien lac = may da khoi dong lai.
REBOOT_TOLERANCE_S = 60
MAX_MACHINE_ALERTS = 20
MACHINE_ALERT_KEY = "machine:%s"


class WatchCode:
    OFFLINE = "machine_offline"
    BACK = "machine_back"


class WatchAction:
    NONE = "none"
    LOST = "lost"
    REMIND = "remind"
    BACK = "back"


class WatchMsg:
    TITLE_LOST = "[KHẨN] AI Live · Máy %s"
    TITLE_BACK = "[XANH] AI Live · Máy %s"
    LOST = "Máy %s mất liên lạc từ %s (mất điện / mất mạng / treo). Đang có live: %s."
    STILL = " Đã %d phút chưa liên lạc lại."
    BACK = "Máy %s đã liên lạc lại sau %d phút."
    REBOOT = " Máy vừa khởi động lại (mất điện / reset)."
    APP_RESTART = " App eC Live vừa mở lại%s (máy không khởi động lại)."
    CRASH = " sau lỗi"
    DAY = " ngày %s"
