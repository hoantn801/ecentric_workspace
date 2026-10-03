# Copyright (c) 2026, eCentric and contributors
"""Hang so cua Gop y cong ty (/gop-y). PO Hoan chot 04/10/2026, thiet ke = mockup Ban 1.

Moi ten DocType / trang thai / gioi han nam o day - service, repository, trang deu doc tu day.
"""

FEEDBACK_DT = "EC Feedback"
TOPIC_DT = "EC Feedback Topic"
MESSAGE_DT = "EC Feedback Message"
IDENTITY_DT = "EC Feedback Identity"
VOTE_DT = "EC Feedback Vote"
FILE_CHILD_DT = "EC Feedback File"
DIGEST_DT = "EC Feedback Digest"

#: Nguoi xu ly = nhan vien Active thuoc phong nay (ca phong con). PO chot 04/10: chung team
#: Management xem va nhan xu ly moi gop y, khong chia nguoi phu trach theo chu de.
HANDLER_DEPARTMENT = "Management - EC"
#: Quan tri he thong: xem duoc hop xu ly (va la nguoi DUY NHAT mo duoc danh tinh, ngoai trang).
ADMIN_ROLE = "System Manager"
#: Ghi thay nguoi gui an danh: owner / modified_by cua ban ghi la tai khoan nay, khong phai ho.
SYSTEM_USER = "Administrator"

#: Trang thai (PO chot 04/10: bo "Se lam").
ST_NEW = "Mới"
ST_VIEWING = "Đang xem"
ST_ANSWERED = "Đã trả lời"
ST_DONE = "Đã làm"
ST_DECLINED = "Không làm"
STATUSES = (ST_NEW, ST_VIEWING, ST_ANSWERED, ST_DONE, ST_DECLINED)
#: Trang thai DONG (nguoi gui bam "Chua on" mo lai duoc mot lan).
CLOSED = (ST_ANSWERED, ST_DONE, ST_DECLINED)
#: Nguoi xu ly chon duoc (Moi chi do he thong dat).
HANDLER_STATUSES = (ST_VIEWING, ST_ANSWERED, ST_DONE, ST_DECLINED)
#: Doi sang trang thai nay thi BAT BUOC co loi nhan cho nguoi gui (ly do / cau tra loi).
NEEDS_MESSAGE = (ST_ANSWERED, ST_DECLINED)
#: Lop CSS cua nhan trang thai.
STATUS_CSS = {ST_NEW: "new", ST_VIEWING: "view", ST_ANSWERED: "reply", ST_DONE: "done", ST_DECLINED: "no"}

#: Loai gop y (PO chot 04/10: giu).
KINDS = ("Đề xuất", "Phản ánh", "Câu hỏi")
KIND_DEFAULT = "Đề xuất"

#: Loai dong trong luong trao doi (EC Feedback Message.kind).
MSG_REPLY = "reply"            # loi nhan - nguoi gui hoac nguoi xu ly
MSG_NOTE = "note"              # ghi chu noi bo - nguoi gui KHONG thay
MSG_STATUS = "status"          # doi trang thai
MSG_TOPIC = "topic"            # chuyen chu de
MSG_REOPEN = "reopen"          # nguoi gui bam "Chua on"
MSG_KINDS = (MSG_REPLY, MSG_NOTE, MSG_STATUS, MSG_TOPIC, MSG_REOPEN)
ROLE_SENDER = "sender"
ROLE_HANDLER = "handler"
ROLE_SYSTEM = "system"

#: Gioi han (PO chot 04/10: 5 gop y / nguoi / ngay, tinh ca an danh).
DAILY_LIMIT = 5
TITLE_MAX = 140
BODY_MAX = 3000
MESSAGE_MAX = 3000
MAX_FILES = 5
FILE_MAX_BYTES = 5 * 1024 * 1024
#: Tong dung luong tep / lan gui: tep di trong than POST dang base64 (+33%), nginx cua site chan
#: than request ~25 MB (reference_attachment_upload_413_limit) -> 12 MB tep ~ 16 MB than.
FILES_TOTAL_MAX_BYTES = 12 * 1024 * 1024
FILE_EXTS = ("png", "jpg", "jpeg", "gif", "webp", "pdf", "docx", "xlsx", "pptx", "txt")
#: Gop y AN DANH chi nhan anh, va anh duoc ve lai (bo EXIF / metadata): PDF, Office giu ten tac gia
#: trong metadata (docProps/core.xml, /Author) - khong lam sach chac chan duoc thi khong nhan.
ANON_FILE_EXTS = ("png", "jpg", "jpeg", "gif", "webp")
#: Nguoi gui mo lai toi da bay nhieu lan cho mot gop y.
REOPEN_MAX = 1

#: Han phan hoi dau tien: 5 ngay lam viec (PO chot 04/10), chua tinh KPI.
SLA_DAYS = 5
#: Nhac "sap het han" khi con <= 1 ngay lam viec.
REMIND_DAYS_LEFT = 1
#: Lich lam viec dung chung voi SLA (EC Approval Business Calendar). Doi qua site_config.
CALENDAR_CONF_KEY = "ec_sla_business_calendar"
CALENDAR_DEFAULT = "EC_STANDARD_9_18"
#: Lich khong doc duoc (thieu calendar) -> han = so ngay lich nay, ghi Error Log.
FALLBACK_CALENDAR_DAYS = 7

#: Bang chung
HOT_VOTES = 10
BOARD_SORTS = ("nhieu-nhat", "moi-nhat")
BOARD_FILTERS = {"": None, "da-tra-loi": ST_ANSWERED, "da-lam": ST_DONE, "dang-xem": ST_VIEWING}

#: Popup trang chu: gop y "Da lam" dang tren bang chung (PO chot 04/10) hien 7 ngay.
POPUP_DAYS = 7
POPUP_CATEGORY = "Thông báo"
POPUP_PREFIX = "Bạn góp ý, công ty đã làm: "
POPUP_LINK_LABEL = "Xem bảng góp ý →"

#: Thong bao (notification_center). feedback_update: teams = False khoa cung trong events.py.
EV_SENDER = "feedback_update"
EV_NEW = "task_assigned"
EV_DUE_SOON = "task_due_soon"
EV_OVERDUE = "task_overdue"
EV_DIGEST = "announcement_urgent"     # ban tin thang cho BGD: chuong + Teams
EV_HANDLER_UPDATE = "mention"         # nguoi gui nhan them / mo lai -> nguoi xu ly
#: Gop y AN DANH: chuong "gop y moi" / "nguoi gui nhan them" KHONG gui ngay - job nhac moi gio gom lai
#: gui (chuong gui ngay thi gio Notification Log = gio nguoi gui bam, lo nguoi dang online).
PENDING_NEW = "new"
PENDING_REPLY = "reply"
PENDING_REOPEN = "reopen"

#: Ban tin thang + AI chu de nong
DIGEST_HOT_MAX = 5
AI_TEXT_MAX_CHARS = 20000
AI_MANUAL_DAILY_LIMIT = 3

#: Trang
ROUTE = "/gop-y"
ROUTE_INBOX = "/gop-y/xu-ly"
ROUTE_OVERVIEW = "/gop-y/tong-quan"
TABS = ("gui", "cua-toi", "bang-chung")
INBOX_FILTERS = ("can-xu-ly", "qua-han", "sap-het-han", "da-dong", "tat-ca")
INBOX_PAGE = 50
MY_RECENT = 4

#: Bieu tuong chu de (Select trong EC Feedback Topic) va mau.
ICONS = ("building", "heart", "flow", "monitor", "users", "dots")
COLORS = {
    "teal": ("#e6f7fa", "#0e7490"),
    "pink": ("#fdeef5", "#b4236a"),
    "purple": ("#f1edfd", "#5b3cc4"),
    "navy": ("#eef0fb", "#2C3DA6"),
    "orange": ("#fff1e8", "#c2410c"),
    "gray": ("#f3f4f6", "#4b5563"),
}
COLOR_DEFAULT = "navy"
