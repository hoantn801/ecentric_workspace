# Copyright (c) 2026, eCentric and contributors
"""Notification Center: map a native Notification Log row to a canonical item.

Notification Log is keyed on (document_type, document_name) plus subject / email_content.
The clickable `action_url` is built by REUSING the Action Center URL builders, so the
"which DocType -> which route" rule lives in ONE place
(ecentric_workspace.action_center.resolvers). Notification Center never re-implements URL
logic and the frontend never builds routes.

Canonical item shape (the only contract the frontend depends on):
    {name, subject, message, source_type, source_label,
     action_url, is_read, created_at, from_user}

PRECEDENCE (2026-08-10). Notification Log carries a native `link` field. When the
producer filled it, that link IS the canonical click target and wins over anything
derived from (document_type, document_name). Reason: the EC approval Server Scripts
(ec_mso_before_save / ec_so_before_save / ec_po_before_save) write
`/approval?id=<name>&type=mso|so|po` there, and MSO / Purchase Order are NOT in
ac.APPROVAL_DOCTYPES -- so without this the bell fell through to
build_desk_fallback_url and dumped approvers on the Desk form (/app/mso/<name>)
instead of the approval page. Rows with an empty `link` keep the old behaviour
exactly, so nothing that worked before changes.
"""

import frappe

from ecentric_workspace.action_center import resolvers as ac

WTU = "Weekly Team Update"
TASK = "Task"

# document_type -> (source_type, source_label) for the UI chip. Unknown -> generic.
_SOURCE = {
    WTU: ("weekly_report", "BÁO CÁO TUẦN"),
    TASK: ("task", "CÔNG VIỆC"),
}


def _action_url(document_type, document_name):
    """Canonical click target = CHINH cai ma Action Center tra cho cung chung tu.

    VI SAO uy quyen tron cho `ac.resolve_item` thay vi tu re nhanh: ham nay tung la
    bo dung URL THU HAI cua he thong. No chi biet ba nhanh (Weekly Update / Task /
    APPROVAL_DOCTYPES) roi rot xuong `build_desk_fallback_url`, nen no KHONG co
    nhanh `has_engine_approval_link` va KHONG doc `PORTAL_FALLBACK` - hai thu ma
    duong ToDo da co tu lau. Hau qua that: cung MOT cong viec, chuong tra
    `/app/task/X` con the Action Center tra `/pm#task/X`; `EC Payment Request`,
    `Attendance Request`, `Leave Application`, `EC Alert` tren chuong deu la link
    Desk - ma ~44% tai khoan la Website User, bam vao la 403. Cong QC
    `action_center/tests/test_no_desk_urls.py` chi soi `resolve_item`, nen nua he
    thong nay chua tung co ai canh.

    Uy quyen thi luat "DocType nao -> route nao" chi con MOT cho: them mot nhanh o
    Action Center la chuong huong theo, khong the lech nua.

    Luu y thu tu: `resolve_notification` uu tien `link` da luu (nhanh PRECEDENCE
    2026-08-10) - deep link theo TUNG BAN GHI (`/approvals/<route>?id=<name>`, route
    doc tu `EC Approval Type`) do `transitions.notify()` tinh va nay da duoc ghi lai
    (xem `events.publish_notification_event`). Ham nay chi chay cho nhung dong khong
    co `link`: thong bao cua Frappe/app khac, va cac dong cu truoc ban va do.
    """
    dt = (document_type or "").strip()
    dn = (document_name or "").strip()
    if not dt or not dn:
        return ""
    try:
        item = ac.resolve_item({"name": "", "description": "",
                                "reference_type": dt, "reference_name": dn})
        url = (item or {}).get("action_url") or ""
    except Exception:
        # MOT dong hong khong duoc lam chet CA hop thu: `api.get_notifications` map
        # ham nay qua moi dong, ma `resolve_item` co the nem that (vd `resolve_title`
        # SELECT vao mot DocType da bi xoa/doi ten). Ghi lai roi ha canh mem.
        frappe.log_error(frappe.get_traceback(), "notification_center action_url")
        url = ""
    if url:
        return url
    # Chi la luoi cuoi cung cho dong hong o tren - giu dung hanh vi truoc day cho
    # RIENG dong do thay vi tra the khong bam duoc.
    return ac.build_desk_fallback_url(dt, dn)


def _source(document_type):
    return _SOURCE.get((document_type or "").strip(), ("system", "HỆ THỐNG"))


def resolve_notification(row):
    """row: a Notification Log dict (name, subject, email_content, document_type,
    document_name, from_user, read, type, creation). Returns the canonical item.
    `message` is treated as TEXT by the frontend (escaped on render)."""
    dt = row.get("document_type") or ""
    dn = row.get("document_name") or ""
    source_type, source_label = _source(dt)
    explicit = (row.get("link") or "").strip()
    return {
        "name": row.get("name"),
        "subject": row.get("subject") or "",
        "message": row.get("email_content") or "",
        "source_type": source_type,
        "source_label": source_label,
        "action_url": explicit or _action_url(dt, dn),
        "is_read": 1 if row.get("read") else 0,
        "created_at": str(row.get("creation") or ""),
        "from_user": row.get("from_user") or "",
    }
