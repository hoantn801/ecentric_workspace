# Copyright (c) 2026, eCentric and contributors
"""New Staff Preparation - TU TAO khi Offer Request duyet xong (28/09/2026, Hoan).

Cac ben chuan bi onboard SONG SONG (Hoan chot "song song, moi ben tick khi xong"): mot cap
duy nhat che do "Each Group" cua engine - Lead HR / HOF / CnB / Operation cung nhan viec mot
luc, moi nhom mot nguoi bam "Da chuan bi" la nhom do xong; phieu xong khi du cac nhom. Cac
nhom la cau hinh process NEW_STAFF_PREPARATION-V1, khong viet cung o day.

Noi dung chep tu Offer - KHONG co muc luong (dung mau New Staff Preparation cu: 9 truong).
Nguoi gui (requested_by) = nguoi da gui Offer (HR tuyen dung). Ngay onboard: 10:00 thiep
Teams, tu 08:30 popup trang chu (xem welcome.py)."""
import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, nowdate

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC New Staff Preparation"
APPROVAL_TYPE = "NEW_STAFF_PREPARATION"
OFFER_DT = "EC Offer Request"
#: Chep tu Offer (khong co `compensation` - co y).
COPY_FIELDS = ("hiring_request", "candidate_name", "position", "line_manager", "department",
               "company", "company_laptop", "onboard_date", "probation_end_date",
               "mobile_phone", "note")
GREETING = ("Dear all, we're going to welcome a new member with the details below. "
            "Kindly help us prepare onboarding process and related items for him/her.")


def _dept_label(dept):
    if not dept:
        return ""
    return frappe.db.get_value("Department", dept, "department_name") or dept


def gen_title(doc):
    parts = [doc.get("candidate_name"), doc.get("position"), _dept_label(doc.get("department"))]
    parts = [str(x).strip() for x in parts if x and str(x).strip()]
    return ("New Staff Preparation - " + " - ".join(parts))[:255]


def prepare_draft(document):
    """draft_preparer: KHONG cho tao tay. Phieu chi sinh ra tu Offer da duyet (create_from_offer)."""
    if document.is_new() and not frappe.flags.get("ec_nsp_from_offer"):
        frappe.throw(_("New Staff Preparation được tạo tự động khi Offer Request duyệt xong - "
                       "không tạo tay."))


def create_from_offer(offer_name, raise_errors=False):
    """Tao + gui New Staff Preparation cho mot Offer DA DUYET. Idempotent.

    Chay o NEN sau khi giao dich duyet Offer commit (xem offer service.on_final_approval), va
    qua nut "Tao lai" tren Offer neu lan dau hong. Hong thi: rollback phan cua minh, ghi Error
    Log, bao nguoi gui Offer - KHONG im lang: phieu chuan bi khong ton tai thi khong ai chuan bi."""
    try:
        name = _create_and_submit(offer_name)
        frappe.db.commit()
        return name
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="New Staff Preparation: khong tao duoc tu %s" % offer_name,
                         message=frappe.get_traceback())
        try:
            req_by = frappe.db.get_value(OFFER_DT, offer_name, "requested_by")
            if req_by:
                engine.notify([req_by], _("Chưa tạo được New Staff Preparation cho {0} - mở Offer "
                                          "và bấm \"Tạo lại\" (hoặc báo quản trị viên).").format(offer_name),
                              OFFER_DT, offer_name)
                frappe.db.commit()
        except Exception:
            pass
        if raise_errors:
            raise
        return None


def _create_and_submit(offer_name):
    frappe.db.get_value(OFFER_DT, offer_name, "name", for_update=True)
    offer = frappe.get_doc(OFFER_DT, offer_name)
    st = offer.approval_request and frappe.db.get_value(
        "EC Approval Request", offer.approval_request, "approval_status")
    if st != "Approved":
        frappe.throw(_("Offer {0} chưa được duyệt xong.").format(offer_name))
    if offer.get("candidate_status"):
        frappe.throw(_("Offer {0} đã ghi nhận \"{1}\" - không tạo New Staff Preparation.").format(
            offer_name, offer.candidate_status))
    name = offer.new_staff_preparation or frappe.db.get_value(
        BUSINESS_DT, {"offer_request": offer_name}, "name")
    if name and frappe.db.get_value(BUSINESS_DT, name, "approval_request"):
        if not offer.new_staff_preparation:
            frappe.db.set_value(OFFER_DT, offer_name, "new_staff_preparation", name)
        return name                                      # da co va da gui
    if name:
        doc = frappe.get_doc(BUSINESS_DT, name)          # ban truoc tao duoc nhung gui hong
    else:
        doc = frappe.new_doc(BUSINESS_DT)
        for f in COPY_FIELDS:
            doc.set(f, offer.get(f))
        doc.offer_request = offer.name
        doc.requested_by = offer.requested_by
        doc.employee = offer.get("employee")
    doc.request_title = gen_title(doc)
    frappe.flags.ec_nsp_from_offer = True
    try:
        doc.save(ignore_permissions=True)
    finally:
        frappe.flags.ec_nsp_from_offer = False
    frappe.db.set_value(OFFER_DT, offer_name, "new_staff_preparation", doc.name)
    doc.submitted_at = now_datetime()
    doc.save(ignore_permissions=True)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, doc.requested_by)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    _dat_han(req_name, doc.onboard_date)
    return doc.name


#: SLA (23/11/2026): moi nhom xong truoc ngay onboard 1 ngay lam viec, nhung toi thieu 2 ngay lam viec.
HAN_TRUOC_ONBOARD = 1
HAN_TOI_THIEU = 2


def han_chuan_bi(onboard_date, hom_nay, le=()):
    """Ham thuan: han chung cho cac nhom (date)."""
    from ecentric_workspace.approval_center.shared import sla_ngay_lam_viec as sla
    toi_thieu = sla.cong_ngay_lam_viec(hom_nay, HAN_TOI_THIEU, le)
    if not onboard_date:
        return toi_thieu
    return max(sla.tru_ngay_lam_viec(getdate(onboard_date), HAN_TRUOC_ONBOARD, le), toi_thieu)


def _dat_han(req_name, onboard_date):
    from ecentric_workspace.approval_center.shared import sla_ngay_lam_viec as sla
    sla.dat_han_cap(req_name, 1, han_chuan_bi(onboard_date, getdate(nowdate()), sla.ngay_le()))


# --------------------------------------------------------------------------- huy theo Offer
def cancel_for_offer(offer_name, actor, note):
    """Ung vien tu choi / huy offer -> huy NSP dang mo (engine.cancel co ly do). NSP da xong thi ghi vet +
    bao cac ben (co the phai thu hoi viec da chuan bi). -> chuoi ket qua."""
    name = frappe.db.get_value(OFFER_DT, offer_name, "new_staff_preparation") or frappe.db.get_value(
        BUSINESS_DT, {"offer_request": offer_name}, "name")
    if not name:
        return "chua co NSP"
    req = frappe.db.get_value(BUSINESS_DT, name, "approval_request")
    if not req:
        return "NSP %s chua gui - giu nhap" % name
    st = frappe.db.get_value("EC Approval Request", req, "approval_status")
    people = frappe.get_all("EC Approval Request Approver", filters={"approval_request": req},
                            pluck="approver")
    if st in ("Pending", "Information Required"):
        engine.cancel(req, actor=actor, reason=note)
        msg, out = _("Đã huỷ chuẩn bị onboard: {0}"), "da huy NSP %s" % name
    elif st == "Approved":
        engine.log_action(req, "Commented", actor, comment=note)
        msg, out = _("Ứng viên không nhận việc - kiểm tra thu hồi đồ đã chuẩn bị: {0}"), "NSP %s da xong - da bao" % name
    else:
        return "NSP %s da %s" % (name, st)
    engine.notify(sorted(set(people) - {actor}), msg.format(engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return out


# --------------------------------------------------------------------------- chon ho so nhan vien
HR_PICK_ROLES = ("EC CnB", "HR", "System Manager")


def may_pick_employee(doc, user=None):
    """Nhom HR cua phieu (co dong duyet trong nhom HR) hoac role CnB/HR/System Manager."""
    user = user or frappe.session.user
    if set(frappe.get_roles(user)) & set(HR_PICK_ROLES):
        return True
    from ecentric_workspace.approval_center.features.new_staff_preparation.infrastructure.setup_v2 import (
        HR_GROUP)
    return bool(doc.get("approval_request") and frappe.db.exists(
        "EC Approval Request Approver", {"approval_request": doc.approval_request, "approver": user,
                                         "participant_group": ["in", [HR_GROUP, "Lead HR"]]}))


def pick_employee(name, employee, actor=None):
    """Nhom HR chon ho so Employee vua tao cho nguoi moi -> ghi dong Thu viec / Thuc tap vao
    Employee.ec_contracts (tu_ngay = ngay onboard, den_ngay = ngay ket thuc thu viec cua Offer). Co ghi vet."""
    actor = actor or frappe.session.user
    frappe.db.get_value(BUSINESS_DT, name, "name", for_update=True)
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not may_pick_employee(doc, actor):
        frappe.throw(_("Chỉ nhóm HR của phiếu (hoặc CnB/HR) mới chọn hồ sơ nhân viên."), frappe.PermissionError)
    if not doc.approval_request:
        frappe.throw(_("Phiếu chưa gửi."))
    st = frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_status")
    if st in ("Rejected", "Cancelled"):
        frappe.throw(_("Phiếu đã kết thúc ({0}).").format(st))
    if doc.get("new_employee") and doc.new_employee != employee \
            and "System Manager" not in frappe.get_roles(actor):
        frappe.throw(_("Đã chọn hồ sơ {0}. Chỉ System Manager đổi được.").format(doc.new_employee))
    emp = frappe.db.get_value("Employee", employee, ["name", "employee_name", "status"], as_dict=True)
    if not emp:
        frappe.throw(_("Không tìm thấy hồ sơ nhân viên {0}.").format(employee))
    ket = ghi_ho_so_nhan_vien(doc, emp.name)
    frappe.db.set_value(BUSINESS_DT, name, {"new_employee": emp.name, "new_employee_set_by": actor,
                                            "contract_row_note": ket})
    engine.log_action(doc.approval_request, "Commented", actor,
                      comment=_("Chọn hồ sơ nhân viên {0} ({1}); {2}").format(emp.name, emp.employee_name, ket))
    return {"new_employee": emp.name, "contract": ket}


def ghi_ho_so_nhan_vien(doc, employee):
    """24/11/2026 (Hoan: vong tuyen dung phai noi toi thu viec): ho so nguoi moi co
      * dong Thu viec / Thuc tap trong ec_contracts (goc cua Danh gia thu viec + Khao sat moc);
      * date_of_joining = ngay onboard, final_confirmation_date = ngay het thu viec - CHI khi trong.
    Offer chua ghi ngay ket thuc thu viec -> mac dinh theo Dieu 25 (employee_contract). Idempotent.
    -> chuoi ket qua (ghi vet tren phieu)."""
    from ecentric_workspace.approval_center.features.new_staff_preparation.infrastructure import (
        employee_contract as ec)
    emp_type = frappe.db.get_value("EC Hiring Request", doc.hiring_request, "employment_type") \
        if doc.get("hiring_request") else None
    loai = ec.loai_hop_dong(emp_type)
    den, ghi_chu_mac_dinh = doc.get("probation_end_date"), None
    if not den:
        den, ghi_chu_mac_dinh = ec.ngay_ket_thuc_mac_dinh(loai, doc.get("onboard_date"))
    nguon = "%s (%s)" % (doc.name, doc.get("offer_request") or "")
    ket = ec.ghi_dong_dau(employee, loai, doc.get("onboard_date"), den,
                          ghi_chu="Từ " + nguon + ("; " + ghi_chu_mac_dinh if ghi_chu_mac_dinh else ""))
    ket += "; " + ec.dien_ho_so(employee, doc.get("onboard_date"), den if loai == "Thử việc" else None, nguon)
    return ket


def suggest_employees(name, user=None):
    """Goi y ho so cho nhom HR chon: ngay vao lam gan ngay onboard (+-15 ngay) hoac trung ten ung vien."""
    from frappe.utils import add_days
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not may_pick_employee(doc, user):
        frappe.throw(_("Chỉ nhóm HR của phiếu (hoặc CnB/HR) mới chọn hồ sơ nhân viên."), frappe.PermissionError)
    fields = ["name", "employee_name", "date_of_joining", "department", "status"]
    rows = []
    if doc.onboard_date:
        rows += frappe.get_all("Employee", filters={"date_of_joining": ["between", [
            add_days(doc.onboard_date, -15), add_days(doc.onboard_date, 15)]]}, fields=fields,
            limit_page_length=20)
    if doc.candidate_name:
        rows += frappe.get_all("Employee", filters={"employee_name": ["like", "%%%s%%" % doc.candidate_name.strip()]},
                               fields=fields, limit_page_length=10)
    seen, out = set(), []
    for r in rows:
        if r.name not in seen:
            seen.add(r.name)
            out.append(r)
    return out[:20]


def submit(name):
    """Gui mot phieu da tao nhung chua gui (lan tao tu dong hong o buoc gui). Nguoi gui Offer
    hoac System Manager."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.approval_request:
        frappe.throw(_("Yêu cầu này đã được gửi."))
    user = frappe.session.user
    if doc.requested_by != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Bạn chỉ có thể gửi yêu cầu của chính mình."))
    return create_from_offer(doc.offer_request, raise_errors=True)


def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yêu cầu chưa được gửi."))
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=False)
    return {"restarted": False}


def _may_edit_welcome(doc, user):
    if doc.requested_by == user or "System Manager" in frappe.get_roles(user):
        return True
    return "EC Recruiter" in frappe.get_roles(user)


def update_welcome(name, welcome_intro=None, onboard_date=None):
    """HR chinh loi gioi thieu / ngay onboard SAU khi phieu da gui (truoc ngay onboard).

    Doi ngay onboard la chuyen thuong (ung vien lui ngay di lam) - bao cac ben dang chuan bi,
    ghi vao lich su. Khong mo lai cac nhom da xac nhan: viec ho chuan bi khong phu thuoc ngay."""
    user = frappe.session.user
    frappe.db.get_value(BUSINESS_DT, name, "name", for_update=True)
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not _may_edit_welcome(doc, user):
        frappe.throw(_("Chỉ HR (người gửi / EC Recruiter) mới sửa được."), frappe.PermissionError)
    st = doc.approval_request and frappe.db.get_value("EC Approval Request", doc.approval_request,
                                                      "approval_status")
    if st in ("Rejected", "Cancelled"):
        frappe.throw(_("Phiếu đã kết thúc, không sửa được."))
    thay = []
    if welcome_intro is not None and (welcome_intro or "") != (doc.welcome_intro or ""):
        if getdate(doc.onboard_date) < getdate(nowdate()):
            frappe.throw(_("Đã qua ngày onboard - không sửa lời giới thiệu được nữa."))
        doc.welcome_intro = (welcome_intro or "").strip()
        thay.append(_("lời giới thiệu"))
    if onboard_date and str(getdate(onboard_date)) != str(getdate(doc.onboard_date)):
        if getdate(onboard_date) < getdate(nowdate()):
            frappe.throw(_("Ngày onboard mới không được ở quá khứ."))
        cu = doc.onboard_date
        doc.onboard_date = onboard_date
        doc.welcome_teams_sent_at = None
        doc.welcome_teams_result = None
        thay.append(_("ngày onboard {0} → {1}").format(cu, onboard_date))
    if not thay:
        return {"changed": False}
    doc.save(ignore_permissions=True)
    if doc.approval_request and onboard_date and st in ("Pending", "Information Required"):
        _dat_han(doc.approval_request, doc.onboard_date)      # han chuan bi theo ngay onboard moi
    if doc.approval_request:
        engine.log_action(doc.approval_request, "Commented", user,
                          comment=_("Cập nhật: {0}").format(", ".join(thay)))
        if any(t.startswith(_("ngày onboard")) for t in thay):
            nhom = frappe.get_all("EC Approval Request Approver",
                                  filters={"approval_request": doc.approval_request},
                                  pluck="approver")
            engine.notify(sorted(set(nhom)),
                          _("Đổi ngày onboard: {0}").format(engine.request_label(BUSINESS_DT, name)),
                          BUSINESS_DT, name)
    return {"changed": True}


def nsp_block(business, request):
    """Khoi doc them cho man hinh chi tiet: checklist tung nhom + loi chao + quyen sua."""
    groups = {}
    if request:
        for r in frappe.get_all("EC Approval Request Approver",
                                filters={"approval_request": request.name},
                                fields=["participant_group", "approver", "status", "decided_at",
                                        "comment"], order_by="creation asc"):
            g = groups.setdefault(r.participant_group or "—",
                                  {"group": r.participant_group or "—", "done": False,
                                   "by": None, "at": None, "note": None, "members": []})
            g["members"].append(r.approver)
            if r.status == "Approved" and not g["done"]:
                g.update(done=True, by=r.approver, at=r.decided_at, note=r.comment)
    user = frappe.session.user
    return {
        "greeting": GREETING,
        "groups": list(groups.values()),
        "offer_route": "/approvals/offer-request?id=%s" % business.get("offer_request"),
        "department_label": _dept_label(business.get("department")),
        "can_edit_welcome": _may_edit_welcome(business, user)
        and not (request and request.approval_status in ("Rejected", "Cancelled")),
        # V2 (23/11): nhom HR chon ho so Employee -> ghi dong Thu viec vao ec_contracts.
        "new_employee": business.get("new_employee"),
        "contract_row_note": business.get("contract_row_note"),
        "can_pick_employee": bool(request and request.approval_status not in ("Rejected", "Cancelled")
                                  and may_pick_employee(business, user)),
    }


def on_final_approval(name):
    """Du cac nhom da chuan bi -> bao them line manager (nguoi de nghi da duoc engine bao)."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    # 24/11/2026: da gan ho so nhan vien -> dam bao dong thu viec + ngay tren ho so (idempotent, nuot loi:
    # loi ghi ho so khong lam hong luot duyet; ghi vet de C&B biet).
    if doc.get("new_employee"):
        try:
            ket = ghi_ho_so_nhan_vien(doc, doc.new_employee)
            if doc.approval_request:
                engine.log_action(doc.approval_request, "Commented", "Administrator",
                                  comment=_("Hồ sơ nhân viên {0}: {1}").format(doc.new_employee, ket))
        except Exception:
            frappe.log_error(title="NSP %s: ghi ho so nhan vien loi" % name, message=frappe.get_traceback())
    if doc.line_manager and doc.line_manager != doc.requested_by:
        engine.notify([doc.line_manager],
                      _("Các bên đã chuẩn bị xong cho nhân viên mới: {0}").format(
                          engine.request_label(BUSINESS_DT, name)), BUSINESS_DT, name)
