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


def default_context():
    """(settings, environment) cho nut "Ket noi SCTS" o Approval Center - khong gan voi phieu
    nao. Lay dong Provider Settings SCTS dang bat tich hop; co DUNG MOT dong thi dung, khong
    co hoac nhieu hon thi bao ro (khong doan moi truong)."""
    rows = frappe.get_all(SETTINGS_DT, filters={"provider": "SCTS", "integration_enabled": 1},
                          pluck="name", limit_page_length=2)
    if len(rows) != 1:
        frappe.throw(_("Cổng ký số SCTS chưa cấu hình (hoặc cấu hình nhiều môi trường)."))
    st = frappe.db.get_value(SETTINGS_DT, rows[0], "*", as_dict=True)
    return st, st.get("environment")


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


#: Cac khoa co the mang `userId` trong phan hoi dang nhap cua eContract, va trong claim cua
#: JWT. KHONG doan mot khoa duy nhat: chua ai nhin thay payload that (muon thay phai co mat
#: khau cua mot nguoi thuc, thu khong duoc dung cham). Do nhieu kha nang roi BAO RA khi khong
#: thay, con hon chot mot khoa roi hong im lang.
_UID_KEYS = ("userId", "userID", "user_id", "id", "guid", "signerId", "signerUserId")
#: Claim tuong ung trong JWT (token cua eContract la JWT; phan giua la base64 KHONG ma hoa,
#: doc duoc ma khong can bi mat gi).
_UID_CLAIMS = _UID_KEYS + ("sub", "nameid", "nameId",
                           "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier")


def _dig(obj, keys):
    if not isinstance(obj, dict):
        return None
    for k in keys:
        v = obj.get(k)
        if v not in (None, "", []):
            return str(v)
    return None


def _uid_from_jwt(token):
    """userId trong claim cua JWT. Chi doc phan payload (base64url), khong xac thuc chu ky -
    khong can: token nay VUA duoc chinh SCTS cap cho phien dang nhap nay."""
    try:
        import base64
        import json as _json
        parts = str(token or "").split(".")
        if len(parts) < 2:
            return None
        seg = parts[1]
        seg += "=" * (-len(seg) % 4)
        return _dig(_json.loads(base64.urlsafe_b64decode(seg).decode("utf-8", "ignore")),
                    _UID_CLAIMS)
    except Exception:
        return None


def _provider_user_id(raw, token):
    """`userId` cua nguoi vua dang nhap. None neu khong tim thay o dau."""
    for src in (raw, (raw or {}).get("data") if isinstance(raw, dict) else None,
                (raw or {}).get("user") if isinstance(raw, dict) else None):
        uid = _dig(src, _UID_KEYS)
        if uid:
            return uid
    return _uid_from_jwt(token)


def _usable_signatures(sigs):
    """Nhung mau chu ky ERP KY DUOC TU MAY CHU.

    `signToken == 1` = ky bang token cam tai may qua OfficeSignTool -> ERP khong ky thay
    duoc; khong co HSM cung vay. Tao mot anh xa tro vao mau nhu the thi no van `Verified`
    nhung den luc ky se "nhan 2xx roi im" - dung cai loi da ton hai dem cua thang 8. Nen
    chan ngay o day, kem cau noi ro phai lam gi.
    """
    return [s for s in (sigs or [])
            if s.get("id") and s.get("active") and s.get("has_hsm") and s.get("sign_token") != 1]


def _auto_create_mapping(user, environment, adapter, raw, token, login_name):
    """Tao anh xa tu chinh phan hoi cua SCTS, sau khi da dang nhap THANH CONG.

    Ban chat cua thay doi nay (09/09/2026, Hoan chot): bo buoc quan tri go tay `scts_user_id`
    + `signature_id`. Cai bi bo KHONG phai phep xac minh danh tinh - dang nhap thanh cong da
    chung minh nguoi do nam tai khoan SCTS do, chat hon la mot quan tri go GUID bang tay.
    Cai bi bo la chot "quan tri quyet dinh ai duoc ky".

    De bu lai, moi gia tri deu lay tu SCTS chu khong tu nguoi dung khai, va anh xa chi thanh
    `Verified` khi SCTS xac nhan dung MOT mau chu ky ky duoc. Khong ro thi tao ban nhap va
    noi ro phai lam gi - khong bao gio doan.
    """
    uid = _provider_user_id(raw, token)
    if not uid:
        # NOI RA payload co nhung KHOA gi (chi ten khoa, khong bao gio gia tri - trong do co
        # token). Lan chay that dau tien se cho biet eContract dat userId o dau.
        co = sorted(raw.keys())[:12] if isinstance(raw, dict) else []
        events.emit("UserMappingAutoCreateFailed", erp_actor=user,
                    request_meta={"environment": environment, "ly_do": "khong_thay_user_id",
                                  "cac_khoa": co})
        frappe.throw(_("Đăng nhập SCTS thành công nhưng không đọc được mã người dùng từ phản "
                       "hồi (các khoá nhận được: {0}). Nhờ quản trị tạo ánh xạ thủ công và "
                       "báo lại thông tin này.").format(", ".join(co) or "không có"))
    try:
        sigs = adapter.list_user_signatures(uid)
    except Exception:
        frappe.throw(_("Không đọc được danh sách chữ ký của bạn từ SCTS. Thử lại sau."))
    usable = _usable_signatures(sigs)
    doc = frappe.get_doc({
        "doctype": MAPPING_DT, "frappe_user": user, "environment": environment,
        "scts_user_id": uid,
        # `signature_id` la truong BAT BUOC cua doctype: khi chua chon duoc thi van phai co
        # gia tri. Dung mau dau tien lam cho giu, nhung KHONG danh dau Verified.
        "signature_id": (usable[0]["id"] if len(usable) == 1
                         else ((sigs or [{}])[0].get("id") or "CHUA-XAC-DINH")),
        "active": 1, "mapping_status": "Draft",
        "notes": "Tu tao khi nguoi dung ket noi SCTS (%s)." % login_name,
    })
    doc.insert(ignore_permissions=True)     # SM-only DocType; nguoi dung tao anh xa CUA MINH
    if len(usable) != 1:
        events.emit("UserMappingAutoCreateFailed", erp_actor=user, scts_effective_user=uid,
                    request_meta={"environment": environment,
                                  "ly_do": "khong_chon_duoc_chu_ky",
                                  "so_mau": len(sigs or []), "so_mau_ky_duoc": len(usable)})
        if not usable:
            frappe.throw(_("Tài khoản SCTS của bạn chưa có mẫu chữ ký ký được từ hệ thống "
                           "(chưa gán chứng thư, hoặc chỉ ký bằng token cắm tại máy). "
                           "Liên hệ SCTS để cấp chứng thư, rồi kết nối lại."))
        frappe.throw(_("Tài khoản SCTS của bạn có {0} mẫu chữ ký ký được — hệ thống không tự "
                       "chọn hộ. Nhờ quản trị chọn mẫu đúng trong ánh xạ {1}.")
                     .format(len(usable), doc.name))
    meta = usable[0]
    doc.db_set({"mapping_status": "Verified", "verified_at": now_datetime(),
                "verified_by": user,
                "signature_meta_summary": ("%s / %s" % (meta.get("type") or "?",
                                                        meta.get("company") or "?"))[:130]})
    events.emit("UserMappingAutoCreated", erp_actor=user, scts_effective_user=uid,
                request_meta={"environment": environment, "mapping": doc.name,
                              "username": login_name,
                              "signature_type": meta.get("type")})
    return _token_row(user, environment)


def link(user, settings, environment, password, username=None):
    """Dang nhap SCTS bang mat khau nguoi dung nhap, luu TOKEN, bo mat khau.

    `password` chi song trong pham vi ham nay: di thang vao client.login va khong duoc gan
    vao doc, event, log hay thong diep loi. Username mac dinh la email ERP, cho phep khai
    khac khi ten dang nhap SCTS lech - va no LECH THAT: 4 nguoi dang nhap bang email nhung
    Uyen phai dung `nv00109`, Tam la `nv00129`. Dung gia dinh ten dang nhap la email.

    THU TU (doi 09/09): DANG NHAP TRUOC, roi moi lo chuyen anh xa. Truoc day ham nay tu choi
    ngay tu dau neu chua co anh xa ("Nho quan tri tao truoc") - nghia la nguoi moi bi chan
    truoc ca khi ERP kip biet ho la ai ben SCTS, va nut "Ket noi SCTS" tren hub cung bi AN
    voi dung nhom can no nhat (`has_mapping` la dieu kien hien nut). Dang nhap truoc thi
    chinh SCTS cho ta moi thu can de tu dung anh xa.
    """
    if not password:
        frappe.throw(_("Vui lòng nhập mật khẩu SCTS."))
    row = _token_row(user, environment)
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
    if not row:
        # Chua co anh xa -> dung chinh phan hoi cua SCTS de tao. Nem loi co noi dung neu
        # khong chac chan; khong bao gio tao mot anh xa "Verified" ma chua chac ky duoc.
        row = _auto_create_mapping(user, environment, adapter, raw, token, login_name)
        if not row:
            frappe.throw(_("Không tạo được ánh xạ chữ ký. Nhờ quản trị kiểm tra."))
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
