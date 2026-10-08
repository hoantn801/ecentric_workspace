# Copyright (c) 2026, eCentric and contributors
"""Nhip gui tin DAY RA NGOAI APP (Teams, web push) - 08/10/2026, Hoan.

Hai luat, ap chung cho MOI nguon thong bao (phieu duyet, PM, nhac han, weekly...) vi ca hai
deu chay o route_delivery - khong phai sua tung job:

1. GIO YEN LANG (21:00 -> 09:00): tin phat sinh trong khung nay KHONG ban ra dien thoai.
   Dong Delivery Log ghi status "Held", next_retry_at = 9:00 ngay LAM VIEC ke tiep cua nguoi
   nhan (bo T7/CN, ngay le, ngay nghi phep da duyet - ngay_lam_viec.la_ngay_nghi). Chuong
   trong ERP van hien ngay: no im lang, chi ai dang mo ERP moi thay.
   Vi sao: 28/09-04/10 job nhac UNC chay 00:01 ban 30 tin Teams/dem cho Finance; 06/10 co
   nguoi giao 10 task PM luc 2h sang -> 10 tin Teams. Doi gio tung job khong chan duoc loai
   thu hai.

2. GOP TIN: nguoi nhan vua nhan mot tin day (cung kenh) trong CUA_SO phut -> tin moi giu lai
   toi het cua so, roi gom tat ca thanh MOT tin "Ban co N phieu can xu ly". Tin dau tien van
   gui ngay (mot phieu le loi khong bi cham). Job nhac hang loat bat `gop_tin()` de gom ngay
   tu tin dau. Vi sao: 08/10 15h chi Phuong nhan 22 tin Payment Request trong mot gio.

Mien tru: severity "urgent" (system_critical, task_overdue) va nhac cham cong (job 8h30/9h30
co y ban truoc han 10:00) - gui nhu cu.
Tat het: site_config `ec_notify_pacing = {"tat": 1}`. Doi khung gio / cua so: cung key do.
Fail-open: loi tra cuu -> gui ngay nhu truoc (mat nhip con hon mat tin)."""
import contextlib
import datetime as _dt
import functools
import hashlib
from collections import Counter, OrderedDict

import frappe

DELIVERY_DT = "EC Notification Delivery Log"
KENH_DAY = ("teams", "webpush")
ST_GIU = "Held"
ST_GOP = "Merged"
_DANG_SONG = ("Pending", "Sent", "Failed", ST_GIU, ST_GOP)
_MAC_DINH = {"tat": 0, "dem_tu": "21:00", "dem_den": "09:00", "gui_luc": "09:00", "cua_so_phut": 3}
_MIEN_EVENT = ("system_critical", "attendance_missing", "attendance_missing_final")
_SEV_RANK = {"info": 0, "action_required": 1, "urgent": 2}
_PROVIDER = {
    "teams": "ecentric_workspace.notification_center.providers.teams.deliver",
    "webpush": "ecentric_workspace.notification_center.providers.webpush.deliver",
}
_TRANG_GOP = "/viec-cua-toi"
_TOI_DA_DONG = 6


# ------------------------------------------------------------------ cau hinh + gio
def cau_hinh():
    out = dict(_MAC_DINH)
    try:
        raw = (frappe.get_conf() or {}).get("ec_notify_pacing")
        if isinstance(raw, dict):
            out.update({k: raw[k] for k in _MAC_DINH if k in raw})
    except Exception:
        pass
    return out


def _phut(hhmm):
    h, m = str(hhmm).split(":")[:2]
    return int(h) * 60 + int(m)


def la_gio_dem(now, cfg):
    s, e, n = _phut(cfg["dem_tu"]), _phut(cfg["dem_den"]), now.hour * 60 + now.minute
    if s == e:
        return False
    return (s <= n < e) if s < e else (n >= s or n < e)


def _la_nghi_mac_dinh(user, day):
    try:
        from ecentric_workspace.approval_center.shared.workflow.ngay_lam_viec import la_ngay_nghi
        return la_ngay_nghi(user, day)
    except Exception:
        return day.weekday() >= 5


def gio_gui_ke_tiep(recipient, now, cfg, la_nghi=None):
    """9:00 (gui_luc) gan nhat SAU `now`, roi doi tiep qua ngay nghi cua nguoi nhan."""
    la_nghi = la_nghi or _la_nghi_mac_dinh
    g = _phut(cfg["gui_luc"])
    day = now.date() if now.hour * 60 + now.minute < g else now.date() + _dt.timedelta(days=1)
    for _ in range(15):
        if not la_nghi(recipient, day):
            break
        day += _dt.timedelta(days=1)
    return _dt.datetime.combine(day, _dt.time(g // 60, g % 60))


# ------------------------------------------------------------------ quyet dinh
def _co_trang_thai_giu():
    """DocType da co status Held/Merged chua (migrate xong). Chua -> KHONG giu: insert "Held"
    vao Select chua khai se hong, _delivery nuot loi va tin bien mat."""
    try:
        opts = (frappe.get_meta(DELIVERY_DT).get_field("status").options or "").split("\n")
        return ST_GIU in opts and ST_GOP in opts
    except Exception:
        return False


@contextlib.contextmanager
def gop_tin():
    """Job nhac hang loat boc vong gui trong khoi nay: moi tin day bi giu cua_so phut roi gop,
    ke ca tin dau - nguoi nhan 5 loi nhac UNC thay 1 tin chu khong phai 1 + 1."""
    flags = getattr(frappe, "flags", None)
    if flags is None:                    # ngoai site (test stub) - khong co gi de bat
        yield
        return
    cu = getattr(flags, "ec_gop_tin", None)
    flags.ec_gop_tin = True
    try:
        yield
    finally:
        flags.ec_gop_tin = cu


def gop_tin_job(fn):
    """Decorator cho job nhac hang loat (cron 09:00): chay ca job trong gop_tin()."""
    @functools.wraps(fn)
    def _w(*a, **k):
        with gop_tin():
            return fn(*a, **k)
    return _w


def _dot_dang_giu(recipient, channel):
    rows = frappe.get_all(DELIVERY_DT, filters={"recipient": recipient, "channel": channel,
                                                "status": ST_GIU},
                          fields=["next_retry_at"], order_by="next_retry_at asc",
                          limit_page_length=1)
    return frappe.utils.get_datetime(rows[0]["next_retry_at"]) if rows and rows[0].get("next_retry_at") else None


def _vua_co_tin(recipient, channel, since):
    return bool(frappe.get_all(DELIVERY_DT, filters={
        "recipient": recipient, "channel": channel, "status": ["in", list(_DANG_SONG)],
        "creation": [">=", since]}, pluck="name", limit_page_length=1))


def hen_gio(recipient, channel, severity, event_type=None, now=None, cfg=None):
    """None = gui ngay. datetime = giu (status Held) den luc do."""
    try:
        if channel not in KENH_DAY or severity == "urgent" or event_type in _MIEN_EVENT:
            return None
        cfg = cfg or cau_hinh()
        if cfg.get("tat") or not _co_trang_thai_giu():
            return None
        now = now or frappe.utils.now_datetime()
        if la_gio_dem(now, cfg):
            return gio_gui_ke_tiep(recipient, now, cfg)
        w = _dt.timedelta(minutes=int(cfg.get("cua_so_phut") or 0))
        if not w:
            return None
        dot = _dot_dang_giu(recipient, channel)
        if dot and dot <= now + w:
            return dot                       # nhap vao dot dang cho gui
        if getattr(getattr(frappe, "flags", None), "ec_gop_tin", None) or _vua_co_tin(recipient, channel, now - w):
            return now + w
        return None
    except Exception:
        frappe.log_error(title="nhip_gui.hen_gio", message=frappe.get_traceback())
        return None


# ------------------------------------------------------------------ noi dung tin gop
def noi_dung_gop(items):
    """items: dong Held cung nguoi nhan + kenh. Tra dict title/message/event_type/severity."""
    n = len(items)
    types_ = Counter(it.get("event_type") or "approval_required" for it in items)
    if set(types_) == {"approval_required"}:
        title = "Bạn có %d phiếu cần xử lý" % n
    else:
        title = "Bạn có %d thông báo mới trên ERP" % n
    lines = ["• " + str(it.get("title") or "")[:110] for it in items[:_TOI_DA_DONG]]
    if n > _TOI_DA_DONG:
        lines.append("… và %d thông báo khác" % (n - _TOI_DA_DONG))
    sev = max((it.get("severity") or "info" for it in items), key=lambda s: _SEV_RANK.get(s, 0))
    return {"title": title, "message": "\n".join(lines),
            "event_type": types_.most_common(1)[0][0], "severity": sev}


# ------------------------------------------------------------------ job xa tin
def _enqueue(channel, name):
    frappe.enqueue(_PROVIDER[channel], queue="default", enqueue_after_commit=True,
                   delivery_log=name)


def _da_doc(items):
    logs = [it["notification_log"] for it in items if it.get("notification_log")]
    if not logs:
        return set()
    return set(frappe.get_all("Notification Log", filters={"name": ["in", logs], "read": 1},
                              pluck="name"))


def _tao_tin_gop(recipient, channel, items, now):
    nd = noi_dung_gop(items)
    eid = hashlib.sha1(("ecnc:gop|%s|%s|%s" % (recipient, channel, now)).encode("utf-8")).hexdigest()[:16]
    try:
        url = (frappe.utils.get_url() or "").rstrip("/") + _TRANG_GOP
    except Exception:
        url = _TRANG_GOP
    doc = frappe.get_doc({
        "doctype": DELIVERY_DT, "idempotency_key": eid + "|" + recipient + "|" + channel,
        "event_id": eid, "recipient": recipient, "channel": channel, "status": "Pending",
        "attempt_count": 0, "provider": "", "event_type": nd["event_type"],
        "severity": nd["severity"], "dedupe_key": ("gop|%s|%s" % (recipient, now))[:140],
        "title": nd["title"], "message": nd["message"], "action_url": url, "actor": "",
        "reference_doctype": "", "reference_name": "", "notification_log": "",
    }).insert(ignore_permissions=True)
    return doc.name


def xa_tin_giu(now=None):
    """Cron moi phut: gui cac dong Held da den gio. Mot nguoi + mot kenh: 1 dong -> gui nguyen
    ban; nhieu dong -> 1 tin gop, cac dong goc chuyen "Merged" (provider = gop:<ten tin gop>).
    Dong ma nguoi nhan DA DOC tren chuong ERP -> "Suppressed" (DA_DOC), khong ban lai."""
    now = now or frappe.utils.now_datetime()
    rows = frappe.get_all(DELIVERY_DT, filters={"status": ST_GIU, "next_retry_at": ["<=", now]},
                          fields=["name", "recipient", "channel", "event_type", "severity",
                                  "title", "notification_log"],
                          order_by="creation asc", limit_page_length=5000)
    nhom = OrderedDict()
    for r in rows:
        nhom.setdefault((r["recipient"], r["channel"]), []).append(r)
    dem = {"don": 0, "gop": 0, "da_doc": 0}
    for (recipient, channel), items in nhom.items():
        try:
            doc_roi = _da_doc(items)
            for it in items:
                if it.get("notification_log") in doc_roi:
                    frappe.db.set_value(DELIVERY_DT, it["name"], {
                        "status": "Suppressed", "next_retry_at": None, "error_code": "DA_DOC",
                        "error_message": "Nguoi nhan da doc tren ERP truoc gio gui"})
                    dem["da_doc"] += 1
            items = [it for it in items if it.get("notification_log") not in doc_roi]
            if not items:
                continue
            if len(items) == 1:
                frappe.db.set_value(DELIVERY_DT, items[0]["name"],
                                    {"status": "Pending", "next_retry_at": None})
                _enqueue(channel, items[0]["name"])
                dem["don"] += 1
                continue
            ten = _tao_tin_gop(recipient, channel, items, now)
            for it in items:
                frappe.db.set_value(DELIVERY_DT, it["name"], {
                    "status": ST_GOP, "next_retry_at": None, "provider": "gop:" + ten})
            _enqueue(channel, ten)
            dem["gop"] += 1
        except Exception:
            frappe.log_error(title="nhip_gui.xa_tin_giu %s" % recipient,
                             message=frappe.get_traceback())
    return dem
