"""Business rules owned by the purchase_request module."""
from ecentric_workspace.approval_center.shared.finance_support import _, frappe, getdate


def purchase_title(doc):
    amount = doc.get("payment_amount")
    amount = "%.0f" % float(amount) if amount not in (None, "") else "?"
    return ("Purchase Request - %s - %s" % (doc.get("department") or "?", amount))[:180]

def validate_purchase(doc):
    required = ("department", "justification", "purchase_details", "payment_term", "supplier_type",
                "supplier_name", "additional_notes_comments", "estimated_purchase_date",
                "estimated_delivery_date", "request_attachment")
    if any(not str(doc.get(f) or "").strip() for f in required) or doc.payment_amount is None:
        frappe.throw(_("Vui lÃƒÆ’Ã‚Â²ng nhÃƒÂ¡Ã‚ÂºÃ‚Â­p Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚ÂºÃ‚Â§y Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã‚Â§ cÃƒÆ’Ã‚Â¡c trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Âng bÃƒÂ¡Ã‚ÂºÃ‚Â¯t buÃƒÂ¡Ã‚Â»Ã¢â€žÂ¢c (bao gÃƒÂ¡Ã‚Â»Ã¢â‚¬Å“m tÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡p Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â­nh kÃƒÆ’Ã‚Â¨m) trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºc khi gÃƒÂ¡Ã‚Â»Ã‚Â­i."))
    if not frappe.db.exists("Department", doc.department): frappe.throw(_("PhÃƒÆ’Ã‚Â²ng ban khÃƒÆ’Ã‚Â´ng hÃƒÂ¡Ã‚Â»Ã‚Â£p lÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡. Vui lÃƒÆ’Ã‚Â²ng chÃƒÂ¡Ã‚Â»Ã‚Ân phÃƒÆ’Ã‚Â²ng ban tÃƒÂ¡Ã‚Â»Ã‚Â« danh sÃƒÆ’Ã‚Â¡ch."))
    try:
        if float(doc.payment_amount) <= 0: frappe.throw(_("SÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ tiÃƒÂ¡Ã‚Â»Ã‚Ân thanh toÃƒÆ’Ã‚Â¡n phÃƒÂ¡Ã‚ÂºÃ‚Â£i lÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºn hÃƒâ€ Ã‚Â¡n 0."))
    except (TypeError, ValueError): frappe.throw(_("SÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ tiÃƒÂ¡Ã‚Â»Ã‚Ân thanh toÃƒÆ’Ã‚Â¡n phÃƒÂ¡Ã‚ÂºÃ‚Â£i lÃƒÆ’Ã‚Â  sÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ."))
    if doc.payment_term == "Other" and not (doc.payment_term_other or "").strip(): frappe.throw(_("Vui lÃƒÆ’Ã‚Â²ng nhÃƒÂ¡Ã‚ÂºÃ‚Â­p Ãƒâ€žÃ¢â‚¬ËœiÃƒÂ¡Ã‚Â»Ã‚Âu khoÃƒÂ¡Ã‚ÂºÃ‚Â£n thanh toÃƒÆ’Ã‚Â¡n khÃƒÆ’Ã‚Â¡c khi chÃƒÂ¡Ã‚Â»Ã‚Ân 'Other'."))
    if doc.estimated_delivery_date < doc.estimated_purchase_date: frappe.throw(_("NgÃƒÆ’Ã‚Â y giao hÃƒÆ’Ã‚Â ng dÃƒÂ¡Ã‚Â»Ã‚Â± kiÃƒÂ¡Ã‚ÂºÃ‚Â¿n khÃƒÆ’Ã‚Â´ng thÃƒÂ¡Ã‚Â»Ã†â€™ trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºc ngÃƒÆ’Ã‚Â y mua dÃƒÂ¡Ã‚Â»Ã‚Â± kiÃƒÂ¡Ã‚ÂºÃ‚Â¿n."))

