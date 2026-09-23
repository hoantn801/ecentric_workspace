"""Permission-safe generic queries and projections for approval request types."""
import frappe
from frappe import _
from datetime import timedelta

from frappe.utils import get_datetime

from ecentric_workspace.approval_center.shared.requests import capabilities


def requester_display(user):
    """Resolve Employee/User display name without leaking lookup failures."""
    if not user:
        return None
    try:
        employee_name = frappe.db.get_value(
            "Employee", {"user_id": user}, "employee_name")
        if employee_name:
            return employee_name
        return frappe.db.get_value("User", user, "full_name") or user
    except Exception:
        return user


def employee_context(user=None):
    user = user or frappe.session.user
    employee = frappe.db.get_value(
        "Employee", {"user_id": user},
        ["name", "employee_name", "department", "company", "reports_to"], as_dict=True)
    manager_user = None
    if employee and employee.reports_to:
        manager_user = frappe.db.get_value("Employee", employee.reports_to, "user_id")
    return {
        "user": user,
        "employee": employee.name if employee else None,
        "employee_name": employee.employee_name if employee else None,
        "department": employee.department if employee else None,
        "company": employee.company if employee else None,
        "manager_user": manager_user,
        "manager_resolvable": bool(manager_user),
    }


def process_preview(approval_type):
    processes = frappe.get_all(
        "EC Approval Process", filters={"approval_type": approval_type, "status": "Active"},
        pluck="name")
    if not processes:
        processes = frappe.get_all(
            "EC Approval Process", filters={"approval_type": approval_type, "status": "Draft"},
            order_by="creation desc", pluck="name")
    if not processes:
        return []
    return frappe.get_all(
        "EC Approval Level", filters={"approval_process": processes[0]},
        fields=["level_no", "level_name"], order_by="level_no asc")


def _can_fulfil(user, definition):
    """Canonical engine rule for 'may this user work the fulfillment queue'.

    The form pages gate their Operation/fulfillment tab on tabs.fulfillment; the shared
    bootstrap never set it (only ai_topup, which kept a bespoke controller, did), so after
    the forms moved onto the shared adapter the tab silently disappeared and nobody could
    claim an approved request -- even though list_fulfillment_queue happily returned it.
    Best-effort: any failure hides the tab rather than breaking the page."""
    try:
        from ecentric_workspace.approval_center.shared.workflow import permissions as _perm
        return bool(_perm.is_eligible_fulfiller(user, definition.code, definition.business_doctype))
    except Exception:
        return False


def bootstrap(definition):
    user = frappe.session.user
    admin = capabilities.is_system_manager(user)
    return {
        "context": employee_context(user),
        "is_system_manager": admin,
        "tabs": {"create": True, "my_requests": True,
                 "my_approvals": capabilities.has_any_approver_row(user) or admin,
                 "fulfillment": _can_fulfil(user, definition),
                 # Tab "Tat ca" bat cho MOI nguoi: pham vi do `reporting.scope` quyet dinh,
                 # nen voi nhan vien thuong no gan trung "Yeu cau cua toi" - dung, khong phai
                 # loi. An tab theo vai tro o day se dung mot luat quyen THU HAI canh
                 # scope_predicate, va hai luat canh nhau thi som muon cung troi nhau.
                 "all": True},
        "form_options": definition.options_provider(),
    }


def list_my_requests(definition, filters=None, start=0, page_length=20):
    user = frappe.session.user
    db_filters = {"requested_by": user}
    supplied = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    if definition.filter_builder:
        definition.filter_builder(db_filters, supplied)
    page_length = min(int(page_length or 20), definition.max_page_length)
    total = frappe.db.count(definition.business_doctype, db_filters)
    rows = frappe.get_all(
        definition.business_doctype, filters=db_filters, fields=list(definition.my_request_fields),
        limit_start=int(start), limit_page_length=page_length, order_by="modified desc")
    active_level_count = None
    for row in rows:
        approval = row.approval_request and frappe.db.get_value(
            "EC Approval Request", row.approval_request,
            ["approval_status", "current_level"], as_dict=True)
        row["approval_status"] = approval.approval_status if approval else "Draft"
        row["current_level"] = approval.current_level if approval else 0
        row["requested_at"] = row.get("creation")
        row["requester_name"] = requester_display(user)
        if row.approval_request:
            row["total_levels"] = frappe.db.count(
                "EC Approval Request Level", {"approval_request": row.approval_request})
            row["current_level_name"] = (
                frappe.db.get_value(
                    "EC Approval Request Level",
                    {"approval_request": row.approval_request,
                     "level_no": row["current_level"]}, "level_name")
                if row["current_level"] else None)
        else:
            if active_level_count is None:
                active_level_count = len(process_preview(definition.code))
            row["total_levels"] = active_level_count
            row["current_level_name"] = None
    return {"rows": rows, "total": total}


def list_my_approvals(definition, section="pending"):
    user = frappe.session.user
    statuses = (["Pending"] if section == "pending"
                else ["Approved", "Rejected", "Information Requested", "Skipped"])
    rows = frappe.get_all(
        "EC Approval Request Approver",
        filters={"approver": user, "status": ["in", statuses]},
        fields=["approval_request", "level_no", "status", "decided_at"],
        order_by="modified desc", limit_page_length=200)
    output = []
    for row in rows:
        request = frappe.db.get_value(
            "EC Approval Request", row.approval_request,
            ["reference_name", "approval_status", "current_level", "requested_by"], as_dict=True)
        if not request:
            continue
        if (section == "pending"
                and (request.approval_status not in capabilities.OPEN_STATUSES
                     or request.current_level != row.level_no)):
            continue
        business = frappe.db.get_value(
            definition.business_doctype, request.reference_name,
            list(definition.approval_list_fields), as_dict=True)
        if not business:
            continue
        current_name = (
            frappe.db.get_value(
                "EC Approval Request Level",
                {"approval_request": row.approval_request,
                 "level_no": request.current_level}, "level_name")
            if request.current_level else None)
        business["requested_at"] = business.get("creation")
        business["requester_name"] = requester_display(request.requested_by)
        projection = {
            "approval_request": row.approval_request, "level_no": row.level_no,
            "approval_status": request.approval_status,
            "requested_by": request.requested_by, "my_status": row.status,
            "total_levels": frappe.db.count(
                "EC Approval Request Level", {"approval_request": row.approval_request}),
        }
        if definition.approval_projection == "legacy_level_name":
            projection["level_name"] = frappe.db.get_value(
                "EC Approval Request Level",
                {"approval_request": row.approval_request, "level_no": row.level_no},
                "level_name")
        else:
            projection.update({"current_level": request.current_level,
                               "current_level_name": current_name})
        business.update(projection)
        output.append(business)
    return {"rows": output}


#: SharePoint lam tron moc thoi gian ve GIAY, va lan ghi cua ta cung mat vai tram mili giay
#: giua luc tai len va luc doc moc ve. Chenh vai giay quanh moc nen la CUA TA, khong phai
#: nguoi sua. De 0 thi canh bao se nhay lung tung ngay sau moi lan dong bo.
DUNG_SAI_GIAY = 5


def gan_sharepoint(attachments, approvers):
    """Gan link SharePoint + canh bao "tep doi sau khi da co cap duyet" vao tung dinh kem.

    LAM O DAY, MOT CHO. `renderAttachments` bi chep y het trong 26 file giao dien
    (`features/*/ui/main_section.html`) - neu tinh canh bao nay o phia JS thi phai sua 26 cho
    va lan sau ai them form thu 29 se quen. Tinh o server thi moi form co san.

    CANH BAO, KHONG CHAN. Ban tren SharePoint la ban SONG (Hoan chot cho sua/comment truc
    tiep), nen tep doi sau khi duyet la chuyen BINH THUONG - nguoi duyet sua cau chu cung lam
    `lastModifiedDateTime` nhay. Chan lai thi tinh nang review online thanh vo dung. Viec cua
    lop nay la noi ro: cap nao da duyet TRUOC thoi diem tep bi sua lan cuoi, tuc cap do duyet
    tren mot ban khong con y nguyen.

    Chi tinh cap da "Approved": cap dang "Pending" thi chua duyet gi de ma lo.
    """
    if not attachments:
        return attachments
    urls = [a.get("file_url") for a in attachments if a.get("file_url")]
    if not urls:
        return attachments
    rows = frappe.get_all(
        "EC SharePoint File Link", filters={"file_url": ["in", urls]},
        fields=["file_url", "sp_web_url", "sp_share_url", "sp_last_modified", "sp_uploaded_at"])
    if not rows:
        return attachments
    theo_url = {r.file_url: r for r in rows}
    da_duyet = [a for a in (approvers or [])
                if a.get("status") == "Approved" and a.get("decided_at")]
    for a in attachments:
        r = theo_url.get(a.get("file_url"))
        if not r or not r.sp_web_url:
            continue
        a["sp_web_url"] = r.sp_web_url
        # Link chia se moi la cua ma quyen cap cho nguoi trong luong gan vao (xem ghi_lien_ket).
        a["sp_share_url"] = r.sp_share_url or ""
        a["sp_last_modified"] = r.sp_last_modified
        if not r.sp_last_modified:
            continue
        moc = get_datetime(r.sp_last_modified)
        # PHAI so voi MOC NEN truoc. `sp_last_modified` bi chinh lan tai len cua he thong
        # ghi de, nen neu chi so no voi moc duyet thi moi phieu dong bo SAU khi da co cap duyet
        # deu bao nham - 15/09 do duoc 5/5 bang canh bao dang hien deu SAI, trong do co mot
        # bang to bon nguoi duyet tren mot tep ma "moc sua" chinh la giay phut ta chay lenh cap
        # bu. Mot canh bao keu oan se day nguoi ta bo qua mau vang, roi den lan that cung bo qua.
        nen = get_datetime(r.sp_uploaded_at) if r.sp_uploaded_at else None
        if nen and moc <= nen + timedelta(seconds=DUNG_SAI_GIAY):
            a["sp_sua_sau_duyet"] = []
            continue
        a["sp_sua_sau_duyet"] = [
            {"approver": x.get("approver"), "level_no": x.get("level_no"),
             "decided_at": x.get("decided_at")}
            for x in da_duyet if get_datetime(x["decided_at"]) < moc]
    return attachments


def dedupe_attachments(rows):
    """One row per physical file.

    Uploading through the form creates TWO File records for the same upload: the
    /api/method/upload_file call stores one with attached_to_field empty, then Frappe's
    standard attach_files_to_document hook -- whose duplicate check includes
    attached_to_field -- does not recognise it and stores a second one for the Attach
    field. Both point at the SAME file_url, so the attachment list showed every file
    twice. Collapse by file_url, keeping the earliest record."""
    seen, out = set(), []
    for r in rows or []:
        key = (r.get("file_url") or "").strip() or ("name:" + str(r.get("file_name") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def fulfillment_block(business, request):
    """Fulfillment state for the detail page (status/owner/result), meta-driven.

    The pages render an 'Xử lý Operation' section from det.fulfillment and gate the claim
    button on capabilities.can_claim. Only ai_topup (bespoke controller) returned this block,
    so on every shared-adapter form the section showed 'Trạng thái xử lý: —' and an approved
    request could not be picked up from its detail page. Returns {} for forms that carry no
    fulfillment fields at all."""
    fields = ("fulfillment_status", "fulfillment_owner", "fulfillment_due_at",
              "completed_by", "completed_at", "fulfillment_summary", "output_link",
              "completed_attachment")
    try:
        present = set(df.fieldname for df in business.meta.fields)
    except Exception:
        present = set()
    if not present & set(fields):
        return {}
    out = {
        "status": business.get("fulfillment_status"),
        "owner": business.get("fulfillment_owner"),
        "due_at": business.get("fulfillment_due_at"),
        "completed_by": business.get("completed_by"),
        "completed_at": business.get("completed_at"),
        "summary": business.get("fulfillment_summary"),
        "output_link": business.get("output_link"),
        "completed_attachment": business.get("completed_attachment"),
        "eligible_fulfillers": [],
    }
    if request and out["status"] == "Assigned":
        try:
            from ecentric_workspace.approval_center.shared.workflow import transitions as _eng
            proc = frappe.get_doc("EC Approval Process",
                                  frappe.db.get_value("EC Approval Request", request.name, "approval_process"))
            out["eligible_fulfillers"] = [u for u, _l in _eng.resolve_participants(
                [p for p in proc.participants if p.participant_purpose == "Fulfiller"],
                business.get("requested_by"))]
        except Exception:
            pass
    return out


def detail(definition, name):
    user = frappe.session.user
    business = frappe.get_doc(definition.business_doctype, name)
    request = capabilities.approval_request_for(definition, name)
    if not capabilities.can_view(user, business, request):
        frappe.throw(_("Bạn không có quyền xem yêu cầu này."), frappe.PermissionError)
    levels, approvers, timeline = [], [], []
    if request:
        levels = frappe.get_all(
            "EC Approval Request Level", filters={"approval_request": request.name},
            fields=["level_no", "level_name", "approval_mode", "minimum_approvals",
                    "mandatory", "level_status", "activated_at", "completed_at", "due_at"],
            order_by="level_no asc")
        approvers = frappe.get_all(
            "EC Approval Request Approver", filters={"approval_request": request.name},
            fields=["level_no", "approver", "source", "status", "decided_at", "comment"],
            order_by="level_no asc")
        timeline = frappe.get_all(
            "EC Approval Action", filters={"approval_request": request.name},
            fields=["seq", "request_level", "actor", "action", "comment", "action_time",
                    "previous_status", "new_status"], order_by="seq asc")
        levels_by_name = {row.name: row for row in frappe.get_all(
            "EC Approval Request Level", filters={"approval_request": request.name},
            fields=["name", "level_no", "level_name"])}
        for action in timeline:
            level = levels_by_name.get(action.get("request_level"))
            if level:
                action["level_no"] = level.level_no
                action["level_name"] = level.level_name
    attachments = gan_sharepoint(dedupe_attachments(frappe.get_all(
        "File", filters={"attached_to_doctype": definition.business_doctype,
                         "attached_to_name": name},
        fields=["file_name", "file_url", "is_private", "owner", "creation"],
        order_by="creation asc")), approvers)
    status = request.approval_status if request else "Draft"
    extra = {}
    if getattr(definition, "detail_extender", None):
        try:
            extra = definition.detail_extender(business, request) or {}
        except Exception:
            # Khoi phu khong duoc lam hong man hinh chi tiet; ghi log de sua.
            frappe.log_error(frappe.get_traceback(), "detail_extender %s" % definition.code)
            extra = {"error": True}
    return {
        "extra": extra,
        "business": business.as_dict(),
        "business_doctype": definition.business_doctype,   # hub can no de goi Duyet & Ky
        "approval": {
            "name": request.name if request else None,
            "approval_status": status,
            "current_level": request.current_level if request else 0,
            "information_requested_from_level": (
                request.information_requested_from_level if request else None),
            "status_label": definition.status_label_map.get(status),
        },
        "levels": levels, "approvers": approvers, "attachments": attachments,
        "fulfillment": fulfillment_block(business, request),
        "timeline": timeline,
        "process_preview": ([] if request else process_preview(
            business.approval_type or definition.code)),
        "capabilities": capabilities.derive(user, business, request),
    }




