# Copyright (c) 2026, eCentric and contributors
"""Hai cua nhan lan quet mat tu may Hikvision (ec-face-checkin-v1).

`push` - MAY tu goi moi lan co nguoi quet (HTTP Listening). May khong gan duoc
         header, nen token nam tren URL: `...api.push?k=<ec_face_push_token>&d=<ten may>`.
`sync` - NUT DONG BO tren laptop CnB (tools/hik_face_sync) doc lai lich su tren
         may roi gui len. Token o header `X-EC-Face-Token` = `ec_face_sync_token`.

Ca hai la allow_guest vi may / script khong co phien dang nhap; token la cua
duy nhat. Chua cau hinh token thi cua do dong (403). `ec_face_checkin_disabled`
= 1 thi van tra 200 (may khong gui lai don dap) nhung khong ghi gi.
"""
import hmac
import json

import frappe

from ecentric_workspace.hr.face_device import constants as C
from ecentric_workspace.hr.face_device import mapper


def _guard(conf_key, given):
    want = str(frappe.conf.get(conf_key) or "")
    if not want or not hmac.compare_digest(want.encode(), str(given or "").encode()):
        frappe.local.response["http_status_code"] = 403
        return False
    if (frappe.request.content_length or 0) > C.MAX_BODY_BYTES:
        frappe.local.response["http_status_code"] = 413
        return False
    return True


def _device(name):
    name = "".join(ch for ch in str(name or "") if ch.isalnum() or ch in "-_")[:40]
    return C.DEVICE_PREFIX + ("-" + name if name else "")


def _run(events, device):
    if frappe.conf.get(C.CONF_DISABLED):
        return {"ok": True, "disabled": True}
    from ecentric_workspace.hr.face_device.service import FaceCheckinService
    minors = frappe.conf.get(C.CONF_PASS_MINORS) or C.DEFAULT_PASS_MINORS
    prev = frappe.session.user
    frappe.set_user(frappe.conf.get(C.CONF_RUN_AS) or C.DEFAULT_RUN_AS)
    try:
        rep = FaceCheckinService(tz_name=frappe.utils.get_system_timezone(),
                                 pass_minors=minors).execute(events, _device(device))
    finally:
        frappe.set_user(prev)
    return {"ok": True, **rep}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def push(k="", d=""):
    q = frappe.request.args          # body JSON thi Frappe khong gop query vao form_dict
    if not _guard(C.CONF_PUSH_TOKEN, k or q.get("k")):
        return {"ok": False}
    raw = frappe.request.get_data(cache=True, as_text=True) if not frappe.request.files else ""
    return _run(mapper.from_push(dict(frappe.form_dict), raw), d or q.get("d"))


@frappe.whitelist(allow_guest=True, methods=["POST"])
def sync(device="", events=None):
    if not _guard(C.CONF_SYNC_TOKEN, frappe.get_request_header(C.TOKEN_HEADER)):
        return {"ok": False}
    items = json.loads(events) if isinstance(events, str) else (events or [])
    return _run(mapper.from_sync(items if isinstance(items, list) else []), device)
