# =============================================================================
# eCentric Workspace API - Frappe Server Scripts (Python)
# =============================================================================
# Replaces 11 Power Automate flows. All approval workflow logic native in Frappe.
#
# DEPLOY OPTIONS:
#
# Option A: Frappe App Code (Recommended for production)
#   - Copy this file to: apps/ecentric_workspace/ecentric_workspace/api.py
#   - Restart bench
#   - Methods callable: /api/method/ecentric_workspace.api.submit_mso
#
# Option B: Server Scripts via UI (works on FC trial / shared bench)
#   - For each @frappe.whitelist() function below, create one Server Script:
#     /app/server-script/new
#     Script Type: API
#     API Method: <function_name> (e.g. submit_mso)
#     Allow Guest: 0
#     Paste function body
#   - Methods callable: /api/method/<function_name>
#
# AUTH:
#   - Web Page form (user logged in): use session cookie + CSRF token
#   - External (PA, Postman): use API key:secret in Authorization header
# =============================================================================

import frappe
from frappe import _
from frappe.utils import nowdate, getdate, today, now_datetime, add_days

# =============================================================================
# Constants
# =============================================================================

DEPT_CODE_MAP = {
    "E-commerce Operation": "ECO",
    "Merchandise, Content & Design": "MCD",
    "Service": "SVC",
    "Media": "MED",
    "Production": "PRD",
    # Current Frappe Department naming (Style A canonical, per 2026-05-29)
    "Operation & Data & System": "ODS",
    "Human Resources": "HRD",
    "Finance & Accounting": "FNA",
    # Back-compat: existing records may have legacy values
    "Operation, Data & System": "ODS",
    "HR": "HRD",
    # Used by Weekly Report only, not approval forms (per user 2026-05-29)
    "Management": "MGT",
}

APPROVAL_RECIPES = {
    "MSO Standard (4 levels)": ["manager", "leader", "finance", "ceo"],
    "SO In-Budget (1 level)":  ["finance"],
    "SO Out-of-Budget (4 levels)": ["manager", "leader", "finance", "ceo"],
    "PO In-Budget (2 levels)": ["manager", "finance"],
    "PO Out-of-Budget (4 levels)": ["manager", "leader", "finance", "ceo"],
    "REC Standard (2 levels)": ["manager", "finance"],
    "Vendor Request (HOF + CEO)": ["hof", "ceo"],
}


# =============================================================================
# SUBMIT ENDPOINTS - Create transactional records
# =============================================================================

@frappe.whitelist()
def submit_mso(department, campaign_no, pic, exp_ecommerce, exp_merch,
               exp_media, exp_production, exp_service, total_est_revenue,
               department_code=None, attachment_url=None):
    """Create MSO Request + build approval chain + notify L1.

    Returns: {success, mso_id, chain_first_approver}
    """
    _require_logged_in()
    _validate_required({
        "department": department,
        "campaign_no": campaign_no,
        "pic": pic,
    })

    mso = frappe.get_doc({
        "doctype": "MSO Request",
        "department": department,
        "department_code": department_code or DEPT_CODE_MAP.get(department, "GEN"),
        "campaign_no": campaign_no,
        "submitted_by": frappe.session.user,
        "pic": pic,
        "exp_ecommerce": _to_num(exp_ecommerce),
        "exp_merch": _to_num(exp_merch),
        "exp_media": _to_num(exp_media),
        "exp_production": _to_num(exp_production),
        "exp_service": _to_num(exp_service),
        "total_est_revenue": _to_num(total_est_revenue),
        "attachment_url": attachment_url or "",
        "status": "Pending",
    })
    mso.insert(ignore_permissions=False)

    # MSO uses "MSO Standard" recipe (no brand_code, use default approvers)
    chain = _build_chain_for_doc(mso, recipe_name="MSO Standard (4 levels)")
    mso.approval_chain = frappe.as_json(chain)
    mso.current_level = 1
    mso.save(ignore_permissions=False)

    if chain:
        _notify_approver(chain[0]["approver"], mso)

    return {
        "success": True,
        "mso_id": mso.name,
        "chain_first_approver": chain[0]["approver"] if chain else None,
    }


@frappe.whitelist()
def submit_so(title, department, service_name, total_est_revenue, total_est_expense,
              department_code=None, service_type=None, description=None,
              client_name=None, platform=None, brand_code=None, pic=None,
              in_out_budget=None, master_service_ref=None, attachment_url=None):
    """Create Service Request (SO) + build chain.

    Recipe selection based on in_out_budget.
    """
    _require_logged_in()
    _validate_required({
        "title": title,
        "department": department,
        "total_est_revenue": total_est_revenue,
        "total_est_expense": total_est_expense,
    })

    # Validate parent MSO if provided
    if master_service_ref and not frappe.db.exists("MSO Request", master_service_ref):
        frappe.throw(_("Parent MSO not found: {0}").format(master_service_ref))

    so = frappe.get_doc({
        "doctype": "Service Request",
        "title": title,
        "department": department,
        "department_code": department_code or DEPT_CODE_MAP.get(department, "GEN"),
        "service_name": service_name,
        "service_type": service_type,
        "description": description,
        "client_name": client_name,
        "platform": platform,
        "brand_code": brand_code,
        "pic": pic or frappe.session.user,
        "created_by_user": frappe.session.user,
        "total_est_revenue": _to_num(total_est_revenue),
        "total_est_expense": _to_num(total_est_expense),
        "in_out_budget": in_out_budget,
        "master_service_ref": master_service_ref,
        "attachment_url": attachment_url or "",
        "status": "Pending",
    })
    so.insert(ignore_permissions=False)

    recipe = "SO In-Budget (1 level)" if in_out_budget == "In Budget" else "SO Out-of-Budget (4 levels)"
    chain = _build_chain_for_doc(so, recipe_name=recipe)
    so.approval_chain = frappe.as_json(chain)
    so.current_level = 1
    so.save(ignore_permissions=False)

    if chain:
        _notify_approver(chain[0]["approver"], so)

    return {"success": True, "so_id": so.name}


@frappe.whitelist()
def create_so_from_form():
    """Tao native Sales Order (che do "Brand truc tiep" cua /gbs-so-form-v2) SERVER-SIDE.

    Truoc day form POST thang /api/resource/Sales Order tu trinh duyet, chay DUOI
    QUYEN cua KAM -> controller ERPNext (get_item_details) kiem quyen doc Item /
    Price List theo KAM -> KAM (chi Customer / Employee / PM Member) bi chan:
    "does not have doctype access ... for document Item". Tao server-side voi
    frappe.flags.ignore_permissions (co THAT trong app code) -> controller bo qua
    kiem quyen noi bo. KAM khong can bat ky quyen doctype nao.

    !!! DEPLOY: BAT BUOC deploy dang APP CODE (Option A o dau file). KHONG chay
    duoc duoi dang Server Script: safe_exec sandbox hoa frappe.flags (chi la ban
    sao rong) nen bypass khong an -- day chinh la ly do phai chuyen sang app code.

    Bao mat: chan Guest; WHITELIST tung field (khong nhan raw doc); ep
    company='eCentric'; owner = session user; submit chi den Pending Manager, con
    lai 4 cap duyet EC SO Approval giu nguyen. Guard ngan sach/nguoi duyet trong
    Server Script Before Save `ec_so_before_save` van chay o buoc save.
    """
    _require_logged_in()
    data = _read_json_body()

    customer = data.get("customer")
    transaction_date = data.get("transaction_date")
    delivery_date = data.get("delivery_date")
    items = data.get("items") or []
    _validate_required({
        "customer": customer,
        "transaction_date": transaction_date,
        "delivery_date": delivery_date,
    })
    if not isinstance(items, list) or not items:
        frappe.throw(_("SO can it nhat 1 dong item."))

    so = frappe.new_doc("Sales Order")
    so.company = "eCentric"                     # ep cung, khong lay tu client
    so.order_type = data.get("order_type") or "Sales"
    so.customer = customer
    so.transaction_date = transaction_date
    so.delivery_date = delivery_date

    for fname in ("ec_channel", "ec_brand", "ec_team", "ec_mso_month", "ec_store",
                  "ec_vat_template", "ec_attach_session", "ec_gbs_so_ref",
                  "ec_gbs_sync_status", "ec_contract", "ec_over_justification"):
        val = data.get(fname)
        if val not in (None, ""):
            so.set(fname, val)
    if data.get("ec_external_service"):
        so.ec_external_service = 1
    if data.get("title"):
        so.title = data.get("title")

    for it in items:
        so.append("items", {
            "item_code": it.get("item_code") or "",
            "qty": _to_num(it.get("qty")),
            "rate": _to_num(it.get("rate")),
            "delivery_date": it.get("delivery_date") or delivery_date,
        })

    for tx in (data.get("taxes") or []):
        if isinstance(tx, dict):
            so.append("taxes", {
                "charge_type": tx.get("charge_type") or "On Net Total",
                "account_head": tx.get("account_head") or "VAT - EC",
                "rate": _to_num(tx.get("rate")),
                "description": tx.get("description") or "VAT",
            })

    user = frappe.session.user
    # owner PHAI set TRUOC insert: Frappe chi gan owner = session user khi owner con
    # trong (set_user_and_timestamp: `if not self.owner`). Dat truoc de
    # ec_so_before_save resolve nguoi duyet cap 1 tu Employee.reports_to cua KAM,
    # chu khong phai cua Administrator.
    so.owner = user

    # TAI SAO PHAI set_user thay vi frappe.flags.ignore_permissions:
    # controller ERPNext (get_item_details) lay doc Item roi goi check_permission ->
    # Document.has_permission() chi doc `self.flags.ignore_permissions` CUA CHINH doc
    # Item do, roi rot xuong frappe.has_permission() -- ham nay CHI nhin
    # frappe.session.user, KHONG doc frappe.flags.ignore_permissions. Vi vay
    # so.flags/insert(ignore_permissions=True) (chi tac dung len doc Sales Order) va
    # frappe.flags.ignore_permissions deu KHONG cuu duoc -> da kiem chung live bang
    # API key tam cua hoang.le: van "does not have doctype access ... for Item".
    # frappe.has_permission tra True ngay lap tuc khi user == "Administrator", nen
    # doi session trong dung pham vi ghi la cach duy nhat chac chan.
    #
    # !!! frappe.set_user() PHA SESSION cua nguoi dang dang nhap -- phai chup lai
    # va tra ve nguyen trang. Frappe set_user() lam:
    #     frappe.local.session.sid  = username
    #     frappe.local.session.data = frappe._dict()      # <-- WIPE
    #     frappe.local.form_dict    = frappe._dict()
    # Cuoi request, Session.update() ghi `str(self.data["data"])` xuong tabSessions
    # theo self.sid THAT -> sessiondata cua phien dang dung bi ghi de bang rong.
    # Request ke tiep resume session khong con thong tin user -> tut ve Guest, moi
    # @frappe.whitelist() tra 403 PermissionError. Da gap live: hoang.le submit xong,
    # trang /approval bao "HTTP 403 PermissionError" va shell hien "Tai khoan" thay
    # vi ten -- tuc la da bi dang xuat, KHONG phai thieu quyen xem phieu.
    original_user = frappe.session.user
    _sess = frappe.local.session
    _saved_sid = _sess.get("sid")
    _saved_data = _sess.get("data")
    _saved_form_dict = frappe.local.form_dict
    frappe.set_user("Administrator")
    try:
        so.insert(ignore_permissions=True)
        # BAT BUOC ghi lai owner SAU insert: Frappe set_user_and_timestamp() chay
        # truoc before_save va ghi de owner khi doc con moi --
        #   if self.is_new() and not (self.creation and self.owner):
        #       self.creation = self.modified; self.owner = self.modified_by
        # `creation` luon trong o doc moi nen dieu kien luon dung -> so.owner dat
        # truoc insert BI GHI DE thanh Administrator (da gap live: phieu ra
        # owner=Administrator, cap 1 resolve theo Administrator nen dinh tuyen nham
        # sang HOF thay vi quan ly truc tiep cua KAM).
        frappe.db.set_value("Sales Order", so.name, "owner", user, update_modified=False)
        # reload de before_save cua buoc submit doc duoc owner = KAM -> resolve dung
        # nguoi duyet cap 1 tu Employee.reports_to cua KAM.
        so.reload()
        so.workflow_state = "Pending Manager"
        so.save(ignore_permissions=True)
    finally:
        frappe.set_user(original_user)
        # tra lai nguyen trang session/form_dict ma set_user da xoa
        _sess.sid = _saved_sid
        _sess.data = _saved_data
        frappe.local.form_dict = _saved_form_dict

    # Nhat ky duyet do ec_so_before_save ghi bang frappe.session.user, luc do dang la
    # Administrator -> tra lai dung ten nguoi gui cho dong "Draft -> Pending ...".
    _fix_submit_log_actor(so.name, user)

    return {"success": True, "name": so.name,
            "workflow_state": so.workflow_state,
            "ec_in_out_budget": so.get("ec_in_out_budget") or ""}


@frappe.whitelist()
def submit_po(title, service_request_id, department, requestor,
              estimated_exp_vat_in, estimated_exp_vat_ex,
              department_code=None, vendor_name=None, procurement_code=None,
              brand_code=None, description=None, estimated_revenue=None,
              vat_mixed=0, contract_option=None, start_date=None, end_date=None,
              payment_recognition=None, needs_paid_directly=0, prepaid_amount=None,
              in_out_budget=None, attachment_url=None):
    """Create Procurement Request (PO) + build chain."""
    _require_logged_in()
    _validate_required({
        "title": title,
        "service_request_id": service_request_id,
        "department": department,
        "requestor": requestor,
        "estimated_exp_vat_in": estimated_exp_vat_in,
        "estimated_exp_vat_ex": estimated_exp_vat_ex,
    })

    if not frappe.db.exists("Service Request", service_request_id):
        frappe.throw(_("Parent SO not found: {0}").format(service_request_id))

    po = frappe.get_doc({
        "doctype": "Procurement Request",
        "title": title,
        "service_request_id": service_request_id,
        "department": department,
        "department_code": department_code or DEPT_CODE_MAP.get(department, "GEN"),
        "requestor": requestor,
        "vendor_name": vendor_name,
        "procurement_code": procurement_code,
        "brand_code": brand_code,
        "description": description,
        "estimated_revenue": _to_num(estimated_revenue or 0),
        "estimated_exp_vat_in": _to_num(estimated_exp_vat_in),
        "estimated_exp_vat_ex": _to_num(estimated_exp_vat_ex),
        "vat_mixed": int(vat_mixed) if vat_mixed else 0,
        "contract_option": contract_option,
        "start_date": start_date,
        "end_date": end_date,
        "payment_recognition": payment_recognition,
        "needs_paid_directly": int(needs_paid_directly) if needs_paid_directly else 0,
        "prepaid_amount": _to_num(prepaid_amount or 0),
        "in_out_budget": in_out_budget,
        "attachment_url": attachment_url or "",
        "status": "Pending",
    })
    po.insert(ignore_permissions=False)

    recipe = "PO In-Budget (2 levels)" if in_out_budget == "In Budget" else "PO Out-of-Budget (4 levels)"
    chain = _build_chain_for_doc(po, recipe_name=recipe)
    po.approval_chain = frappe.as_json(chain)
    po.current_level = 1
    po.save(ignore_permissions=False)

    if chain:
        _notify_approver(chain[0]["approver"], po)

    return {"success": True, "po_id": po.name}


@frappe.whitelist()
def submit_rec(title, procurement_request_id, department, requestor,
               actual_exp_vat_in, actual_exp_vat_ex,
               department_code=None, client_name=None, vat_mixed=0,
               invoice_no=None, contract_no=None, attachment_url=None):
    """Create Reconciliation Request (REC) + auto-compute chenh_lech + build chain."""
    _require_logged_in()
    _validate_required({
        "title": title,
        "procurement_request_id": procurement_request_id,
        "department": department,
        "requestor": requestor,
        "actual_exp_vat_in": actual_exp_vat_in,
        "actual_exp_vat_ex": actual_exp_vat_ex,
    })

    parent_po = frappe.db.get_value(
        "Procurement Request",
        procurement_request_id,
        ["name", "estimated_exp_vat_in"],
        as_dict=True
    )
    if not parent_po:
        frappe.throw(_("Parent PO not found: {0}").format(procurement_request_id))

    chenh_lech = _to_num(actual_exp_vat_in) - _to_num(parent_po.estimated_exp_vat_in or 0)

    rec = frappe.get_doc({
        "doctype": "Reconciliation Request",
        "title": title,
        "procurement_request_id": procurement_request_id,
        "department": department,
        "department_code": department_code or DEPT_CODE_MAP.get(department, "GEN"),
        "requestor": requestor,
        "submitted_by": frappe.session.user,
        "client_name": client_name,
        "actual_exp_vat_in": _to_num(actual_exp_vat_in),
        "actual_exp_vat_ex": _to_num(actual_exp_vat_ex),
        "vat_mixed": int(vat_mixed) if vat_mixed else 0,
        "invoice_no": invoice_no,
        "contract_no": contract_no,
        "chenh_lech": chenh_lech,
        "attachment_url": attachment_url or "",
        "status": "Pending",
    })
    rec.insert(ignore_permissions=False)

    chain = _build_chain_for_doc(rec, recipe_name="REC Standard (2 levels)")
    rec.approval_chain = frappe.as_json(chain)
    rec.current_level = 1
    rec.save(ignore_permissions=False)

    if chain:
        _notify_approver(chain[0]["approver"], rec)

    return {"success": True, "rec_id": rec.name, "chenh_lech": chenh_lech}


@frappe.whitelist()
def submit_vendor_request(proposed_vendor_name, department, requested_by, purpose,
                          tax_code=None, proposed_vendor_code=None,
                          contact_person=None, contact_email=None, contact_phone=None,
                          address=None, payment_terms_proposed=None,
                          estimated_annual_spend=None, attachment_url=None):
    """Create Vendor Code Request + chain (HOF + CEO)."""
    _require_logged_in()
    _validate_required({
        "proposed_vendor_name": proposed_vendor_name,
        "department": department,
        "requested_by": requested_by,
        "purpose": purpose,
    })

    vrq = frappe.get_doc({
        "doctype": "Vendor Code Request",
        "proposed_vendor_name": proposed_vendor_name,
        "proposed_vendor_code": proposed_vendor_code,
        "tax_code": tax_code,
        "department": department,
        "requested_by": requested_by,
        "contact_person": contact_person,
        "contact_email": contact_email,
        "contact_phone": contact_phone,
        "address": address,
        "payment_terms_proposed": payment_terms_proposed,
        "purpose": purpose,
        "estimated_annual_spend": _to_num(estimated_annual_spend or 0),
        "final_status": "Pending",
    })
    vrq.insert(ignore_permissions=False)

    chain = _build_chain_for_doc(vrq, recipe_name="Vendor Request (HOF + CEO)")
    vrq.approval_chain = frappe.as_json(chain)
    vrq.current_level = 1
    vrq.save(ignore_permissions=False)

    if chain:
        _notify_approver(chain[0]["approver"], vrq)

    return {"success": True, "vrq_id": vrq.name}


# =============================================================================
# APPROVAL DECISION - Approve / Reject
# =============================================================================

@frappe.whitelist()
def approval_decision(doctype, name, decision, comment=None):
    """Process approval/rejection by current_level approver.

    decision: 'approved' or 'rejected'
    """
    _require_logged_in()
    if decision not in ("approved", "rejected"):
        frappe.throw(_("Invalid decision: must be 'approved' or 'rejected'"))

    doc = frappe.get_doc(doctype, name)

    chain = frappe.parse_json(doc.approval_chain or "[]")
    if not chain:
        frappe.throw(_("No approval chain configured"))

    current_idx = (doc.current_level or 1) - 1
    if current_idx >= len(chain):
        frappe.throw(_("Chain already complete"))

    current_step = chain[current_idx]
    user = frappe.session.user
    if current_step.get("approver") != user:
        frappe.throw(_("You are not authorized to approve this step. Expected: {0}").format(
            current_step.get("approver")))

    # Update chain step
    current_step["status"] = decision.title()
    current_step["action_date"] = str(now_datetime())
    current_step["comment"] = comment or ""

    # Append history
    history = frappe.parse_json(doc.approval_history or "[]")
    history.append({
        "level": doc.current_level,
        "approver": user,
        "decision": decision,
        "comment": comment or "",
        "timestamp": str(now_datetime()),
    })
    doc.approval_history = frappe.as_json(history)

    # Determine next state
    if decision == "rejected":
        # Reject final
        status_field = "final_status" if doctype == "Vendor Code Request" else "status"
        doc.set(status_field, "Rejected")
        doc.approval_chain = frappe.as_json(chain)
        doc.save(ignore_permissions=False)
        _notify_submitter(doc, "Rejected", comment)
        return {"success": True, "status": "Rejected"}

    # decision == approved
    if doc.current_level >= len(chain):
        # Final approval
        status_field = "final_status" if doctype == "Vendor Code Request" else "status"
        doc.set(status_field, "Approved")
        doc.approval_chain = frappe.as_json(chain)
        doc.save(ignore_permissions=False)

        # Side effect: create Supplier from Vendor Request
        if doctype == "Vendor Code Request":
            supplier_name = _create_supplier_from_vrq(doc)
            frappe.db.set_value(doctype, name, "created_vendor_id", supplier_name)

        _notify_submitter(doc, "Approved", comment)
        return {"success": True, "status": "Approved"}

    # Move to next level
    doc.current_level = doc.current_level + 1
    doc.approval_chain = frappe.as_json(chain)
    doc.save(ignore_permissions=False)

    next_approver = chain[doc.current_level - 1].get("approver")
    if next_approver:
        _notify_approver(next_approver, doc)

    return {"success": True, "status": "Pending", "current_level": doc.current_level}


# =============================================================================
# BUDGET QUERIES
# =============================================================================

@frappe.whitelist()
def get_mso_budget(mso_id):
    """Return total/used/remaining budget for MSO."""
    mso = frappe.get_doc("MSO Request", mso_id)
    total = sum(_to_num(mso.get(f) or 0) for f in [
        "exp_ecommerce", "exp_merch", "exp_media", "exp_production", "exp_service"
    ])

    used = frappe.db.sql("""
        SELECT COALESCE(SUM(total_est_expense), 0)
        FROM `tabService Request`
        WHERE master_service_ref = %s AND status = 'Approved'
    """, mso_id)[0][0]
    used = _to_num(used)

    remaining = total - used
    return {
        "mso_id": mso_id,
        "total_budget": total,
        "used_budget": used,
        "remaining": remaining,
        "in_budget": remaining > 0,
    }


@frappe.whitelist()
def get_so_budget(so_id):
    """Return total/used/remaining budget for SO."""
    so_total = frappe.db.get_value("Service Request", so_id, "total_est_expense")
    if so_total is None:
        frappe.throw(_("SO not found: {0}").format(so_id))
    total = _to_num(so_total)

    used = frappe.db.sql("""
        SELECT COALESCE(SUM(estimated_exp_vat_ex), 0)
        FROM `tabProcurement Request`
        WHERE service_request_id = %s AND status = 'Approved'
    """, so_id)[0][0]
    used = _to_num(used)

    remaining = total - used
    return {
        "so_id": so_id,
        "total_budget": total,
        "used_budget": used,
        "remaining": remaining,
        "in_budget": remaining > 0,
    }


# =============================================================================
# LOOKUP - Get parent record by type+id
# =============================================================================

TYPE_DOCTYPE_MAP = {
    "mso": "MSO Request",
    "so": "Service Request",
    "po": "Procurement Request",
    "rec": "Reconciliation Request",
    "brand": "Brand",
    "client": "Customer",
    "service_type": "Item",
    "vendor": "Supplier",
    "vendor_request": "Vendor Code Request",
}


@frappe.whitelist()
def lookup_parents(type, id):
    """Return basic record info by type+id. Returns 404 if not found."""
    dt = TYPE_DOCTYPE_MAP.get(type)
    if not dt:
        frappe.throw(_("Unknown type: {0}").format(type))

    if not frappe.db.exists(dt, id):
        frappe.local.response.http_status_code = 404
        return {"success": False, "error": "Not found"}

    doc = frappe.get_doc(dt, id)
    return {"success": True, "data": doc.as_dict()}


@frappe.whitelist()
def get_ticket_detail(type, id):
    """Same as lookup_parents but always returns full detail (alias)."""
    return lookup_parents(type, id)


# =============================================================================
# HELPERS - Internal (not whitelisted)
# =============================================================================

def _require_logged_in():
    if frappe.session.user == "Guest":
        frappe.throw(_("Login required"), frappe.PermissionError)


def _validate_required(fields):
    missing = [k for k, v in fields.items() if v in (None, "", 0) and not (isinstance(v, (int, float)) and v == 0)]
    # Special: 0 valid for numbers
    missing = [k for k, v in fields.items() if v is None or v == ""]
    if missing:
        frappe.throw(_("Missing required fields: {0}").format(", ".join(missing)))


def _to_num(v):
    try:
        return float(v) if v not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


#: Doctype native chay qua workflow duyet cua eCentric (dung cho apply_native_workflow).
NATIVE_APPROVAL_DOCTYPES = ("Sales Order", "Purchase Order", "MSO")

#: CHI cac trang thai duoi day moi nang quyen, vi khong role native nao dien ta
#: duoc nguoi hop le:
#:   - Draft / Rejected : nguoi TAO chung tu (KAM) -- theo thiet ke KAM khong co
#:     quyen doctype nao het, nen khong the cap role.
#:   - Pending Manager  : "quan ly truc tiep cua chinh nguoi tao" la quan he DONG
#:     (Employee.reports_to), khong phai mot role co dinh.
#: Cac cap con lai (Finance / HOF / CEO / Sales Admin) UNG voi role native that ->
#: chay thang workflow native duoi quyen nguoi duyet, giu nguyen guard trong
#: Before Save. KHONG nang quyen o do (tranh nhan doi logic bao mat).
ELEVATED_STATES = {
    "Draft": {"owner": True},
    "Rejected": {"owner": True},
    "Pending Manager": {"field": "ec_manager_email"},
    # Pending CEO la buoc SUBMIT (doc_status=1), khong phai save. Submit kich hoat
    # chuoi validate cua ERPNext -> doc sang Customer roi Item. Da kiem chung live
    # 2026-08-24 voi lam.nguyen (chi co role EC CEO): cap read Customer xong thi
    # chan tiep o Item. Item la STANDARD-perm -- them Custom DocPerm vao Item se
    # xoa sach phan quyen chuan cua Item cho CA CONG TY, tuyet doi khong lam.
    # Vi vay buoc nay nang quyen, guard bang dung role EC CEO (trung voi role cua
    # transition "Pending CEO -> Approved" trong workflow EC SO Approval).
    "Pending CEO": {"role": "EC CEO"},
}

# GHI CHU (2026-08-24): cap Finance (L2) va HOF (L3) van chay NATIVE va dang chay
# duoc -- nhung la nho MOI nguoi duyet hien tai (van.bui, thu.trinh, dan.ha,
# phuong.nguyen1) deu dang co san role `Sales User` (kem read Customer/Item).
# Neu sau nay co nguoi duyet chi duoc gan EC Finance / EC HOF ma khong co
# Sales User, ho se bi chan y het CEO -> luc do them state tuong ung vao
# ELEVATED_STATES (kem guard role) thay vi cap quyen doc danh muc.


def _assert_can_act(doc, user):
    """Chan truoc khi nang quyen. Nem PermissionError neu user khong phai nguoi
    duoc phep thao tac o trang thai hien tai cua chung tu."""
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return
    state = (doc.get("workflow_state") or "").strip()
    rule = ELEVATED_STATES.get(state)
    if not rule:
        frappe.throw(_("Trang thai '{0}' khong duoc nang quyen.").format(state),
                     frappe.PermissionError)
    if rule.get("owner"):
        if user != (doc.owner or ""):
            frappe.throw(_("Chi nguoi tao chung tu moi thao tac duoc o buoc nay."),
                         frappe.PermissionError)
        return
    if rule.get("field"):
        expected = (doc.get(rule["field"]) or "").strip()
        if user != expected:
            frappe.throw(_("Buoc duyet nay danh cho {0}. Ban ({1}) khong phai nguoi duyet cap nay.")
                         .format(expected or "(chua xac dinh)", user), frappe.PermissionError)
        return
    role = rule.get("role")
    if role and role not in frappe.get_roles(user):
        frappe.throw(_("Buoc duyet nay can Role '{0}'. Ban ({1}) chua co.").format(role, user),
                     frappe.PermissionError)


@frappe.whitelist()
def apply_native_workflow(doctype, name, action):
    """Chuyen trang thai workflow cho chung tu native, SERVER-SIDE.

    Ly do: trang /approval goi apply_workflow duoi quyen NGUOI DUYET. Nguoi duyet
    cap 1 (quan ly truc tiep) va CEO khong co role nao cho phep doc/ghi Sales Order
    -> frappe.model.workflow.get_transitions() goi has_permission(read, throw=True)
    va chan ngay -> Server Script approval_decision_override tra "workflow_error"
    voi detail rong. Da kiem chung live: thai.cao (L1) va lam.nguyen (CEO) deu bi.

    An toan: _assert_can_act() kiem DUNG nguoi duyet cua trang thai hien tai TRUOC
    khi doi session, vi guard trong Before Save bi bo qua khi chay duoi Administrator.
    Session duoc chup va tra nguyen trang (xem ghi chu o create_so_from_form).
    """
    _require_logged_in()
    if doctype not in NATIVE_APPROVAL_DOCTYPES:
        frappe.throw(_("Doctype khong duoc phep: {0}").format(doctype), frappe.PermissionError)

    user = frappe.session.user
    doc = frappe.get_doc(doctype, name)
    prev_state = (doc.get("workflow_state") or "").strip()

    # Kiem chung live 2026-08-24: transition "Pending Manager -> Approve" de allowed=All,
    # NHUNG ec_so_before_save van chan dung nguoi (thu bang phuong.nguyen1 -- co quyen
    # ghi SO nhung khong phai sep cua nguoi tao -> bi chan dung thong bao "Buoc duyet
    # nay danh cho quan ly truc tiep (thai.cao@...)"). Vay allowed=All KHONG phai lo
    # hong, va KHONG duoc siet transition ve mot role: cac quan ly truc tiep khong
    # chung role nao ca, siet la gay cap 1.
    if prev_state not in ELEVATED_STATES:
        # Cap Finance / HOF / CEO / Sales Admin: chay NATIVE duoi quyen nguoi duyet.
        # Workflow tu kiem role cua transition, va guard trong Before Save chay nguyen
        # ven (khong bi bo qua vi session KHONG phai Administrator).
        from frappe.model.workflow import apply_workflow
        apply_workflow(doc, action)
        return {"success": True,
                "workflow_state": frappe.db.get_value(doctype, name, "workflow_state") or "",
                "docstatus": frappe.db.get_value(doctype, name, "docstatus")}

    _assert_can_act(doc, user)

    original_user = user
    _sess = frappe.local.session
    _saved_sid = _sess.get("sid")
    _saved_data = _sess.get("data")
    _saved_form_dict = frappe.local.form_dict
    frappe.set_user("Administrator")
    try:
        from frappe.model.workflow import apply_workflow
        apply_workflow(frappe.get_doc(doctype, name), action)
    finally:
        frappe.set_user(original_user)
        _sess.sid = _saved_sid
        _sess.data = _saved_data
        frappe.local.form_dict = _saved_form_dict

    _fix_approval_log_actor(doctype, name, prev_state, user)
    return {"success": True,
            "workflow_state": frappe.db.get_value(doctype, name, "workflow_state") or "",
            "docstatus": frappe.db.get_value(doctype, name, "docstatus")}


def _fix_approval_log_actor(doctype, name, prev_state, actor):
    """Before Save ghi nhat ky bang frappe.session.user -- luc do dang la
    Administrator. Tra lai dung email nguoi duyet cho dong vua ghi."""
    try:
        log = frappe.db.get_value(doctype, name, "ec_approval_log") or ""
        needle = "Administrator | " + prev_state + " ->"
        if needle in log:
            log = log.replace(needle, actor + " | " + prev_state + " ->")
            frappe.db.set_value(doctype, name, "ec_approval_log", log, update_modified=False)
    except Exception:
        pass


def _fix_submit_log_actor(so_name, actor):
    """Doi "Administrator | Draft -> ..." thanh dung email nguoi gui trong
    ec_approval_log. Can thiet vi buoc submit chay duoi session Administrator
    (xem create_so_from_form). Chi doi dong Draft -> Pending, khong dung dong khac."""
    try:
        log = frappe.db.get_value("Sales Order", so_name, "ec_approval_log") or ""
        if "Administrator | Draft ->" in log:
            log = log.replace("Administrator | Draft ->", actor + " | Draft ->")
            frappe.db.set_value("Sales Order", so_name, "ec_approval_log", log,
                                update_modified=False)
    except Exception:
        pass


def _read_json_body():
    """Parse JSON POST body. Form /gbs-so-form-v2 gui nested items/taxes nen doc
    thang tu request body thay vi kwargs."""
    data = None
    try:
        raw = frappe.request.get_data(as_text=True)
        if raw:
            data = frappe.parse_json(raw)
    except Exception:
        data = None
    if not isinstance(data, dict):
        data = dict(frappe.form_dict)
    return data


def _build_chain_for_doc(doc, recipe_name):
    """Build approval chain based on recipe + doc context.

    Returns: list of {level, approver, status, role}
    """
    recipe = APPROVAL_RECIPES.get(recipe_name, [])
    if not recipe:
        return []

    brand = None
    if getattr(doc, "brand_code", None):
        brand = frappe.db.get_value(
            "Brand",
            doc.brand_code,
            ["ec_manager_email as manager_email",
             "ec_leader_email as leader_email",
             "ec_finance_email as finance_email"],
            as_dict=True
        )

    chain = []
    level = 1
    for role in recipe:
        approver = _resolve_approver(role, brand, doc)
        if not approver:
            continue
        chain.append({
            "level": level,
            "approver": approver,
            "role": role,
            "status": "Pending",
        })
        level += 1
    return chain


def _resolve_approver(role, brand_approver, doc):
    """Resolve role to user email."""
    if role == "manager":
        return (brand_approver or {}).get("manager_email") or _get_global_role("manager")
    if role == "leader":
        return (brand_approver or {}).get("leader_email") or _get_global_role("leader")
    if role == "finance":
        return (brand_approver or {}).get("finance_email") or _get_global_role("finance_lead")
    if role == "ceo":
        return _get_global_role("ceo")
    if role == "hof":
        return _get_global_role("hof")
    return None


def _get_global_role(role_key):
    """Return user_email of active user with this role."""
    result = frappe.db.get_value(
        "Global Role",
        {"role_key": role_key, "active": 1},
        "user_email"
    )
    return result


def _notify_approver(approver_email, doc):
    """Send the approval-request email AND publish an in-app `approval_required` event.

    This is the single point a request enters "needs this approver to act" -- it fires on
    initial submit (chain[0]) and on each level advance (next_approver). The in-app event
    flows through the ONE central publish service (toast/sound/desktop/Teams + the native
    Notification Log) with a STABLE dedupe key (doctype|name|approver|level) so reloading
    a list or re-opening the page never re-notifies. Fail-open: notification errors never
    block the approval transaction."""
    if not approver_email:
        return
    # Shared Action Center resolver so email, homepage card and in-app event agree on URL.
    from ecentric_workspace.action_center.resolvers import build_approval_url
    rel_url = build_approval_url(doc.doctype, doc.name)
    try:
        from ecentric_workspace.approval_center.shared.workflow.transitions import request_label as _rlabel
        _label = _rlabel(doc.doctype, doc.name)
    except Exception:
        _label = doc.name
    try:
        from ecentric_workspace.notification_center import events as _ncev
        _level = doc.get("current_level") or 1
        _ncev.publish_notification_event(
            "approval_required", approver_email,
            "C\u1ea7n duy\u1ec7t: " + _label,
            "Y\u00eau c\u1ea7u \"" + _label + "\" \u0111ang ch\u1edd b\u1ea1n duy\u1ec7t.",
            action_url=rel_url, reference_doctype=doc.doctype, reference_name=doc.name,
            actor=(doc.get("submitted_by") or doc.owner),
            dedupe_key="approval_required|" + doc.doctype + "|" + doc.name + "|"
                       + str(approver_email) + "|" + str(_level))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "_notify_approver in-app event")
    try:
        site_url = frappe.utils.get_url()
        approval_url = site_url + rel_url
        frappe.sendmail(
            recipients=[approver_email],
            subject="[Approval needed] {0}".format(_label),
            message="""
            <p>You have a new approval request:</p>
            <p><b>Type:</b> {0}<br>
               <b>ID:</b> {1}<br>
               <b>Submitted by:</b> {2}</p>
            <p><a href="{3}">Review and decide</a></p>
            """.format(doc.doctype, doc.name, doc.get("submitted_by") or doc.owner, approval_url),
            reference_doctype=doc.doctype,
            reference_name=doc.name,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "_notify_approver failed")


def _notify_submitter(doc, status, comment=None):
    """Notify submitter of final decision."""
    submitter = doc.get("submitted_by") or doc.owner
    if not submitter:
        return
    try:
        frappe.sendmail(
            recipients=[submitter],
            subject="[{0}] {1}: {2}".format(status, doc.doctype, doc.name),
            message="""
            <p>Your request <b>{0}</b> has been <b>{1}</b>.</p>
            <p><b>Comment:</b> {2}</p>
            """.format(doc.name, status, comment or "(no comment)"),
            reference_doctype=doc.doctype,
            reference_name=doc.name,
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "_notify_submitter failed")


def _create_supplier_from_vrq(vrq):
    """When Vendor Request approved, auto-create ERPNext Supplier."""
    supplier = frappe.get_doc({
        "doctype": "Supplier",
        "supplier_name": vrq.proposed_vendor_name,
        "tax_id": vrq.tax_code,
        "supplier_group": "All Supplier Groups",
        "country": "Vietnam",
    })
    supplier.insert(ignore_permissions=True)
    return supplier.name


# =============================================================================
# FILE STORAGE - SharePoint integration (Phase 2 — placeholder)
# =============================================================================
# Real implementation needs Microsoft Graph API OAuth token.
# For Phase 1: form uploads file to SP directly (client-side via Graph SDK),
# then calls PATCH /api/resource/<DocType>/<name> with attachment_url field.

# When ready: implement here using `requests` + Graph API token caching.
