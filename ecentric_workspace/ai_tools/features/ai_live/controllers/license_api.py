# Copyright (c) 2026, eCentric and contributors
"""2 API cho app eLive / eSync / eVoice (KHONG dang nhap - may moi chua co token). Duong dan ngan cho app:
/api/method/ecentric_workspace.ai_live.api.license_request | license_checkin (re-export o ai_live/api.py).
Song con (Hoan 17/11 - live on dinh la so 1): qua tan suat -> 429; loi bat ky -> request "pending", checkin "ok";
KHONG BAO GIO de loi xu ly thanh "blocked"; khong de traceback / khoa / token lot ra."""
import frappe

from ecentric_workspace.ai_tools.features.ai_live import license_constants as L
from ecentric_workspace.ai_tools.features.ai_live.domain import ec_license_issuer as I
from ecentric_workspace.ai_tools.features.ai_live.infrastructure import license_guard as G

_SAFE = {"request": {"status": L.Reply.PENDING, "message": I.CLIENT_PENDING_MSG, "poll_s": L.POLL_S},
         "checkin": {"status": L.Reply.OK}}


def _serve(endpoint, limit, service_cls):
    ip = G.client_ip()
    if G.over_limit(endpoint, ip, limit):
        frappe.local.response["http_status_code"] = 429
        return {"success": False, "message": "Too many requests", "data": None}
    try:
        data = service_cls().execute(G.read_body(), ip)
        frappe.db.commit()
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="ai_live license_%s: %s" % (endpoint, type(e).__name__))  # khong kem payload
        data = dict(_SAFE[endpoint])
    return {"success": True, "message": "", "data": data}


@frappe.whitelist(allow_guest=True, methods=["POST"])
def license_request(**kwargs):
    from ecentric_workspace.ai_tools.features.ai_live.application.license_request_service import LicenseRequestService
    return _serve("request", L.REQUEST_PER_MIN, LicenseRequestService)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def license_checkin(**kwargs):
    from ecentric_workspace.ai_tools.features.ai_live.application.license_checkin_service import LicenseCheckinService
    return _serve("checkin", L.CHECKIN_PER_MIN, LicenseCheckinService)
