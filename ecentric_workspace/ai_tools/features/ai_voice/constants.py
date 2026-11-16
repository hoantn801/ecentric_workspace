# Copyright (c) 2026, eCentric and contributors
"""Hang so Giong doc AI (eVoice tren ERP): ten DocType, role, gioi han, trang thai, thong bao.

eVoice API chay tren may GPU van phong (cong 7895), ra Internet qua Cloudflare Tunnel
(mac dinh https://voice.ecentric.asia). Moi yeu cau qua tunnel bat buoc Bearer token."""

SETTINGS = "EC AI Voice Settings"
PROFILE = "EC AI Voice Profile"
JOB = "EC AI Voice Job"

#: Dung trang /ai-voice (tao giong doc, xem phieu cua minh). Role AI cu duoc dung luon cho do phai gan lai.
USER_ROLES = ("EC AI Voice User", "EC AI Voice Manager", "EC AI Content", "EC AI Video Admin", "System Manager")
#: Quan ly thu vien giong (them / sua / ngung / xoa giong, bang chung dong y) + xem moi phieu.
MANAGER_ROLES = ("EC AI Voice Manager", "EC AI Video Admin", "System Manager")
#: Cai dat ket noi (dia chi + token) - chi System Manager.
ADMIN_ROLES = ("System Manager",)

#: site_config `ec_ai_voice_disabled: 1` -> tat job nen (poll / gui / tai file). Trang van mo duoc.
KILL_SWITCH = "ec_ai_voice_disabled"

DEFAULT_BASE_URL = "https://voice.ecentric.asia"
DEFAULT_TIMEOUT = 30          # giay / yeu cau thuong
UPLOAD_TIMEOUT = 600          # giay - them giong: eVoice cat mau + khu on + chep loi (co the vai phut)
CALLBACK_METHOD = "/api/method/ecentric_workspace.ai_tools.features.ai_voice.controllers.api.evoice_callback"

MAX_CHARS = 15000             # eVoice: MAX_CHARS * 5 / job
MAX_VOICE_BYTES = 25 * 1024 * 1024
VOICE_EXTS = (".wav", ".mp3", ".m4a", ".flac", ".ogg")
MAX_ACTIVE_PER_USER = 10      # phieu dang cho / dang tao cua 1 nguoi (hang doi eVoice toi da 50)
SPEED_MIN, SPEED_MAX, SPEED_DEFAULT = 0.5, 2.0, 1.1
MAX_TITLE = 140
MAX_NAME = 80
MAX_DESC = 300
LIST_LIMIT = 50

#: Chat luong -> ma eVoice (thang PerfectVoice). Thu tu = thu tu hien tren trang.
QUALITIES = (
    ("quality_lightning", "Nhanh", "15 bước"),
    ("quality_fast", "Chuẩn", "20 bước"),
    ("quality_standard", "Cao", "32 bước"),
    ("quality_ultra", "Tối đa", "50 bước"),
)
DEFAULT_QUALITY = "quality_fast"

LANGUAGES = (
    ("vi", "Tiếng Việt"), ("en", "Tiếng Anh"), ("zh", "Tiếng Trung"), ("ja", "Tiếng Nhật"),
    ("ko", "Tiếng Hàn"), ("th", "Tiếng Thái"), ("id", "Tiếng Indonesia"),
)  # 15/11 QC: bo "auto" - chua xac nhan engine nhan
GENDERS = ("Nữ", "Nam", "Khác")


class JobStatus:
    PENDING = "pending"        # da luu tren ERP, chua gui duoc sang may (dang gui / may chua ket noi)
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"

    ACTIVE = (PENDING, QUEUED, RUNNING)
    FINAL = (DONE, ERROR, CANCELLED)
    ALL = (PENDING, QUEUED, RUNNING, DONE, ERROR, CANCELLED)


class VoiceStatus:
    ACTIVE = "active"
    DISABLED = "disabled"
    PROCESSING = "processing"  # ERP dang gui file mau sang may (cat mau, khu on, chep loi)
    FAILED = "failed"

    ALL = (ACTIVE, DISABLED, PROCESSING, FAILED)


class VoiceSource:
    ERP = "erp"                # them tu ERP (co bang chung dong y tren ERP)
    MACHINE = "machine"        # dong bo tu may eVoice (giong da co san trong app)


#: Poll / gui lai (job nen moi 2 phut).
SUBMIT_MAX_ATTEMPTS = 6       # gui that bai (may tat / hang doi day) toi da N lan roi bao loi
POLL_GRACE_SECONDS = 60       # callback chua toi sau N giay moi hoi lai
RUNNING_TIMEOUT_SECONDS = 3 * 3600   # tinh tu luc may BAT DAU doc (started_at)
QUEUED_TIMEOUT_SECONDS = 12 * 3600   # nam hang doi qua lau (gio live may uu tien live)
FETCH_GIVE_UP_SECONDS = 23 * 3600    # eVoice giu file 24 gio -> thu tai lai (gian dan) toi 23 gio
FETCH_MAX_WAIT = 60 * 60             # backoff tai file: 2, 4, 8 ... toi da 60 phut
POLL_TIMEOUT = 15                    # giay / yeu cau trong job poll (may cham -> bo qua luot nay)
ERP_MARKER = "[erp:%s]"              # gan vao mo ta giong gui len may -> doi chieu chinh xac khi upload bi cat
LOST_JOB_MSG_KEY = "lost"


class Msg:
    NEED_USER = "Cần quyền dùng Giọng đọc AI (EC AI Voice User hoặc EC AI Content)."
    NEED_MANAGER = "Chỉ quản lý giọng (EC AI Voice Manager) được làm việc này."
    NEED_ADMIN = "Chỉ System Manager được sửa cài đặt kết nối."
    NOT_CONFIGURED = "Chưa cài đặt kết nối máy giọng đọc (địa chỉ + token). Báo System Manager."
    DOWN = "Máy giọng đọc đang không kết nối (máy tắt / mất mạng / eVoice API chưa chạy)."
    EMPTY_TEXT = "Chưa nhập nội dung cần đọc."
    NO_WORDS = "Nội dung không có chữ / số để đọc."
    TOO_LONG = "Nội dung quá dài: %d ký tự (tối đa %d)."
    BAD_VOICE = "Chưa chọn giọng đọc."
    VOICE_NOT_FOUND = "Không tìm thấy giọng này (đã bị xoá hoặc ngừng dùng)."
    VOICE_RESTRICTED = "Giọng này chỉ chủ giọng hoặc quản lý được dùng."
    VOICE_NOT_READY = "Giọng này chưa sẵn sàng (đang xử lý hoặc lỗi)."
    BAD_QUALITY = "Chất lượng không hợp lệ."
    BAD_SPEED = "Tốc độ phải từ 0.5 đến 2.0."
    BAD_LANGUAGE = "Ngôn ngữ không hợp lệ."
    TOO_MANY = "Bạn đang có %d phiếu chờ / đang tạo (tối đa %d). Đợi xong bớt rồi tạo tiếp."
    JOB_NOT_FOUND = "Không tìm thấy phiếu giọng đọc."
    NOT_YOURS = "Phiếu này của người khác."
    CANNOT_CANCEL = "Phiếu đã xong / đã huỷ, không huỷ được nữa."
    CANNOT_DELETE = "Phiếu đang chờ / đang tạo - huỷ trước rồi mới xoá."
    NO_AUDIO = "Phiếu chưa có file âm thanh."
    LOST = "Máy giọng đọc đã khởi động lại nên mất phiếu này - bấm Tạo lại."
    TIMEOUT = "Quá lâu không xong (hơn 3 giờ) - bấm Tạo lại."
    SUBMIT_GAVE_UP = "Không gửi được sang máy giọng đọc sau nhiều lần thử: %s"
    FETCH_GAVE_UP = "Không tải được file âm thanh về ERP: %s"
    CANCELLED = "Đã huỷ."
    # Giong
    NAME_REQUIRED = "Thiếu tên giọng."
    NAME_TOO_LONG = "Tên giọng tối đa %d ký tự." % MAX_NAME
    BAD_GENDER = "Giới tính không hợp lệ."
    FILE_REQUIRED = "Chưa tải file giọng mẫu lên."
    BAD_EXT = "File giọng mẫu chỉ nhận wav / mp3 / m4a / flac / ogg."
    FILE_TOO_BIG = "File giọng mẫu quá lớn (tối đa 25 MB)."
    FILE_NOT_YOURS = "File này không phải do bạn tải lên."
    CONSENT_REQUIRED = "Thiếu bằng chứng đồng ý: cần tên người cho giọng, ngày đồng ý và tick xác nhận."
    CONSENT_DATE = "Ngày đồng ý không hợp lệ (định dạng YYYY-MM-DD)."
    PROFILE_NOT_FOUND = "Không tìm thấy giọng."
    PROFILE_BUSY = "Giọng đang được xử lý trên máy, đợi xong rồi thử lại."
    BAD_URL = "Địa chỉ phải bắt đầu bằng https:// (hoặc http:// trong mạng nội bộ)."
    PAUSED = "Giọng đọc AI đang tạm tắt để bảo trì. Thử lại sau."
    BRAND_NEEDS_MACHINE = "Không lấy được giọng của brand vì máy giọng đọc đang mất kết nối - chọn giọng trong thư viện."
    BRAND_NO_VOICE = "Brand này chưa chọn giọng đang dùng trên máy eVoice."
    BRAND_VOICE_UNKNOWN = "Giọng brand đang dùng chưa có trong thư viện ERP (chưa ghi bằng chứng đồng ý) - báo quản lý giọng."
    CANCELLED_OFFLINE = "Đã huỷ (máy đang mất kết nối - nếu máy vẫn đọc thì kết quả bị bỏ qua)."
    UNKNOWN = "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT."


class AiVoiceError(Exception):
    """Loi nghiep vu - thong diep tieng Viet hien thang cho nguoi dung."""


class AiVoicePermission(AiVoiceError):
    """Thieu quyen -> HTTP 403."""
