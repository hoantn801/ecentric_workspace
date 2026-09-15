# Copyright (c) 2026, eCentric and contributors
"""Web Push delivery (Notification Delivery v1, kenh "webpush").

MUC DICH: dua thong bao RA NGOAI app - popup tren man hinh dien thoai / desktop ngay
ca khi khong mo tab nao. Day la kenh duy nhat khong phu thuoc Microsoft Teams.

KIEN TRUC
  Notification Center -> route_delivery() ghi mot EC Notification Delivery Log
  (channel="webpush", status="Pending") roi enqueue deliver() o hang doi nen.
  deliver() tim moi EC Web Push Subscription dang active cua nguoi nhan (mot nguoi
  co the co nhieu trinh duyet/thiet bi) va day payload qua VAPID.

FAIL-OPEN BANG THIET KE
  Chua cai pywebpush, chua sinh khoa VAPID, nguoi dung chua cap quyen -> tat ca deu
  ket thuc bang status "Skipped" kem error_code ro rang. Khong bao gio nem loi len
  nghiep vu goi no, va khong bao gio chan cac kenh khac.

VE SINH VONG DOI DANG KY
  Push service tra 404/410 nghia la dang ky da chet vinh vien (go PWA, xoa du lieu
  trinh duyet). Khi do ban ghi bi BO TICH active - khong xoa, de con dau vet chuan
  doan. Loi 401/403 la loi KHOA VAPID sai, khong phai loi cua nguoi dung, nen khong
  bao gio tat dang ky vi ly do do.
"""
import json

import frappe

DELIVERY_DT = "EC Notification Delivery Log"
SUB_DT = "EC Web Push Subscription"
SETTINGS_DT = "EC Web Push Settings"
MAX_ATTEMPTS = 3
TIMEOUT = 10
_RETRY_BACKOFF_MIN = (2, 15)      # phut giua lan 1->2 va 2->3
_DEAD_CODES = (404, 410)          # dang ky chet han
TTL = 3600                        # push service giu toi da 1 gio roi bo


# --------------------------------------------------------------------- cau hinh
def get_settings():
    """Tra ve dict cau hinh (khong bao gio nem). private_key co the rong."""
    out = {"enabled": 0, "public_key": "", "private_key": "", "subject": ""}
    try:
        doc = frappe.get_cached_doc(SETTINGS_DT)
    except Exception:
        return out
    out["enabled"] = 1 if doc.get("enabled") else 0
    out["public_key"] = (doc.get("vapid_public_key") or "").strip()
    out["subject"] = (doc.get("vapid_subject") or "").strip()
    try:
        out["private_key"] = doc.get_password("vapid_private_key", raise_exception=False) or ""
    except Exception:
        out["private_key"] = ""
    return out


def is_configured(cfg=None):
    cfg = cfg or get_settings()
    return bool(cfg["enabled"] and cfg["public_key"] and cfg["private_key"] and cfg["subject"])


def _import_pywebpush():
    """Import tre: thieu thu vien la mot trang thai HOP LE (Skipped), khong phai crash."""
    try:
        from pywebpush import webpush, WebPushException
        return webpush, WebPushException
    except Exception:
        return None, None


# --------------------------------------------------------------------- sinh khoa
@frappe.whitelist(methods=["POST"])
def generate_vapid_keys_api():
    """Nut "Sinh khoa VAPID" tren EC Web Push Settings.

    VI SAO CAN DIEM VAO NAY: site chay tren Frappe Cloud, khong co ai co shell de go
    `bench execute`. Neu khong co nut nay thi cach duy nhat con lai la sinh khoa o mot
    may khac roi DAN KHOA BI MAT qua chat/email - tuc la bi mat di qua mot kenh khong
    kiem soat duoc. Khoa sinh o day khong bao gio roi khoi server.

    Chi System Manager. Khong ghi de khoa da co."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(frappe._("Chi System Manager moi duoc sinh khoa VAPID."))
    return generate_vapid_keys()


@frappe.whitelist(methods=["POST"])
def send_test_push():
    """Nut "Gui thu" - day mot thong bao push den chinh nguoi dang bam.

    Di THANG qua provider (khong qua Notification Center) de test dung mot thu: cap
    khoa + thu vien + dang ky trinh duyet. Khong dinh den ma tran kenh, khong tao
    Notification Log rac trong hop thu."""
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(frappe._("Can dang nhap."))
    cfg = get_settings()
    if not is_configured(cfg):
        return {"ok": False, "reason": "NOT_CONFIGURED",
                "detail": "Chua bat hoac chua co khoa VAPID."}
    webpush, _exc = _import_pywebpush()
    if webpush is None:
        return {"ok": False, "reason": "NO_LIBRARY",
                "detail": "Chua cai pywebpush tren bench. Kiem tra pyproject.toml roi deploy lai."}
    subs = frappe.get_all(SUB_DT, filters={"user": user, "active": 1},
                          fields=["name", "endpoint", "p256dh", "auth"], limit=20)
    if not subs:
        return {"ok": False, "reason": "NO_SUBSCRIPTION",
                "detail": "Trinh duyet nay chua cap quyen thong bao. Mo mot trang ERP, bam Bat o dai thong bao roi thu lai."}
    import json as _json
    body = _json.dumps({"title": "eCentric ERP",
                        "body": "Đây là thông báo thử. Nếu bạn thấy dòng này thì web push đã chạy.",
                        "url": "/ec-hr/attendance", "tag": "ec-test",
                        "ts": _ts_ms(frappe.utils.now_datetime())}, ensure_ascii=False)
    ok = 0
    errs = []
    for s in subs:
        try:
            webpush(subscription_info={"endpoint": s.endpoint,
                                       "keys": {"p256dh": s.p256dh or "", "auth": s.auth or ""}},
                    data=body, vapid_private_key=cfg["private_key"],
                    vapid_claims={"sub": cfg["subject"]}, ttl=TTL, timeout=TIMEOUT)
            ok += 1
        except Exception as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            errs.append(str(code or e.__class__.__name__))
            if code in _DEAD_CODES:
                _deactivate(s.name, "HTTP %s (gui thu)" % code)
    frappe.db.commit()
    return {"ok": ok > 0, "sent": ok, "devices": len(subs), "errors": errs}


def generate_vapid_keys():
    """Sinh cap khoa EC P-256 theo chuan VAPID, ghi thang vao EC Web Push Settings.

    Goi tu nut tren man hinh Settings (generate_vapid_keys_api), hoac tu shell:
        bench --site <site> execute
            ecentric_workspace.notification_center.providers.webpush.generate_vapid_keys
    KHONG ghi de khoa da co - doi khoa khi da co nguoi dang ky se lam chet toan bo
    dang ky cu. Muon doi that thi xoa tay hai o trong Settings roi chay lai.
    """
    doc = frappe.get_doc(SETTINGS_DT)
    if (doc.vapid_public_key or "").strip():
        return {"ok": False, "reason": "Da co khoa VAPID - khong ghi de."}
    import base64
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    def b64(raw):
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    priv = ec.generate_private_key(ec.SECP256R1())
    pub_raw = priv.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    priv_raw = priv.private_numbers().private_value.to_bytes(32, "big")

    doc.vapid_public_key = b64(pub_raw)
    doc.vapid_private_key = b64(priv_raw)
    if not (doc.vapid_subject or "").strip():
        doc.vapid_subject = "mailto:it@ecentric.vn"
    doc.enabled = 1
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True, "public_key": doc.vapid_public_key}


# --------------------------------------------------------------------- gui
def _payload(doc):
    """Payload gui xuong service worker. Chi mang chuoi hien thi + duong dan -
    KHONG mang du lieu nhay cam: noi dung nay nam tren push service cua Google/Apple."""
    return json.dumps({
        "title": (doc.get("title") or "eCentric ERP")[:120],
        "body": _plain(doc.get("message"))[:240],
        "url": doc.get("action_url") or "/",
        "tag": doc.get("event_type") or "ec",
        "event_id": doc.get("event_id") or "",
        # Gio SU KIEN (ms). Push co the den muon vai phut - dien thoai ngu, mang
        # chap chon - va neu khong gui moc nay thi the thong bao ghi "vua xong"
        # cho mot loi nhac tu 20 phut truoc, va xep sai thu tu trong khay.
        "ts": _ts_ms(doc.get("creation")),
    }, ensure_ascii=False)


def _ts_ms(dt):
    """Doi gio cua ban ghi sang epoch mili-giay. Hong thi tra 0 - service worker
    tu lui ve Date.now(), te hon mot chut nhung khong bao gio lam mat thong bao."""
    try:
        import calendar
        d = frappe.utils.get_datetime(dt)
        return int(calendar.timegm(d.utctimetuple()) * 1000)
    except Exception:
        return 0


def _plain(s):
    import re
    if not s:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", str(s))).strip()


def _deactivate(sub_name, reason):
    try:
        frappe.db.set_value(SUB_DT, sub_name,
                            {"active": 0, "last_error": str(reason)[:500]},
                            update_modified=False)
    except Exception:
        pass


def _mark_retry_or_fail(doc, code, err):
    n = doc.attempt_count or 1
    if n < MAX_ATTEMPTS:
        mins = _RETRY_BACKOFF_MIN[min(n - 1, len(_RETRY_BACKOFF_MIN) - 1)]
        doc.status = "Failed"
        doc.next_retry_at = frappe.utils.add_to_date(frappe.utils.now_datetime(), minutes=mins)
    else:
        doc.status = "Failed"
        doc.next_retry_at = None
    doc.provider = "webpush"
    doc.error_code = str(code or "ERROR")[:140]
    doc.error_message = str(err or "")[:500]


def deliver(delivery_log):
    """Diem vao cua hang doi. Gui MOT thong bao toi MOI thiet bi dang ky cua nguoi
    nhan. Idempotent: dong da Sent thi khong gui lai."""
    try:
        doc = frappe.get_doc(DELIVERY_DT, delivery_log)
    except Exception:
        return
    if doc.get("status") == "Sent":
        return

    doc.attempt_count = (doc.attempt_count or 0) + 1
    doc.last_attempt_at = frappe.utils.now_datetime()

    cfg = get_settings()
    if not is_configured(cfg):
        doc.provider = "webpush"
        doc.status = "Skipped"
        doc.next_retry_at = None
        doc.error_code = "NOT_CONFIGURED"
        doc.error_message = "Web push chua bat hoac chua co khoa VAPID."
        doc.save(ignore_permissions=True)
        return

    webpush, WebPushException = _import_pywebpush()
    if webpush is None:
        doc.provider = "webpush"
        doc.status = "Skipped"
        doc.next_retry_at = None
        doc.error_code = "NO_LIBRARY"
        doc.error_message = "Chua cai pywebpush tren bench."
        doc.save(ignore_permissions=True)
        return

    subs = frappe.get_all(
        SUB_DT, filters={"user": doc.get("recipient"), "active": 1},
        fields=["name", "endpoint", "p256dh", "auth"], limit=20)
    if not subs:
        doc.provider = "webpush"
        doc.status = "Skipped"
        doc.next_retry_at = None
        doc.error_code = "NO_SUBSCRIPTION"
        doc.error_message = "Nguoi nhan chua cap quyen thong bao tren trinh duyet nao."
        doc.save(ignore_permissions=True)
        return

    body = _payload(doc)
    claims = {"sub": cfg["subject"]}
    sent = 0
    last_code = last_err = None
    for s in subs:
        info = {"endpoint": s.endpoint,
                "keys": {"p256dh": s.p256dh or "", "auth": s.auth or ""}}
        try:
            webpush(subscription_info=info, data=body,
                    vapid_private_key=cfg["private_key"], vapid_claims=dict(claims),
                    ttl=TTL, timeout=TIMEOUT)
            sent += 1
            frappe.db.set_value(SUB_DT, s.name,
                                {"last_success_at": frappe.utils.now_datetime(),
                                 "failure_count": 0, "last_error": ""},
                                update_modified=False)
        except Exception as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            last_code, last_err = code or e.__class__.__name__, str(e)[:300]
            if code in _DEAD_CODES:
                _deactivate(s.name, "HTTP %s - dang ky da chet, da bo tich active." % code)
            else:
                try:
                    frappe.db.set_value(
                        SUB_DT, s.name,
                        {"failure_count": (frappe.db.get_value(SUB_DT, s.name, "failure_count") or 0) + 1,
                         "last_error": last_err},
                        update_modified=False)
                except Exception:
                    pass

    if sent:
        doc.provider = "webpush"
        doc.status = "Sent"
        doc.sent_at = frappe.utils.now_datetime()
        doc.next_retry_at = None
        doc.error_code = ""
        doc.error_message = "" if sent == len(subs) else ("Gui duoc %s/%s thiet bi." % (sent, len(subs)))
    elif last_code in _DEAD_CODES:
        # Moi dang ky deu chet -> khong co gi de thu lai.
        doc.provider = "webpush"
        doc.status = "Skipped"
        doc.next_retry_at = None
        doc.error_code = "SUBSCRIPTION_GONE"
        doc.error_message = last_err or ""
    else:
        _mark_retry_or_fail(doc, last_code, last_err)
    doc.save(ignore_permissions=True)


def process_webpush_retries():
    """Scheduler: day lai nhung ban gui that bai da den han thu lai. Co chan tren
    MAX_ATTEMPTS, idempotent."""
    now = frappe.utils.now_datetime()
    rows = frappe.get_all(DELIVERY_DT, filters={
        "channel": "webpush", "status": "Failed",
        "next_retry_at": ["<=", now],
        "attempt_count": ["<", MAX_ATTEMPTS],
    }, pluck="name", limit=200)
    for nm in rows:
        try:
            frappe.enqueue("ecentric_workspace.notification_center.providers.webpush.deliver",
                           queue="default", delivery_log=nm)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "process_webpush_retries")
    return {"requeued": len(rows)}
