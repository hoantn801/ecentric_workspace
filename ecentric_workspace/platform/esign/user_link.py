# Copyright (c) 2026, eCentric and contributors
"""Ket noi tai khoan SCTS theo TUNG NGUOI: token cua chinh ho, khong phai mat khau.

Vi sao (04/09/2026). eContract giao buoc dau tien ("Khoi tao hop dong" -> Trinh ky) cho tai
khoan TAO chung tu, va chi ky bang chung thu cua `userId` dang giu task. ERP dang tao moi
chung tu bang MOT tai khoan tich hop (Provider Settings.username), nen nguoi de nghi nao khac
tai khoan do deu khong bao gio giu task Trinh ky: 00046/00047/00048/00050 - `transition` 400
"khong co quyen", `bulk-process` 2xx roi 0 chu ky, gan vai tro cho node khong doi duoc, va
gui signatureInfo cua nguoi de nghi voi userId tich hop thi chu ky dong len la cua tai khoan
tich hop. Cach duy nhat de nguoi de nghi ky bang chinh chung thu cua minh: chung tu phai
duoc tao bang TOKEN CUA HO.

Mo hinh:
  - Nguoi dung tu vao ERP, nhap mat khau SCTS MOT LAN. ERP goi Auth/login, nhan token
    (SCTS: 525600 phut = 1 nam), luu token (Password field, ma hoa) - MAT KHAU KHONG LUU,
    KHONG LOG, khong xuat hien trong su kien.
  - Chan nguoi de nghi: tao chung tu + Trinh ky bang token cua ho. Cap duyet giu nguyen.
  - Chua ket noi thi CHAN ngay luc bam Gui (khong tao chung tu rac ben SCTS), va worker
    cung chan lai lan nua (defense in depth) - KHONG BAO GIO roi ve tai khoan tich hop
    trong im lang, vi do chinh la loi dang sua.
  - Nguoi de nghi TRUNG tai khoan tich hop (10 goi dau cua Hoan) thi khong can ket noi.

Chi doc/ghi mapping cua CHINH nguoi dang dang nhap. Khong co tham so `user` o tang API.
"""
import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime
from frappe.utils.password import get_decrypted_password

from ecentric_workspace.platform.esign import events
from ecentric_workspace.platform.esign.permissions import verified_mapping
from ecentric_workspace.platform.esign.providers import get_adapter
from ecentric_workspace.platform.esign.providers.base import ProviderError

MAPPING_DT = "EC SCTS User Mapping"
SETTINGS_DT = "EC Digital Signature Provider Settings"
#: Token gan het han trong khoang nay thi coi nhu het - de lenh ky khong chet giua chung.
TOKEN_SKEW_MIN = 60
#: SCTS khong tra expiresInMinutes thi KHONG doan 1 nam - coi nhu het han ngay, bat ket noi
#: lai. Doan sai o day la mot chan ky chet sau khi nguoi dung tuong minh da ket noi.
NO_EXPIRY_MINUTES = 0


def _settings_value(settings, key):
    if isinstance(settings, dict):
        return settings.get(key)
    return getattr(settings, key, None)


def needs_own_token(user, settings):
    """Nguoi nay co can token rieng khong. Trung tai khoan tich hop thi khong."""
    api_user = (_settings_value(settings, "username") or "").strip().lower()
    return (user or "").strip().lower() != api_user


def _token_row(user, environment):
    """Mapping Active + Verified kem cac truong token (khong doc token o day)."""
    m = verified_mapping(user, environment)
    if not m:
        return None
    row = frappe.db.get_value(MAPPING_DT, m["name"],
                              ["name", "api_token_expires_at", "api_token_linked_at",
                               "api_token_username"], as_dict=True) or {}
    row["mapping"] = m
    return row


def _expires_in_minutes(raw):
    """eContract boc trong `data` ({success, data:{token, expiresInMinutes}}); mot so ban
    tra phang. Khong doc duoc thi 0 - het han ngay, KHONG doan 1 nam."""
    if not isinstance(raw, dict):
        return NO_EXPIRY_MINUTES
    v = raw.get("expiresInMinutes")
    if v is None and isinstance(raw.get("data"), dict):
        v = raw["data"].get("expiresInMinutes")
    try:
        return int(v or NO_EXPIRY_MINUTES)
    except (TypeError, ValueError):
        return NO_EXPIRY_MINUTES


def _token_alive(expires_at):
    if not expires_at:
        return False
    try:
        return get_datetime(expires_at) > add_to_date(now_datetime(), minutes=TOKEN_SKEW_MIN)
    except Exception:
        return False


def token_for(user, environment):
    """Token con hieu luc cua nguoi nay, hoac None. Khong bao gio tra token het han."""
    row = _token_row(user, environment)
    if not row or not _token_alive(row.get("api_token_expires_at")):
        return None
    try:
        tok = get_decrypted_password(MAPPING_DT, row["name"], "api_token",
                                     raise_exception=False)
    except Exception:
        return None
    return tok or None


def link_status(user, settings, environment):
    """Trang thai ket noi de UI hien. Khong co token, khong co bi mat."""
    row = _token_row(user, environment) or {}
    exp = row.get("api_token_expires_at")
    alive = _token_alive(exp)
    days_left = None
    if alive:
        try:
            days_left = max(0, int((get_datetime(exp) - now_datetime()).total_seconds() // 86400))
        except Exception:
            days_left = None
    return {
        "needs_link": needs_own_token(user, settings),
        "has_mapping": bool(row),
        "linked": bool(alive),
        "expires_at": exp,
        "linked_at": row.get("api_token_linked_at"),
        "username": row.get("api_token_username"),
        "days_left": days_left,
    }


def link(user, settings, environment, password, username=None):
    """Dang nhap SCTS bang mat khau nguoi dung nhap, luu TOKEN, bo mat khau.

    `password` chi song trong pham vi ham nay: di thang vao client.login va khong duoc gan
    vao doc, event, log hay thong diep loi. Username mac dinh la email ERP (SCTS dang nhap
    bang email - kiem chung tren tai khoan tich hop), cho phep khai khac khi email SCTS lech.
    """
    if not password:
        frappe.throw(_("Vui lòng nhập mật khẩu SCTS."))
    row = _token_row(user, environment)
    if not row:
        frappe.throw(_("Bạn chưa có ánh xạ chữ ký SCTS được xác minh. Nhờ quản trị tạo trước."))
    login_name = (username or user or "").strip()
    site = _settings_value(settings, "site")
    adapter = get_adapter(settings)
    try:
        raw = adapter._client.login(site, login_name, password)
    except ProviderError:
        events.emit("UserTokenLinkFailed", erp_actor=user,
                    request_meta={"environment": environment, "username": login_name})
        frappe.throw(_("Đăng nhập SCTS không thành công. Kiểm tra lại tên đăng nhập và mật khẩu."))
    token = adapter._extract_token(raw)
    if not token:
        frappe.throw(_("SCTS không trả về token. Thử lại sau hoặc báo quản trị."))
    mins = _expires_in_minutes(raw)
    expires_at = add_to_date(now_datetime(), minutes=mins)
    doc = frappe.get_doc(MAPPING_DT, row["name"])
    doc.api_token = token
    doc.api_token_username = login_name
    doc.api_token_linked_at = now_datetime()
    doc.api_token_expires_at = expires_at
    doc.save(ignore_permissions=True)       # SM-only DocType; nguoi dung ghi mapping CUA MINH
    events.emit("UserTokenLinked", erp_actor=user,
                scts_effective_user=row["mapping"].get("scts_user_id"),
                request_meta={"environment": environment, "username": login_name,
                              "expires_at": str(expires_at)})
    return link_status(user, settings, environment)


def unlink(user, settings, environment):
    row = _token_row(user, environment)
    if not row:
        return link_status(user, settings, environment)
    doc = frappe.get_doc(MAPPING_DT, row["name"])
    doc.api_token = None
    doc.api_token_username = None
    doc.api_token_linked_at = None
    doc.api_token_expires_at = None
    doc.save(ignore_permissions=True)
    events.emit("UserTokenUnlinked", erp_actor=user, request_meta={"environment": environment})
    return link_status(user, settings, environment)


def assert_requester_linked(user, settings, environment):
    """Chot truoc khi tao DSR / tao chung tu. Fail-closed, thong diep noi ro phai lam gi."""
    if not needs_own_token(user, settings):
        return None
    tok = token_for(user, environment)
    if not tok:
        events.emit("RequesterNotLinked", erp_actor=user,
                    request_meta={"environment": environment})
        frappe.throw(_("Bạn chưa kết nối tài khoản ký số SCTS (hoặc kết nối đã hết hạn). "
                       "Mở mục 'Ký của người đề nghị' trên phiếu, nhập mật khẩu SCTS để kết nối, "
                       "rồi gửi lại."), frappe.PermissionError)
    return tok
