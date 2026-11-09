# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu dot 3 - QUY TAC THUAN chuyen phieu Data Request cu (EC Data Request + EC Approval
Request + EC Approval Action) sang EC Data Ticket. Khong cham DB, khong import frappe: migration.py doc
du lieu qua repository roi goi build_ticket(); test chay bang bang du lieu (table-driven).

BANG CHUYEN DOI (PO duyet trong spec 09/11/2026; ghi o README):

Loai yeu cau
  Data accuracy, visualization, retrieval -> Xử lý dữ liệu
  New BI report                           -> Power BI mới
  Historical data crawling                -> Crawl data mới
  Client onboarding / Client offboarding / Data training / Access / Other / (trong, la) -> Khác
  (loai cu luon ghi lai trong mo ta "Thông tin từ phiếu cũ")

Uu tien = muc CAO HON giua hai cot cu:
  urgency    U0 -> Khẩn · U1 -> Cao · U2 -> Bình thường · U3 -> Thấp
  importance I0 -> Cao  · I1 -> Bình thường · I2 / I3 -> Thấp
  (Khan chi tu U0 - "as soon as possible"; thieu ca hai -> Bình thường.)

Trang thai (approval_status cua EC Approval Request + fulfillment_status cua phieu)
  chua gui (khong co EC Approval Request)        -> BO QUA (nhap chua gui, khong phai yeu cau)
  Pending / Information Required                 -> Chờ tiếp nhận
  Approved + Not Started / Assigned / (trong)    -> Chờ tiếp nhận
  Approved + In Progress                         -> Đang xử lý, nguoi xu ly = fulfillment_owner
                                                    (khong co nguoi -> Chờ tiếp nhận)
  Approved + Completed                           -> Hoàn tất, nghiem thu "Đạt", done_at = completed_at
  Rejected / Cancelled                           -> Huỷ (ly do = binh luan cuoi cung cua phieu cu)
  trang thai khac                                -> BO QUA (bao trong bao cao de xu ly tay)

Han: due_date = ngay cua fulfillment_due_at, khong co thi expected_resolution_date (yeu cau Cho tiep
nhan: team Data tinh lai khi Nhan). Han tiep nhan cua yeu cau Cho tiep nhan tinh tu NGAY CHUYEN
(phieu cu khong co khai niem nay) - khong de ca loat yeu cau cu do "qua han nhan" ngay sau khi chuyen.
Nhat ky: dong "Chuyển từ phiếu cũ" + moi dong EC Approval Action thanh "Lịch sử phiếu cũ" GIU GIO GOC
("Submitted" -> "Tạo" de dong dau tien doc la "X gửi yêu cầu").
"""
from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import domain as D

TYPE_MAP = {
    "Data accuracy, visualization, retrieval": "Xử lý dữ liệu",
    "New BI report": "Power BI mới",
    "Historical data crawling": "Crawl data mới",
    "Client onboarding": "Khác",
    "Client offboarding": "Khác",
    "Data training": "Khác",
    "Access": "Khác",
    "Other": "Khác",
}
URGENCY_PRI = {"U0": C.PRI_URGENT, "U1": C.PRI_HIGH, "U2": C.PRI_NORMAL, "U3": C.PRI_LOW}
IMPORTANCE_PRI = {"I0": C.PRI_HIGH, "I1": C.PRI_NORMAL, "I2": C.PRI_LOW, "I3": C.PRI_LOW}
WAITING_APPROVAL = ("Pending", "Information Required")
CLOSED_APPROVAL = ("Rejected", "Cancelled")
#: Nhan tieng Viet cho EC Approval Action.action (giong ec_approval_ui.bundle.js).
ACTION_VI = {
    "Submitted": "đã gửi yêu cầu", "Approved": "đã duyệt", "Rejected": "đã từ chối",
    "Information Requested": "yêu cầu bổ sung thông tin", "Resubmitted": "đã gửi lại sau khi bổ sung",
    "Restarted": "duyệt lại từ đầu", "Skipped": "bỏ qua cấp", "Cancelled": "đã huỷ yêu cầu",
    "System Transition": "hệ thống tự chuyển bước", "Assigned": "đã giao người xử lý",
    "Started": "đã nhận xử lý", "Completed": "đã xử lý xong", "Commented": "ghi chú",
    "Reminded": "đã nhắc người xử lý", "Attachment Added": "đã thêm tệp đính kèm",
}


def map_type(old):
    return TYPE_MAP.get((old or "").strip(), "Khác")


def _code(v, n=2):
    return (v or "").strip()[:n].upper()


def map_priority(urgency, importance):
    cands = [p for p in (URGENCY_PRI.get(_code(urgency)), IMPORTANCE_PRI.get(_code(importance))) if p]
    if not cands:
        return C.PRI_NORMAL
    return min(cands, key=lambda p: C.PRIORITY_RANK[p])


def map_status(approval_status, fulfillment_status, has_request=True):
    """-> (trang thai moi | None, ly do bo qua)."""
    if not has_request or not approval_status:
        return None, "Nháp chưa gửi duyệt"
    if approval_status in WAITING_APPROVAL:
        return C.ST_WAITING, ""
    if approval_status in CLOSED_APPROVAL:
        return C.ST_CANCELLED, ""
    if approval_status == "Approved":
        fs = (fulfillment_status or "").strip()
        if fs == "Completed":
            return C.ST_DONE, ""
        if fs == "In Progress":
            return C.ST_DOING, ""
        if fs in ("", "Not Started", "Assigned"):
            return C.ST_WAITING, ""
        return None, "Trạng thái xử lý lạ: %s" % fs
    return None, "Trạng thái duyệt lạ: %s" % approval_status


def _dt(v):
    return D.as_datetime(v)


def _last(actions, names):
    for a in reversed(actions or ()):
        if a.get("action") in names:
            return a
    return None


def _note(rec):
    lines = ["— Thông tin từ phiếu Data Request cũ %s (Approval Center):" % rec["name"]]
    for label, field in (("Loại cũ", "request_type"), ("Mức khẩn", "urgency"), ("Mức quan trọng", "importance")):
        if rec.get(field):
            lines.append("%s: %s" % (label, rec[field]))
    if rec.get("expected_resolution_date"):
        lines.append("Ngày mong muốn hoàn thành: %s" % D.fmt_date_full(rec["expected_resolution_date"]))
    if rec.get("fulfillment_summary"):
        lines.append("Kết quả xử lý: %s" % rec["fulfillment_summary"])
    return "\n".join(lines)


def level_label(a):
    if a.get("level_no"):
        return ("Cấp %s · %s" % (a["level_no"], a.get("level_name") or "")).strip(" ·")
    return a.get("level_name") or ""


def build_ticket(rec, actions, rules, today, holidays=(), now=None):
    """rec = phieu cu (+ approval_status, approval_completed_at); actions = EC Approval Action (theo gio).
    -> {"skip": ly do} hoac {"values": {...}, "created": datetime, "logs": [...], "status": ...}."""
    actions = sorted(actions or (), key=lambda a: (str(a.get("action_time") or ""), int(a.get("seq") or 0)))
    status, why = map_status(rec.get("approval_status"), rec.get("fulfillment_status"), bool(rec.get("approval_request")))
    if not status:
        return {"skip": why}
    rtype = map_type(rec.get("request_type"))
    pri = map_priority(rec.get("urgency"), rec.get("importance"))
    created = _dt(rec.get("submitted_at")) or _dt(rec.get("creation")) or now
    assignee = (rec.get("fulfillment_owner") or "").strip()
    if status == C.ST_DONE:
        assignee = assignee or (rec.get("completed_by") or "").strip()
    note = ""
    if status == C.ST_DOING and not assignee:
        status, note = C.ST_WAITING, "Phiếu cũ đang xử lý nhưng không có người nhận - để team Data nhận lại."
    started = _last(actions, ("Started",))
    approved = _last(actions, ("Approved",))
    start_at = (_dt(started.get("action_time")) if started else None) or _dt(rec.get("approval_completed_at")) \
        or (_dt(approved.get("action_time")) if approved else None) or created
    due = D.as_date(rec.get("fulfillment_due_at")) or D.as_date(rec.get("expected_resolution_date"))
    n = D.ticket_sla_days(rules, rtype, pri)
    desc = ((rec.get("detailed_description") or "").strip() + "\n\n" + _note(rec)).strip()
    title = D.one_line(rec.get("request_title"), C.TITLE_MAX) or ("Data Request " + rec["name"])
    v = {
        "kind": C.KIND_REQUEST, "naming_series": C.SERIES[C.KIND_REQUEST], "title": title, "request_type": rtype,
        "description": desc, "requester": rec.get("requested_by") or "", "requester_department": rec.get("department") or "",
        "data_used": "", "reference_link": "", "proposed_priority": pri,
        "urgent_reason": ("Phiếu cũ: " + (rec.get("urgency") or "")) if pri == C.PRI_URGENT else "",
        "priority": "", "status": status, "rule_version": rules.get("version") or None, "sla_days": n,
        "legacy_ref": rec["name"], "output_link": (rec.get("output_link") or "").strip()[:C.LINK_MAX],
        "due_date": due, "original_due_date": due,
    }
    if status == C.ST_WAITING:
        v["intake_due_date"] = D.intake_due(today, rules, holidays)
    else:
        v["intake_due_date"] = D.intake_due(D.as_date(created) or today, rules, holidays)
    if status in (C.ST_DOING, C.ST_DONE):
        start = D.as_date(start_at)
        v.update({"assignee": assignee, "priority": pri, "start_date": start, "accepted_at": start_at,
                  "accepted_by": assignee})
        if not due:
            v["due_date"] = v["original_due_date"] = D.due_from(start, n, holidays)
    if status == C.ST_DONE:
        comp = _last(actions, ("Completed",))
        done = _dt(rec.get("completed_at")) or (_dt(comp.get("action_time")) if comp else None) or start_at
        v.update({"done_at": done, "closed_at": done, "acceptance": C.ACC_OK})
    if status == C.ST_CANCELLED:
        last = _last(actions, ("Rejected", "Cancelled"))
        closed = _dt(rec.get("approval_completed_at")) or (_dt(last.get("action_time")) if last else None) or created
        verb = "bị từ chối" if rec.get("approval_status") == "Rejected" else "đã huỷ"
        reason = (last.get("comment") or "").strip() if last else ""
        v.update({"closed_at": closed, "cancel_reason": ("Phiếu cũ %s%s" % (verb, (": " + reason) if reason else ""))[:C.REASON_MAX]})
    logs = []
    if not any(a.get("action") == "Submitted" for a in actions):
        logs.append({"event": C.EV_CREATED, "actor": v["requester"], "at": created, "from_value": "",
                     "to_value": pri, "note": ""})
    for a in actions:
        act = a.get("action") or ""
        if act == "Submitted":
            logs.append({"event": C.EV_CREATED, "actor": a.get("actor") or v["requester"], "at": _dt(a.get("action_time")) or created,
                         "from_value": "", "to_value": pri, "note": (a.get("comment") or "")[:C.REASON_MAX]})
            continue
        logs.append({"event": C.EV_LEGACY_HISTORY, "actor": a.get("actor") or "", "at": _dt(a.get("action_time")) or created,
                     "from_value": act[:140], "to_value": level_label(a)[:140],
                     "note": (a.get("comment") or "")[:C.REASON_MAX]})
    logs.append({"event": C.EV_LEGACY, "actor": C.SYSTEM_USER, "at": now, "from_value": rec["name"],
                 "to_value": status, "note": note or "Chuyển tự động từ Data Request (Approval Center) - giữ mã cũ và lịch sử."})
    return {"values": v, "created": created, "logs": logs, "status": status}


def timeline_text(ev, who, a, b):
    """Cau hien thi cho hai su kien cua dot 3 (service._timeline). Khong phai su kien dot 3 -> None."""
    if ev == C.EV_LEGACY:
        return "Chuyển từ Data Request %s (Approval Center)" % (a or "")
    if ev == C.EV_LEGACY_HISTORY:
        text = "Phiếu cũ · %s %s" % (who, ACTION_VI.get(a, a or ""))
        return text + (" (%s)" % b if b else "")
    return None
