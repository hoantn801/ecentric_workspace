# Copyright (c) 2026, eCentric and contributors
"""Vong doi cua mot nghia vu: MO -> DONG / LOAI TRU / HUY. Loi cua module.

Moi ham o day deu IDEMPOTENT qua `dedupe_key`. Khong phai de cho dep: cac diem
cam vao luong duyet don co the chay lai (retry cua job, resubmit, backfill bu
sau su co), va mot lan chay lai tao ban sao se lam mau so phinh len - tuc la ti
le cua mot nguoi tut xuong vi HE THONG chay hai lan, khong phai vi ho lam sai.
Do la kieu loi khong the giai thich cho nguoi bi tru diem.

`dedupe_key` co kem SO LAN (attempt). Mot ho so bi tra ve roi gui lai la mot dau
viec MOI - nguoi duyet phai phan hoi lai lan nua - chu khong phai ghi de len dau
viec cu. Gop lai se xoa mat lan tre dau tien.
"""
import hashlib
import json

import frappe
from frappe.utils import now_datetime

from ecentric_workspace.sla.application import policy_service
from ecentric_workspace.sla.constants import (
    DEDUPE_SEPARATOR, DT_OBLIGATION, DT_PAUSE, DUE_BUSINESS_HOURS, EXCL_NO_POLICY,
    STATUS_CANCELLED, STATUS_EXCLUDED, STATUS_OPEN,
)
from ecentric_workspace.sla.domain import due_rules, scoring

_KEY_MAX = 255
# Cac trang thai KHONG the dung tay dua ve Excluded nua. Ngan hon
# TERMINAL_STATUSES co chu dich: `Late` va `Missed` PHAI loai tru duoc, vi do
# chinh la truong hop nghi phep duoc duyet hoi to sau khi job da cham diem.
_UNTOUCHABLE = (STATUS_EXCLUDED, STATUS_CANCELLED)


def make_dedupe_key(type_code, owner_user, source_doctype, source_name,
                    source_detail=None, attempt=1):
    """Khoa chong trung, luon <= 255 ky tu.

    Khi qua dai thi BAM phan dai, khong cat duoi. Cat duoi se chem mat dung hai
    manh phia sau - `source_detail` (so cap duyet) va `attempt` - tuc la cap 1
    va cap 2 cua cung mot ho so ra cung mot khoa, va cap 2 khong bao gio duoc mo.
    Bam giu duoc tinh duy nhat; cat thi khong.
    """
    parts = [str(p or "") for p in (type_code, owner_user, source_doctype,
                                    source_name, source_detail, attempt or 1)]
    key = DEDUPE_SEPARATOR.join(parts)
    if len(key) <= _KEY_MAX:
        return key
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    head = DEDUPE_SEPARATOR.join(parts[:1] + parts[4:])          # type:detail:attempt
    return (head[:_KEY_MAX - 41] + DEDUPE_SEPARATOR + digest)[:_KEY_MAX]


def _log(label):
    # Frappe >= 14 nhan (title, message). Truyen bang TEN de khong phu thuoc vao
    # co che tu doi cho cua thu vien - neu doi sai thi tieu de Error Log tro
    # thanh mot doan traceback cat cut va khong the tim lai duoc bang tieu de.
    frappe.log_error(title=label, message=frappe.get_traceback())


def _employee_of(user):
    """(employee, department, company) cua mot user. Fail-safe: bang Employee
    hong khong duoc lam chet luong duyet don o tang tren."""
    try:
        row = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"},
                                  ["name", "department", "company"], as_dict=True)
    except Exception:
        _log("sla._employee_of")
        row = None
    if not row:
        return None, None, None
    return row.get("name"), row.get("department"), row.get("company")


# --------------------------------------------------------------------------- #
# MO
# --------------------------------------------------------------------------- #
def open_obligation(type_code, owner_user, source_doctype, source_name,
                    opened_at=None, source_detail=None, attempt=1, title=None,
                    policy_code=None, explicit_due=None):
    """Mo mot dau viec. Tra ve docname, hoac docname cu neu da ton tai."""
    if not owner_user:
        return None
    key = make_dedupe_key(type_code, owner_user, source_doctype, source_name,
                          source_detail, attempt)
    existing = frappe.db.get_value(DT_OBLIGATION, {"dedupe_key": key}, "name")
    if existing:
        return existing

    t, pol = policy_service.resolve_for_type(type_code, policy_code)
    if not t or not t.get("active"):
        return None

    opened_at = opened_at or now_datetime()
    employee, department, company = _employee_of(owner_user)
    try:
        due_at = policy_service.compute_due(pol, opened_at, explicit_due=explicit_due,
                                            employee=employee, company=company)
    except Exception:
        # Chinh sach hong -> van MO nghia vu, nhung khong co han. `due_at` rong
        # duoc cham la "khong tinh diem" (xem scoring.classify_close), KHONG
        # phai dung han - nen mot cau hinh thieu hien ra nhu mot viec phai lam
        # chu khong phai nhu mot diem tuyet doi.
        _log("sla.open_obligation.due")
        due_at = None

    doc = frappe.get_doc({
        "doctype": DT_OBLIGATION,
        "obligation_type": t["name"],
        "group_key": t["group_key"],
        "counts_toward_sla": t.get("counts_toward_sla") or 0,
        "owner_user": owner_user,
        "employee": employee,
        "department": department,
        "period_month": due_rules.period_of(opened_at),
        "title": (title or "")[:255] or None,
        "opened_at": opened_at,
        "due_at": due_at,
        "status": STATUS_OPEN,
        "source_doctype": source_doctype,
        "source_name": source_name,
        "source_detail": str(source_detail) if source_detail is not None else None,
        "attempt": int(attempt or 1),
        "dedupe_key": key,
        "policy": pol.get("name") if pol else None,
        "policy_snapshot": policy_service.snapshot(pol),
        "excluded_reason": None if pol else EXCL_NO_POLICY,
    })
    mark = _log_mark()
    try:
        doc.insert(ignore_permissions=True)
    except Exception:
        # Hai tien trinh cung mo mot dau viec. Khoa duy nhat tren `dedupe_key` da
        # lam dung viec cua no. Bat rong chu khong bat DuplicateEntryError: khoa
        # duy nhat tren mot cot KHONG PHAI `name` nem UniqueValidationError, mot
        # nhanh khac han - va `frappe.throw` da kip nhet mot dong vao message_log,
        # thu se noi len man hinh nguoi dang duyet don duoi dang toast do neu
        # khong don. Do luong khong duoc phep lam phien viec duoc do luong.
        dup = frappe.db.get_value(DT_OBLIGATION, {"dedupe_key": key}, "name")
        _trim_messages(mark)
        if dup:
            return dup
        _log("sla.open_obligation.insert")
        return None
    return doc.name


def _log_mark():
    """Do dai message_log TRUOC mot thao tac co the `frappe.throw`."""
    try:
        return len(frappe.local.message_log or [])
    except Exception:
        return None


def _trim_messages(mark):
    """Cat bo dung nhung thong bao ma thao tac vua roi them vao, khong xoa sach.

    `frappe.throw` ghi vao message_log TRUOC khi nem; loi da bi nuot nhung
    thong bao van duoc gui ve client trong `_server_messages`. Xoa sach ca danh
    sach se nuot luon thong bao cua luong dang chay o tang tren.
    """
    if mark is None:
        return
    try:
        if len(frappe.local.message_log or []) > mark:
            frappe.local.message_log = frappe.local.message_log[:mark]
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# DONG
# --------------------------------------------------------------------------- #
def _elapsed_fn_for(row):
    """Ham do "tre bao lau" dung thuoc do cua chinh sach da CHUP tren dong do.

    Chinh sach gio lam viec -> do bang gio lam viec. Doc snapshot chu khong doc
    ban chinh sach hien tai: lich su phai bat bien.
    """
    raw = row.get("policy_snapshot")
    if not raw:
        return None
    try:
        snap = json.loads(raw)
    except Exception:
        return None
    if snap.get("due_rule") != DUE_BUSINESS_HOURS or not snap.get("business_calendar"):
        return None

    def _fn(from_dt, to_dt):
        try:
            from ecentric_workspace.approval_center.shared.workflow import business_hours as bh
            from ecentric_workspace.approval_center.shared.workflow import holidays as hol
            cal = frappe.get_cached_doc("EC Approval Business Calendar",
                                        snap["business_calendar"])
            hl = snap.get("holiday_list")
            return bh.business_seconds_between(
                from_dt, to_dt, bh.build_periods(cal.working_periods),
                hol.holiday_dates(hl) if hl else set())
        except Exception:
            _log("sla._elapsed_fn_for")
            return None          # -> classify_close quay ve do bang dong ho
    return _fn


def close_obligation(name, closed_at=None):
    """Dong mot dau viec va cham diem no. Da o trang thai cuoi thi khong lam gi."""
    row = frappe.db.get_value(DT_OBLIGATION, name,
                              ["name", "status", "due_at", "paused_seconds",
                               "policy_snapshot"], as_dict=True)
    if not row or row["status"] != STATUS_OPEN:
        return None
    closed_at = closed_at or now_datetime()
    status, late = scoring.classify_close(row["due_at"], closed_at,
                                          row["paused_seconds"] or 0,
                                          elapsed_fn=_elapsed_fn_for(row))
    update = {"status": status, "closed_at": closed_at,
              "late_seconds": late, "is_breached": 0}
    if status == STATUS_EXCLUDED:
        update["excluded_reason"] = EXCL_NO_POLICY
    frappe.db.set_value(DT_OBLIGATION, name, update, update_modified=False)
    return status


def exclude_obligation(name, reason, excluded_at=None):
    """Khong tinh diem dau viec nay.

    CO Y cho phep loai tru mot dong da `Late` hoac `Missed`. Do chinh la truong
    hop nghi phep duoc duyet HOI TO: nguoi ta nghi that, don ve sau, va luc do
    job da kip cham `Missed`. Chan lai o day se lam hanh dong sua sai cua HR im
    lang khong co tac dung - API van bao thanh cong, diem van sai.
    """
    row = frappe.db.get_value(DT_OBLIGATION, name, ["name", "status"], as_dict=True)
    if not row or row["status"] in _UNTOUCHABLE:
        return None
    frappe.db.set_value(DT_OBLIGATION, name, {
        "status": STATUS_EXCLUDED, "closed_at": excluded_at or now_datetime(),
        "excluded_reason": (reason or "")[:500], "is_breached": 0, "late_seconds": 0,
    }, update_modified=False)
    return STATUS_EXCLUDED


def cancel_obligations_for_source(source_doctype, source_name):
    """Ho so bi huy -> moi dau viec con mo cua no bien khoi phep tinh."""
    names = frappe.get_all(DT_OBLIGATION, filters={
        "source_doctype": source_doctype, "source_name": source_name,
        "status": STATUS_OPEN}, pluck="name")
    done = 0
    for n in names:
        # try/except TUNG DONG. Mot dong ket ban ghi khong duoc lam nhung dong
        # con lai o nguyen `Open` - chung se bi job quet thanh `Missed` cho mot
        # ho so da huy, va nguoi do bi tru diem vi mot viec khong con ton tai.
        try:
            frappe.db.set_value(DT_OBLIGATION, n, {
                "status": STATUS_CANCELLED, "closed_at": now_datetime(),
                "is_breached": 0}, update_modified=False)
            done += 1
        except Exception:
            _log("sla.cancel_obligations_for_source")
    return done


# --------------------------------------------------------------------------- #
# TAM DUNG
# --------------------------------------------------------------------------- #
def start_pause(obligation, reason, from_dt, source_doctype=None,
                source_name=None, notes=None):
    """Mo mot doan tam dung. Dang co doan chua dong thi khong mo them."""
    open_seg = _open_segment(obligation, reason)
    if open_seg:
        return open_seg
    doc = frappe.get_doc({
        "doctype": DT_PAUSE, "obligation": obligation, "reason": reason,
        "from_dt": from_dt or now_datetime(), "to_dt": None,
        "source_doctype": source_doctype, "source_name": source_name,
        "dedupe_key": _pause_key(obligation, reason, from_dt), "notes": notes,
    })
    mark = _log_mark()
    try:
        doc.insert(ignore_permissions=True)
    except Exception:
        _trim_messages(mark)
        return _open_segment(obligation, reason)
    return doc.name


def end_pause(obligation, reason, to_dt):
    """Dong doan tam dung DANG mo. Khong co doan nao dang mo thi khong lam gi.

    Moi lan cho - dong la MOT doan rieng. Dung mot khoa co dinh cho ca nghia vu
    se lam lan cho thu hai bi bo qua, va nguoi duyet phai chiu ca khoang thoi
    gian bong dang o phia nguoi gui.
    """
    seg = _open_segment(obligation, reason)
    if not seg or not to_dt:
        return None
    try:
        doc = frappe.get_doc(DT_PAUSE, seg)
        doc.to_dt = to_dt
        doc.save(ignore_permissions=True)
    except Exception:
        _log("sla.end_pause")
        return None
    return _recompute_paused(obligation)


def _open_segment(obligation, reason):
    rows = frappe.get_all(DT_PAUSE, filters={
        "obligation": obligation, "reason": reason, "to_dt": ("is", "not set"),
    }, pluck="name", order_by="from_dt desc", limit_page_length=1)
    return rows[0] if rows else None


def _pause_key(obligation, reason, from_dt):
    key = DEDUPE_SEPARATOR.join([obligation, reason, str(from_dt or now_datetime())])
    if len(key) <= _KEY_MAX:
        return key
    return (key[:_KEY_MAX - 41] + DEDUPE_SEPARATOR
            + hashlib.sha1(key.encode("utf-8")).hexdigest())[:_KEY_MAX]


def _recompute_paused(obligation):
    """Cong lai TU DAU thay vi cong don. Cong don se lech vinh vien neu mot lan
    goi bi chay hai lan - va `paused_seconds` day han ra xa, nen lech theo huong
    co loi cho nguoi duoc cham diem ma khong ai phat hien."""
    secs = frappe.get_all(DT_PAUSE, filters={"obligation": obligation}, pluck="seconds")
    total = sum(int(s or 0) for s in secs)
    frappe.db.set_value(DT_OBLIGATION, obligation, {"paused_seconds": total},
                        update_modified=False)
    return total


# --------------------------------------------------------------------------- #
# QUET QUA HAN
# --------------------------------------------------------------------------- #
def sweep_overdue(limit=5000):
    """Danh dau `is_breached` cho cac dau viec CON MO nhung da qua han.

    Bang diem khong PHU THUOC vao job nay - `domain.scoring.effective_status`
    tinh lai tai cho moi lan doc, nen ti le van dung ke ca khi job chet. Job chi
    lam cho cot `is_breached` trong DB khop voi su that, de loc/bao cao/danh sach
    cua Desk cung thay dieu bang diem thay. Hai duong, mot ket qua - co y.
    """
    now = now_datetime()
    rows = frappe.get_all(DT_OBLIGATION, filters={"status": STATUS_OPEN, "is_breached": 0},
                          fields=["name", "status", "due_at", "paused_seconds"],
                          order_by="due_at asc", limit_page_length=limit)
    n = 0
    for r in rows:
        if scoring.is_breached(r["status"], r["due_at"], now, r["paused_seconds"] or 0):
            try:
                frappe.db.set_value(DT_OBLIGATION, r["name"], {"is_breached": 1},
                                    update_modified=False)
                n += 1
            except Exception:
                _log("sla.sweep_overdue")
    return {"checked": len(rows), "breached": n, "capped": len(rows) >= limit}
