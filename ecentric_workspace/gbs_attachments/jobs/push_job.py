# Copyright (c) 2026, eCentric and contributors
"""Job nen: day file goc cua 1 phieu GBS sang boxme.

Chong chay trung: job_id + deduplicate o noi enqueue, them co khoa trong cache
(cung API frappe.cache().get_value/set_value ma gbs_comment_proxy dang dung).
Service idempotent nen neu hai lan lo chay sat nhau cung chi up file con thieu.
"""

import frappe

from ecentric_workspace.gbs_attachments import constants as C


def run(doctype, name, reason=""):
    cache = frappe.cache()
    key = "gbs_att_push:" + doctype + ":" + name
    if cache.get_value(key):
        return  # lan chay khac dang lam
    cache.set_value(key, 1, expires_in_sec=C.LOCK_SECONDS)
    try:
        from ecentric_workspace.gbs_attachments.application.push_service import PushOriginalsService
        res = PushOriginalsService().execute(doctype, name, reason=reason)
        frappe.db.commit()
        if res.get("errors"):
            frappe.log_error(name + " | " + "; ".join(res["errors"])[:1500], "gbs_att_push loi")
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "gbs_att_push " + name)
    finally:
        cache.delete_value(key)
