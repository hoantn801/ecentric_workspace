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
