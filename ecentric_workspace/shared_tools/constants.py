# Copyright (c) 2026, eCentric and contributors
"""Cong cu dung chung (/kalodata) - hang so. Mot tai khoan Kalodata, mot nguoi dung mot luc.

Trinh duyet Kalodata chay tren may 24/7 (bo kalodata-host-poc: Chromium + Guacamole + Cloudflare
Tunnel). ERP chi giu HANG DOI va goi broker tren may do de cap / thu hoi link. ERP khong bao gio
thay mat khau Kalodata, cookie hay mat khau VNC.
"""
MODULE = "Shared Tools"

TOOL_DT = "EC Shared Tool"
QUEUE_DT = "EC Shared Tool Queue"
EVENT_DT = "EC Shared Tool Event"
EXPORT_DT = "EC Shared Tool Export"

TOOL_KALODATA = "kalodata"
ROUTE = "kalodata"

#: Quan ly hang doi (buoc ket thuc luot cua nguoi khac, sua cau hinh). Nguoi dung thuong khong can role.
ROLE_MANAGER = "EC Shared Tool Manager"
MANAGER_ROLES = ("System Manager", ROLE_MANAGER)

# --- site_config (KHONG o repo, KHONG in ra log) ---
CONF_BROKER_URL = "ec_kalodata_broker_url"        # vd https://kalodata-gw.ecentric.asia/ec
CONF_BROKER_SECRET = "ec_kalodata_broker_secret"  # giong EC_BROKER_SECRET trong .env may 24/7

# --- trang thai mot luot ---
ST_WAITING = "Waiting"
ST_READY = "Ready"
ST_ACTIVE = "Active"
ST_COMPLETED = "Completed"
ST_CANCELLED = "Cancelled"
ST_SKIPPED = "Skipped"
ST_EXPIRED = "Expired"
STATUSES = (ST_WAITING, ST_READY, ST_ACTIVE, ST_COMPLETED, ST_CANCELLED, ST_SKIPPED, ST_EXPIRED)
OPEN_STATUSES = (ST_WAITING, ST_READY, ST_ACTIVE)
STATUS_LABELS = {
    ST_WAITING: "Đang chờ", ST_READY: "Đến lượt", ST_ACTIVE: "Đang dùng", ST_COMPLETED: "Đã xong",
    ST_CANCELLED: "Rời hàng", ST_SKIPPED: "Bỏ lượt", ST_EXPIRED: "Hết giờ",
}

# --- ly do ket thuc ---
END_TIME = "time"          # het 30 phut (hoac het gia han)
END_IDLE = "idle"          # khong thao tac trong Kalodata qua idle_minutes
END_USER = "user"          # tu bam Ket thuc som / Bo luot / Roi hang
END_NO_SHOW = "no_show"    # den luot ma khong mo trong ready_minutes
END_ADMIN = "admin"        # quan ly buoc ket thuc
END_LABELS = {
    END_TIME: "Hết thời gian", END_IDLE: "Để yên quá lâu", END_USER: "Tự kết thúc",
    END_NO_SHOW: "Không mở kịp", END_ADMIN: "Quản lý kết thúc",
}

# --- nhat ky ---
EV_JOIN = "Join"
EV_LEAVE = "Leave"
EV_READY = "Ready"
EV_OPEN = "Open"
EV_REOPEN = "Reopen"
EV_EXTEND = "Extend"
EV_END = "End"
EV_REVOKE_FAIL = "Revoke Failed"
EV_EXPORT = "Export"
EV_DOWNLOAD = "Download"
EVENTS = (EV_JOIN, EV_LEAVE, EV_READY, EV_OPEN, EV_REOPEN, EV_EXTEND, EV_END, EV_REVOKE_FAIL,
          EV_EXPORT, EV_DOWNLOAD)

# --- mac dinh (sua tren ban ghi EC Shared Tool "kalodata") ---
DEFAULT_LEASE_MIN = 30
DEFAULT_READY_MIN = 3
DEFAULT_EXTEND_MIN = 15
DEFAULT_IDLE_MIN = 10
#: Chi gia han duoc khi con it hon so phut nay (tranh cong don gia han tu som).
EXTEND_WINDOW_MIN = 10
#: Link Guacamole song bao lau (giay). Moi lan bam "Mo" la mot link moi.
LINK_TTL_SEC = 60
#: Giu file xuat tren ERP bao nhieu ngay.
EXPORT_KEEP_DAYS = 7
#: Trang hoi trang thai moi bao nhieu giay (JS). Dong bo voi may 24/7 toi da 1 lan / khoang nay.
POLL_SEC = 10
HOST_SYNC_SEC = 10

# --- cache (frappe.cache) ---
CACHE_HOST = "ec_shared_tool:host:%s"        # trang thai may 24/7 lan hoi gan nhat
CACHE_SYNC_LOCK = "ec_shared_tool:sync:%s"   # chong hoi may 24/7 don dap
CACHE_OPEN_LOCK = "ec_shared_tool:open:%s"   # chong bam "Mo" lien tuc (theo user)
CACHE_EXPORT_LOCK = "ec_shared_tool:pull:%s"  # mot trang dang keo file xuat tai mot thoi diem
HOST_CACHE_TTL = 120
OPEN_LOCK_SEC = 4

EXPORT_SOURCE_LABELS = {"extension": "Nút Xuất bảng", "kalodata_native": "Export của Kalodata",
                        "diagnostic": "Chẩn đoán cấu trúc bảng"}
