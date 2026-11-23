# Copyright (c) 2026, eCentric and contributors
"""Clearance Request - TU TAO khi Don nghi viec (Resignation) duyet xong (29/09/2026, Hoan).

Line Manager / Operation / HR / HOF - moi ben kiem muc ban giao cua minh, SONG SONG (cap "Each
Group" cua engine, cung khuon New Staff Preparation). Cac nhom la cau hinh process (V1 / V2), khong
viet cung o day.

V2 (23/11/2026) - sua goc "9 don nghi viec, 0 Clearance":
  * NGUOI GUI KHONG CON LA NGUOI NGHI. Truoc day phieu mang ten nguoi nghi; tai khoan do bi khoa
    00:30 sau ngay cuoi, "Yeu cau bo sung" tra ve mot tai khoan da khoa va phieu ket. Nay nguoi gui
    = nguoi da duyet cap CnB/HR cua don -> nguoi lap don (neu khac nguoi nghi) -> mot nguoi dang
    bat cua role CnB/HR. Doi tuong cua phieu (employee_email) van la nguoi nghi.
  * Ket qua tao phieu GHI LEN DON (clearance_error) chu khong chi nam trong Error Log; job quet
    hang ngay (`quet_hang_ngay`) tao bu cho don da duyet ma chua co Clearance (ngay cuoi chua qua),
    va MO SOM khi con <= 5 ngay lam viec toi ngay cuoi ma chuoi duyet chua xong nhung LM da duyet.
  * Don duyet TRUOC khi co ham nay (29/09) khong bao gio co Clearance: tao bu bang endpoint System
    Manager `controllers.api.tao_bu_clearance` (dry-run mac dinh, co chan doan tung don).
  * `tao_clearance(employee, ly_do, ngay_cuoi)` - cong cho module khac (Ky luat sa thai...).

Khoa tai khoan KHONG nam o day: job hang ngay cua module HR (hr/offboarding) doc
Employee.relieving_date - ngay do do Don nghi viec ghi luc duyet xong."""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC Clearance Request"
APPROVAL_TYPE = "CLEARANCE_REQUEST"
RESIGNATION_DT = "EC Resignation Request"
GREETING = ("A handover clearance process has been initiated. Please help to carefully check out "
            "all related items to your departments respectively, before or on the last working day. "
            "Vui lòng hoàn tất danh sách clearance trước hoặc trong ngày làm việc cuối cùng.")
#: Muc ban giao theo tung nhom (hien tren phieu). Ten nhom khop group_label cua process.
CHECKLIST = {
    "Line Manager": ["Role handover: bàn giao công việc chuyên môn cho quản lý trực tiếp"],
    "HOF": ["Payable clearance: quyết toán các khoản phải trả cho công ty, tạm ứng, hoàn ứng, đề nghị thanh toán",
            "Last month's salary: quyết toán tháng lương cuối cùng"],
    "Operation": ["Asset return: trả tài sản đã cấp (laptop, màn hình...) qua Asset Request",
                  "Microsoft 365, Lark, license / tool khác: thu hồi tài khoản đã cấp"],
    "HR": ["Exit interview: phỏng vấn thôi việc",
           "Termination decision: quyết định thôi việc",
           "Thẻ văn phòng, thẻ thang máy, thẻ gửi xe, chìa khoá locker và tài sản HR cấp"],
}


def gen_title(doc):
    parts = [doc.get("employee_name") or doc.get("employee_email"), doc.get("last_working_day")]
    return ("Clearance - " + " - ".join(str(p) for p in parts if p))[:255]


def prepare_draft(document):
    """draft_preparer: KHONG cho tao tay. Phieu chi sinh ra tu Don nghi viec da duyet."""
    if document.is_new() and not frappe.flags.get("ec_clearance_from_resignation"):
        frappe.throw(_("Clearance được tạo tự động khi Đơn nghỉ việc duyệt xong - không tạo tay."))


#: Role nhom CnB/HR (cau hinh role - khong phai danh tinh nguoi).
CNB_ROLES = ("EC CnB", "HR")
RES_OPEN = ("Pending", "Information Required")
#: Mo Clearance SOM khi con <= so ngay lam viec nay toi ngay cuoi (Hoan chot 23/11).
MO_SOM_NGAY_LV = 5


def _active(user):
    row = user and frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")


def nguoi_gui_clearance(leaver_user, res=None, preferred=None):
    """Nguoi gui phieu Clearance - KHONG BAO GIO la nguoi nghi (tai khoan sap bi khoa)."""
    from ecentric_workspace.approval_center.shared.workflow.participants import active_role_users
    cands = [preferred] if preferred else []
    if res is not None and res.get("approval_request"):
        rows = frappe.get_all("EC Approval Request Approver",
                              filters={"approval_request": res.approval_request, "status": "Approved"},
                              fields=["approver", "source", "level_no"], order_by="level_no desc")
        cands += [r.approver for r in rows
                  if engine.role_of(r.source) in CNB_ROLES]
    if res is not None:
        cands.append(res.get("requested_by"))
    for role in CNB_ROLES:
        cands += active_role_users(role)
    leaver = (leaver_user or "").lower()
    for u in cands:
        if u and u.lower() != leaver and u not in ("Guest",) and _active(u):
            return u
    return "Administrator"


def _ghi_ket_qua(resignation_name, loi):
    """Ghi ket qua tao Clearance len DON (nguoi duyet / HR thay ngay tren phieu, khong chi Error Log)."""
    try:
        frappe.db.set_value(RESIGNATION_DT, resignation_name, "clearance_error",
                            (loi or "")[:500] or None, update_modified=False)
        frappe.db.commit()
    except Exception:
        pass


def create_from_resignation(resignation_name, raise_errors=False, early=False):
    """Tao + gui Clearance cho mot Don nghi viec DA DUYET (hoac MO SOM - early=True). Idempotent.
    Hong thi rollback phan cua minh, ghi Error Log + ghi loi len don - khong im lang."""
    try:
        name = _create_and_submit(resignation_name, early=early)
        frappe.db.commit()
        _ghi_ket_qua(resignation_name, None)
        return name
    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(title="Clearance: khong tao duoc tu %s" % resignation_name,
                         message=frappe.get_traceback())
        import re as _re
        msg = _re.sub(r"<[^>]+>", " ", str(e) or "").strip() or type(e).__name__
        _ghi_ket_qua(resignation_name, "%s: %s" % (str(now_datetime())[:16], msg))
        if raise_errors:
            raise
        return None


def _employee_of(email):
    if not email:
        return None
    for f in ("user_id", "company_email", "personal_email"):
        emp = frappe.db.get_value("Employee", {f: email},
                                  ["name", "employee_name", "user_id", "department", "company",
                                   "reports_to", "company_email"], as_dict=True)
        if emp:
            return emp
    return None


def _lm_level_approved(approval_request):
    return frappe.db.get_value("EC Approval Request Level",
                               {"approval_request": approval_request, "level_no": 1},
                               "level_status") == "Approved"


def _create_and_submit(resignation_name, early=False):
    frappe.db.get_value(RESIGNATION_DT, resignation_name, "name", for_update=True)
    res = frappe.get_doc(RESIGNATION_DT, resignation_name)
    if res.get("withdrawn_at"):
        frappe.throw(_("Đơn nghỉ việc {0} đã rút.").format(resignation_name))
    st = res.approval_request and frappe.db.get_value(
        "EC Approval Request", res.approval_request, "approval_status")
    if st != "Approved":
        if not (early and st in RES_OPEN and _lm_level_approved(res.approval_request)):
            frappe.throw(_("Đơn nghỉ việc {0} chưa được duyệt xong.").format(resignation_name))
    name = frappe.db.get_value(BUSINESS_DT, {"resignation_request": resignation_name}, "name")
    if name and frappe.db.get_value(BUSINESS_DT, name, "approval_request"):
        return name                                      # da co va da gui
    emp = _employee_of(res.employee_email)
    if name:
        doc = frappe.get_doc(BUSINESS_DT, name)          # ban truoc tao duoc nhung gui hong
    else:
        doc = frappe.new_doc(BUSINESS_DT)
        doc.resignation_request = res.name
        doc.employee_email = res.employee_email
        doc.last_working_day = res.last_working_day
        doc.resignation_reason = res.resignation_reason
        doc.clearance_source = "Resignation"
        doc.source_reference = res.name
        _fill_employee(doc, emp)
    doc.opened_early = 1 if st != "Approved" else 0
    leaver = (emp and emp.user_id) or res.employee_email
    if not doc.requested_by or (doc.requested_by or "").lower() == (leaver or "").lower():
        doc.requested_by = nguoi_gui_clearance(leaver, res)
    return _save_and_submit(doc)


def _fill_employee(doc, emp):
    if not emp:
        return
    doc.employee = emp.name
    doc.employee_name = emp.employee_name
    doc.department = emp.department
    doc.company = emp.company
    if emp.reports_to:
        doc.line_manager = frappe.db.get_value("Employee", emp.reports_to, "user_id")


def _save_and_submit(doc):
    doc.request_title = gen_title(doc)
    frappe.flags.ec_clearance_from_resignation = True
    try:
        doc.save(ignore_permissions=True)
    finally:
        frappe.flags.ec_clearance_from_resignation = False
    doc.submitted_at = now_datetime()
    doc.save(ignore_permissions=True)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, doc.requested_by)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    _dat_han(req_name, doc.last_working_day)
    return doc.name


def _dat_han(req_name, last_working_day):
    """SLA Clearance (Hoan 23/11): moi nhom han = ngay lam viec cuoi (qua roi thi hom nay)."""
    from frappe.utils import getdate, nowdate
    from ecentric_workspace.approval_center.shared import sla_ngay_lam_viec as sla
    han = max(getdate(last_working_day), getdate(nowdate())) if last_working_day else None
    sla.dat_han_cap(req_name, 1, han)


def tao_clearance(employee, ly_do, ngay_cuoi, nguoi_gui=None, nguon="Discipline", tham_chieu=None):
    """Cong cho module khac (Ky luat sa thai - Agent E; cham dut HD...): tao + gui Clearance cho mot
    nhan vien KHONG qua Don nghi viec. Idempotent theo nhan vien: con mot Clearance dang mo (chua gui /
    dang xu ly) thi tra lai phieu do. Nem loi khi du lieu sai (ben goi tu guard + log).

    employee: ma Employee. ly_do: chuoi (<=140 ky tu luu vao resignation_reason). ngay_cuoi: ngay lam
    viec cuoi. nguoi_gui: tuy chon (mac dinh: nguoi goi neu khong phai nguoi nghi, roi nhom CnB/HR)."""
    from frappe.utils import getdate
    row = frappe.db.get_value("Employee", employee,
                              ["name", "employee_name", "user_id", "department", "company",
                               "reports_to", "company_email"], as_dict=True)
    if not row:
        frappe.throw(_("Không tìm thấy hồ sơ nhân viên {0}.").format(employee))
    if not ngay_cuoi:
        frappe.throw(_("Thiếu ngày làm việc cuối."))
    email = row.user_id or row.company_email
    if not email:
        frappe.throw(_("Hồ sơ {0} chưa có tài khoản / email công ty.").format(employee))
    frappe.db.get_value("Employee", employee, "name", for_update=True)
    for c in frappe.get_all(BUSINESS_DT, filters={"employee": employee},
                            fields=["name", "approval_request"]):
        st = c.approval_request and frappe.db.get_value("EC Approval Request", c.approval_request,
                                                        "approval_status")
        if not c.approval_request or st in RES_OPEN:
            return c.name
    doc = frappe.new_doc(BUSINESS_DT)
    doc.employee_email = email
    doc.last_working_day = getdate(ngay_cuoi)
    doc.resignation_reason = (ly_do or "")[:140]
    doc.clearance_source = nguon if nguon in ("Resignation", "Discipline", "Other") else "Other"
    doc.source_reference = (tham_chieu or "")[:140] or None
    _fill_employee(doc, row)
    sess = frappe.session.user
    doc.requested_by = nguoi_gui_clearance(email, None,
                                           preferred=nguoi_gui or (sess if sess not in ("Administrator", "Guest") else None))
    return _save_and_submit(doc)


def cancel_for_resignation(resignation_name, actor, reason):
    """Don nghi viec bi rut -> huy Clearance dang mo cua don (engine.cancel, co ghi vet)."""
    c = frappe.db.get_value(BUSINESS_DT, {"resignation_request": resignation_name},
                            ["name", "approval_request"], as_dict=True)
    if not c or not c.approval_request:
        return None
    st = frappe.db.get_value("EC Approval Request", c.approval_request, "approval_status")
    if st not in RES_OPEN:
        return "clearance %s da %s - giu nguyen" % (c.name, st)
    engine.cancel(c.approval_request, actor=actor, reason=reason)
    pending = frappe.get_all("EC Approval Request Approver",
                             filters={"approval_request": c.approval_request, "status": "Pending"},
                             pluck="approver")
    engine.notify(sorted(set(pending)), _("Clearance đã huỷ vì đơn nghỉ việc được rút: {0}").format(
        engine.request_label(BUSINESS_DT, c.name)), BUSINESS_DT, c.name)
    return "da huy clearance %s" % c.name


# --------------------------------------------------------------------------- chan doan + tao bu
def chan_doan(resignation_name):
    """Vi sao don nay chua co Clearance - chi DOC. -> dict."""
    from frappe.utils import getdate, nowdate
    res = frappe.db.get_value(RESIGNATION_DT, resignation_name,
                              ["name", "employee_email", "last_working_day", "approval_request",
                               "requested_by", "withdrawn_at", "clearance_error", "submitted_at"],
                              as_dict=True)
    if not res:
        return {"name": resignation_name, "ly_do": ["khong ton tai"]}
    out = {"name": res.name, "employee_email": res.employee_email,
           "last_working_day": str(res.last_working_day or ""), "ly_do": [], "co_the_tao": False}
    st = res.approval_request and frappe.db.get_value("EC Approval Request", res.approval_request,
                                                      ["approval_status", "completed_at"], as_dict=True)
    out["approval_status"] = st.approval_status if st else "Draft"
    out["approved_at"] = str(st.completed_at or "") if st else ""
    clr = frappe.db.get_value(BUSINESS_DT, {"resignation_request": res.name},
                              ["name", "approval_request"], as_dict=True)
    out["clearance"] = clr.name if clr else None
    if clr and clr.approval_request:
        out["ly_do"].append("da co clearance")
        return out
    if res.withdrawn_at:
        out["ly_do"].append("don da rut")
        return out
    if not st or st.approval_status != "Approved":
        out["ly_do"].append("don chua duyet xong (%s)" % out["approval_status"])
        return out
    ap = frappe.get_all("EC Approval Action", filters={"approval_request": res.approval_request,
                                                        "action": "Commented", "actor": "Administrator"},
                        fields=["comment"], order_by="seq asc")
    if not any("clearance=" in (a.comment or "") for a in ap):
        out["ly_do"].append("handler sau duyet chua tung chay cho don nay (duyet truoc ban 29/09, "
                            "hoac job nen bi mat)")
    elif any("clearance=LOI" in (a.comment or "") for a in ap):
        out["ly_do"].append("handler da chay nhung tao Clearance LOI (xem Error Log 'Clearance: khong tao duoc')")
    if res.clearance_error:
        out["ly_do"].append("loi gan nhat: %s" % res.clearance_error)
    proc = frappe.get_all("EC Approval Process", filters={"approval_type": APPROVAL_TYPE, "status": "Active"},
                          pluck="name")
    out["process_active"] = proc
    if not proc:
        out["ly_do"].append("CHUA co process CLEARANCE_REQUEST Active")
    emp = _employee_of(res.employee_email)
    out["employee"] = emp.name if emp else None
    if not emp:
        out["ly_do"].append("khong thay ho so nhan vien theo email (nhom Line Manager se dung du phong)")
    leaver = (emp and emp.user_id) or res.employee_email
    out["nguoi_gui_du_kien"] = nguoi_gui_clearance(leaver, frappe.get_doc(RESIGNATION_DT, res.name))
    out["da_qua_ngay_cuoi"] = bool(res.last_working_day and getdate(res.last_working_day) < getdate(nowdate()))
    out["co_the_tao"] = bool(proc)
    return out


def danh_sach_thieu_clearance():
    """Don da duyet xong, chua rut, chua co Clearance da gui."""
    out = []
    for r in frappe.get_all(RESIGNATION_DT, filters={"approval_request": ["is", "set"]},
                            fields=["name", "approval_request", "withdrawn_at"], order_by="creation asc"):
        if r.withdrawn_at:
            continue
        if frappe.db.get_value("EC Approval Request", r.approval_request, "approval_status") != "Approved":
            continue
        clr = frappe.db.get_value(BUSINESS_DT, {"resignation_request": r.name}, "approval_request")
        if not clr:
            out.append(r.name)
    return out


def tao_bu(dry_run=1, names=None, include_past=0):
    """Tao bu Clearance (System Manager, ben goi kiem quyen). dry_run=1: chi chan doan.
    Mac dinh CHI tao cho don chua qua ngay lam viec cuoi; include_past=1 de tao ca don da qua."""
    names = [n for n in (names or danh_sach_thieu_clearance()) if n]
    rep = {"mode": "dry_run" if int(dry_run or 0) else "apply", "items": []}
    for n in names:
        d = chan_doan(n)
        if int(dry_run or 0) or "da co clearance" in d["ly_do"] or not d.get("co_the_tao"):
            d["hanh_dong"] = "khong tao (dry-run)" if int(dry_run or 0) else "bo qua"
        elif d.get("da_qua_ngay_cuoi") and not int(include_past or 0):
            d["hanh_dong"] = "bo qua - da qua ngay cuoi (include_past=1 de tao)"
        else:
            clr = create_from_resignation(n)
            d["hanh_dong"] = "da tao %s" % clr if clr else "LOI - xem clearance_error tren don"
        rep["items"].append(d)
    return rep


def quet_hang_ngay():
    """Job hang ngay (hooks.scheduler_events): (1) don da duyet chua co Clearance, ngay cuoi chua qua
    -> tao bu (lan duyet bi mat job nen / loi tam thoi); (2) don CHUA duyet xong nhung LM da duyet va
    con <= 5 ngay lam viec toi ngay cuoi -> MO SOM Clearance song song. Moi don mot try."""
    from frappe.utils import getdate, nowdate
    from ecentric_workspace.approval_center.shared import sla_ngay_lam_viec as sla
    if not frappe.get_all("EC Approval Process", filters={"approval_type": APPROVAL_TYPE, "status": "Active"},
                          limit_page_length=1):
        return {"skipped": "no active clearance process"}
    today = getdate(nowdate())
    le = sla.ngay_le()
    ket = {"tao_bu": [], "mo_som": [], "loi": []}
    rows = frappe.get_all(RESIGNATION_DT, filters={"approval_request": ["is", "set"],
                                                   "last_working_day": [">=", str(today)]},
                          fields=["name", "approval_request", "last_working_day", "withdrawn_at"])
    for r in rows:
        if r.withdrawn_at or frappe.db.get_value(BUSINESS_DT, {"resignation_request": r.name},
                                                 "approval_request"):
            continue
        st = frappe.db.get_value("EC Approval Request", r.approval_request, "approval_status")
        early = False
        if st == "Approved":
            kind = "tao_bu"
        elif st in RES_OPEN and _lm_level_approved(r.approval_request) \
                and sla.dem_ngay_lam_viec(today, getdate(r.last_working_day), le) <= MO_SOM_NGAY_LV:
            kind, early = "mo_som", True
        else:
            continue
        name = create_from_resignation(r.name, early=early)
        if name:
            ket[kind].append(name)
            if early:
                _bao_mo_som(r, name)
        else:
            ket["loi"].append(r.name)
    return ket


def _bao_mo_som(res_row, clearance_name):
    try:
        people = frappe.get_all("EC Approval Request Approver",
                                filters={"approval_request": res_row.approval_request}, pluck="approver")
        engine.log_action(res_row.approval_request, "Commented", "Administrator",
                          comment=_("Mở Clearance sớm ({0}): còn ≤ {1} ngày làm việc tới ngày cuối, "
                                    "quản lý trực tiếp đã duyệt.").format(clearance_name, MO_SOM_NGAY_LV))
        engine.notify(sorted(set(people)), _("Đã mở Clearance sớm cho {0}").format(
            engine.request_label(RESIGNATION_DT, res_row.name)), RESIGNATION_DT, res_row.name)
        frappe.db.commit()
    except Exception:
        frappe.log_error(title="Clearance mo som: khong bao duoc %s" % clearance_name,
                         message=frappe.get_traceback())


def submit(name):
    """Gui lai mot phieu da tao nhung gui hong. Chi System Manager (phieu khong co nguoi gui that)."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.approval_request:
        frappe.throw(_("Yêu cầu này đã được gửi."))
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Chỉ quản trị viên gửi lại được phiếu Clearance."), frappe.PermissionError)
    if not doc.resignation_request:
        return _save_and_submit(doc)
    return create_from_resignation(doc.resignation_request, raise_errors=True, early=True)


def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yêu cầu chưa được gửi."))
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=False)
    return {"restarted": False}


def clearance_block(business, request):
    """Checklist tung nhom (ai da xac nhan, luc nao, ghi chu) + muc ban giao cua nhom."""
    groups = {}
    if request:
        for r in frappe.get_all("EC Approval Request Approver",
                                filters={"approval_request": request.name},
                                fields=["participant_group", "approver", "status", "decided_at",
                                        "comment"], order_by="creation asc"):
            key = r.participant_group or "—"
            g = groups.setdefault(key, {"group": key, "done": False, "by": None, "at": None,
                                        "note": None, "members": [],
                                        "items": CHECKLIST.get(key, [])})
            g["members"].append(r.approver)
            if r.status == "Approved" and not g["done"]:
                g.update(done=True, by=r.approver, at=r.decided_at, note=r.comment)
    return {"greeting": GREETING, "groups": list(groups.values()),
            "source": business.get("clearance_source") or "Resignation",
            "opened_early": business.get("opened_early"),
            "resignation_route": ("/approvals/resignation?id=%s" % business.get("resignation_request"))
            if business.get("resignation_request") else None}


def on_final_approval(name):
    """Du cac nhom da ban giao -> bao line manager (nguoi gui da duoc engine bao)."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.line_manager and doc.line_manager != doc.requested_by:
        engine.notify([doc.line_manager],
                      _("Đã hoàn tất bàn giao nghỉ việc: {0}").format(
                          engine.request_label(BUSINESS_DT, name)), BUSINESS_DT, name)
