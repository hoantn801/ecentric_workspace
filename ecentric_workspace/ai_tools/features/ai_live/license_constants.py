# Copyright (c) 2026, eCentric and contributors
"""Hang so Ban quyen AI Live (cap license tu dong eLive / eSync / eVoice, Hoan chot 17/11/2026).
Tach khoi constants.py (da ~530 dong). Luat duyet nam nguyen trong domain/ec_license_issuer.py (khop tung byte voi app)."""
import re

SETTINGS = "EC License Settings"
MACHINE = "EC License Machine"
INSTALL = "EC License Install"
DIST = "EC License Dist"
EVENT = "EC License Event"

ADMIN_ROLE = "AI Live License Admin"
#: Duyet / khoa may: System Manager hoac role rieng (nguoi khac goi API -> 403).
ADMIN_ROLES = (ADMIN_ROLE, "System Manager")

PRODUCTS = ("elive", "esync", "evoice")
PRODUCT_LABEL = {"elive": "eLive", "esync": "eSync", "evoice": "eVoice"}


class Status:
    PENDING = "pending"
    APPROVED = "approved"
    BLOCKED = "blocked"


STATUSES = (Status.PENDING, Status.APPROVED, Status.BLOCKED)


class Reply:
    """Trang thai tra cho app (ec_online.py doc)."""
    ISSUED = "issued"
    PENDING = "pending"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"
    OK = "ok"


class Kind:
    """EC License Event.kind"""
    REQUEST = "request"
    ISSUED = "issued"
    PENDING = "pending"
    BLOCKED = "blocked"
    CHECKIN = "checkin"
    APPROVE = "approve"
    BLOCK = "block"
    UNBLOCK = "unblock"
    EDIT = "edit"
    DIST_EDIT = "dist_edit"
    MODE = "mode"
    CLONE = "clone_warning"
    NOTIFY = "notify"
    ERROR = "error"


KINDS = tuple(v for k, v in vars(Kind).items() if not k.startswith("_"))
HUMAN_KINDS = (Kind.APPROVE, Kind.BLOCK, Kind.UNBLOCK, Kind.EDIT, Kind.DIST_EDIT, Kind.MODE)

# ------------------------------------------------------------------ API cho app (khach) ---
MAX_BODY = 32 * 1024
REQUEST_PER_MIN = 30
CHECKIN_PER_MIN = 60
RATE_WINDOW_S = 60
POLL_S = 30
#: Khoa dong (GET_LOCK) theo guid_h va dist_id trong luc quyet dinh; doi toi da N giay.
LOCK_WAIT_S = 8
LOCK_PREFIX = "eclic:"

HEX_RE = re.compile(r"^[0-9a-f]{1,20}$")
HW32_RE = re.compile(r"^[0-9A-F]{32}$")
HW24_RE = re.compile(r"^[0-9a-f]{24}$")
MAX_MACS = 16
#: Do dai toi da cac chu may tu khai (cat bot, bo ky tu dieu khien).
TEXT_LIMITS = {"host": 80, "user": 80, "os": 120, "app_dir": 260, "build_id": 80, "request_code": 400,
               "machine_id": 40, "license_hw": 64, "cust": 80, "exp": 40}
DIST_KEYS = ("dist_id", "label", "parent", "created_at", "server", "kind", "package", "sig")
MAX_DIST_TEXT = 200

DIST_KIND_LABEL = {"khach": "Khách", "noi_bo": "Nội bộ"}
REASON_MANUAL_KEY = "key tay trước 17/11"
REASON_MANUAL_ASK = "máy key tay (ERP chỉ thấy qua báo về) xin license mới – chờ duyệt"

# ------------------------------------------------------------------ Trang duyet ---
ROUTE = "/ai-live/ban-quyen"
DEEP_LINK = ROUTE + "#may-%s"
PAGE_SIZE = 50
DETAIL_EVENTS = 50
RUNNING_HOURS = 24
STALE_DAYS = 3
MAX_LABEL = 140
MAX_NOTE = 1000
MAX_BLOCK_MSG = 300
MAX_APPROVE = 100
EVENT_KEEP_DAYS = 90          # chi xoa su kien checkin cu (thao tac cua nguoi + cap/khoa giu mai)
SECRET_KEYS = {"elive": ("mk", "app_secret", "rsa_private_pem"),
               "esync": ("mk", "app_secret", "rsa_private_pem", "premium_fernet_key"),
               "evoice": ("private_key", "master_key", "app_secret")}
TEAMS_FORMATS = ("workflows", "messagecard")
#: Tat khan ca hai API cho app (tra "chua san sang" - app khong khoa): site_config ec_license_disabled = 1
KILL_SWITCH = "ec_license_disabled"


class Msg:
    BAD_CODE = "Mã yêu cầu không hợp lệ"
    DEFAULT_BLOCK = "Máy này đã bị eCentric khoá. Liên hệ người phụ trách."
    NOT_READY = "Máy chủ chưa sẵn sàng cấp license"
    NEED_ADMIN = "Chỉ quản trị Bản quyền AI Live được làm việc này."
    NOT_FOUND = "Không tìm thấy máy %s."
    DIST_NOT_FOUND = "Không tìm thấy gói %s."
    NOT_PENDING = "Máy %s không ở trạng thái Chờ duyệt."
    NOT_BLOCKED = "Máy %s không bị khoá."
    ALREADY_BLOCKED = "Máy %s đã bị khoá."
    NEED_PICK = "Chưa chọn máy nào."
    TOO_MANY = "Tối đa %d máy mỗi lần duyệt."
    BUSY = "Máy %s đang được xử lý, thử lại sau vài giây."
    BAD_FILTER = "Bộ lọc không hợp lệ: %s"
    APPROVED = "Đã duyệt – app trên máy đó tự mở trong khoảng 30 giây."
    TEAMS_TITLE = "[AI Live · Bản quyền] Máy chờ duyệt"
    TEAMS_PENDING = "Máy %s xin dùng %s, gói %s, nguồn %s, lý do %s."
    TEAMS_CLONE_TITLE = "[AI Live · Bản quyền] Nghi nhân bản"
    TEAMS_CLONE = ("Máy %s (%s) báo về cùng mã Windows và ổ C: với máy đã có nhưng khác card mạng và tên máy (%s). "
                   "Có thể cài từ cùng bản Ghost / sao ổ. Chỉ cảnh báo, chưa khoá.")
    TEAMS_BUTTON = "Mở để duyệt"
    NO_DIST = "không có mã gói"
    NO_SOURCE = "—"


class LicenseError(Exception):
    """Loi nghiep vu trang Ban quyen - thong diep tieng Viet hien thang."""


class LicensePermission(LicenseError):
    pass


class BadPayload(ValueError):
    """Du lieu app gui sai kieu / qua dai: request -> pending, checkin -> ok (KHONG bao gio blocked)."""
