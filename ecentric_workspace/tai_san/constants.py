# Copyright (c) 2026, eCentric and contributors
"""Quan ly tai san & thiet bi (/tai-san) - hang so dot 0 (khao sat + plan 26/11/2026, xem README).

Thiet bi = ban ghi Asset GOC cua ERPNext (KHONG sua DocType goc, KHONG tao DocType tai san thu hai):
them Custom Field ec_* (fixtures), bang con EC Asset Spec (cau hinh goc trong may).
Linh kien lap them = Asset rieng tro ve may me qua custom_installed_on (field co san tren site).
"""
ASSET = "Asset"
CATEGORY = "Asset Category"
SPEC_DT = "EC Asset Spec"
EMPLOYEE = "Employee"
MODULE = "Tai San"

ROLE_MANAGER = "EC Asset Manager"

# --- field CO SAN tren site (tao tay thang 08/2026, KHONG nam trong fixtures cua app) ---
# Giu nguyen ten (doi ten = migrate du lieu 54 may). Code luon doc qua hang so nay.
OPS_STATUS_FIELD = "custom_asset_"           # nhan "Asset Status" - trang thai van hanh that
TAG_FIELD = "custom_asset_tag"               # EC202400001
SERIAL_FIELD = "custom_serie_number"
INSTALLED_ON_FIELD = "custom_installed_on"   # Link Asset: linh kien nay dang lap trong may nao
INSTALLED_DATE_FIELD = "custom_installed_date"
OPS_STATUS_CUSTOM_FIELD = ASSET + "-" + OPS_STATUS_FIELD

# --- trang thai van hanh (gia tri luu = tieng Anh nhu site dang dung; nhan hien thi tieng Viet) ---
ST_AVAILABLE = "Available"
ST_RESERVED = "Reserved"
ST_IN_USE = "In Use"
ST_PENDING_CHECK = "Pending Check"    # moi (dot 0): vua thu hoi, cho kiem tra / xoa du lieu
ST_BROKEN = "Broken"                  # moi (dot 0): hong, cho quyet dinh sua / thanh ly
ST_UNDER_REPAIR = "Under Repair"
ST_LOST = "Lost"
ST_DISPOSED = "Disposed"
ST_RETIRED = "Retired"
# Thu tu chuan cua o Select sau dot 0.
STATUSES = (ST_AVAILABLE, ST_RESERVED, ST_IN_USE, ST_PENDING_CHECK, ST_BROKEN,
            ST_UNDER_REPAIR, ST_LOST, ST_DISPOSED, ST_RETIRED)
STATUS_LABELS = {
    ST_AVAILABLE: "Sẵn sàng", ST_RESERVED: "Đã giữ chỗ", ST_IN_USE: "Đang dùng",
    ST_PENDING_CHECK: "Chờ kiểm tra", ST_BROKEN: "Hỏng chờ xử lý", ST_UNDER_REPAIR: "Đang sửa",
    ST_LOST: "Mất", ST_DISPOSED: "Thanh lý", ST_RETIRED: "Ngừng dùng",
}
# Trang thai ma may phai co nguoi giu / khong duoc co nguoi giu.
HOLDER_REQUIRED = (ST_IN_USE,)
HOLDER_FORBIDDEN = (ST_AVAILABLE, ST_PENDING_CHECK, ST_DISPOSED, ST_RETIRED)

# --- tinh trang (khac trang thai: may hong mot phan van co the Dang dung) ---
COND_GOOD = "Good"
COND_PARTIAL = "Partially Damaged"
COND_FULL = "Fully Damaged"
CONDITIONS = (COND_GOOD, COND_PARTIAL, COND_FULL)

# --- hinh thuc so huu ---
OWN_COMPANY = "Owned"
OWN_RENTED = "Rented"
OWN_PERSONAL = "Personal"      # may ca nhan nhan phu cap laptop
OWNERSHIPS = (OWN_COMPANY, OWN_RENTED, OWN_PERSONAL)

# --- mac dinh theo loai (Asset Category). Laptop ~10 tr la cong cu dung cu (<30 tr, TT45/2013):
# phan bo toi da 3 nam -> 36 thang. Linh kien 24 thang. Finance xac nhan truoc khi vao PnL. ---
CATEGORY_DEFAULTS = {
    "LAPTOP": {"life": 36, "component": 0,
               "spec": "CPU, RAM, SSD, Màn hình, GPU, Hệ điều hành"},
    "PC": {"life": 36, "component": 0,
           "spec": "CPU, Mainboard, RAM, SSD, HDD, GPU, PSU, Case"},
    "MONITOR": {"life": 36, "component": 0, "spec": "Kích thước, Độ phân giải, Cổng kết nối"},
    "PRINTER": {"life": 36, "component": 0, "spec": "Loại máy, Kết nối"},
    "RAM": {"life": 24, "component": 1, "spec": "Dung lượng, Chuẩn, Bus"},
    # Dot 3 (thiet bi livestream / van phong / linh kien khac): chi la MAC DINH - Asset Category phai
    # tao tay tren Desk (ERPNext bat buoc khai tai khoan ke toan cho tung loai), co ten khop la ap.
    "SSD": {"life": 24, "component": 1, "spec": "Dung lượng, Chuẩn (NVMe / SATA)"},
    "GPU": {"life": 24, "component": 1, "spec": "Chip, VRAM"},
    "CAMERA": {"life": 36, "component": 0, "spec": "Model, Cảm biến, Ống kính, Cổng ra"},
    "LIGHT": {"life": 24, "component": 0, "spec": "Công suất, Nhiệt màu, Kích thước"},
    "MIC": {"life": 24, "component": 0, "spec": "Loại, Kết nối"},
    "CAPTURE": {"life": 24, "component": 1, "spec": "Model, Độ phân giải, Kết nối"},
    "PHONE": {"life": 24, "component": 0, "spec": "Model, Bộ nhớ, IMEI"},
    "TABLET": {"life": 36, "component": 0, "spec": "Model, Bộ nhớ"},
    "NETWORK": {"life": 36, "component": 0, "spec": "Model, Chuẩn Wi-Fi, Cổng"},
}
MAX_LIFE_UNDER_THRESHOLD = 36          # canh bao neu dat > 36 thang cho tai san < nguong TSCD
FIXED_ASSET_THRESHOLD = 30_000_000     # TT45/2013: duoi muc nay la cong cu dung cu
RETURN_CATCHUP_DAYS = 3                # job thu hoi quet lai 3 ngay gan nhat (dem loi khong bi bo sot)
MAX_LIFE_MONTHS = 240                  # tran thoi gian khau hao quan tri (20 nam)

# --- ra soat du lieu (domain.audit_assets) ---
SHARED_CATEGORIES = ("PRINTER",)       # dung chung, Dang dung khong can nguoi giu
COMPONENT_PRICE_ALERT = 5_000_000      # linh kien lap them gia >= muc nay -> nghi nhap nham
PLACEHOLDER_SERIALS = ("", "UNKNOW", "UNKNOWN", "N/A", "NA", "-")
TAG_PATTERN = r"^EC\d{9}(-\d+)?$"
EMPLOYEE_LEFT = "Left"

# --- ma van de ra soat (on dinh, dung lam khoa loc) ---
ISSUE_HOLDER_LEFT = "holder_left"
ISSUE_AVAILABLE_WITH_HOLDER = "available_with_holder"
ISSUE_IN_USE_NO_HOLDER = "in_use_no_holder"
ISSUE_DUP_SERIAL = "duplicate_serial"
ISSUE_NO_SERIAL = "missing_serial"
ISSUE_BAD_TAG = "bad_tag"
ISSUE_DATE_ORDER = "use_before_purchase"
ISSUE_COMPONENT_PRICE = "component_price"
ISSUE_COMPONENT_STATUS = "component_parent_status"
ISSUE_NO_PRICE = "missing_price"
ISSUE_LABELS = {
    ISSUE_HOLDER_LEFT: "Người giữ đã nghỉ việc nhưng máy vẫn Đang dùng",
    ISSUE_AVAILABLE_WITH_HOLDER: "Ghi Sẵn sàng nhưng vẫn còn người giữ",
    ISSUE_IN_USE_NO_HOLDER: "Ghi Đang dùng nhưng không có người giữ",
    ISSUE_DUP_SERIAL: "Serial trùng với máy khác",
    ISSUE_NO_SERIAL: "Thiếu serial thật",
    ISSUE_BAD_TAG: "Tag sai mẫu ECYYYYNNNNN",
    ISSUE_DATE_ORDER: "Ngày đưa vào dùng trước ngày mua",
    ISSUE_COMPONENT_PRICE: "Giá linh kiện bất thường",
    ISSUE_COMPONENT_STATUS: "Trạng thái linh kiện khác máy mẹ",
    ISSUE_NO_PRICE: "Chưa có nguyên giá",
}

# =============================================================== dot 1-3 =====
EVENT_DT = "EC Asset Event"
REPAIR_DT = "EC Asset Repair"
MONTHLY_DT = "EC Asset Monthly"
COUNT_DT = "EC Asset Count"
COUNT_ITEM_DT = "EC Asset Count Item"
DEPARTMENT = "Department"
ITEM = "Item"

DEFAULT_LIFE_MONTHS = 36
RESERVED_FOR_FIELD = "ec_reserved_for"     # Link Employee - giu cho ai (dot 1)
END_DATE_FIELD = "ec_end_date"             # ngay ghi giam (thanh ly / mat) - dung khau hao

# --- vai tro ---
ROLE_SYSTEM = "System Manager"
ROLE_HOF = "EC HOF"
ROLE_FINANCE = "EC Finance"
ROLE_CEO = "EC CEO"
ROLE_OPS = "EC Ops System"            # nhom Operation cua Clearance / NSP / Asset Request
MANAGER_ROLES = (ROLE_SYSTEM, ROLE_MANAGER)
COST_ROLES = (ROLE_SYSTEM, ROLE_MANAGER, ROLE_HOF, ROLE_FINANCE, ROLE_CEO)
FINANCE_ROLES = (ROLE_SYSTEM, ROLE_HOF, ROLE_FINANCE)
OVERVIEW_ROLES = COST_ROLES

# --- thao tac (lifecycle.TRANSITIONS) ---
A_RESERVE = "reserve"
A_UNRESERVE = "unreserve"
A_ASSIGN = "assign"
A_TRANSFER = "transfer"
A_RETURN = "return"
A_CHECK_PASS = "check_pass"
A_CHECK_FAIL = "check_fail"
A_BREAK = "break"
A_REPAIR_START = "repair_start"
A_REPAIR_DONE = "repair_done"
A_REPAIR_FAIL = "repair_fail"
A_LOST = "lost"
A_FOUND = "found"
A_DISPOSE = "dispose"
A_RETIRE = "retire"
ACTION_LABELS = {
    A_RESERVE: "Giữ chỗ", A_UNRESERVE: "Huỷ giữ chỗ", A_ASSIGN: "Cấp phát", A_TRANSFER: "Điều chuyển",
    A_RETURN: "Thu hồi", A_CHECK_PASS: "Kiểm tra đạt", A_CHECK_FAIL: "Kiểm tra không đạt",
    A_BREAK: "Báo hỏng", A_REPAIR_START: "Gửi sửa", A_REPAIR_DONE: "Nhận lại sau sửa",
    A_REPAIR_FAIL: "Sửa không được", A_LOST: "Báo mất", A_FOUND: "Tìm lại được",
    A_DISPOSE: "Thanh lý", A_RETIRE: "Ngừng dùng",
}

# --- su kien (EC Asset Event.event_type) ---
EV_INTAKE = "Intake"
EV_RESERVE = "Reserve"
EV_UNRESERVE = "Unreserve"
EV_ASSIGN = "Assign"
EV_TRANSFER = "Transfer"
EV_RETURN = "Return"
EV_CHECK_PASS = "Check Passed"
EV_CHECK_FAIL = "Check Failed"
EV_BREAK = "Broken"
EV_REPAIR_START = "Repair Start"
EV_REPAIR_DONE = "Repair Done"
EV_REPAIR_FAIL = "Repair Failed"
EV_LOST = "Lost"
EV_FOUND = "Found"
EV_DISPOSE = "Disposed"
EV_RETIRE = "Retired"
EV_ACK = "Acknowledged"
EV_DAMAGE_REPORT = "Damage Reported"
EV_COMPONENT_IN = "Component Installed"
EV_COMPONENT_OUT = "Component Removed"
EV_SPEC = "Spec Updated"
EV_COUNT = "Counted"
EV_EDIT = "Edited"
EVENT_TYPES = (EV_INTAKE, EV_RESERVE, EV_UNRESERVE, EV_ASSIGN, EV_TRANSFER, EV_RETURN,
               EV_CHECK_PASS, EV_CHECK_FAIL, EV_BREAK, EV_REPAIR_START, EV_REPAIR_DONE,
               EV_REPAIR_FAIL, EV_LOST, EV_FOUND, EV_DISPOSE, EV_RETIRE, EV_ACK, EV_DAMAGE_REPORT,
               EV_COMPONENT_IN, EV_COMPONENT_OUT, EV_SPEC, EV_COUNT, EV_EDIT)
EVENT_LABELS = {
    EV_INTAKE: "Nhập kho", EV_RESERVE: "Giữ chỗ", EV_UNRESERVE: "Huỷ giữ chỗ", EV_ASSIGN: "Cấp phát",
    EV_TRANSFER: "Điều chuyển", EV_RETURN: "Thu hồi", EV_CHECK_PASS: "Kiểm tra đạt",
    EV_CHECK_FAIL: "Kiểm tra không đạt", EV_BREAK: "Báo hỏng", EV_REPAIR_START: "Gửi sửa",
    EV_REPAIR_DONE: "Sửa xong", EV_REPAIR_FAIL: "Không sửa được", EV_LOST: "Báo mất",
    EV_FOUND: "Tìm lại được", EV_DISPOSE: "Thanh lý", EV_RETIRE: "Ngừng dùng",
    EV_ACK: "Nhân viên xác nhận đã nhận", EV_DAMAGE_REPORT: "Nhân viên báo hỏng",
    EV_COMPONENT_IN: "Lắp linh kiện", EV_COMPONENT_OUT: "Tháo linh kiện",
    EV_SPEC: "Cập nhật cấu hình", EV_COUNT: "Kiểm kê", EV_EDIT: "Sửa thông tin",
}

# --- sua chua ---
REP_OPEN = "Open"
REP_IN_REPAIR = "In Repair"
REP_DONE = "Done"
REP_CANCELLED = "Cancelled"
REPAIR_STATUSES = (REP_OPEN, REP_IN_REPAIR, REP_DONE, REP_CANCELLED)
REPAIR_STATUS_LABELS = {REP_OPEN: "Chờ gửi", REP_IN_REPAIR: "Đang sửa", REP_DONE: "Đã xong",
                        REP_CANCELLED: "Đã huỷ"}
MODE_INTERNAL = "Internal"
MODE_WARRANTY = "Warranty"
MODE_EXTERNAL = "External"
REPAIR_MODES = (MODE_INTERNAL, MODE_WARRANTY, MODE_EXTERNAL)
REPAIR_MODE_LABELS = {MODE_INTERNAL: "Sửa nội bộ", MODE_WARRANTY: "Bảo hành",
                      MODE_EXTERNAL: "Sửa bên ngoài"}
RES_FIXED = "Fixed"
RES_UNFIXABLE = "Unfixable"
REPAIR_RESULTS = (RES_FIXED, RES_UNFIXABLE)
DAMAGE_PARTIAL = "Partial"
DAMAGE_FULL = "Full"
DAMAGE_LOST = "Lost"
DAMAGE_LEVELS = (DAMAGE_PARTIAL, DAMAGE_FULL, DAMAGE_LOST)
REPAIR_APPROVAL_THRESHOLD = 3_000_000   # chi phi du kien > muc nay: tao phieu Asset Damage/Loss (gia dinh, cho PO chot)
REPAIR_OVERDUE_DAYS = 0                 # qua ngay du kien nhan lai la tre

# --- kiem ke (dot 3) ---
CNT_OPEN = "Open"
CNT_CLOSED = "Closed"
CR_OK = "OK"
CR_WRONG_HOLDER = "Wrong Holder"
CR_WRONG_STATUS = "Wrong Status"
CR_NOT_FOUND = "Not Found"
CR_DAMAGED = "Damaged"
COUNT_RESULTS = (CR_OK, CR_WRONG_HOLDER, CR_WRONG_STATUS, CR_NOT_FOUND, CR_DAMAGED)
COUNT_RESULT_LABELS = {CR_OK: "Đúng như sổ", CR_WRONG_HOLDER: "Sai người giữ",
                       CR_WRONG_STATUS: "Sai trạng thái", CR_NOT_FOUND: "Không tìm thấy",
                       CR_DAMAGED: "Hỏng"}

# --- canh bao tren Tong quan ---
WARRANTY_SOON_DAYS = 60
IDLE_ALERT_DAYS = 60                    # may Sang sang nam kho qua lau
OLD_AGE_MONTHS = 48                     # may tren 4 nam
REPEAT_REPAIR_COUNT = 3                 # sua cung mot may lan thu 3
RETURN_HORIZON_DAYS = 30                # nguoi nghi trong 30 ngay toi
ONBOARD_HORIZON_DAYS = 30
AGE_BUCKETS = ((12, "< 1 năm"), (24, "1–2 năm"), (36, "2–3 năm"), (None, "> 3 năm"))
STOCK_BUCKET = "Kho chung"              # chi phi may nam kho tinh vao nhom nay
NO_DEPT_BUCKET = "Chưa gắn phòng"       # may co nguoi giu nhung thieu phong ban (loi du lieu)
OUT_OF_BOOK = (ST_LOST, ST_DISPOSED, ST_RETIRED)   # khong con nam trong so dem theo phong

# --- nguon phieu (Approval Center) - chi DOC + link, khong ghi thay luong duyet ---
SRC_ASSET_REQUEST = "EC Asset Request"
SRC_NSP = "EC New Staff Preparation"
SRC_CLEARANCE = "EC Clearance Request"
SRC_DAMAGE = "EC Asset Damage Loss Request"
APPROVAL_REQUEST_DT = "EC Approval Request"
SOURCE_ROUTES = {SRC_ASSET_REQUEST: "/approvals/asset-request", SRC_NSP: "/approvals/new-staff-preparation",
                 SRC_CLEARANCE: "/approvals/clearance-request", SRC_DAMAGE: "/approvals/asset-damage-loss"}
SOURCE_LABELS = {SRC_ASSET_REQUEST: "Asset Request", SRC_NSP: "Chuẩn bị nhân sự mới",
                 SRC_CLEARANCE: "Clearance", SRC_DAMAGE: "Báo hỏng / mất"}
APPROVED = "Approved"
OPEN_APPROVAL = ("Pending", "Information Required", "Approved")
FULFILL_OPEN = ("Assigned", "In Progress")

# --- route trang ---
ROUTE_HOME = "tai-san"
ROUTE_LIST = "tai-san/thiet-bi"
ROUTE_MOVES = "tai-san/luan-chuyen"
ROUTE_REPAIRS = "tai-san/sua-chua"
ROUTE_MINE = "tai-san/cua-toi"
ROUTE_COUNT = "tai-san/kiem-ke"

# --- checklist ---
HANDOVER_CHECKLIST = ("Cài phần mềm chuẩn (Office, Teams, VPN)", "Đăng nhập Microsoft 365",
                      "Kèm sạc", "Kèm túi chống sốc", "Chụp ảnh tình trạng khi giao")
RETURN_CHECKLIST = ("Ngoại hình: không nứt vỡ, đủ phím", "Đủ sạc và phụ kiện đã cấp",
                    "Xoá dữ liệu, đăng xuất M365 / Lark / trình duyệt", "Cài lại Windows chuẩn công ty")

# --- ban quyen phan mem (dot 4, Hoan 26/11/2026) ---
# Ban quyen la "mot dang tai san" voi nguoi dung (cung module, cung trang Cua toi) nhung KHONG phai
# Asset ERPNext: co so cho (seat), co han va gia han theo ky - Asset goc khong mo ta duoc.
LICENSE_DT = "EC Software License"
LICENSE_SEAT_DT = "EC Software License Seat"
LICENSE_RENEWAL_DT = "EC Software License Renewal"
ROUTE_LICENSES = "tai-san/ban-quyen"

LT_SUBSCRIPTION = "Subscription"
LT_PERPETUAL = "Perpetual"
LICENSE_TYPES = (LT_SUBSCRIPTION, LT_PERPETUAL)
LICENSE_TYPE_LABELS = {LT_SUBSCRIPTION: "Thuê bao (có hạn)", LT_PERPETUAL: "Vĩnh viễn"}

CY_MONTHLY = "Monthly"
CY_QUARTERLY = "Quarterly"
CY_YEARLY = "Yearly"
CY_OTHER = "Other"
BILLING_CYCLES = (CY_MONTHLY, CY_QUARTERLY, CY_YEARLY, CY_OTHER)
BILLING_CYCLE_LABELS = {CY_MONTHLY: "Theo tháng", CY_QUARTERLY: "Theo quý", CY_YEARLY: "Theo năm",
                        CY_OTHER: "Kỳ khác"}
CYCLE_MONTHS = {CY_MONTHLY: 1, CY_QUARTERLY: 3, CY_YEARLY: 12}

LS_ACTIVE = "Active"
LS_EXPIRED = "Expired"
LS_CANCELLED = "Cancelled"
LICENSE_STATUSES = (LS_ACTIVE, LS_EXPIRED, LS_CANCELLED)
LICENSE_STATUS_LABELS = {LS_ACTIVE: "Đang dùng", LS_EXPIRED: "Hết hạn", LS_CANCELLED: "Đã huỷ"}

SEAT_ACTIVE = "Active"
SEAT_REVOKED = "Revoked"
SEAT_STATUSES = (SEAT_ACTIVE, SEAT_REVOKED)

LICENSE_CATEGORIES = ("Văn phòng", "Thiết kế", "AI", "Phát triển", "Bảo mật", "Dữ liệu", "Khác")

# Nhac han: truoc 30 ngay; goi ngan han (theo thang / ky <= 31 ngay) truoc 10 ngay (Hoan chot 26/11).
LICENSE_LEAD_DAYS = 30
LICENSE_LEAD_DAYS_SHORT = 10
SHORT_TERM_MAX_DAYS = 31
# Giai doan nhac (ghi vao alert_stage de moi moc chi bao MOT lan cho moi han).
STAGE_OK = "OK"
STAGE_DUE = "Due"
STAGE_EXPIRED = "Expired"
STAGE_LABELS = {STAGE_OK: "Còn hạn", STAGE_DUE: "Sắp hết hạn", STAGE_EXPIRED: "Đã quá hạn"}
