# Copyright (c) 2026, eCentric and contributors
"""Hang so AI Live (app eCentric AI Live tren may phat): ten DocType, role, gioi han, thong bao."""
import re

BRAND_CONFIG = "EC AI Live Brand Config"
MACHINE = "EC AI Live Machine"
COST_LOG = "EC AI Live Cost Log"

#: Quan tri cau hinh AI Live (key, may phat): giong quan tri AI Video.
ADMIN_ROLES = ("EC AI Video Admin", "System Manager")
#: Xem chi phi AI Live: ai co quyen trang /ai-video.
VIEW_ROLES = ("EC AI Content", "EC AI Video Admin", "System Manager")

MODES = ("full", "lite")
BREAK_SECS = (20, 25, 30, 35)
DEFAULT_BREAK_SEC = 20

BRAND_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,39}$")
MACHINE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,39}$")
SESSION_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,80}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Khoa (Password) tra ve cho may phat. Ten truong DocType = ten khoa trong JSON.
KEY_FIELDS = ("claude_key", "minimax_key", "kie_key", "plenx_key",
              "shopee_partner_key", "shopee_access_token", "shopee_refresh_token")
PLAIN_FIELDS = ("gpu_url", "mode", "break_sec", "kit_folder", "minimax_group", "daily_cost_cap_usd",
                "shopee_partner_id", "shopee_shop_id")
#: Shopee Open Platform: chi luu va tra cho may phat; chua goi API Shopee (chua co tai lieu live).
#: Cai dat app sua duoc va dong bo lai len ERP (JSON).
SETTING_FIELDS = {"templates": "templates_json", "playlist": "playlist_json", "cooldowns": "cooldowns_json"}
MAX_SETTING_BYTES = 200 * 1024
MAX_COST_ITEMS = 50
MAX_USD = 10000.0

MACHINE_EMAIL = "ailive-%s@machines.ecentric.local"


class Msg:
    NOT_MACHINE = "Tài khoản này không phải máy phát AI Live (hoặc máy đã bị tắt)."
    WRONG_MACHINE = "Mã máy không khớp với token."
    BRAND_NOT_ALLOWED = "Máy này chưa được giao brand %s."
    BAD_BRAND = "Mã brand không hợp lệ (chữ thường, số, - _; 2–40 ký tự): %s"
    BAD_MACHINE = "Mã máy không hợp lệ (chữ, số, - _; 2–40 ký tự)."
    BAD_MODE = "Chế độ phải là full (Đầy đủ) hoặc lite (Tiết kiệm)."
    BAD_BREAK = "Khoảng nghỉ phải là 20, 25, 30 hoặc 35 giây."
    BAD_JSON = "Dữ liệu %s không phải JSON hợp lệ."
    TOO_BIG = "Dữ liệu %s quá lớn (tối đa 200 KB)."
    BAD_COST = "Dữ liệu chi phí không hợp lệ: %s"
    NEED_ADMIN = "Chỉ quản trị AI Video được làm việc này."
    NEED_VIEW = "Cần quyền EC AI Content."
    UNKNOWN_BRAND = "Chưa có cấu hình brand %s."
    UNKNOWN = "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT."


class AiLiveError(Exception):
    """Loi nghiep vu AI Live - thong diep tieng Viet hien thang cho nguoi dung."""


class AiLivePermission(AiLiveError):
    pass


# ------------------------------------------------------------------ Bo live + kho host (fix10b) ---
KIT = "EC AI Live Kit"


class KitStatus:
    DRAFT = "Nháp"
    SENDING = "Đang gửi"
    BUILDING = "Đang dựng"
    DONE = "Xong"
    ERROR = "Lỗi"


PRODUCT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
HOST_RE = re.compile(r"^H_[A-Z0-9_]{3,40}$")
PLATFORM_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{0,40}$")
AUDIO_EXT = (".mp3", ".wav", ".m4a")
BG_EXT = {".mp4": "video", ".webm": "video", ".mov": "video", ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image"}
MAX_PRODUCTS = 60
MAX_AUDIO_PER_GROUP = 6
MAX_FAQ_TOPICS = 30
FAQ_COPIES = (2, 5)
#: Nhom video cua 1 SP: khoa trong bolive.json (products[].groups)
PRODUCT_AUDIO_GROUPS = ("main_free", "main_hold")
GENERIC_GROUPS = ("greet", "thanks", "answer")

#: Studio anh host: model -> nhan, credit PlenX moi anh (None = chua co bang gia, khong uoc tinh).
IMAGE_MODELS = (("nano-banana-full", "Nano Banana Full 2K (PlenX)", 10),
                ("nano-banana-pro", "Nano Banana Pro", None),
                ("gpt-image", "GPT Image", None),
                ("seedream", "Seedream", None))
HOST_IMAGE_N = 4
MAX_REFS = 4
MAX_PROMPT = 2000

#: Bo motion de xuat cho host moi (17/10, tinh tu H_BOO3HGI9JF 81 clip va H_FAQ_GREEN 22 clip): 20 clip noi.
MOTION_PROPOSAL = ((10, 10), (8, 5), (6, 3), (4, 2))
MOTION_DURS = (4, 6, 8, 10)
MAX_MOTION_CLIPS = 60
#: Uoc tinh: PlenX ~3 credit/giay video (1080p), x1,5 cho lan gen lai do QC; 80 d/credit (goi 399.000d / 5.000).
PX_CREDIT_PER_S = 3
QC_FACTOR = 1.5
VND_PER_PX_CREDIT = 80
#: Lipsync (giong AI Video): ~$0.012/giay neu chay fal; may GPU rieng thi gan nhu khong ton.
LS_USD_PER_S = 0.012
HOST_LABELS_KEY = "ec_ai_live_host_labels"
#: Tien to batch_id tren may chay video (tach lo Bo live / Studio anh / bo motion).
BATCH_KIT, BATCH_HOST_IMAGE, BATCH_MOTION = "kit_", "hi_", "ms_"


class KitMsg:
    NOT_FOUND = "Không tìm thấy Bộ live %s."
    BAD_PRODUCT = "Dòng sản phẩm %d: %s"
    BAD_FAQ = "Chủ đề FAQ %d: %s"
    BAD_FILE = "File không hợp lệ hoặc không phải của bạn: %s"
    NEED_HOST = "Chưa chọn host (host phải có trong Kho host)."
    NEED_BRAND = "Chưa chọn brand."
    NOTHING = "Bộ live chưa có voice nào để dựng."
    BUSY = "Bộ live đang dựng, đợi xong rồi gửi lại."
    BAD_HOST = "Mã host không hợp lệ."
    BAD_MODEL = "Model ảnh không hợp lệ."
    BAD_PLAN = "Bộ motion không hợp lệ (mỗi loại 0–20 clip, tổng 1–60, độ dài 4/6/8/10 giây)."
    NEED_PROMPT = "Chưa nhập mô tả ảnh host."
    BAD_PICK = "Ảnh này chưa xong hoặc không thuộc lượt tạo hiện tại."
