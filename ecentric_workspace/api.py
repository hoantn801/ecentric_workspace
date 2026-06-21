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
    "brand": "Brand Approver",
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
            "Brand Approver",
            doc.brand_code,
            ["manager_email", "leader_email", "finance_email"],
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
        from ecentric_workspace.notification_center import events as _ncev
        _level = doc.get("current_level") or 1
        _ncev.publish_notification_event(
            "approval_required", approver_email,
            "C\u1ea7n duy\u1ec7t: " + doc.doctype + " " + doc.name,
            "Y\u00eau c\u1ea7u " + doc.name + " \u0111ang ch\u1edd b\u1ea1n duy\u1ec7t.",
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
            subject="[Approval needed] {0}: {1}".format(doc.doctype, doc.name),
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
