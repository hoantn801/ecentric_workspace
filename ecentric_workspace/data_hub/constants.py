# Copyright (c) 2026, eCentric and contributors
"""Hang so cua Trung tam Du lieu (/du-lieu). PO Hoan chot 09/11/2026 (spec + mockup da duyet).

Moi ten DocType / trang thai / muc uu tien / gioi han nam o day - domain, service, repository, trang
deu doc tu day. KHONG co email nao trong code: nguoi duyet quy tac / role team Data / project /pm
nam trong EC Data Hub Settings (patch p001 seed).
"""

TICKET_DT = "EC Data Ticket"
LOG_DT = "EC Data Ticket Log"
MSG_DT = "EC Data Ticket Message"
FOLLOWER_DT = "EC Data Ticket Follower"     # bang con cua EC Data Ticket (followers)
FILE_DT = "EC Data Ticket File"             # bang con cua EC Data Ticket (attachments)
SETTINGS_DT = "EC Data Hub Settings"        # Single
RULE_DT = "EC Data SLA Rule Set"
RULE_ITEM_DT = "EC Data SLA Rule Item"      # bang con cua EC Data SLA Rule Set (items)

ADMIN_ROLE = "System Manager"
#: Mac dinh khi Settings chua co gia tri (patch p001 seed dung gia tri nay). Menu trai (shell/nav)
#: cung dung ten nay cho muc chi team Data thay - doi role trong Settings thi doi ca o day.
DEFAULT_DATA_TEAM_ROLE = "EC Data Team"
#: Viec /pm duoc tao / dong bo duoi tai khoan nay (moi quyen da kiem o Trung tam Du lieu truoc).
SYSTEM_USER = "Administrator"

# ------------------------------------------------------------------ loai work item ---------
KIND_REQUEST = "request"            # DR-YYYY-#### - yeu cau du lieu (dot 1)
KIND_AVAILABILITY = "availability"  # DA-YYYY-#### - ke hoach bo sung data (dot 2, chua co UI)
KINDS = (KIND_REQUEST, KIND_AVAILABILITY)
SERIES = {KIND_REQUEST: "DR-.YYYY.-.####", KIND_AVAILABILITY: "DA-.YYYY.-.####"}

# ------------------------------------------------------------------ trang thai -------------
ST_WAITING = "Chờ tiếp nhận"
ST_DOING = "Đang xử lý"
ST_PAUSED = "Tạm dừng"
ST_REVIEW = "Chờ nghiệm thu"
ST_DONE = "Hoàn tất"
ST_CANCELLED = "Huỷ"
STATUSES = (ST_WAITING, ST_DOING, ST_PAUSED, ST_REVIEW, ST_DONE, ST_CANCELLED)
OPEN = (ST_WAITING, ST_DOING, ST_PAUSED, ST_REVIEW)
CLOSED = (ST_DONE, ST_CANCELLED)
#: Dang chay dong ho han (Tam dung = dong ho dung; Cho nghiem thu = team Data da xong).
CLOCK_RUNNING = (ST_DOING,)
#: Nhan hien thi (Tam dung la cho nguoi gui - mockup).
STATUS_LABEL = {ST_PAUSED: "Tạm dừng – chờ người gửi"}
STATUS_CSS = {ST_WAITING: "gray", ST_DOING: "navy", ST_PAUSED: "amber", ST_REVIEW: "teal",
              ST_DONE: "green", ST_CANCELLED: "muted"}
#: Trang thai team Data dat duoc tu o "Cap nhat" (Cho tiep nhan -> chi qua "Nhan viec").
TEAM_SET_STATUSES = (ST_DOING, ST_PAUSED, ST_REVIEW)

# ------------------------------------------------------------------ nghiem thu -------------
ACC_OK = "Đạt"
ACC_FAIL = "Chưa đạt"
ACC_AUTO = "Đạt (tự động)"
ACCEPTANCES = (ACC_OK, ACC_FAIL, ACC_AUTO)
#: Nguoi gui khong phan hoi trong bay nhieu ngay lam viec sau khi team Data bam Hoan tat -> tu dong.
AUTO_CLOSE_WORKING_DAYS = 3

# ------------------------------------------------------------------ uu tien ----------------
PRI_URGENT = "Khẩn"
PRI_HIGH = "Cao"
PRI_NORMAL = "Bình thường"
PRI_LOW = "Thấp"
#: Thu tu = thu tu hang doi (Khan truoc).
PRIORITIES = (PRI_URGENT, PRI_HIGH, PRI_NORMAL, PRI_LOW)
PRIORITY_RANK = {p: i for i, p in enumerate(PRIORITIES)}
PRIORITY_CSS = {PRI_URGENT: "red", PRI_HIGH: "amber", PRI_NORMAL: "gray", PRI_LOW: "gray"}
#: Truong he so tren EC Data SLA Rule Set.
MULT_FIELDS = {PRI_URGENT: "mult_urgent", PRI_HIGH: "mult_high", PRI_NORMAL: "mult_normal", PRI_LOW: "mult_low"}
#: Uu tien Task /pm (ERPNext Task.priority).
PM_PRIORITY = {PRI_URGENT: "Urgent", PRI_HIGH: "High", PRI_NORMAL: "Medium", PRI_LOW: "Low"}

# ------------------------------------------------------------------ loai yeu cau + quy tac --
#: (rule_key, nhan tren yeu cau, nhan tren bang quy tac, so ngay lam viec mac dinh v1, ghi chu)
RULE_DEFAULTS = (
    ("pbi_new", "Power BI mới", "Power BI mới", 7, "Dashboard mới"),
    ("pbi_edit", "Sửa Power BI có sẵn", "Sửa / thêm vào Power BI có sẵn", 3, ""),
    ("crawl_new", "Crawl data mới", "Crawl data mới", 7, "Tính từ lúc đề xuất được duyệt"),
    ("data_processing", "Xử lý dữ liệu", "Xử lý / làm sạch dữ liệu", 3, ""),
    ("other", "Khác", "Khác", 3, ""),
    ("proposal_review", "", "Duyệt đề xuất data cần crawl", 1, ""),
    ("intake", "", "Tiếp nhận yêu cầu mới", 1, "Từ lúc gửi tới lúc có người nhận"),
)
MULT_DEFAULTS = {PRI_URGENT: 0.5, PRI_HIGH: 0.8, PRI_NORMAL: 1.0, PRI_LOW: 1.5}
#: Loai yeu cau nguoi gui chon (nhan) -> rule_key.
REQUEST_TYPES = tuple(r[1] for r in RULE_DEFAULTS if r[1])
TYPE_RULE_KEY = {r[1]: r[0] for r in RULE_DEFAULTS if r[1]}
#: Nhan ngan tren bang / Gantt.
TYPE_SHORT = {"Power BI mới": "Power BI", "Sửa Power BI có sẵn": "Power BI", "Crawl data mới": "Crawl data",
              "Xử lý dữ liệu": "Xử lý dữ liệu", "Khác": "Khác"}
RULE_INTAKE = "intake"
RULE_CRAWL = "crawl_new"

RULE_DRAFT = "Draft"
RULE_PENDING = "Chờ duyệt"
RULE_ACTIVE = "Đang áp dụng"
RULE_REJECTED = "Từ chối"
RULE_EXPIRED = "Hết hiệu lực"
RULE_STATUSES = (RULE_DRAFT, RULE_PENDING, RULE_ACTIVE, RULE_REJECTED, RULE_EXPIRED)

# ------------------------------------------------------------------ nhat ky (timeline) -----
EV_CREATED = "Tạo"
EV_ACCEPTED = "Nhận việc"
EV_ASSIGNEE = "Đổi người xử lý"
EV_DUE = "Đổi hạn"
EV_START = "Đổi ngày bắt đầu"
EV_PRIORITY = "Đổi ưu tiên"
EV_PAUSE = "Tạm dừng"
EV_RESUME = "Tiếp tục"
EV_DONE = "Hoàn tất"
EV_ACCEPT_OK = "Nghiệm thu đạt"
EV_ACCEPT_FAIL = "Nghiệm thu chưa đạt"
EV_AUTO_CLOSE = "Tự đóng"
EV_CANCEL = "Huỷ"
EV_PM = "Đồng bộ /pm"
EV_PM_ERROR = "Lỗi đồng bộ /pm"
LOG_EVENTS = (EV_CREATED, EV_ACCEPTED, EV_ASSIGNEE, EV_DUE, EV_START, EV_PRIORITY, EV_PAUSE, EV_RESUME,
              EV_DONE, EV_ACCEPT_OK, EV_ACCEPT_FAIL, EV_AUTO_CLOSE, EV_CANCEL, EV_PM, EV_PM_ERROR)
SRC_HUB = "Trung tâm Dữ liệu"
SRC_PM = "/pm"
SRC_SYSTEM = "Hệ thống"

# ------------------------------------------------------------------ gioi han ---------------
TITLE_MAX = 140
BODY_MAX = 5000
DATA_USED_MAX = 500
REASON_MAX = 1000
MESSAGE_MAX = 3000
LINK_MAX = 500
MAX_FILES = 5
FILE_MAX_BYTES = 10 * 1024 * 1024
#: Tep di trong than POST dang base64 (+33%); nginx chan ~25 MB (xem feedback/constants.py).
FILES_TOTAL_MAX_BYTES = 15 * 1024 * 1024
FILE_EXTS = ("png", "jpg", "jpeg", "gif", "webp", "pdf", "docx", "xlsx", "xls", "csv", "pptx", "txt", "pbix",
             "zip", "json", "sql")
#: Chong spam: so yeu cau mot nguoi gui trong mot ngay.
DAILY_LIMIT = 20

# ------------------------------------------------------------------ nhac viec / thong bao ---
#: Nhac "sap toi han" khi con <= bay nhieu ngay lam viec.
DUE_SOON_DAYS = 1
EV_NEW = "task_assigned"            # yeu cau moi -> team Data
EV_ASSIGNED = "task_assigned"       # nguoi xu ly moi (khi khong co task /pm lo viec bao)
EV_UPDATE = "mention"               # nhan / doi han / tam dung / tin nhan -> nguoi gui + nguoi theo doi
EV_MENTION = "mention"              # @ten trong tin nhan
EV_REVIEW = "approval_required"     # cho nghiem thu -> nguoi gui (can lam)
EV_DUE_SOON = "task_due_soon"
EV_OVERDUE = "task_overdue"

# ------------------------------------------------------------------ trang ------------------
ROUTE = "/du-lieu"
ROUTE_OPS = "/du-lieu/dieu-phoi"
ROUTE_AVAIL = "/du-lieu/san-co"
ROUTE_RULES = "/du-lieu/quy-tac"
#: So ngay (lich) cot "Xong" cua Dieu phoi / hang "Da xong" cua Gantt.
DONE_RECENT_DAYS = 7
#: Gantt: 3 tuan, bat dau thu Hai cua tuan truoc.
GANTT_DAYS = 21
GANTT_BACK_WEEKS = 1
#: Danh sach toi da tren trang (moi nguoi doc duoc moi yeu cau; trang chi ve bay nhieu dong).
LIST_LIMIT = 500


# =========================================================================================
# DOT 2 (PO Hoan chot 09/11/2026) - Data availability, de xuat data can crawl, ke hoach bo sung
# (DA-), do tuoi du lieu, Thu vien bao cao. Code o avail_domain / avail_repository / avail_service.
# =========================================================================================
AVAIL_DT = "EC Data Availability"
PROPOSAL_DT = "EC Data Proposal"
LIBRARY_DT = "EC Report Library"

#: Ba san chinh = ba cot cua ma tran (ten CHUAN luu trong DB; nhap "tiktok"/"Tiktok" -> "TikTok").
#: San khac (Boxme, Misa, GOV, Omisell...) vao cot "Khac" kem ten.
MAIN_PLATFORMS = ("Shopee", "TikTok", "Lazada")
OTHER_PLATFORM = "Khác"
#: Kenh dich (truong Check tren EC Data Availability) - thu tu = thu tu cham trong o ma tran.
CHANNELS = (("sharepoint", "in_sharepoint", "SharePoint"), ("dw", "in_dw", "Data Warehouse"),
            ("powerbi", "in_powerbi", "Power BI"))
CHANNEL_KEYS = tuple(c[0] for c in CHANNELS)
CHANNEL_FIELD = {c[0]: c[1] for c in CHANNELS}
CHANNEL_LABEL = {c[0]: c[2] for c in CHANNELS}
CHANNEL_SHORT = {"sharepoint": "SharePoint", "dw": "DW", "powerbi": "Power BI"}
#: Cach lay du lieu (EC Data Ticket.method).
METHODS = ("Crawl", "API sàn", "Nhập tay / file")

FREQ_HOURLY = "Theo giờ"
FREQ_DAILY = "Hằng ngày"
FREQ_WEEKLY = "Hằng tuần"
FREQ_MONTHLY = "Hằng tháng"
FREQ_NONE = "Không định kỳ"
FREQUENCIES = (FREQ_HOURLY, FREQ_DAILY, FREQ_WEEKLY, FREQ_MONTHLY, FREQ_NONE)
#: Do tuoi: "cap nhat lan cuoi" cu hon bay nhieu GIO (lich) so voi tan suat -> canh bao "Trễ cập nhật".
#: Co bien do (giờ: 1 ngay, ngày: 2 ngay, tuần: 8 ngay, tháng: 35 ngay) vi ngay cap nhat do team Data ghi
#: tay / hoan tat DA ghi - khong phai nhip dong bo tu dong. Khong dinh ky -> khong canh bao.
FRESH_MAX_HOURS = {FREQ_HOURLY: 24, FREQ_DAILY: 48, FREQ_WEEKLY: 8 * 24, FREQ_MONTHLY: 35 * 24}

PROP_PENDING = "Chờ duyệt"
PROP_APPROVED = "Đã duyệt"
PROP_REJECTED = "Từ chối"
PROP_STATUSES = (PROP_PENDING, PROP_APPROVED, PROP_REJECTED)
#: Muc can gap cua de xuat = muc uu tien de xuat cho ke hoach DA (team Data xac nhan khi len ke hoach).
PROP_URGENCIES = (PRI_NORMAL, PRI_HIGH, PRI_URGENT)
RULE_PROPOSAL = "proposal_review"
#: Chong spam: so de xuat mot nguoi gui trong mot ngay.
PROPOSAL_DAILY_LIMIT = 10
#: Bang de xuat tren trang: moi de xuat Cho duyet + bay nhieu de xuat da quyet gan nhat.
PROPOSAL_RECENT = 30

TEAM_MAX = 60
DATA_TYPE_MAX = 80
PLATFORM_MAX = 40
NOTE_MAX = 500
PURPOSE_MAX = 1000
TAGS_MAX = 140
SOURCES_MAX = 500
#: Goi y "da co dashboard tuong tu" khi go tieu de (form tao yeu cau).
SUGGEST_MIN_CHARS = 3
SUGGEST_LIMIT = 3
#: Loai yeu cau ma "Dat" + co link ket qua -> tu them vao Thu vien bao cao.
LIBRARY_TYPES = ("Power BI mới", "Sửa Power BI có sẵn")
#: Nhan hien thi cua ke hoach bo sung data (thay "Crawl data" o dau popup).
DA_TYPE_LABEL = "Bổ sung data"
#: DA-ticket tinh han theo quy tac nay (spec: "ket thuc mac dinh theo quy tac crawl").
DA_REQUEST_TYPE = "Crawl data mới"
ROUTE_LIBRARY = ROUTE_AVAIL + "?xem=thu-vien"
EV_PROPOSAL = "approval_required"   # de xuat moi -> team Data (can duyet)
