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
    return doc.name


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
    }


def on_final_approval(name):
    """Du cac nhom da chuan bi -> bao them line manager (nguoi de nghi da duoc engine bao)."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.line_manager and doc.line_manager != doc.requested_by:
        engine.notify([doc.line_manager],
                      _("Các bên đã chuẩn bị xong cho nhân viên mới: {0}").format(
                          engine.request_label(BUSINESS_DT, name)), BUSINESS_DT, name)
