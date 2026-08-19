"""Business rules owned by the payment_request module."""
from ecentric_workspace.approval_center.shared.finance_support import _, frappe, getdate


def payment_title(doc):
    amount = doc.get("payment_amount")
    amount = "%.0f" % float(amount) if amount not in (None, "") else "?"
    return ("Payment Request - %s - %s" % (doc.get("payee_full_name") or "?", amount))[:180]

def normalize_payment(doc):
    doc.details_and_attachments_correct = ("Yes" if doc.details_and_attachments_correct is True
        or str(doc.details_and_attachments_correct or "").strip().lower() in ("yes", "1", "true") else "No")

def validate_payment(doc):
    required = ("reason", "payment_date", "payee_full_name", "account_bank", "bank_account_number",
                "has_purchase_request", "is_cost_valid", "request_attachment")
    if any(not str(doc.get(f) or "").strip() for f in required) or doc.payment_amount is None:
        frappe.throw(_("Vui lÃƒÆ’Ã‚Â²ng nhÃƒÂ¡Ã‚ÂºÃ‚Â­p Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚ÂºÃ‚Â§y Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã‚Â§ cÃƒÆ’Ã‚Â¡c trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Âng bÃƒÂ¡Ã‚ÂºÃ‚Â¯t buÃƒÂ¡Ã‚Â»Ã¢â€žÂ¢c (bao gÃƒÂ¡Ã‚Â»Ã¢â‚¬Å“m tÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡p Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â­nh kÃƒÆ’Ã‚Â¨m) trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºc khi gÃƒÂ¡Ã‚Â»Ã‚Â­i."))
    try:
        if float(doc.payment_amount) <= 0: frappe.throw(_("SÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ tiÃƒÂ¡Ã‚Â»Ã‚Ân thanh toÃƒÆ’Ã‚Â¡n phÃƒÂ¡Ã‚ÂºÃ‚Â£i lÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºn hÃƒâ€ Ã‚Â¡n 0."))
    except (TypeError, ValueError): frappe.throw(_("SÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ tiÃƒÂ¡Ã‚Â»Ã‚Ân thanh toÃƒÆ’Ã‚Â¡n phÃƒÂ¡Ã‚ÂºÃ‚Â£i lÃƒÆ’Ã‚Â  sÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ."))
    normalize_payment(doc)
    if doc.details_and_attachments_correct != "Yes": frappe.throw(_("Vui lÃƒÆ’Ã‚Â²ng tÃƒÆ’Ã‚Â­ch xÃƒÆ’Ã‚Â¡c nhÃƒÂ¡Ã‚ÂºÃ‚Â­n thÃƒÆ’Ã‚Â´ng tin vÃƒÆ’Ã‚Â  tÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡p Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â­nh kÃƒÆ’Ã‚Â¨m lÃƒÆ’Ã‚Â  chÃƒÆ’Ã‚Â­nh xÃƒÆ’Ã‚Â¡c trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºc khi gÃƒÂ¡Ã‚Â»Ã‚Â­i."))
    if doc.has_purchase_request == "Yes":
        if not (doc.purchase_request or "").strip() or not frappe.db.exists("EC Purchase Request", doc.purchase_request): frappe.throw(_("Purchase Request liÃƒÆ’Ã‚Âªn quan khÃƒÆ’Ã‚Â´ng hÃƒÂ¡Ã‚Â»Ã‚Â£p lÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡."))
        request = frappe.db.get_value("EC Purchase Request", doc.purchase_request, "approval_request")
        if not request or frappe.db.get_value("EC Approval Request", request, "approval_status") != "Approved": frappe.throw(_("Purchase Request liÃƒÆ’Ã‚Âªn quan phÃƒÂ¡Ã‚ÂºÃ‚Â£i Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â£ Ãƒâ€žÃ¢â‚¬ËœÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Â£c duyÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡t (Approved/Completed) trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºc khi tÃƒÂ¡Ã‚ÂºÃ‚Â¡o Payment Request."))
    elif doc.has_purchase_request == "No" and not (doc.no_purchase_request_reason or "").strip(): frappe.throw(_("Vui lÃƒÆ’Ã‚Â²ng nhÃƒÂ¡Ã‚ÂºÃ‚Â­p lÃƒÆ’Ã‚Â½ do khÃƒÆ’Ã‚Â´ng cÃƒÆ’Ã‚Â³ Purchase Request khi chÃƒÂ¡Ã‚Â»Ã‚Ân 'No'."))

