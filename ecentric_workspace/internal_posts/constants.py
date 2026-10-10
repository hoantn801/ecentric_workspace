# Copyright (c) 2026, eCentric and contributors
"""Hang so cua Tin noi bo (/tin-noi-bo). PO Hoan chot 01/10/2026, thiet ke = artifact v5.

Moi ten DocType / role / gioi han nam o day - service, repository, trang deu doc tu day.
"""

POST_DT = "EC Internal Post"
CATEGORY_DT = "EC Post Category"
DEPT_CHILD_DT = "EC Internal Post Department"
FILE_CHILD_DT = "EC Internal Post File"
COVER_JOB_DT = "EC Post Cover Job"
REACTION_DT = "EC Home Reaction"          # dung lai bang cam xuc cua popup (target = "post:<ten>")
COMMENT_DT = "EC Post Comment"

#: Ai duoc soan / dang / go bai (PO chot 01/10: HR dang thang, khong buoc duyet).
EDITOR_ROLES = ("System Manager", "HR Manager", "HR User")
#: Ai duoc doc: nguoi co ho so Employee dang Active gan voi tai khoan (kiem o permissions.py).
READER_ROLE = "Employee"

#: Trang
ROUTE = "/tin-noi-bo"
ROUTE_COMPOSE = "/tin-noi-bo/viet-bai"
ROUTE_MANAGE = "/tin-noi-bo/quan-ly"
#: slug khong duoc trung route tinh cua module.
RESERVED_SLUGS = ("viet-bai", "quan-ly", "bai", "index")
SLUG_MAX = 80

#: Chuyen muc cua bai huong dan cu (guides.registry) - bai cu hien chung danh sach nay.
GUIDES_CATEGORY = "huong-dan"

#: Danh sach
PAGE_SIZE = 12
SECTION_SIZE = 3
FEATURE_SIDE = 3
HOME_MAX = 4                 # trang chu: bai ghim truoc, roi bai moi nhat (PO chot 6a)
SEARCH_MAX = 60

#: Popup trang chu: bai co tich "Dua len popup" hien 7 ngay (start..start+6) neu khong co han.
POPUP_DAYS = 7
POPUP_LINK_LABEL = "Đọc bài →"
#: Loai thong bao cua popup (Select trong EC Home Announcement).
HOME_CATEGORIES = ("Tính năng mới", "Module mới", "Chính sách", "Sự kiện", "Thông báo")
HOME_CATEGORY_DEFAULT = "Thông báo"

#: Chuong thong bao: event type cua notification_center (teams = False khoa cung).
NOTIFY_EVENT = "announcement"
#: "Gui kem tin nhan Teams" (PO duyet v6 03/10, mac dinh TAT): event co san, teams = True.
NOTIFY_EVENT_TEAMS = "announcement_urgent"

#: Hen gio dang (v6): job kiem moi 5 phut -> bai len tre toi da 5 phut. Hen xa nhat 60 ngay.
SCHEDULE_CRON = "*/5 * * * *"
SCHEDULE_LAG_MINUTES = 5
SCHEDULE_MAX_DAYS = 60
#: Gio chon nhanh tren trang viet bai (buoc 30 phut).
SCHEDULE_TIMES = tuple("%02d:%02d" % (h, m) for h in range(6, 22) for m in (0, 30))
SCHEDULE_TIME_DEFAULT = "08:30"

#: Anh bia: 8 mau nen (PO duyet v4). key -> (ten, mau 1, mau 2). Doi o day thi doi ca CSS.
COVER_COLORS = {
    "navy": ("Navy", "#2C3DA6", "#5b6fe0"),
    "green": ("Xanh lá", "#0f8f6b", "#34d399"),
    "pink": ("Hồng", "#c43a7f", "#f59ac6"),
    "yellow": ("Vàng", "#b37800", "#FFC000"),
    "purple": ("Tím", "#5b3cc4", "#a78bfa"),
    "orange": ("Cam", "#c2410c", "#fb923c"),
    "teal": ("Ngọc", "#0e7490", "#22d3ee"),
    "charcoal": ("Than", "#1f2937", "#6b7280"),
}
COVER_COLOR_DEFAULT = "navy"
#: Khao sat kem bai: do dai toi da cau keu goi.
SURVEY_CTA_MAX = 140

COVER_KIND_COLOR = "color"
COVER_KIND_IMAGE = "image"
#: Bieu tuong chuyen muc (Select trong EC Post Category).
ICONS = ("megaphone", "book", "star", "doc", "calendar", "heart")
ICON_DEFAULT = "megaphone"

#: Cam xuc - giong popup (EC Home Reaction.kind).
REACTION_KINDS = ("heart", "flower", "cake", "party")
REACTION_TARGET_PREFIX = "post:"
REACTION_EMOJI = {"heart": "\u2764\ufe0f", "flower": "\U0001f338", "cake": "\U0001f382", "party": "\U0001f389"}
REACTION_LABELS = {"heart": "Thích", "flower": "Tặng hoa", "cake": "Chúc mừng", "party": "Vui quá"}

#: Luot xem: do la "da mo bai" (PO chot 01/10: khong co nut xac nhan).
SEEN_FACES = 5

#: AI tao anh bia - PO chot 01/10: toi da 5 lan / bai / ngay. Moi lan = 3 phuong an.
#: v6 (03/10): ve AI_COVER_GENERATE anh, AI soi tung anh, bo anh dinh chu / logo, giu toi da
#: AI_COVER_VARIANTS anh sach. Mot lan bam van tinh 1/5 luot.
AI_COVER_DAILY_LIMIT = 5
AI_COVER_VARIANTS = 3
AI_COVER_GENERATE = 4
AI_COVER_POLL_SECONDS = 3
AI_COVER_TIMEOUT_SECONDS = 180
#: Tran cua ca job (ve + tai + soi 4 anh). Qua AI_COVER_CHECK_UNTIL giay thi bo soi anh con lai.
AI_COVER_JOB_TIMEOUT = 900
AI_COVER_CHECK_UNTIL = 600
AI_COVER_MAX_BYTES = 8 * 1024 * 1024
#: Anh AI khong duoc chon lam bia sau ngan nay ngay thi xoa (job dem).
AI_COVER_KEEP_DAYS = 3
AI_TEXT_MAX_CHARS = 6000

#: AI viet giup (v6): HR dan y chinh -> AI viet tieu de + tom tat + noi dung. 10 lan / bai / ngay
#: (bai chua luu: tinh theo nguoi). Chi tinh lan AI tra bai duoc.
AI_WRITE_DAILY_LIMIT = 10
AI_WRITE_POINTS_MAX = 4000
AI_WRITE_TONES = {
    "short": "Thông báo ngắn gọn",
    "steps": "Hướng dẫn từng bước",
    "friendly": "Thân thiện, vui",
}
AI_WRITE_TONE_DEFAULT = "short"

#: Binh luan (v6): tra loi MOT cap, HR an duoc, nguoi dang bai nhan chuong.
COMMENT_MAX_CHARS = 2000
COMMENT_RATE_SECONDS = 60            # toi da COMMENT_RATE_MAX binh luan / nguoi / bai trong khoang nay
COMMENT_RATE_MAX = 5
COMMENT_RX_PREFIX = "cmt:"
COMMENT_RX_KIND = "heart"
COMMENT_NOTIFY_EVENT = "announcement"   # chuong, KHONG Teams
COMMENT_ANCHOR = "binh-luan"

#: Xac nhan da doc (v6): nut "Toi da doc va hieu"; tu nhac 1 ngay truoc han + dung ngay han luc
#: 09:00; HR nhac tay toi da 1 lan / ngay.
ACK_REMIND_DAYS_BEFORE = 1
ACK_REMIND_CRON = "0 9 * * *"
ACK_REMIND_HOUR_LABEL = "09:00"

#: Tep dinh kem: private, chi nguoi doc duoc bai moi tai duoc (File.has_permission).
MAX_ATTACHMENTS = 10

WEEKDAYS = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")
