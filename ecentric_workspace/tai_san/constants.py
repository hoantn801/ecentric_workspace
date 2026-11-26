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
}
MAX_LIFE_UNDER_THRESHOLD = 36          # canh bao neu dat > 36 thang cho tai san < nguong TSCD
FIXED_ASSET_THRESHOLD = 30_000_000     # TT45/2013: duoi muc nay la cong cu dung cu

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
