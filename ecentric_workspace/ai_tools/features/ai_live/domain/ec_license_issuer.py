"""eCentric – bộ CẤP LICENSE tự động cho eLive / eSync / eVoice (đặt PHÍA MÁY CHỦ – ERP ecentric_workspace).

Chỉ gồm hàm thuần (không đụng DB / Frappe): ERP gọi từ service của license_request.
  - decode_request(product, payload)  -> mã phần cứng / mã máy cần gắn license (kiểm khớp với payload['hw'])
  - issue(product, secret, ident, cust, exp=None) -> token license (đúng định dạng launcher từng app đang kiểm)
  - match_machine(machines, fp)       -> bản ghi máy trùng (nhận ra cùng máy khi chỉ đổi card mạng / ổ)
  - decide(...)                       -> 'issue' | 'pending' | 'blocked' + lý do (luật duyệt anh Hoàn chốt 17/11)

`secret` = nội dung file khoá (anh tự tải lên ERP vào ô mã hoá, KHÔNG gửi qua chat):
  eLive : 3_SOURCE_KHONG_GUI\\eC Live\\ec-live\\bao_mat_ec\\khoa_ec.json              (mk, app_secret, rsa_private_pem…)
  eSync : 3_SOURCE_KHONG_GUI\\eSync\\esync\\bao_mat\\khoa_bi_mat.json                  (mk, app_secret, rsa_private_pem…)
          + khoá 'premium_fernet_key' = giá trị FERNET_KEY trong bao_mat\\tao_license.py
  eVoice: 3_SOURCE_KHONG_GUI\\eVoice\\voice-lab\\vendor_secret.json                    (private_key, master_key – base64)
          + 'app_secret' (base64) nếu file chưa có = APP_SECRET trong secure\\vendor_pub.py
Không bao giờ log secret / token.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import struct
from datetime import datetime

PRODUCTS = ("elive", "esync", "evoice")
HEX32 = re.compile(r"^[0-9A-F]{32}$")
HEX24 = re.compile(r"^[0-9a-f]{24}$")


# ---------------------------------------------------------------- tiện ích chung (khớp protect_common của launcher)
def _b64u_d(text: str) -> bytes:
    text = (text or "").strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _b64u_e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def normalize_mid(mid: str) -> str:
    clean = (mid or "").strip().upper().replace(" ", "").replace("-", "")
    if clean.startswith("SYNC"):
        clean = clean[4:]
    if len(clean) >= 16:
        clean = clean[:16]
        return f"SYNC-{clean[0:4]}-{clean[4:8]}-{clean[8:12]}-{clean[12:16]}"
    return (mid or "").strip().upper()


def format_hwid(value: str) -> str:
    value = str(value).replace("-", "").upper()
    return "-".join(value[i:i + 4] for i in range(0, len(value), 4))


def wrap_mk(mk: bytes, app_secret: bytes, machine_value: str) -> str:
    key = hmac.new(app_secret, b"esync-mk|" + str(machine_value).strip().upper().encode("ascii"), hashlib.sha256).digest()
    nonce = os.urandom(16)
    mask = hmac.new(key, b"mask|" + nonce, hashlib.sha256).digest()
    wrapped = bytes(a ^ b for a, b in zip(mk, mask))
    tag = hmac.new(key, b"tag|" + nonce + wrapped, hashlib.sha256).digest()
    return _b64u_e(nonce + wrapped + tag)


def _rsa_sign(pem: str, data: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key(pem.encode("ascii"), password=None)
    return key.sign(data, padding.PKCS1v15(), hashes.SHA256())


def _secret_mk_app(secret: dict) -> tuple:
    mk = secret.get("mk_bytes") or _b64u_d(secret["mk"])
    app = secret.get("app_secret_bytes") or _b64u_d(secret["app_secret"])
    return mk, app


# ---------------------------------------------------------------- giải mã yêu cầu
class RequestError(ValueError):
    pass


def decode_request(product: str, payload: dict) -> dict:
    """-> {'hw': ..., 'mid': ...} đã kiểm. Mã yêu cầu phải khớp trường 'hw' app gửi (chống ghép lệch)."""
    product = str(product or "").lower()
    code = str(payload.get("request_code") or "").strip()
    hw = str(payload.get("hw") or "").replace("-", "").strip()
    if product == "elive":
        if not code.startswith("EC-"):
            raise RequestError("Mã yêu cầu eLive phải bắt đầu bằng EC-")
        parts = _b64u_d(code[3:]).decode("utf-8", "replace").split("|")
        if len(parts) != 2 or parts[0] != "ELIVE1":
            raise RequestError("Mã yêu cầu eLive sai định dạng")
        h = parts[1].replace("-", "").upper()
        if not HEX32.match(h) or h != hw.upper():
            raise RequestError("Mã phần cứng eLive không hợp lệ / không khớp")
        return {"hw": h, "mid": ""}
    if product == "esync":
        if not code.startswith("YC-"):
            raise RequestError("Mã yêu cầu eSync phải bắt đầu bằng YC-")
        parts = _b64u_d(code[3:]).decode("utf-8", "replace").split("|")
        if len(parts) != 3 or parts[0] != "ESYNC1":
            raise RequestError("Mã yêu cầu eSync sai định dạng")
        mid, h = normalize_mid(parts[1]), parts[2].replace("-", "").upper()
        if not HEX32.match(h) or h != hw.upper() or not mid.startswith("SYNC-") or len(mid) != 24:
            raise RequestError("Mã máy / mã phần cứng eSync không hợp lệ / không khớp")
        if payload.get("machine_id") and normalize_mid(payload["machine_id"]) != mid:
            raise RequestError("Mã máy eSync không khớp")
        return {"hw": h, "mid": mid}
    if product == "evoice":
        mid = code.lower().replace("-", "")
        if not HEX24.match(mid) or mid != hw.lower().replace("-", ""):
            raise RequestError("Mã máy eVoice không hợp lệ / không khớp")
        return {"hw": mid, "mid": mid}
    raise RequestError("Sản phẩm không hợp lệ")


# ---------------------------------------------------------------- cấp license
def issue_elive(secret: dict, hw: str, cust: str = "eCentric", exp: str = "2099-12-31") -> str:
    hw = hw.replace("-", "").upper()
    if not HEX32.match(hw):
        raise RequestError("HWID eLive phải 32 hex")
    mk, app = _secret_mk_app(secret)
    body = {"v": 1, "product": "eLive", "hwid": hw, "exp": exp, "cust": str(cust)[:80],
            "code_key": wrap_mk(mk, app, hw)}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    body["sig"] = base64.b64encode(_rsa_sign(secret["rsa_private_pem"], raw)).decode()
    return "ELIVEKEY-" + base64.b64encode(json.dumps(body, ensure_ascii=False).encode()).decode()


def issue_esync(secret: dict, mid: str, hw: str, cust: str = "eCentric") -> str:
    """Gói Lifetime (hết hạn 2099-12-31) – như mọi máy đang cấp."""
    from cryptography.fernet import Fernet
    mid, hw = normalize_mid(mid), hw.replace("-", "").upper()
    if not HEX32.match(hw) or not mid.startswith("SYNC-"):
        raise RequestError("Mã máy / HWID eSync không hợp lệ")
    fkey = secret.get("premium_fernet_key")
    if not fkey:
        raise RequestError("Thiếu premium_fernet_key trong khoá eSync trên máy chủ")
    expiry = datetime(2099, 12, 31)
    expiry_str = expiry.strftime("%Y-%m-%d %H:%M:%S")
    tier, max_duration = "Lifetime", 0
    premium_key = Fernet(fkey.encode() if isinstance(fkey, str) else fkey).encrypt(json.dumps({
        "datetime": expiry.strftime("%Y-%m-%d"), "is_font": False, "is_mac": []}).encode("utf-8")).decode("ascii")
    data_str = f"{mid}:{expiry_str}:{tier}:{max_duration}:{premium_key}"
    sig = _rsa_sign(secret["rsa_private_pem"], data_str.encode("utf-8"))
    mk, app = _secret_mk_app(secret)
    payload = {"machine_id": mid, "expiry_date": expiry_str, "license_type": tier, "max_video_duration": max_duration,
               "premium_key": premium_key, "signature": base64.b64encode(sig).decode("ascii"),
               "hwid": hw, "customer": str(cust)[:80], "model_key": wrap_mk(mk, app, hw)}
    return "SYNCKEY-" + base64.b64encode(json.dumps(payload, ensure_ascii=False).encode("utf-8")).decode("ascii")


_EVO_MAGIC = b"EVOX1\x00"


def issue_evoice(secret: dict, mid: str, cust: str = "eCentric", exp: str = "") -> str:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    def b(v):
        return v if isinstance(v, (bytes, bytearray)) else base64.b64decode(v)
    mid = mid.strip().lower().replace("-", "")
    if not HEX24.match(mid):
        raise RequestError("Mã máy eVoice phải 24 hex")
    app_secret = b(secret["app_secret"])
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=b"evoice-ai/mk-wrap/v1",
               info=b"evoice-ai/model-key").derive(app_secret + mid.encode())
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, b(secret["master_key"]), b"")
    wmk = _EVO_MAGIC + struct.pack("<I", 0) + nonce + ct
    payload = {"v": 1, "cust": str(cust)[:80], "mid": mid, "exp": exp, "feat": ["tts"], "wmk": _b64u_e(wmk)}
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    sig = Ed25519PrivateKey.from_private_bytes(b(secret["private_key"])).sign(raw)
    return f"{_b64u_e(raw)}.{_b64u_e(sig)}"


def issue(product: str, secret: dict, ident: dict, cust: str = "eCentric") -> str:
    if product == "elive":
        return issue_elive(secret, ident["hw"], cust)
    if product == "esync":
        return issue_esync(secret, ident["mid"], ident["hw"], cust)
    if product == "evoice":
        return issue_evoice(secret, ident["mid"], cust)
    raise RequestError("Sản phẩm không hợp lệ")


# ---------------------------------------------------------------- mã gói có chữ ký (chống tự bịa mã gói để được "máy đầu tiên")
def dist_message(dist: dict) -> bytes:
    d = dist or {}
    return "|".join(str(d.get(k) or "") for k in ("dist_id", "kind", "label", "created_at")).encode("utf-8")


GUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
DIST_KINDS = ("khach", "noi_bo")


def verify_dist(dist: dict, dist_secret: str) -> dict:
    """Mã gói do laptop ký (HMAC-SHA256, khoá khoa_goi.key – chỉ laptop + ERP có). Sai / thiếu chữ ký -> {} (coi như
    không có mã gói -> chờ duyệt). Không có dist_secret trên ERP -> cũng {} (an toàn: không tự cấp theo mã gói)."""
    d = dict(dist or {})
    sig = str(d.get("sig") or "").lower()
    key = (dist_secret or "").strip()
    if not d.get("dist_id") or not sig or not key:
        return {}
    # QC bảo mật T4: dist_id phải là GUID, kind thuộc danh sách, nhãn không chứa "|" (chống ghép chuỗi ký ra mã gói khác)
    if not GUID_RE.match(str(d.get("dist_id") or "").lower()) or d.get("kind") not in DIST_KINDS or "|" in str(d.get("label") or ""):
        return {}
    good = hmac.new(key.encode("utf-8"), dist_message(d), hashlib.sha256).hexdigest()
    return d if hmac.compare_digest(good, sig) else {}


# ---------------------------------------------------------------- nhận ra máy + luật duyệt
def _fp(d) -> dict:
    d = d or {}
    return {"guid_h": str(d.get("guid_h") or ""), "disk_h": str(d.get("disk_h") or ""),
            "mac_h": [str(x) for x in (d.get("mac_h") or []) if x][:8]}


def same_machine(a: dict, b: dict) -> bool:
    """Cùng máy khi: trùng MachineGuid VÀ (trùng ổ C: HOẶC trùng ít nhất 1 card mạng). Chỉ đổi card mạng / chỉ đổi ổ
    -> vẫn là máy cũ. Máy ảo nhân bản (trùng MachineGuid + ổ) -> coi là cùng máy (Windows nhân bản đúng cách sẽ đổi GUID)."""
    a, b = _fp(a), _fp(b)
    if not a["guid_h"] or a["guid_h"] != b["guid_h"]:
        return False
    if a["disk_h"] and a["disk_h"] == b["disk_h"]:
        return True
    return bool(set(a["mac_h"]) & set(b["mac_h"]))


def match_machine(machines: list, fp: dict):
    """machines: [{'name', 'fp': {...}, 'status'}] -> bản ghi trùng (ưu tiên đã duyệt) hoặc None."""
    hits = [m for m in machines or [] if same_machine(m.get("fp") or {}, fp)]
    hits.sort(key=lambda m: {"approved": 0, "blocked": 1, "pending": 2}.get(m.get("status"), 3))
    return hits[0] if hits else None


FIRST_DAYS = 14          # QC T5: gói chưa ai kích hoạt quá 14 ngày -> máy đầu tiên cũng phải chờ duyệt
INTERNAL_DAYS = 30       # QC C3: gói nội bộ chỉ tự cấp trong 30 ngày đầu, tối đa INTERNAL_MAX máy (ngoài IP văn phòng)
INTERNAL_MAX = 10
REISSUE_DAYS = 30        # QC C1: máy đã duyệt đổi ổ C: (mã phần cứng mới) -> tự cấp lại tối đa 1 lần / 30 ngày


def _age_days(created_at: str, now: float) -> float:
    try:
        txt = str(created_at).strip().replace("Z", "+00:00")
        txt = re.sub(r"(\.\d{6})\d+", r"\1", txt)  # PowerShell 'o' có 7 số lẻ giây
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is None:
            from datetime import timezone
            dt = dt.replace(tzinfo=timezone.utc)
        return (now - dt.timestamp()) / 86400.0
    except Exception:
        return 1e9  # không đọc được ngày -> coi như quá hạn (an toàn: chờ duyệt)


def decide(machine, dist: dict, dist_owner, ip: str = "", office_ips=(), internal_kinds=("noi_bo",),
           product: str = "", hw: str = "", fp: dict | None = None, now: float | None = None,
           dist_count: int = 0) -> tuple:
    """Luật anh Hoàn 17/11 + QC bảo mật. -> ('issue'|'pending'|'blocked', lý do NỘI BỘ – không trả nguyên cho máy khách).
    machine    : bản ghi máy trùng (match_machine) hoặc None. Có thể có 'hw' = {product: mã phần cứng v2 đã cấp / đã báo},
                 'reissued_at' = {product: thời điểm tự cấp lại gần nhất}
    dist       : mã gói ĐÃ KIỂM CHỮ KÝ (verify_dist) – {} nếu không có / sai
    dist_owner : máy ĐÃ DUYỆT đầu tiên của dist_id này (khác máy hiện tại) hoặc None
    dist_count : số máy đã được cấp theo dist_id này (cho gói nội bộ)
    """
    import time as _t
    now = _t.time() if now is None else now
    office = set(office_ips or ())
    if machine is not None:
        st = machine.get("status")
        if st == "blocked":
            return "blocked", "máy bị khoá"
        if st != "approved":
            return "pending", "đang chờ duyệt"
        known = (machine.get("hw") or {}).get(product) if product else None
        if not known or not hw or known == hw:
            return "issue", "máy đã duyệt (cấp lại đúng mã phần cứng cũ)"
        # QC C1: máy đã duyệt nhưng xin cho mã phần cứng KHÁC
        mf, nf = _fp(machine.get("fp")), _fp(fp)
        if mf["disk_h"] and mf["disk_h"] == nf["disk_h"]:
            # cùng Windows + cùng ổ mà mã phần cứng khác = không thể là máy này -> có người giả fp
            return "pending", "mã phần cứng không khớp máy đã duyệt (nghi giả máy) – chờ duyệt"
        last = float((machine.get("reissued_at") or {}).get(product) or 0)
        if now - last >= REISSUE_DAYS * 86400:
            return "issue", "máy đã duyệt đổi ổ C: – tự cấp lại (1 lần / 30 ngày)"
        return "pending", "máy đã duyệt đổi phần cứng nhiều lần – chờ duyệt"
    if ip and ip in office:
        return "issue", "mạng văn phòng"
    kind = (dist or {}).get("kind")
    age = _age_days((dist or {}).get("created_at"), now) if dist else 1e9
    if kind in set(internal_kinds or ()):
        if age <= INTERNAL_DAYS and dist_count < INTERNAL_MAX:
            return "issue", "gói nội bộ"
        return "pending", "gói nội bộ quá hạn / quá số máy – chờ duyệt"
    if (dist or {}).get("dist_id") and dist_owner is None:
        if age <= FIRST_DAYS:
            return "issue", "máy đầu tiên của gói"
        return "pending", "gói quá 14 ngày mới kích hoạt – chờ duyệt"
    if dist_owner is not None:
        return "pending", f"bản chép từ máy {dist_owner.get('name') or '?'} – chờ duyệt"
    return "pending", "không có mã gói (gói cũ / chép tay) – chờ duyệt"


CLIENT_PENDING_MSG = "Bản này đang chờ eCentric duyệt"  # QC T8: không lộ tên máy nguồn cho máy khách
