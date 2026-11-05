# Copyright (c) 2026, eCentric and contributors
"""ERP tu day khuon mat xuong may Hikvision (ec-face-push-v1, 05/11/2026).

Hoan chot 05/11: ERP goi THANG vao may qua router van phong (mo cong, CHI cho IP cua ERP).
  * Nhan vien gui anh tren /khuon-mat -> job nen day ngay xuong moi may.
  * Moi 10 phut: doi chieu lai (may vua bat lai, lan truoc loi...) + XOA nguoi da nghi viec
    khoi may (mat quyen mo cua).
  * Chi xoa nguoi ERP biet la da nghi. Nguoi tren may ma ERP khong biet -> de nguyen.

Cau hinh (Frappe Cloud > Site Config), KHONG commit:
  ec_face_devices = [{"name": "T1", "url": "https://<IP public>:<cong>", "user": "admin",
                      "password": "...", "fingerprint": "<sha256 chung chi, xem tren /khuon-mat>"}]
  ec_face_push_disabled = 1  -> tam dung day.
Trang thai moi may luu o __global defaults (khong them DocType / truong).
"""
import json
import time

import frappe

from ecentric_workspace.hr.face_photo import constants as C
from ecentric_workspace.hr.face_photo import isapi, naming

CONF_DEVICES = "ec_face_devices"
CONF_DISABLED = "ec_face_push_disabled"
STATE_KEY = "ec_face_push_state"      # {device: {no: photo | "fail:photo"}}
STATUS_KEY = "ec_face_push_status"    # {device: {...}} - hien tren trang HR
LOCK_KEY = "ec_face_push_lock"
LOCK_SECONDS = 600
JOB = "ecentric_workspace.hr.face_photo.push.run_all"
LEFT_STATUSES = ("Left", "Inactive", "Suspended")


def devices():
    raw = frappe.conf.get(CONF_DEVICES) or []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = []
    return [d for d in raw if isinstance(d, dict) and d.get("name")]


def _load(key):
    try:
        return json.loads(frappe.db.get_global(key) or "{}") or {}
    except ValueError:
        return {}


def _save(key, value):
    frappe.db.set_global(key, json.dumps(value, ensure_ascii=False))


def _cert_der(host, port):
    import ssl
    return ssl.PEM_cert_to_DER_cert(ssl.get_server_certificate((host, port), timeout=10))


def _http():
    import requests
    try:
        import urllib3
        urllib3.disable_warnings()
    except Exception:
        pass
    return requests.Session()


def erp_snapshot():
    from ecentric_workspace.hr.face_photo import service
    act = frappe.get_all("Employee", filters={"status": "Active"},
                         fields=["name", "employee_name", "attendance_device_id"], limit_page_length=0)
    ph = service._photos([e.name for e in act])
    active = [{"no": naming.device_no(e.name, e.attendance_device_id),
               "name": naming.ascii_name(e.employee_name), "employee": e.name,
               "photo": ph[e.name].name if e.name in ph else ""} for e in act]
    left = [naming.device_no(e.name, e.attendance_device_id)
            for e in frappe.get_all("Employee", filters={"status": ("in", LEFT_STATUSES)},
                                    fields=["name", "attendance_device_id"], limit_page_length=0)]
    return {"active": active, "left": set(left) - {a["no"] for a in active}}


def sync_device(cfg, erp, state, photo_bytes, http=None, cert_der=None):
    """Mot may. -> (state_moi, status). Khong raise: loi ghi vao status."""
    from frappe.utils import now
    st = {"name": cfg.get("name"), "at": now(),
          "ok": False, "error": "", "on_device": 0, "added": 0, "faces": 0, "deleted": 0,
          "failed": [], "fingerprint": ""}
    names = {a["no"]: a["name"] for a in erp["active"]}
    try:
        dev = isapi.Device(cfg, http or _http(), cert_der=cert_der or _cert_der)
        users = dev.list_users()
        st["fingerprint"] = dev.seen_fp
        todo = isapi.plan(erp, users, state)
        for no, name, exists in todo["user"]:
            try:
                dev.upsert_user(no, name, exists)
                users[no] = name
                st["added"] += 0 if exists else 1
            except isapi.DeviceError as e:
                st["failed"].append({"no": no, "name": name, "why": str(e)})
        for no, photo in todo["face"]:
            if no not in users:
                continue
            try:
                dev.set_face(no, photo_bytes(photo))
                state[no] = photo
                st["faces"] += 1
            except isapi.DeviceError as e:
                state[no] = "fail:" + photo
                st["failed"].append({"no": no, "name": names.get(no, ""), "why": str(e)})
        if todo["delete"]:
            dev.delete_users(todo["delete"])
            for no in todo["delete"]:
                users.pop(no, None)
                state.pop(no, None)
            st["deleted"] = len(todo["delete"])
        st["on_device"] = len(users)
        st["ok"] = True
    except isapi.DeviceError as e:
        st["error"] = str(e)
    except Exception as e:      # khong de mot may hong lam hong ca job
        st["error"] = "Lỗi không mong đợi: %s" % type(e).__name__
        frappe.log_error(title="ec_face_push %s" % cfg.get("name"))
    return state, st


def run_all():
    if frappe.conf.get(CONF_DISABLED):
        return
    devs = devices()
    if not devs:
        return
    cache = frappe.cache()
    if cache.get_value(LOCK_KEY):
        return
    cache.set_value(LOCK_KEY, 1, expires_in_sec=LOCK_SECONDS)
    try:
        erp = erp_snapshot()
        all_state, status = _load(STATE_KEY), _load(STATUS_KEY)

        def photo_bytes(file_name):
            return frappe.get_doc("File", file_name).get_content()
        for cfg in devs:
            name = str(cfg["name"])
            st_dev, st = sync_device(cfg, erp, dict(all_state.get(name) or {}), photo_bytes)
            all_state[name] = st_dev
            status[name] = st
        _save(STATE_KEY, all_state)
        _save(STATUS_KEY, status)
        frappe.db.commit()
    finally:
        cache.delete_value(LOCK_KEY)


def scheduled():
    """cron */10 (hooks.py)."""
    run_all()


def enqueue():
    """Sau khi luu anh / HR bam 'Dong bo ngay'. Khong co may nao -> khong lam gi."""
    if not devices() or frappe.conf.get(CONF_DISABLED):
        return False
    try:
        frappe.enqueue(JOB, queue="long", job_id="ec_face_push", deduplicate=True,
                       enqueue_after_commit=True)
    except TypeError:       # frappe cu khong co deduplicate
        frappe.enqueue(JOB, queue="long", enqueue_after_commit=True)
    return True


def outbound_ip():
    """IP ma ERP dung khi goi ra ngoai -> Hoan dien vao router (chi cho IP nay vao may)."""
    cache = frappe.cache()
    ip = cache.get_value("ec_face_outbound_ip")
    if ip:
        return ip
    try:
        import requests
        ip = requests.get("https://api.ipify.org", timeout=5).text.strip()[:45]
    except Exception:
        return ""
    cache.set_value("ec_face_outbound_ip", ip, expires_in_sec=3600)
    return ip


def status():
    st = _load(STATUS_KEY)
    out = []
    for cfg in devices():
        s = st.get(str(cfg["name"])) or {}
        host = str(cfg.get("url") or "").split("://", 1)[-1].split("/", 1)[0]
        out.append({"name": cfg["name"], "host": host, "at": s.get("at", ""), "ok": s.get("ok"),
                    "error": s.get("error", ""), "on_device": s.get("on_device", 0),
                    "faces": s.get("faces", 0), "deleted": s.get("deleted", 0),
                    "failed": (s.get("failed") or [])[:20], "fingerprint": s.get("fingerprint", ""),
                    "pinned": bool(isapi.norm_fp(cfg.get("fingerprint")))})
    return {"devices": out, "configured": bool(out), "disabled": bool(frappe.conf.get(CONF_DISABLED)),
            "outbound_ip": outbound_ip(), "every_min": 10}
