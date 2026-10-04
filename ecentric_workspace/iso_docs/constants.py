# Copyright (c) 2026, eCentric and contributors
"""Thu vien tai lieu ISO - hang so (PO Hoan chot 04/10/2026, xem iso_docs/README.md).

Tai lieu = ban ghi Quality Procedure cua ERPNext (KHONG sua DocType goc): them Custom Field
ec_*, bang con EC Document Revision (lich su ban hanh), Workflow "Tai lieu ISO".
Trinh tu duyet theo QT Quan ly tai lieu 3.0: Truong BP -> Ban ISO -> TGD -> ban hanh.
"""
QP = "Quality Procedure"
REVISION_DT = "EC Document Revision"
DEPT_CHILD_DT = "EC Document Department"
HOME_DT = "EC Home Announcement"

WORKFLOW_NAME = "Tài liệu ISO"
STATE_FIELD = "ec_doc_state"

# --- trang thai workflow (7) ---
S_DRAFT = "Nháp"
S_HEAD = "Chờ trưởng bộ phận"
S_ISO = "Chờ Ban ISO"
S_CEO = "Chờ Tổng giám đốc"
S_PUBLISHED = "Ban hành"
S_WITHDRAW = "Chờ thu hồi"
S_EXPIRED = "Hết hiệu lực"
STATES = (S_DRAFT, S_HEAD, S_ISO, S_CEO, S_PUBLISHED, S_WITHDRAW, S_EXPIRED)

# --- vai tro ---
ROLE_ISO = "Ban ISO"
ROLE_CEO = "TGĐ duyệt tài liệu"
ROLE_EMPLOYEE = "Employee"          # truong BP / nguoi soan: role Employee + dieu kien tren doc
MANAGER_ROLES = ("System Manager", ROLE_ISO, ROLE_CEO)

# --- kieu sua (X.Y: X = lon, co quyet dinh; Y = nho, sua noi bo - nho thi bo buoc TGD) ---
KIND_MAJOR = "Lớn"
KIND_MINOR = "Nhỏ"
KINDS = (KIND_MAJOR, KIND_MINOR)

# --- trang thai mot dong lich su ban hanh ---
REV_EFFECTIVE = "Hiệu lực"
REV_EXPIRED = "Hết hiệu lực"        # bi phien ban moi thay
REV_WITHDRAWN = "Đã thu hồi"        # thu hoi ca tai lieu
REV_STATUSES = (REV_EFFECTIVE, REV_EXPIRED, REV_WITHDRAWN)

SOURCES = ("Soạn trên ERP", "Gói từ Claude", "Nhập file cũ")

# --- loai tai lieu: (tien to ma, ten) - cung bang voi NHIEU_LOP/iso/kiem_goi_quy_trinh.py ---
DOC_TYPES = (
    ("QT", "Quy trình"), ("QD", "Quy định"), ("QC", "Quy chế"), ("CS", "Chính sách"),
    ("HD", "Hướng dẫn"), ("BM", "Biểu mẫu"), ("TL", "Tài liệu hệ thống"),
)
CODE_PREFIXES = ("QT", "QD", "QC", "CS", "HD", "BM", "TL", "BN")
CODE_RE = r"^(QT|QD|QC|CS|HD|BM|TL|BN)-[A-Z]{2,5}-\d{2}(-\d{2})?$"

REVIEW_MONTHS_DEFAULT = 12

# --- thong bao trang chu khi ban hanh (spec PO 04/10) ---
HOME_CATEGORY = "Chính sách"
HOME_DAYS = 7                        # start_date .. start_date + 6 ngay
HOME_LINK_LABEL = "Xem tài liệu →"
HOME_LINK_PREFIX = "/tai-lieu/"
