# Copyright (c) 2026, eCentric and contributors
"""Luat nghiep vu Giong doc AI - ham thuan (khong Frappe, khong mang), test duoc doc lap."""
import datetime
import hashlib
import hmac
import re

from ecentric_workspace.ai_tools.features.ai_voice import constants as C

_WORD = re.compile(r"\w", re.UNICODE)
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ------------------------------------------------------------------ quyen ---

def is_user(roles):
    return bool(set(roles or ()) & set(C.USER_ROLES))


def is_manager(roles):
    return bool(set(roles or ()) & set(C.MANAGER_ROLES))


def is_admin(roles):
    return bool(set(roles or ()) & set(C.ADMIN_ROLES))


def require_user(roles):
    if not is_user(roles):
        raise C.AiVoicePermission(C.Msg.NEED_USER)


def require_manager(roles):
    if not is_manager(roles):
        raise C.AiVoicePermission(C.Msg.NEED_MANAGER)


def require_admin(roles):
    if not is_admin(roles):
        raise C.AiVoicePermission(C.Msg.NEED_ADMIN)


def can_touch_job(job, user, roles):
    """Chu phieu hoac quan ly."""
    return bool(job) and (job.get("owner") == user or is_manager(roles))


def can_use_profile(profile, user, roles):
    """Giong dang dung + (khong han che, hoac la chu giong / quan ly)."""
    if not profile or profile.get("status") != C.VoiceStatus.ACTIVE or not profile.get("voice_id"):
        return False
    if int(profile.get("missing_on_server") or 0):          # may khong con giong -> phieu chac chan loi
        return False
    if int(profile.get("restricted") or 0):
        return profile.get("owner_user") == user or is_manager(roles)
    return True


# ------------------------------------------------------------------ noi dung phieu ---

def clean_text(text):
    """Giu nguyen chu nguoi dung go (kich ban live viet phien am co chu dich - KHONG sua chinh ta).
    Chi bo khoang trang dau / cuoi va chuan hoa xuong dong Windows."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def validate_text(text):
    t = clean_text(text)
    if not t:
        raise C.AiVoiceError(C.Msg.EMPTY_TEXT)
    if not _WORD.search(t):
        raise C.AiVoiceError(C.Msg.NO_WORDS)
    if len(t) > C.MAX_CHARS:
        raise C.AiVoiceError(C.Msg.TOO_LONG % (len(t), C.MAX_CHARS))
    return t


def norm_quality(q):
    q = str(q or "").strip() or C.DEFAULT_QUALITY
    if q not in {k for k, _, _ in C.QUALITIES}:
        raise C.AiVoiceError(C.Msg.BAD_QUALITY)
    return q


def norm_speed(s):
    if s in (None, ""):
        return C.SPEED_DEFAULT
    try:
        v = round(float(s), 2)
    except (TypeError, ValueError):
        raise C.AiVoiceError(C.Msg.BAD_SPEED)
    if v != v or not (C.SPEED_MIN <= v <= C.SPEED_MAX):   # v != v: NaN
        raise C.AiVoiceError(C.Msg.BAD_SPEED)
    return v


def norm_language(lang):
    lang = str(lang or "").strip() or "vi"
    if lang not in {k for k, _ in C.LANGUAGES}:
        raise C.AiVoiceError(C.Msg.BAD_LANGUAGE)
    return lang


def norm_title(title, text):
    t = re.sub(r"\s+", " ", str(title or "")).strip()
    if not t:
        t = re.sub(r"\s+", " ", text or "").strip()
        t = t[:60] + ("…" if len(t) > 60 else "")
    return t[:C.MAX_TITLE]


def job_payload(job, callback_url):
    """Body POST /v1/jobs gui sang eVoice."""
    p = {"input": job["text"], "voice": job["voice_key"], "quality": job["quality"],
         "speed": job["speed"], "language": job["language"], "format": "mp3", "ref": job["name"]}
    if job.get("breath") is not None:
        p["breath"] = bool(int(job["breath"]))
    if callback_url:
        p["callback_url"] = callback_url
    return p


# ------------------------------------------------------------------ trang thai tu may ---

def remote_update(remote):
    """Ket qua GET /v1/jobs/{id} (hoac body callback) -> cac truong cap nhat cho EC AI Voice Job.
    Trang thai la -> bo qua (tra {})."""
    if not isinstance(remote, dict):
        return {}
    st = str(remote.get("status") or "")
    if st not in (C.JobStatus.QUEUED, C.JobStatus.RUNNING, C.JobStatus.DONE, C.JobStatus.ERROR, C.JobStatus.CANCELLED):
        return {}
    out = {"status": st, "progress": str(remote.get("progress") or "")[:20]}
    if st == C.JobStatus.QUEUED:
        out["position"] = _int(remote.get("position"))
    else:
        out["position"] = 0
    for k in ("seconds", "gen_seconds"):
        v = _float(remote.get(k))
        if v is not None:
            out[k] = v
    if st == C.JobStatus.ERROR:
        out["error"] = (str(remote.get("error") or "") or "Máy giọng đọc báo lỗi.")[:500]
    if st == C.JobStatus.CANCELLED:
        out["error"] = C.Msg.CANCELLED
    return out


def is_stale_update(current_status, new_status):
    """Callback / poll den tre khong duoc keo phieu da xong lui lai (done -> running...)."""
    if current_status in C.JobStatus.FINAL:
        return True
    order = {C.JobStatus.PENDING: 0, C.JobStatus.QUEUED: 1, C.JobStatus.RUNNING: 2}
    if new_status in C.JobStatus.FINAL:
        return False
    return order.get(new_status, -1) < order.get(current_status, -1)


# ------------------------------------------------------------------ chu ky callback ---

def sign(token, body):
    return hmac.new(str(token or "").encode("utf-8"), body or b"", hashlib.sha256).hexdigest()


def verify_signature(token, body, signature):
    """X-eVoice-Signature = hex(HMAC-SHA256(token, raw_body)). Khong co token -> tu choi."""
    if not token or not signature or not isinstance(body, (bytes, bytearray)):
        return False
    return hmac.compare_digest(sign(token, bytes(body)), str(signature).strip().lower())


# ------------------------------------------------------------------ giong ---

def norm_gender(g):
    g = str(g or "").strip()
    if g and g not in C.GENDERS:
        raise C.AiVoiceError(C.Msg.BAD_GENDER)
    return g


def validate_voice_fields(name, gender, description):
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    if not name:
        raise C.AiVoiceError(C.Msg.NAME_REQUIRED)
    if len(name) > C.MAX_NAME:
        raise C.AiVoiceError(C.Msg.NAME_TOO_LONG)
    return name, norm_gender(gender), str(description or "").strip()[:C.MAX_DESC]


def validate_sample_file(file_name, size):
    ext = ("." + str(file_name or "").rsplit(".", 1)[-1].lower()) if "." in str(file_name or "") else ""
    if ext not in C.VOICE_EXTS:
        raise C.AiVoiceError(C.Msg.BAD_EXT)
    if size is not None and int(size) > C.MAX_VOICE_BYTES:
        raise C.AiVoiceError(C.Msg.FILE_TOO_BIG)
    return ext


def validate_consent(by, date, confirmed):
    by = re.sub(r"\s+", " ", str(by or "")).strip()[:140]
    date = str(date or "").strip()
    if not by or not date or not _truthy(confirmed):
        raise C.AiVoiceError(C.Msg.CONSENT_REQUIRED)
    if not _DATE.match(date):
        raise C.AiVoiceError(C.Msg.CONSENT_DATE)
    try:
        datetime.date.fromisoformat(date)
    except ValueError:
        raise C.AiVoiceError(C.Msg.CONSENT_DATE)
    return by, date


def norm_base_url(url):
    url = str(url or "").strip().rstrip("/")
    if not re.match(r"^https?://[A-Za-z0-9.-]+(:\d+)?(/[\w./-]*)?$", url):
        raise C.AiVoiceError(C.Msg.BAD_URL)
    return url


def erp_marker(profile_name):
    return C.ERP_MARKER % profile_name


def with_marker(description, profile_name):
    """Mo ta gui len may = mo ta + dau [erp:<ho so>] (de doi chieu khi upload bi Cloudflare cat ngang)."""
    m = erp_marker(profile_name)
    d = str(description or "").strip()
    return (d + " " + m).strip() if m not in d else d


def strip_marker(description):
    return re.sub(r"\s*\[erp:[A-Za-z0-9_-]+\]", "", str(description or "")).strip()


def marker_of(description):
    m = re.search(r"\[erp:([A-Za-z0-9_-]+)\]", str(description or ""))
    return m.group(1) if m else None


def match_remote_voice(remote_voices, profile_name, known_ids):
    """Tim giong vua tao tren may theo DAU [erp:<ho so>] trong mo ta - KHONG doan theo ten (QC 15/11: trung ten
    voi giong tao tay trong app se gan nham va ghi dong y cho giong cua nguoi khac)."""
    cand = [v for v in (remote_voices or []) if marker_of(v.get("description")) == profile_name
            and v.get("id") and v.get("id") not in known_ids]
    return cand[-1]["id"] if cand else None


def fetch_backoff_seconds(attempts):
    """Tai MP3 that bai: 2, 4, 8, 16, 32 phut roi 60 phut / lan (job poll moi 2 phut)."""
    return min(60 * (2 ** max(int(attempts or 0), 0)), C.FETCH_MAX_WAIT) if attempts else 0


def callback_base(url):
    """Dia chi ERP cho callback: bat buoc https voi ten mien that (POST bi redirect http->https se thanh GET)."""
    u = str(url or "").strip().rstrip("/")
    if u.startswith("http://") and not re.match(r"^http://(localhost|127\.|10\.|192\.168\.|\[?::1)", u):
        u = "https://" + u[7:]
    return u if u.startswith(("http://", "https://")) else ""


# ------------------------------------------------------------------ nho ---

def _truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _float(v):
    try:
        f = float(v)
        return None if f != f else round(f, 2)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ thoi gian ---

def parse_dt(v):
    """'YYYY-MM-DD HH:MM:SS[.ffffff]' / datetime -> datetime (None neu rong / sai)."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime.datetime):
        return v
    s = str(v).strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def age_seconds(v, now):
    """So giay tu moc v toi now; moc rong -> rat lon (coi nhu qua han)."""
    d = parse_dt(v)
    if d is None:
        return 10 ** 9
    return (now - d).total_seconds()


def submit_backoff_seconds(attempts):
    """Gui lai phieu PENDING: 0, 2, 4, 8, 16, 30 phut (job nen chay moi 2 phut)."""
    return min(60 * (2 ** max(int(attempts or 0), 0)), 30 * 60) if attempts else 0
