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


# ====================================================================== DOT 3 (09/11/2026) ===
# Phan noi them cua dot 3 - sua + duyet quy tac thoi han, chuyen phieu Data Request cu.
# (Noi cuoi file thay vi chen vao cac khoi o tren: dot 2 sua song song cung file.)

# ------------------------------------------------------------------ quy tac: sua + duyet ----
#: Nguoi de xuat rut lai ban nhap / ban dang cho duyet (giu ban ghi de con dau vet, khong xoa).
RULE_CANCELLED = "Đã huỷ"
RULE_STATUSES = RULE_STATUSES + (RULE_CANCELLED,)
#: Moi luc chi MOT thay doi quy tac dang mo (nhap hoac cho duyet).
RULE_OPEN = (RULE_DRAFT, RULE_PENDING)
RULE_STATUS_CSS = {RULE_DRAFT: "gray", RULE_PENDING: "amber", RULE_ACTIVE: "green", RULE_REJECTED: "red",
                   RULE_EXPIRED: "muted", RULE_CANCELLED: "muted"}
RULE_STATUS_LABEL = {RULE_DRAFT: "Bản nháp"}
#: Gioi han nhap (PO chot): so ngay la so nguyen 1..60, he so 0,25..3.
RULE_DAYS_MIN, RULE_DAYS_MAX = 1, 60
RULE_MULT_MIN, RULE_MULT_MAX = 0.25, 3.0
RULE_REASON_MAX = 1000
EV_RULE_REVIEW = "approval_required"   # gui duyet -> nguoi duyet quy tac (ERP + Teams)
EV_RULE_UPDATE = "mention"             # duyet / tu choi / rut lai -> nguoi lien quan

# ------------------------------------------------------------------ phieu Data Request cu ---
LEGACY_DT = "EC Data Request"
LEGACY_APPROVAL_TYPE = "DATA_REQUEST"
LEGACY_REQUEST_DT = "EC Approval Request"
LEGACY_ACTION_DT = "EC Approval Action"
#: Route cu cua the "Data Request" trong Approval Center - patch p003 chi doi route khi dang la mot
#: trong cac gia tri nay (khong de len route ai do da chinh tay).
LEGACY_ROUTES = ("", "/approvals/data-request", "approvals/data-request")
EV_LEGACY = "Chuyển từ phiếu cũ"
EV_LEGACY_HISTORY = "Lịch sử phiếu cũ"
LOG_EVENTS = LOG_EVENTS + (EV_LEGACY, EV_LEGACY_HISTORY)
