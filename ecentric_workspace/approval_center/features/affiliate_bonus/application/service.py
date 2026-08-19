"""Business rules owned by the affiliate_bonus module."""
from ecentric_workspace.approval_center.shared.finance_support import _, frappe, getdate


def affiliate_title(doc):
    date = getdate(doc.get("service_month")) if doc.get("service_month") else None
    month = "%04d-%02d" % (date.year, date.month) if date else "?"
    amount = doc.get("total_amount")
    amount = "%.0f" % float(amount) if amount not in (None, "") else "?"
    return ("Affiliate Bonus - %s - %s" % (month, amount))[:180]

def validate_affiliate(doc):
    missing = [field for field in ("service_month", "detail", "request_attachment")
               if not str(doc.get(field) or "").strip()]
    if doc.total_amount is None: missing.append("total_amount")
    if doc.budget is None: missing.append("budget")
    if missing: frappe.throw(_("Vui lÃƒÆ’Ã‚Â²ng nhÃƒÂ¡Ã‚ÂºÃ‚Â­p Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚ÂºÃ‚Â§y Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã‚Â§ cÃƒÆ’Ã‚Â¡c trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Âng bÃƒÂ¡Ã‚ÂºÃ‚Â¯t buÃƒÂ¡Ã‚Â»Ã¢â€žÂ¢c (bao gÃƒÂ¡Ã‚Â»Ã¢â‚¬Å“m tÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡p Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â­nh kÃƒÆ’Ã‚Â¨m) trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºc khi gÃƒÂ¡Ã‚Â»Ã‚Â­i."))
    try:
        if float(doc.total_amount) <= 0: frappe.throw(_("TÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¢ng sÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ tiÃƒÂ¡Ã‚Â»Ã‚Ân phÃƒÂ¡Ã‚ÂºÃ‚Â£i lÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºn hÃƒâ€ Ã‚Â¡n 0."))
        if float(doc.budget) < 0: frappe.throw(_("NgÃƒÆ’Ã‚Â¢n sÃƒÆ’Ã‚Â¡ch khÃƒÆ’Ã‚Â´ng thÃƒÂ¡Ã‚Â»Ã†â€™ lÃƒÆ’Ã‚Â  sÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ ÃƒÆ’Ã‚Â¢m."))
    except (TypeError, ValueError): frappe.throw(_("GiÃƒÆ’Ã‚Â¡ trÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¹ sÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ tiÃƒÂ¡Ã‚Â»Ã‚Ân/ngÃƒÆ’Ã‚Â¢n sÃƒÆ’Ã‚Â¡ch khÃƒÆ’Ã‚Â´ng hÃƒÂ¡Ã‚Â»Ã‚Â£p lÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡."))
    if getdate(doc.service_month).day != 1: frappe.throw(_("ThÃƒÆ’Ã‚Â¡ng dÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¹ch vÃƒÂ¡Ã‚Â»Ã‚Â¥ (Service month) phÃƒÂ¡Ã‚ÂºÃ‚Â£i lÃƒÆ’Ã‚Â  ngÃƒÆ’Ã‚Â y 1 cÃƒÂ¡Ã‚Â»Ã‚Â§a thÃƒÆ’Ã‚Â¡ng."))

