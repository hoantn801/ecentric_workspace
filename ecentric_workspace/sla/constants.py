# Copyright (c) 2026, eCentric and contributors
"""Hang so cua module SLA - KHONG import frappe.

Moi chuoi dung o service/controller/patch deu phai lay tu day. Ly do cu the,
khong phai "cho dep": ma nhom (`group_key`) va ma trang thai duoc ghi thang vao
cot cua `EC SLA Obligation` va duoc doc lai boi bang diem, boi UI, va boi patch
seed. Mot chuoi go sai o mot cho se tao ra mot nhom rong - va mot nhom rong
hien ra la 100%, tuc la loi im lang theo huong CO LOI cho nguoi bi do. Do la
dung kieu loi nguy hiem nhat cua he nay.
"""

# --------------------------------------------------------------------------- #
# Nhom nghia vu (5 nhom da chot voi chu so huu 16/09)
# --------------------------------------------------------------------------- #
GROUP_APPROVAL = "approval"      # Phan hoi phe duyet
GROUP_ATTENDANCE = "attendance"  # Cham cong
GROUP_RSVP = "rsvp"              # RSVP lich hop
GROUP_WEEKLY_REPORT = "weekly"   # Bao cao tuan
GROUP_TASK = "task"              # Cong viec - DO NHUNG KHONG TINH VAO SLA

ALL_GROUPS = (GROUP_APPROVAL, GROUP_ATTENDANCE, GROUP_RSVP, GROUP_WEEKLY_REPORT, GROUP_TASK)

# Nhan tieng Viet - hien tren trang /sla. Giu o day de UI va patch seed khong
# lech nhau.
GROUP_LABEL = {
    GROUP_APPROVAL: "Phản hồi phê duyệt",
    GROUP_ATTENDANCE: "Chấm công",
    GROUP_RSVP: "RSVP lịch họp",
    GROUP_WEEKLY_REPORT: "Báo cáo tuần",
    GROUP_TASK: "Công việc",
}

GROUP_UNIT = {
    GROUP_APPROVAL: "hồ sơ",
    GROUP_ATTENDANCE: "ngày công",
    GROUP_RSVP: "lời mời",
    GROUP_WEEKLY_REPORT: "tuần",
    GROUP_TASK: "đầu việc",
}

# Co MAU chot bao nhieu dau viec thi ti le moi co nghia. Duoi nguong nay bang
# diem hien "chua du mau" thay vi mot con so %. Khong phai thi vi - mot nguoi co
# 1 dau viec va lam dung se hien 100%, xep tren nguoi co 80 dau viec dung 78.
GROUP_MIN_SAMPLE = {
    GROUP_APPROVAL: 5,
    GROUP_ATTENDANCE: 5,
    GROUP_RSVP: 5,
    # 1, KHONG phai 3. Chu so huu chot 21/09 sau khi nhin du lieu that: mot
    # thang chi co 4-5 tuan, nen doi du 3 tuan la de ca cong ty nhin mot cot
    # TRONG trong hai phan ba dau thang - trong khi ho DA bi tinh diem roi.
    # Nguong khong giau duoc hinh phat, no chi giau LY DO.
    #
    # Danh doi da biet truoc: voi 1 tuan, ti le nhom chi co 0% hoac 100%. Chap
    # nhan, vi voi nhom nay mot con so nhay con hon mot o trong bi doc thanh
    # "khong co du lieu".
    #
    # Ban ghi `EC SLA Obligation Type` phai doi theo (patch p012): day la con so
    # de CHAM, ban ghi kia la con so de HIEN.
    GROUP_WEEKLY_REPORT: 1,
    GROUP_TASK: 5,
}

# Nhom nao duoc cong vao %SLA thang. `task` bi loai theo quyet dinh 16/09:
# van do, van hien, nhung khong vao mau so.
GROUP_COUNTS_TOWARD_SLA = {
    GROUP_APPROVAL: 1,
    GROUP_ATTENDANCE: 1,
    GROUP_RSVP: 1,
    GROUP_WEEKLY_REPORT: 1,
    GROUP_TASK: 0,
}

# Nguong cho TONG: KHONG CO. Chu so huu chot 18/09.
#
# Lap luan cua ong ay, va no dung: mot dau viec du dung le van la MOT dau viec co
# han, va no da tac dong toi ti le tong roi. Dat mot nguong o day khong lam con
# so chinh xac hon - no chi lam con so BIEN MAT, va nguoi doc thi khong biet minh
# dang o dau.
#
# Vi sao nguong cua TUNG NHOM van giu (xem GROUP_MIN_SAMPLE / DEFAULT_MIN_SAMPLE):
# do la mot cau hoi khac. Ti le RIENG cua mot nhom la thu dem ra so giua nguoi
# nay voi nguoi kia, va 1/1 = 100% hay 1/2 = 50% nhay qua manh de so. Con ti le
# TONG thi khong dung de so - no la buc tranh cua chinh nguoi do, va no phai hien
# ngay tu dau viec dau tien.
#
# `scoring._finalize` van co `if bucket["scored"]` truoc phep chia, nen 0 dau viec
# van tra ve rate=None - "chua co dau viec nao", khong phai "chia cho khong".
OVERALL_MIN_SAMPLE = 0

# Nguong cho mot nhom KHONG nam trong danh muc tren (loai nghia vu them sau).
# Mac dinh phai la mot so DUONG: mac dinh 0 nghia la mot nhom moi voi dung mot
# dau viec se hien 100%, tuc la loi nay tu dong quay lai moi lan ai do them mot
# loai nghia vu.
DEFAULT_MIN_SAMPLE = 5

GROUP_SORT = {
    GROUP_APPROVAL: 10,
    GROUP_ATTENDANCE: 20,
    GROUP_RSVP: 30,
    GROUP_WEEKLY_REPORT: 40,
    GROUP_TASK: 90,
}

# --------------------------------------------------------------------------- #
# Loai nghia vu (seed p001)
# --------------------------------------------------------------------------- #
TYPE_APPROVAL_STEP = "APPROVAL_STEP"
TYPE_ATTENDANCE_DAY = "ATTENDANCE_DAY"
TYPE_RSVP = "RSVP"
TYPE_WEEKLY_REPORT = "WEEKLY_REPORT"
TYPE_TASK = "TASK"

TYPE_TO_GROUP = {
    TYPE_APPROVAL_STEP: GROUP_APPROVAL,
    TYPE_ATTENDANCE_DAY: GROUP_ATTENDANCE,
    TYPE_RSVP: GROUP_RSVP,
    TYPE_WEEKLY_REPORT: GROUP_WEEKLY_REPORT,
    TYPE_TASK: GROUP_TASK,
}

TYPE_NAME = {
    TYPE_APPROVAL_STEP: "Bước phê duyệt",
    TYPE_ATTENDANCE_DAY: "Ngày công",
    TYPE_RSVP: "Phản hồi lời mời họp",
    TYPE_WEEKLY_REPORT: "Báo cáo tuần",
    TYPE_TASK: "Đầu việc (ngoài SLA)",
}

# --------------------------------------------------------------------------- #
# Trang thai nghia vu
# --------------------------------------------------------------------------- #
STATUS_OPEN = "Open"          # chua den han, chua dong
STATUS_MET = "Met"            # dong truoc han  -> tu so
STATUS_LATE = "Late"          # dong sau han    -> mau so, khong vao tu so
STATUS_MISSED = "Missed"      # het ky ma khong dong
STATUS_EXCLUDED = "Excluded"  # khong tinh diem (nghi phep, dieu chinh...)
STATUS_CANCELLED = "Cancelled"  # nguon bi huy -> bien mat khoi moi phep tinh

ALL_STATUSES = (STATUS_OPEN, STATUS_MET, STATUS_LATE, STATUS_MISSED,
                STATUS_EXCLUDED, STATUS_CANCELLED)

# Trang thai duoc CHAM DIEM: nam trong mau so cua ti le.
# `Open` co mat o day co dieu kien - xem domain/scoring.py. Mot nghia vu con mo
# NHUNG da qua han (`is_breached`) van phai vao mau so, neu khong thi cach de
# nhat de dat 100%% la khong bao gio dong viec.
SCORED_STATUSES = (STATUS_MET, STATUS_LATE, STATUS_MISSED)

TERMINAL_STATUSES = (STATUS_MET, STATUS_LATE, STATUS_MISSED, STATUS_EXCLUDED,
                     STATUS_CANCELLED)

# --------------------------------------------------------------------------- #
# Luat tinh han
# --------------------------------------------------------------------------- #
DUE_BUSINESS_HOURS = "Business Hours"   # gio lam viec, tru le/cuoi tuan
DUE_CALENDAR_HOURS = "Calendar Hours"   # gio dong ho
DUE_FIXED_TIME = "Fixed Time Of Day"    # vd cham cong: dau ca + an han
DUE_EXPLICIT = "Explicit"               # nguon tu dua due_at vao

ALL_DUE_RULES = (DUE_BUSINESS_HOURS, DUE_CALENDAR_HOURS, DUE_FIXED_TIME, DUE_EXPLICIT)

# --------------------------------------------------------------------------- #
# Ly do tam dung
# --------------------------------------------------------------------------- #
PAUSE_ABSENCE = "Absence"
PAUSE_WAITING_INFO = "Waiting Information"
PAUSE_HOLIDAY = "Holiday"
PAUSE_MANUAL = "Manual"

ALL_PAUSE_REASONS = (PAUSE_ABSENCE, PAUSE_WAITING_INFO, PAUSE_HOLIDAY, PAUSE_MANUAL)

# --------------------------------------------------------------------------- #
# Ly do loai tru chuan (chuoi co dinh, de UI va bao cao dem duoc)
# --------------------------------------------------------------------------- #
# Loai nghia vu chua ai cau hinh han. 57/60 buoc duyet dang o trang thai nay.
# KHONG duoc cham la dung han: mot buoc duyet khong co han ma tinh la dung han
# thi ca nhom Phan hoi phe duyet se hien 100% trong khi chua do duoc gi.
EXCL_NO_POLICY = "Chưa cấu hình hạn SLA cho bước này"
EXCL_ANY_ONE = "Người khác trong cùng cấp đã xử lý (Any-One)"

# --------------------------------------------------------------------------- #
# Hanh dong dieu chinh
# --------------------------------------------------------------------------- #
ADJ_EXCLUDE = "Exclude"
ADJ_RESTORE = "Restore"
ADJ_MARK_MET = "Mark Met"
ADJ_MARK_MISSED = "Mark Missed"
ADJ_EXTEND_DUE = "Extend Due"

ALL_ADJUSTMENTS = (ADJ_EXCLUDE, ADJ_RESTORE, ADJ_MARK_MET, ADJ_MARK_MISSED, ADJ_EXTEND_DUE)

# --------------------------------------------------------------------------- #
# Ten DocType
# --------------------------------------------------------------------------- #
DT_TYPE = "EC SLA Obligation Type"
DT_POLICY = "EC SLA Policy"
DT_OBLIGATION = "EC SLA Obligation"
DT_PAUSE = "EC SLA Pause Segment"
DT_ADJUSTMENT = "EC SLA Adjustment"

# --------------------------------------------------------------------------- #
# Pham vi quyen
# --------------------------------------------------------------------------- #
SCOPE_SELF = "self"
SCOPE_DEPARTMENT = "department"
SCOPE_ALL = "all"

# Phong Ban Giam doc - xem duoc tat ca. Ten docname trong ERPNext co hau to cong
# ty. Ghi de duoc qua site_config de bench khac abbr van chay.
MANAGEMENT_DEPARTMENT_DEFAULT = "Management - EC"
MANAGEMENT_DEPARTMENT_CONF_KEY = "ec_sla_management_department"

# --------------------------------------------------------------------------- #
# Khac
# --------------------------------------------------------------------------- #
PERIOD_FORMAT = "%Y-%m"        # khoa ky: "2026-09"
DEDUPE_SEPARATOR = ":"
MAX_PAGE_SIZE = 500
