"""Generic request commands delegating authoritative transitions to the engine."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.requests import capabilities, query_service


def attach_extra_files(document, urls):
    """Attach the EXTRA files of a multi-file upload to the record.

    Only one file URL fits in the Attach field, so the form uploads the rest and passes their
    URLs in the payload (`_attachments`). Files uploaded before the record existed have no
    attached_to_name, so they would never show up under 'Đính kèm'; this links them (and is a
    no-op for ones already attached). Best-effort: never blocks the save."""
    for url in (urls or []):
        url = (url or "").strip() if isinstance(url, str) else (url or {}).get("url", "")
        if not url.startswith(("/files", "/private/files")):
            continue
        try:
            if frappe.db.exists("File", {"file_url": url, "attached_to_doctype": document.doctype,
                                         "attached_to_name": document.name}):
                continue
            # Tệp nào đang là giá trị của một trường Attach thì gắn kèm attached_to_field,
            # để hook attach_files_to_document của Frappe nhận ra và không tạo bản ghi thứ hai.
            field_for_url = None
            try:
                for df in document.meta.fields:
                    if df.fieldtype in ("Attach", "Attach Image") and (document.get(df.fieldname) or "") == url:
                        field_for_url = df.fieldname
                        break
            except Exception:
                field_for_url = None
            orphan = frappe.db.get_value("File", {"file_url": url,
                                                  "attached_to_name": ["in", ["", None]]}, "name")
            if orphan:
                values = {"attached_to_doctype": document.doctype, "attached_to_name": document.name}
                if field_for_url:
                    values["attached_to_field"] = field_for_url
                frappe.db.set_value("File", orphan, values)
            else:
                frappe.get_doc({"doctype": "File", "file_url": url,
                                "file_name": url.rsplit("/", 1)[-1],
                                "is_private": 1 if url.startswith("/private") else 0,
                                "attached_to_doctype": document.doctype,
                                "attached_to_name": document.name}).insert(ignore_permissions=True)
        except Exception:
            frappe.logger("approval_center").warning(
                "attach_extra_files: could not attach %s to %s" % (url, document.name))


def claim_uploaded_files(document):
    """Stop Frappe creating a SECOND File row for the same upload.

    The forms upload through /api/method/upload_file without a `fieldname`, so the File row
    is stored with attached_to_field empty. Frappe's attach_files_to_document hook (on_update)
    looks for an existing File matching doctype+name+url+FIELD; the empty field never matches,
    so it inserts a duplicate row for the Attach field and the attachment list shows every
    file twice.

    Called right before save: for each Attach field carrying a value, adopt the orphan row
    (same doc + same url, no field yet) by stamping the fieldname on it, so the hook's check
    matches and no duplicate is inserted. Best-effort: never blocks the save."""
    try:
        attach_fields = [df.fieldname for df in document.meta.fields
                         if df.fieldtype in ("Attach", "Attach Image")]
    except Exception:
        return
    for fieldname in attach_fields:
        url = (document.get(fieldname) or "").strip()
        if not url.startswith(("/files", "/private/files")):
            continue
        try:
            if frappe.db.exists("File", {"file_url": url, "attached_to_doctype": document.doctype,
                                         "attached_to_name": document.name,
                                         "attached_to_field": fieldname}):
                continue
            orphan = frappe.db.get_value("File", {"file_url": url,
                                                  "attached_to_doctype": document.doctype,
                                                  "attached_to_name": document.name,
                                                  "attached_to_field": ["in", ["", None]]}, "name")
            if orphan:
                frappe.db.set_value("File", orphan, "attached_to_field", fieldname)
        except Exception:
            frappe.logger("approval_center").warning(
                "claim_uploaded_files: could not adopt file for %s.%s" % (document.doctype, fieldname))


def save_draft(definition, name=None, payload=None):
    user = frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    if name:
        document = frappe.get_doc(definition.business_doctype, name)
        request = capabilities.approval_request_for(definition, name)
        if document.requested_by != user and not capabilities.is_system_manager(user):
            frappe.throw(_("Bạn chỉ có thể sửa yêu cầu của mình."), frappe.PermissionError)
        if request and request.approval_status != "Information Required":
            frappe.throw(_("Chỉ có thể sửa yêu cầu ở trạng thái Nháp hoặc Cần bổ sung."))
    else:
        document = frappe.new_doc(definition.business_doctype)
        document.requested_by = user
    for fieldname in definition.editable_fields:
        if fieldname in data:
            document.set(fieldname, data.get(fieldname))
    context = query_service.employee_context(document.requested_by)
    document.employee = context["employee"]
    document.department = document.department or context["department"]
    document.company = document.company or context["company"]
    if definition.draft_preparer:
        definition.draft_preparer(document)
    if definition.title_builder:
        document.request_title = definition.title_builder(document)
    if document.name:
        claim_uploaded_files(document)   # adopt orphan File rows so the save does not duplicate them
    document.save(ignore_permissions=True)
    attach_extra_files(document, (data or {}).get("_attachments"))
    request = capabilities.approval_request_for(definition, document.name)
    return {"name": document.name,
            "capabilities": capabilities.derive(user, document, request)}


def submit(definition, name):
    previous = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        request_name = definition.submitter(name)
    finally:
        frappe.flags.mute_messages = previous
    frappe.local.message_log = []
    return {"approval_request": request_name, "submitted": True,
            "detail": query_service.detail(definition, name)}


#: Trang thai ma tu do duoc phep tao mot phieu moi. Deu la trang thai DA KET THUC: khong
#: con duong nao di tiep tren phieu cu, nen ban sao khong the tao ra hai ho so cung song.
_CLONEABLE = ("Rejected", "Cancelled")


def clone_request(definition, name):
    """Tao mot yeu cau NHAP moi, chep noi dung + dinh kem tu mot yeu cau da ket thuc.

    Vi sao can: mot phieu bi tu choi la ngo cut vinh vien - `resubmit` chi nhan trang thai
    "Information Required", va giao dien cung noi thang voi cap duyet la "sau khi tu choi,
    yeu cau se ket thuc". Dung nhu the. Nhung hau qua la nguoi de nghi phai go lai tu dau:
    so tien, so tai khoan, ly do, roi tai lai tung tep. Voi mot phieu bi tu choi chi vi sai
    mot con so, do la toan bo cong nhap lieu bi vut di.

    Chuyen nay vua thanh chuyen thuong xuyen: da chot rang muon doi TAI LIEU CAN KY thi cap
    duyet Tu choi chu khong "Yeu cau bo sung" (SCTS khong cho them tep vao tai lieu da tao).
    Nen duong "tu choi -> lam lai" gio la duong chinh, khong con la ngoai le.

    Ban sao la mot phieu NHAP hoan toan doc lap: khong co approval_request, khong co goi ky,
    khong co chu ky nao. Phieu cu giu nguyen - khong sua, khong xoa, vet kiem toan con day.

    CO Y KHONG chay `definition.validator`. Ban sao la mot phieu NHAP, va nhap thi duoc phep
    chua day du - dung nhu khi nguoi dung tu bam "Luu nhap". Chay kiem tra hop le o day se
    lam mot phieu bi tu choi vi thieu truong KHONG TAO LAI DUOC, tuc dung cai be tac ma nut
    nay sinh ra de xoa bo. Kiem tra van chay day du o `Submitter` luc gui - va do la noi
    dung, vi do la luc phieu roi khoi tay nguoi de nghi.
    """
    user = frappe.session.user
    source = frappe.get_doc(definition.business_doctype, name)
    request = capabilities.approval_request_for(definition, name)

    if source.requested_by != user and not capabilities.is_system_manager(user):
        frappe.throw(_("Bạn chỉ có thể tạo lại yêu cầu của chính mình."), frappe.PermissionError)
    status = getattr(request, "approval_status", None) if request else None
    if status not in _CLONEABLE:
        frappe.throw(_("Chỉ tạo được phiếu mới từ yêu cầu đã bị từ chối hoặc đã hủy. "
                       "Yêu cầu này đang ở trạng thái “{0}”.").format(
                           definition.status_label_map.get(status or "", status or "Nháp")))

    document = frappe.new_doc(definition.business_doctype)
    document.requested_by = user
    skip = set(definition.clone_exclude_fields or ())
    for fieldname in definition.editable_fields:
        if fieldname in skip:
            continue
        document.set(fieldname, source.get(fieldname))
    context = query_service.employee_context(user)
    document.employee = context["employee"]
    document.department = document.department or context["department"]
    document.company = document.company or context["company"]
    if definition.draft_preparer:
        definition.draft_preparer(document)
    if definition.title_builder:
        document.request_title = definition.title_builder(document)
    document.insert(ignore_permissions=True)

    copied, failed = _copy_attachments(source, document)
    return {"name": document.name, "attachments_copied": copied,
            "attachments_failed": failed,
            "capabilities": capabilities.derive(user, document, None)}


#: Tep do CHINH HE THONG sinh ra tren phieu cu - khong duoc chep sang phieu moi.
#:
#: `SIGNED-<ten>.pdf`  : ban PDF DA KY tai tu SCTS ve (signed_files._store_signed).
#: `REVIEW-<sha>-<ten>`: ban ung vien khi ma bam lech, giu de doi chieu.
#:
#: Vi sao quan trong: `requester._add_requester_pdf_files` nap MOI PDF private dinh kem vao
#: goi ky voi requires_signature=1. Chep mot ban DA KY sang phieu moi nghia la phieu moi doi
#: nguoi ta dat o ky len mot tai lieu da co chu ky so cua phieu truoc - hoac preflight chan
#: (khong gui duoc), hoac day sang SCTS mot bo ho so sai. Gia dinh cua ham nap la "PDF private
#: dinh kem = tai lieu nguoi de nghi chuan bi", va gia dinh do chi dung khi khong ai chep
#: hang loat File vao phieu.
_SYSTEM_FILE_PREFIXES = ("SIGNED-", "REVIEW-")


def _is_system_artefact(file_name):
    return str(file_name or "").startswith(_SYSTEM_FILE_PREFIXES)


def _copy_attachments(source, target):
    """Gan cac tep cua phieu cu sang phieu moi. Tra ve (so tep chep duoc, danh sach loi).

    Dung chung mot tep vat ly (cung `file_url`) - khong nhan doi du lieu tren dia.

    KHONG nuot loi. `attach_extra_files` ghi loi bang `logger().warning`, thu khong hien
    tren giao dien, nen mot tep khong gan duoc se bien mat trong im lang va nguoi dung tuong
    ho so da day du. O day tra danh sach ve cho man hinh noi ra.
    """
    rows = frappe.get_all("File",
                          filters={"attached_to_doctype": source.doctype,
                                   "attached_to_name": source.name},
                          fields=["file_url", "file_name", "is_private"],
                          limit_page_length=0)
    rows = [r for r in rows if not _is_system_artefact(r.get("file_name"))]
    seen, copied, failed = set(), 0, []
    for r in rows:
        url = (r.get("file_url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        try:
            frappe.get_doc({"doctype": "File", "file_url": url,
                            "file_name": r.get("file_name") or url.rsplit("/", 1)[-1],
                            "is_private": r.get("is_private") or 0,
                            "attached_to_doctype": target.doctype,
                            "attached_to_name": target.name}).insert(ignore_permissions=True)
            copied += 1
        except Exception:
            failed.append(r.get("file_name") or url)
    return copied, failed


def resolve_request(definition, name):
    document = frappe.get_doc(definition.business_doctype, name)
    if not document.approval_request:
        frappe.throw(_("Yêu cầu này chưa được gửi."))
    return document, document.approval_request


def approve(definition, name, comment=None):
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    _, request_name = resolve_request(definition, name)
    engine.approve(request_name, comment=comment)
    return {"detail": query_service.detail(definition, name)}


def approve_with_operation_date(definition, name, comment=None,
                                operation_expected_completion_date=None):
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    _, request_name = resolve_request(definition, name)
    current_level = frappe.db.get_value("EC Approval Request", request_name, "current_level")
    level_name = (frappe.db.get_value(
        "EC Approval Request Level",
        {"approval_request": request_name, "level_no": current_level}, "level_name")
        if current_level else None)
    if level_name == "Operation Review":
        new_value = operation_expected_completion_date or ""
        new_value = new_value.strip() if isinstance(new_value, str) else new_value
        existing = frappe.db.get_value(
            definition.business_doctype, name, "operation_expected_completion_date")
        if not existing and not new_value:
            frappe.throw(_("Vui long nhap ngay du kien hoan thanh (Operation) truoc khi duyet."))
        if new_value:
            frappe.db.set_value(
                definition.business_doctype, name,
                "operation_expected_completion_date", new_value)
    engine.approve(request_name, comment=comment)
    return {"detail": query_service.detail(definition, name)}


def reject(definition, name, comment=None):
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    _, request_name = resolve_request(definition, name)
    engine.reject(request_name, comment=comment)
    return {"detail": query_service.detail(definition, name)}


def request_information(definition, name, comment=None):
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    _, request_name = resolve_request(definition, name)
    engine.request_information(request_name, comment=comment)
    return {"detail": query_service.detail(definition, name)}


def resubmit(definition, name, payload=None):
    # Chot quyen o CUA VAO, giong cancel(). `can_resubmit` da co san trong capabilities tu
    # lau nhung facade khong he goi - nen chi co may trang thai o tang duoi chan, con "ai
    # duoc gui lai" thi khong ai hoi (BOT 8, 01/09). Kiem TRUOC save_draft: sai nguoi thi
    # khong duoc ghi de ban nhap cua nguoi khac.
    user = frappe.session.user
    document = frappe.get_doc(definition.business_doctype, name)
    request = capabilities.approval_request_for(definition, name)
    if not capabilities.derive(user, document, request)["can_resubmit"]:
        frappe.throw(_("Bạn không được phép gửi lại yêu cầu này."), frappe.PermissionError)
    if payload:
        save_draft(definition, name=name, payload=payload)
    result = definition.resubmitter(name, frappe.session.user) or {}
    return {"restarted": bool(result.get("restarted")),
            # Lop ky so co the da tao phien ban moi cho goi ky va bat duyet lai tu cap 1.
            # Khong truyen ra thi giao dien khong the giai thich vi sao.
            "esign": result.get("esign") or {},
            "detail": query_service.detail(definition, name)}


def cancel(definition, name, reason=None):
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    user = frappe.session.user
    document = frappe.get_doc(definition.business_doctype, name)
    request = capabilities.approval_request_for(definition, name)
    if not capabilities.derive(user, document, request)["can_cancel"]:
        frappe.throw(_("Bạn không được phép hủy yêu cầu này."), frappe.PermissionError)
    if request:
        engine.cancel(request.name, reason=reason)
        return {"detail": query_service.detail(definition, name)}
    # Ban nhap chua gui = xoa. Goi ky nhap (neu da "Thiet lap chu ky") tro vao phieu nen
    # phai don truoc, khong thi Frappe chan "linked with EC Digital Signature Package"
    # (05/09, 00043). Goi da khoa/da sang nha cung cap thi hook tu choi - fail-closed.
    _esign_on_draft_discarded(definition.business_doctype, name)
    frappe.delete_doc(definition.business_doctype, name, ignore_permissions=True)
    return {"deleted": True}


def _esign_on_draft_discarded(business_doctype, name):
    """Loi goi xuyen module da khai bao vao platform.esign (cung kieu transitions._esign_on_reopen).
    Chi dung thu khi THIEU module; loi that phai noi len - xoa phieu ma de goi ky mo coi thi
    la dung thu sai."""
    try:
        from ecentric_workspace.platform.esign import lifecycle as esign_lifecycle
    except ImportError:
        return {"discarded": []}
    return esign_lifecycle.on_draft_discarded(business_doctype, name)


def admin_approve_current_level(definition, name, reason=None):
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    if not capabilities.is_system_manager():
        frappe.throw(_("Chỉ System Manager mới được duyệt thay."), frappe.PermissionError)
    if not (reason or "").strip():
        frappe.throw(_("Vui lòng nhập lý do duyệt thay."))
    document, request_name = resolve_request(definition, name)
    request = capabilities.approval_request_for(definition, name)
    if not capabilities.derive(
            frappe.session.user, document, request)["can_admin_approve_current_level"]:
        frappe.throw(_("Không thể duyệt thay ở trạng thái hiện tại."))
    previous = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        engine.admin_override_current_level(
            request_name, actor=frappe.session.user, reason=reason)
    finally:
        frappe.flags.mute_messages = previous
    frappe.local.message_log = []
    return {"admin_approved": True, "detail": query_service.detail(definition, name)}




