# Copyright (c) 2026, eCentric and contributors
"""Hang so cua Bang tin + Cau lac bo (/bang-tin, mockup v2, PO Hoan duyet 04/10/2026)."""

ROUTE = "/bang-tin"
CLUBS_ROUTE = "/bang-tin/cau-lac-bo"
POST_ROUTE = "/bang-tin/bai"
MOD_ROUTE = "/bang-tin/quan-ly"
HALL_ROUTE = "/hall"

POST_DT = "EC Social Post"
IMAGE_DT = "EC Social Post Image"
MENTION_DT = "EC Social Mention"
CLUB_DT = "EC Club"
MEMBER_DT = "EC Club Member"
RSVP_DT = "EC Event RSVP"
REPORT_DT = "EC Social Report"

#: HR kiem duyet (an bai, xu ly bao cao, duyet CLB) - cung nhom bien tap Tin noi bo.
MODERATOR_ROLES = ("System Manager", "HR Manager", "HR User")

# ------------------------------------------------------------------ loai bai ------
KIND_POST = "post"
KIND_KUDOS = "kudos"
KIND_EVENT = "event"
KIND_MOMENT = "moment"
KINDS = (KIND_POST, KIND_KUDOS, KIND_EVENT, KIND_MOMENT)

BODY_MAX = 3000
EVENT_TITLE_MAX = 140
EVENT_PLACE_MAX = 140
MENTIONS_MAX = 20
IMAGES_MAX = 6
IMAGE_MAX_BYTES = 10 * 1024 * 1024
IMAGE_EXTS = ("jpg", "jpeg", "png", "gif", "webp")
#: Anh dien thoai 4000px -> ve lai toi da 1600px canh dai (nhe trang, bo EXIF / GPS).
IMAGE_MAX_SIDE = 1600
#: Chong spam: toi da POST_RATE_MAX bai / nguoi trong POST_RATE_SECONDS giay.
POST_RATE_MAX = 6
POST_RATE_SECONDS = 600
REPORT_REASON_MAX = 300

#: Gia tri cua loi khen - TAM THOI (PO chua gui bo gia tri that cua cong ty). Doi o day.
KUDOS_VALUES = (
    ("tan-tam", "Tận tâm"),
    ("dong-doi", "Đồng đội"),
    ("sang-tao", "Sáng tạo"),
    ("trach-nhiem", "Trách nhiệm"),
)

# ------------------------------------------------------------------ bang tin ------
FEED_PAGE = 20
#: Xem truoc binh luan tren the bai: so binh luan goc moi nhat + do dai toi da moi binh luan.
PREVIEW_COMMENTS = 2
PREVIEW_CHARS = 200
#: Tin noi bo ghim con "noi" dau trang 1 trong bay nhieu ngay ke tu luc dang.
PIN_FLOAT_DAYS = 14
#: ?loc= tren /bang-tin
FILTERS = (
    ("", "Tất cả"),
    ("tin-hr", "Tin HR"),
    ("loi-khen", "Lời khen"),
    ("phong-toi", "Phòng tôi"),
    ("clb-cua-toi", "CLB của tôi"),
    ("su-kien", "Sự kiện & khảo sát"),
    ("cua-toi", "Bài của tôi"),
)
FILTER_KEYS = tuple(k for k, _ in FILTERS)

# ------------------------------------------------------------------ cam xuc -------
#: Dung chung bang EC Home Reaction voi popup / Tin noi bo. Target "soc:<ten bai>".
RX_PREFIX = "soc:"
RX_KIND = "heart"
RX_EMOJI = {"heart": "❤️", "flower": "\U0001f338", "cake": "\U0001f382", "party": "\U0001f389"}
#: Khoanh khac hom nay: bam "Chuc mung" tren Bang tin = cung cam xuc tren popup (cung khoa).
MOMENT_RX = {"bd": "cake", "ann": "flower", "new": "party"}
MOMENT_LABEL = {"bd": "Sinh nhật", "ann": "Kỷ niệm gắn bó", "new": "Bạn mới"}
MOMENT_ICON = {"bd": "\U0001f382", "ann": "⭐", "new": "\U0001f44b"}

# ------------------------------------------------------------------ su kien -------
RSVP_GOING = "going"
RSVP_MAYBE = "maybe"
RSVP_ANSWERS = (RSVP_GOING, RSVP_MAYBE)
#: Popup "Hom nay o eCentric": su kien CLB trong bay nhieu ngay toi.
POPUP_EVENT_DAYS = 14
POPUP_EVENT_MAX = 6
EVENT_PAST_GRACE_HOURS = 3

# ------------------------------------------------------------------ CLB -----------
CLUB_PENDING = "Chờ duyệt"
CLUB_ACTIVE = "Đang hoạt động"
CLUB_REJECTED = "Từ chối"
CLUB_ARCHIVED = "Ngừng hoạt động"
CLUB_CATEGORIES = ("Thể thao", "Sở thích")
CLUB_COLORS = ("green", "pink", "navy", "orange", "purple")
CLUB_NAME_MAX = 60
CLUB_DESC_MAX = 300
#: Goi y tren the "De xuat CLB moi" (khong chan cung): nen co it nhat ngan nay nguoi muon vao.
CLUB_SUGGEST_MIN = 5
CLUB_PROPOSE_MAX_OPEN = 3

# ------------------------------------------------------------------ bao cao -------
REPORT_NEW = "Mới"
REPORT_DONE = "Đã xử lý"

# ------------------------------------------------------------------ chuong --------
#: Chuong thuong (KHONG Teams) - cung event voi binh luan Tin noi bo.
NOTIFY_EVENT = "announcement"

AV_COLORS = 4
