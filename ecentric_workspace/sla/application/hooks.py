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

    matched = _has_row_for(request_doctype, request_name, level_no, attempt, acted_by)
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


# --------------------------------------------------------------------------- #
# Ket thuc KHONG do nguoi duyet bam: ep duyet, va lam lai ho so tu dau
#
# Hai viec nay giong nhau o dung mot diem quan trong: nguoi duyet MAT NUT BAM.
# Sau lenh ep duyet, hoac sau khi ho so duoc lam lai tu cap 1, ho khong con cach
# nao dap ung cai han cu nua. Nen cau hoi duy nhat con lai la: luc do ho DA tre
# chua?
#
# Chu so huu chot 17/09 - THEO HAN:
#   da qua han  -> van tinh la khong phan hoi. Mot lan ep duyet khong duoc phep
#                  xoa mot vet tre da co, neu khong thi ai tre cung chi can nho
#                  ep duyet mot cai la sach.
#   chua toi han -> loai tru. Giu ho chiu mot cai han khong con cach nao dap ung
#                  khong con la do hanh vi nua.
# --------------------------------------------------------------------------- #
def settle_open_due_aware(request_doctype, request_name, reason, level_no=None,
                          attempt=1, at=None):
    """Ket so nhung dau viec CON MO cua mot ho so theo han.

    `level_no=None` nghia la moi cap cua lan chay do (dung cho "lam lai tu dau").
    Tra ve {"missed": n, "excluded": n} de ben goi ghi log doi chieu duoc.
    """
    from ecentric_workspace.sla.constants import STATUS_MISSED, TYPE_APPROVAL_STEP
    from ecentric_workspace.sla.domain import approval_rules as ar
    from ecentric_workspace.sla.domain import scoring

    at = at or now_datetime()
    filters = {
        # LOC DUNG NHOM. Khong co dong nay thi mot nghia vu nhom `task` gan vao
        # cung mot chung tu se bi ket so theo luat cua nhom phe duyet - va no bi
        # ghi `Missed` vi mot lenh ep duyet khong lien quan gi den no.
        "obligation_type": TYPE_APPROVAL_STEP,
        "source_doctype": request_doctype, "source_name": request_name,
        "status": STATUS_OPEN,
        # `<=` chu khong phai `=`: neu mot lan lam lai truoc do da truot hook thi
        # nhung dong cua lan do con nam nguyen `Open` va se bi job quet thanh
        # `Missed` cho mot vong duyet khong con ton tai. Mot lan ket so don sach
        # moi vong cu chua duoc ket.
        "attempt": ("<=", int(attempt or 1)),
    }
    if level_no is not None:
        filters["source_detail"] = str(level_no)
    try:
        rows = frappe.get_all(DT_OBLIGATION, filters=filters,
                              fields=["name", "due_at", "paused_seconds"],
                              limit_page_length=0)
    except Exception:
        frappe.log_error(title="sla.settle_open_due_aware",
                         message=frappe.get_traceback())
        return {"missed": 0, "excluded": 0}

    done = {"missed": 0, "excluded": 0}
    for r in rows:
        try:
            # DONG DOAN TAM DUNG CON MO TRUOC KHI CAN DO.
            #
            # `paused_seconds` tren nghia vu chi duoc cong lai luc `end_pause`;
            # trong suot thoi gian dang cho nguoi de nghi bo sung, no van la gia
            # tri cu. Bo qua buoc nay thi: nguoi duyet bam "yeu cau bo sung" thu
            # Hai, ho so quay lai thu Nam, va lenh ep duyet (hoac lan lam lai)
            # se thay "da qua han" roi ghi `Missed` - cho quang thoi gian ma
            # nguoi duyet KHONG CO nut nao de bam.
            #
            # Va day la trang thai CUOI: khac voi `Open`, no khong con duoc
            # `scoring.effective_status` tinh lai o moi lan doc nua. Sai o day
            # la sai vinh vien.
            obl.end_pause(obligation=r["name"], reason=PAUSE_WAITING_INFO, to_dt=at)
            paused = frappe.db.get_value(DT_OBLIGATION, r["name"], "paused_seconds")
            # Dung CHINH `is_breached` ma bang diem dung, khong viet lai phep so
            # sanh: no da tinh ca thoi gian tam dung (cho bo sung thong tin).
            # Hai cong thuc "qua han" song song la hai cong thuc se troi ra khoi
            # nhau, va lan troi do se hien ra duoi dang mot nguoi bi tru diem ma
            # bang diem lai bao dung han.
            def _late(due, when, _p=paused):
                return scoring.is_breached(STATUS_OPEN, due, when, _p or 0)

            action, why = ar.override_outcome(r.get("due_at"), at, cmp_fn=_late)
            if action == ar.ACT_MISSED:
                frappe.db.set_value(DT_OBLIGATION, r["name"],
                                    {"status": STATUS_MISSED, "is_breached": 0},
                                    update_modified=False)
                done["missed"] += 1
            else:
                if obl.exclude_obligation(r["name"], why or reason, at):
                    done["excluded"] += 1
        except Exception:
            frappe.log_error(title="sla.settle_open_due_aware",
                             message=frappe.get_traceback())
    return done


def override_approval_step_obligations(request_doctype, request_name, level_no,
                                       attempt=1, at=None):
    """Ban Giam doc ep duyet MOT cap."""
    from ecentric_workspace.sla.domain import approval_rules as ar
    return settle_open_due_aware(request_doctype, request_name,
                                 reason=ar.REASON_OVERRIDE, level_no=level_no,
                                 attempt=attempt, at=at)


def restart_approval_obligations(request_doctype, request_name, attempt=1, at=None):
    """Ho so duoc lam lai tu cap 1 -> ket so CA LAN CHAY vua roi.

    Lan chay moi se co `attempt` khac nen khoa chong trung khong dung nhau; neu
    khong ket so lan cu thi nhung dong con mo cua no se nam lai mai va bi job
    quet thanh `Missed` cho mot vong duyet khong con ton tai.
    """
    return settle_open_due_aware(request_doctype, request_name,
                                 reason="Hồ sơ được làm lại từ đầu",
                                 level_no=None, attempt=attempt, at=at)


def exclude_approver_obligation(request_doctype, request_name, level_no, user, reason=None):
    """MOT nguoi bi rut khoi cap duyet (mat role / co ghe rieng o cap sau - xem
    approval_center/shared/workflow/role_pool.py). Ho khong con nut bam, nen dau viec
    con mo cua ho la Excluded - khong de job quet thanh `Missed` roi tru diem."""
    n = 0
    for r in _open_rows(request_doctype, request_name, level_no):
        if r["owner_user"] != user:
            continue
        try:
            if obl.exclude_obligation(r["name"], reason or "Rut khoi cap duyet"):
                n += 1
        except Exception:
            frappe.log_error(title="sla.exclude_approver_obligation",
                             message=frappe.get_traceback())
    return n


def _has_row_for(source_doctype, source_name, level_no, attempt, user):
    """Nguoi nay CO mot dau viec o cap nay khong - o BAT KY trang thai nao.

    Khac `_open_rows`: dong cua nguoi vua bam thuong da duoc dong boi
    `on_approver_acted` truoc khi cap dong. Neu lan chan chi nhin nhung dong con
    mo thi duong di binh thuong se bi bat nham la "lech dinh danh", va nhung
    nguoi con lai cua cap Any-One se nam nguyen `Open` cho den khi thanh Missed.
    """
    if not user:
        return False
    try:
        return bool(frappe.db.get_value(DT_OBLIGATION, {
            "source_doctype": source_doctype, "source_name": source_name,
            "source_detail": str(level_no), "attempt": int(attempt or 1),
            "owner_user": user}, "name"))
    except Exception:
        frappe.log_error(title="sla._has_row_for", message=frappe.get_traceback())
        return False
# --------------------------------------------------------------------------- #
# Cong VAO: `Employee Checkin` vua duoc tao
#
# Doi xung voi `sla_port` - o kia la cong ra, o day la cong vao - va chiu dung
# mot rang buoc: DO LUONG KHONG DUOC PHEP LAM HONG CAI NO DO. Ham nay chay BEN
# TRONG giao dich cham cong cua nguoi dung. Mot exception lot ra khoi day se
# lam MariaDB rollback ca lan cham cong, va nguoi dung se dung truoc man hinh
# bao loi khi ho vua lam dung viec cua ho.
#
# Vi vay: nuot moi Exception, khong tra ve gia tri nao ben goi phu thuoc vao,
# va import muon de mot module SLA chua migrate tren mot bench nao do khong lam
# vo trang cham cong.
# --------------------------------------------------------------------------- #
def on_employee_checkin(doc, method=None):
    """Dong ngay cong ngay luc cham cong, thay vi cho job dem.

    Job dem VAN CHAY va van can: hook co the truot (may chu restart giua giao
    dich, module chua migrate, hoac chinh ham nay nuot mot loi). Luoi do ban dem
    bat lai nhung ngay do. Hai duong, mot bo luat - ca hai deu goi
    `attendance_source._sync_employee`.
    """
    try:
        emp = getattr(doc, "employee", None)
        if not emp:
            return
        when = getattr(doc, "time", None)
        from ecentric_workspace.sla.infrastructure import attendance_source
        attendance_source.sync_one(emp, when)
    except Exception:
        try:
            frappe.log_error(title="sla.on_employee_checkin",
                             message=frappe.get_traceback())
        except Exception:
            pass
    return None
