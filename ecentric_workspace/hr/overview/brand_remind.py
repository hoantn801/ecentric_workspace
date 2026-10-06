# Copyright (c) 2026, eCentric and contributors
"""Nut "Nhac" tren tab Phan bo cong viec (/tong-quan#nhan-su/phan-bo) - Hoan 02/10/2026.

HR / CnB bam cho MOT phong (hoac tat ca phong chua xong). Gui qua Notification Center
(chuong ERP + Teams), moi nguoi MOT tin:
  - nguoi chua nop / phieu bi tra lai  -> nhac nop (lai) phieu ky do;
  - nguoi dang phai duyet (lead / truong phong, dung cap hien tai cua phieu) -> nhac duyet;
  - truong phong (Department.manager_email) -> tinh hinh phong, neu khong nam o hai nhom tren.
Chong bam lien tay: cung phong + cung nguoi nhan -> toi da 1 tin / 30 phut (dedupe_key).
Quyen chan o api._guard (HR_CARD_ROLES). Khong co so luong nao trong tin.
"""
import frappe
from frappe.utils import now_datetime

from ecentric_workspace.notification_center.events import publish_notification_event

ACTION_URL = "/ec-hr/phan-bo-cong-viec"
NEED_SUBMIT = ("none", "draft", "returned")
PENDING = ("wait_lead", "wait_head")


def _label(period):
    return "tháng %d/%s" % (int(period[5:7]), period[:4])


def plan(data, departments):
    """Thuan: data = brand_summary(period) -> {user: {...}}. `departments` = danh sach key phong.
    Can them employee->user va doc->approvers (dien san vao member bang _enrich)."""
    out = {}
    for d in data.get("departments") or []:
        if d["department"] not in departments:
            continue
        open_n = 0
        for m in d["members"]:
            if m["status"] in NEED_SUBMIT:
                open_n += 1
                if m.get("user"):
                    s = out.setdefault(m["user"], {})
                    s["submit"] = "returned" if m["status"] == "returned" else "none"
            elif m["status"] in PENDING:
                open_n += 1
                for u in m.get("approvers") or []:
                    s = out.setdefault(u, {})
                    s["approve"] = s.get("approve", 0) + 1
        mgr = d.get("manager_user")
        if open_n and mgr:
            s = out.setdefault(mgr, {})
            s.setdefault("dept", []).append((d["label"], open_n))
    return out


def _enrich(data):
    """Them user cua tung nguoi + nguoi dang phai duyet + tai khoan truong phong."""
    emps = [m["employee"] for d in data["departments"] for m in d["members"]]
    users = {e.name: e.user_id for e in frappe.get_all(
        "Employee", filters={"name": ["in", emps or [""]]}, fields=["name", "user_id"], limit_page_length=0)}
    docs = [m["doc"] for d in data["departments"] for m in d["members"] if m.get("doc") and m["status"] in PENDING]
    appr = {}
    if docs:
        for r in frappe.db.sql(
                """select b.name doc, ap.approver
                   from `tabEC Brand Weight Request` b
                   inner join `tabEC Approval Request` r on r.name = b.approval_request
                   inner join `tabEC Approval Request Approver` ap on ap.approval_request = r.name
                   where b.name in %(docs)s and r.approval_status = 'Pending' and ap.status = 'Pending'
                     and ap.level_no = r.current_level""", {"docs": tuple(docs)}, as_dict=True):
            appr.setdefault(r.doc, []).append(r.approver)
    mgrs = {r.name: r.manager_email for r in frappe.get_all(
        "Department", fields=["name", "manager_email"], limit_page_length=0)}
    for d in data["departments"]:
        d["manager_user"] = mgrs.get(d["department"])
        for m in d["members"]:
            m["user"] = users.get(m["employee"])
            m["approvers"] = appr.get(m.get("doc"), [])
    return data


def remind(sender, period, department=None, all_open=False):
    from ecentric_workspace.hr.overview import team_summary_repo as TR
    data = _enrich(TR.brand_summary(period))
    if all_open:
        depts = [d["department"] for d in data["departments"] if d["state"] != "done"]
    else:
        depts = [department or ""]
    p = plan(data, set(depts))
    if not p:
        return {"sent": 0, "submit": 0, "approve": 0, "note": "Không còn ai cần nhắc."}
    slot = int(now_datetime().timestamp() // 1800)
    sent = n_submit = n_approve = 0
    lb = _label(period)
    for user, x in p.items():
        if not user or user in ("Administrator", "Guest") or not frappe.db.get_value("User", user, "enabled"):
            continue
        parts = []
        if x.get("submit") == "returned":
            parts.append("Phiếu phân bổ công việc %s của bạn bị trả lại — xem lý do, sửa rồi nộp lại." % lb)
        elif x.get("submit"):
            parts.append("Bạn chưa nộp phân bổ công việc (tỷ trọng brand) %s." % lb)
        if x.get("approve"):
            parts.append("Có %d phiếu phân bổ công việc %s đang chờ bạn duyệt." % (x["approve"], lb))
        for name, n in x.get("dept") or []:
            if not x.get("approve"):
                parts.append("Phòng %s còn %d người chưa xong phân bổ công việc %s." % (name, n, lb))
        if not parts:
            continue
        try:
            publish_notification_event(
                "task_assigned", user, "Nhân sự nhắc: phân bổ công việc %s" % lb, " ".join(parts),
                severity="action_required", action_url=ACTION_URL,
                reference_doctype="EC Brand Weight Request",
                dedupe_key="bwremind|%s|%s|%s|%s" % (period, ",".join(sorted(depts)), user, slot),
                from_user=sender)
            sent += 1
            n_submit += 1 if x.get("submit") else 0
            n_approve += 1 if x.get("approve") else 0
        except Exception:
            frappe.log_error(frappe.get_traceback(), "brand_remind " + str(user))
    return {"sent": sent, "submit": n_submit, "approve": n_approve, "departments": len(depts)}
