# Copyright (c) 2026, eCentric and contributors
"""Viec cua NGUOI DANG XEM tren mot phieu (24/11/2026, Tien trinh phe duyet - phuong an A, PO chot).

Bang "Viec cua ban" phia tren stepper can biet nguoi dang mo phieu co viec gi o phieu nay:
  approve   - la nguoi duyet Pending cua cap HIEN TAI (dung cap.can_approve: cung mot luat voi nut
              Duyet - khong tinh lai lan hai de khong lech nhau)
  resubmit  - la nguoi gui, phieu dang bi tra lai de bo sung (cap.can_resubmit)
  fulfill   - phieu da duyet, nguoi nay giu viec xu ly (fulfillment_owner) hoac duoc nhan viec
              (cap.can_claim, KHONG tinh nho quyen System Manager)
  watch     - co lien quan (nguoi gui / nguoi duyet cap khac / nguoi theo doi / nguoi xu ly) nhung
              luc nay khong co viec
  ""        - khong lien quan (vd quan tri xem qua quyen doc) -> trang khong ve bang

Tinh o SERVER, chi tu du lieu ma `detail()` DA tra cho chinh nguoi nay (levels / approvers /
fulfillment / capabilities). Khong lo them gi ve nguoi khac: `mine` chi danh dau cap cua nguoi xem;
`waiting_on` la ten hien thi cua nhung nguoi da nam san trong `approvers` / `fulfillment.owner`.

Module thuan Python (frappe chi nap trong `build`), de test standalone khong can bench.
"""

OPEN_FULFILLMENT = ("Assigned", "In Progress")


def _empty():
    return {
        "kind": "", "role": "", "level_no": None, "level_name": "",
        "waiting_since": None, "waiting_seconds": None, "waiting_on": [],
        "next_level_no": None, "next_level_name": "", "step_label": "",
        "due_at": None, "claimable": False,
    }


def _seconds(since, now):
    if not since or not now:
        return None
    try:
        sec = int((now - since).total_seconds())
    except Exception:
        return None
    return sec if sec >= 0 else 0


def _as_str(v):
    return None if v in (None, "") else str(v)


def _who(value, display):
    """Ten hien thi cua mot dong approver. Dong kieu "Role: X" (ca nhom) -> "nhom X"."""
    v = str(value or "")
    if v.startswith("Role: "):
        return "nhóm " + v[len("Role: "):]
    return display(v) or v


def compute(user, status, current_level, levels, approvers, caps, requested_by=None,
            fulfillment=None, watchers=(), journey=(), now=None, display=None, parse_dt=None):
    """Tra khoi `viewer` va gan co `mine` (bool) cho tung dong `levels` (sua tai cho).

    `parse_dt` doi chuoi/datetime thanh datetime (frappe.utils.get_datetime khi chay that)."""
    display = display or (lambda u: u)
    parse_dt = parse_dt or (lambda v: v)
    caps = caps or {}
    fulfillment = fulfillment or {}
    out = _empty()
    for row in levels or ():
        row["mine"] = False
    if not status or status == "Draft":
        return out

    approvers = approvers or []
    if user and user == requested_by:
        role = "requester"
    elif user and fulfillment.get("owner") == user:
        role = "fulfiller"
    elif user and any(a.get("approver") == user for a in approvers):
        role = "approver"
    elif user and user in (watchers or ()):
        role = "follower"
    else:
        role = ""
    out["role"] = role

    cur = None
    for row in levels or ():
        if row.get("level_no") == current_level:
            cur = row
            break

    if status == "Pending" and cur is not None:
        since = parse_dt(cur.get("activated_at")) if cur.get("activated_at") else None
        out.update({
            "level_no": cur.get("level_no"), "level_name": cur.get("level_name") or "",
            "waiting_since": _as_str(cur.get("activated_at")),
            "waiting_seconds": _seconds(since, now), "due_at": _as_str(cur.get("due_at")),
        })
        if caps.get("can_approve"):
            cur["mine"] = True
            out["kind"] = "approve"
            for row in levels:
                if (row.get("level_no") or 0) > (current_level or 0) \
                        and row.get("level_status") not in ("Skipped", "Approved"):
                    out["next_level_no"] = row.get("level_no")
                    out["next_level_name"] = row.get("level_name") or ""
                    break
            return out
        if role:
            out["kind"] = "watch"
            seen = []
            for a in approvers:
                if a.get("level_no") == current_level and a.get("status") == "Pending":
                    name = _who(a.get("approver"), display)
                    if name not in seen:
                        seen.append(name)
            out["waiting_on"] = seen
        return out

    if status == "Information Required":
        if caps.get("can_resubmit"):
            out["kind"] = "resubmit"
            out["level_no"] = current_level or None
            if cur is not None:
                out["level_name"] = cur.get("level_name") or ""
        elif role:
            out["kind"] = "watch"
            out["waiting_on"] = [_who(requested_by, display)] if requested_by else []
        return out

    if status == "Approved" and fulfillment.get("status") in OPEN_FULFILLMENT:
        label = ""
        for j in journey or ():
            if j.get("kind") == "fulfillment" and j.get("label"):
                label = j["label"]
                break
        last_done = None
        for row in levels or ():
            if row.get("completed_at"):
                last_done = row.get("completed_at")
        since = parse_dt(last_done) if last_done else None
        out.update({
            "step_label": label or "Xử lý sau duyệt",
            "due_at": _as_str(fulfillment.get("due_at")),
            "waiting_since": _as_str(last_done), "waiting_seconds": _seconds(since, now),
        })
        owner = fulfillment.get("owner")
        claimable = bool(fulfillment.get("status") == "Assigned" and caps.get("can_claim")
                         and not caps.get("claim_is_admin_override") and owner != user)
        if user and (owner == user or claimable):
            out["kind"] = "fulfill"
            out["claimable"] = claimable
        elif role:
            out["kind"] = "watch"
            out["waiting_on"] = [_who(owner, display)] if owner else []
        return out

    return out


def build(user, definition, business, request, levels, approvers, fulfillment, caps, privacy_block,
          journey):
    """Ban chay that trong query_service.detail(). Loi -> khong ve bang (khong lam hong trang)."""
    import frappe
    from frappe.utils import get_datetime, now_datetime

    from ecentric_workspace.approval_center.shared.requests.query_service import requester_display

    watchers = [w.get("user") for w in ((privacy_block or {}).get("watchers") or []) if w.get("user")]
    try:
        return compute(
            user,
            request.approval_status if request else None,
            request.current_level if request else 0,
            levels, approvers, caps,
            requested_by=getattr(business, "requested_by", None),
            fulfillment=fulfillment, watchers=watchers, journey=journey,
            now=now_datetime(), display=requester_display, parse_dt=get_datetime)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "viewer_task %s" % getattr(definition, "code", ""))
        for row in levels or ():
            row["mine"] = False
        return _empty()
