# Copyright (c) 2026, eCentric and contributors
"""Be mat VAO duy nhat cua module SLA cho cac module khac.

`shared/workflow/sla_port.py` chi biet den file nay. Giu mot cua duy nhat co mot
ly do cu the: khi cam SLA vao luong duyet don o dot sau, thu can doc lai de kiem
chung la MOT file nay, khong phai ra soat ca module. Va khi phai go SLA ra khoi
luong duyet don gap, chi can mot file tra ve no-op.

Moi ham o day deu an toan khi goi lai (idempotent) va khong bao gio nem loi
nguoc len - `sla_port._safe` van boc them mot lop nua. Hai lop la co y: lop
trong cho phep ghi log co ngu canh, lop ngoai la lan chan cuoi.
"""
import frappe
from frappe.utils import now_datetime

from ecentric_workspace.sla.application import obligation_service as obl
from ecentric_workspace.sla.constants import (
    DT_OBLIGATION, EXCL_ANY_ONE, PAUSE_WAITING_INFO, STATUS_OPEN, TYPE_APPROVAL_STEP,
)


def _title_for_step(request_doctype, request_name, level_no):
    return "%s %s - cấp %s" % (request_doctype, request_name, level_no)


def _open_rows(source_doctype, source_name, level_no, attempt=None):
    filters = {"source_doctype": source_doctype, "source_name": source_name,
               "source_detail": str(level_no), "status": STATUS_OPEN}
    if attempt is not None:
        filters["attempt"] = int(attempt or 1)
    return frappe.get_all(DT_OBLIGATION, filters=filters,
                          fields=["name", "owner_user"])


def open_approval_step_obligations(request_doctype, request_name, level_no, approvers,
                                   opened_at=None, sla_policy_code=None, attempt=1):
    """Mot cap duyet vua mo -> mot dau viec cho MOI nguoi duyet cua cap do.

    Mo cho tat ca, ke ca khi cap la Any-One. Ly do: luc mo chua biet ai se bam.
    Nguoi khong bam se duoc `Excluded` luc dong, chu khong phai Missed. Neu chi
    mo cho mot nguoi thi khong the biet cap do co bi bo quen boi ai.
    """
    opened_at = opened_at or now_datetime()
    out = []
    for user in (approvers or []):
        # try/except TUNG NGUOI. Mot loi o nguoi thu nhat khong duoc lam nguoi
        # thu hai va thu ba khong co nghia vu nao - do la mien phi im lang, dung
        # loai sai lech ma module nay sinh ra de chan.
        try:
            name = obl.open_obligation(
                type_code=TYPE_APPROVAL_STEP, owner_user=user,
                source_doctype=request_doctype, source_name=request_name,
                opened_at=opened_at, source_detail=level_no, attempt=attempt,
                title=_title_for_step(request_doctype, request_name, level_no),
                policy_code=sla_policy_code)
            if name:
                out.append(name)
        except Exception:
            frappe.log_error(title="sla.open_approval_step_obligations",
                             message=frappe.get_traceback())
    return out


def on_approver_acted(request_doctype, request_name, level_no, acted_by,
                      acted_at=None, attempt=1):
    """MOT nguoi duyet vua bam nut. Dong dung dau viec cua nguoi do.

    Ham nay ton tai cho cap duyet DONG THUAN (tat ca phai duyet): moi nguoi co
    dong ho rieng, va nguoi duyet dung han khong duoc mat diem cong vi nguoi thu
    ba duyet muon. Voi cap Any-One thi goi ham nay cung dung - `on_level_closed`
    sau do se don not nhung nguoi con lai.
    """
    for r in _open_rows(request_doctype, request_name, level_no, attempt):
        if r["owner_user"] == acted_by:
            try:
                return obl.close_obligation(r["name"], acted_at or now_datetime())
            except Exception:
                frappe.log_error(title="sla.on_approver_acted",
                                 message=frappe.get_traceback())
    return None


def close_approval_step_obligations(request_doctype, request_name, level_no, acted_by,
                                    closed_at=None, attempt=1, any_one=True):
    """Cap duyet da xong.

    Ba nhanh, va nhanh thu ba la quan trong nhat:

      * nguoi bam nut -> cham diem binh thuong;
      * nhung nguoi con lai, neu cap la Any-One -> `Excluded`. Ho khong lam sai
        gi, nguoi khac da xu ly;
      * nhung nguoi con lai, neu cap la DONG THUAN -> GIU NGUYEN `Open`. Ho van
        con no mot chu ky.

    Va mot lan chan: neu `acted_by` khong khop VOI AI trong cap thi KHONG loai
    tru ai ca. Truong hop nay xay ra khi may goi len mot dinh danh khac kieu
    (Employee ID thay vi email), hoac khi cap dong tu dong (`acted_by=None`).
    Neu cu the ma loai tru, ca cap bien mat khoi mau so va khong ai duoc do -
    mot lo hong do lech dinh danh chu khong do hanh vi. Tha khong cham diem con
    hon cham diem sai theo huong mien phi cho tat ca.
    """
    closed_at = closed_at or now_datetime()
    rows = _open_rows(request_doctype, request_name, level_no, attempt)
    if not rows:
        return {"closed": 0, "excluded": 0, "left_open": 0, "matched": False}

    matched = any(r["owner_user"] == acted_by for r in rows) if acted_by else False
    done = {"closed": 0, "excluded": 0, "left_open": 0, "matched": matched}
    if not matched:
        frappe.log_error(
            title="sla.close_approval_step_obligations: khong khop nguoi duyet",
            message="%s %s cap %s lan %s: acted_by=%r khong nam trong %r. "
                    "Khong loai tru ai - de tranh ca cap bien mat khoi mau so."
                    % (request_doctype, request_name, level_no, attempt, acted_by,
                       [r["owner_user"] for r in rows]))
        done["left_open"] = len(rows)
        return done

    for r in rows:
        try:
            if r["owner_user"] == acted_by:
                obl.close_obligation(r["name"], closed_at)
                done["closed"] += 1
            elif any_one:
                obl.exclude_obligation(r["name"], EXCL_ANY_ONE, closed_at)
                done["excluded"] += 1
            else:
                done["left_open"] += 1
        except Exception:
            frappe.log_error(title="sla.close_approval_step_obligations",
                             message=frappe.get_traceback())
    return done


def cancel_obligations_for_source(source_doctype, source_name):
    return obl.cancel_obligations_for_source(source_doctype, source_name)


def start_pause(source_doctype, source_name, level_no, from_dt, attempt=1):
    """Yeu cau bo sung thong tin -> dung dong ho cua moi dau viec dang mo o cap do."""
    n = 0
    for r in _open_rows(source_doctype, source_name, level_no, attempt):
        try:
            obl.start_pause(obligation=r["name"], reason=PAUSE_WAITING_INFO,
                            from_dt=from_dt, source_doctype=source_doctype,
                            source_name=source_name)
            n += 1
        except Exception:
            frappe.log_error(title="sla.start_pause", message=frappe.get_traceback())
    return n


def end_pause(source_doctype, source_name, level_no, to_dt, attempt=1):
    """Nguoi gui da bo sung -> dong ho chay lai. Chi dong doan DANG mo; khong co
    doan nao dang mo thi khong lam gi (SLA bat len giua chung thi se gap)."""
    n = 0
    for r in _open_rows(source_doctype, source_name, level_no, attempt):
        try:
            if obl.end_pause(obligation=r["name"], reason=PAUSE_WAITING_INFO,
                             to_dt=to_dt) is not None:
                n += 1
        except Exception:
            frappe.log_error(title="sla.end_pause", message=frappe.get_traceback())
    return n
