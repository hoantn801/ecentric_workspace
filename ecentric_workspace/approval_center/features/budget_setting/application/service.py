"""Business rules owned by the budget_setting module."""
from ecentric_workspace.approval_center.shared.finance_support import _, frappe, getdate


def budget_title(doc):
    date = getdate(doc.get("period_start")) if doc.get("period_start") else None
    tag = (("%04d-%02d" % (date.year, date.month)) if doc.get("budget_period_type") == "Monthly"
           else ("%04d" % date.year)) if date else "?"
    return ("Budget Setting - %s - %s - %s" %
            (doc.get("budget_period_type") or "Annual", doc.get("department") or "?", tag))[:180]

def validate_budget(doc):
    required = ("budget_period_type", "period_start", "department", "forecast_justification",
                "has_financial_risks", "request_attachment")
    amounts = ("approved_budget_current_period", "actual_spending_current_period",
               "forecast_budget_next_period")
    if any(not str(doc.get(f) or "").strip() for f in required) or any(doc.get(f) is None for f in amounts):
        frappe.throw(_("Vui lÃƒÆ’Ã‚Â²ng nhÃƒÂ¡Ã‚ÂºÃ‚Â­p Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚ÂºÃ‚Â§y Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã‚Â§ cÃƒÆ’Ã‚Â¡c trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Âng bÃƒÂ¡Ã‚ÂºÃ‚Â¯t buÃƒÂ¡Ã‚Â»Ã¢â€žÂ¢c (bao gÃƒÂ¡Ã‚Â»Ã¢â‚¬Å“m tÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡p Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â­nh kÃƒÆ’Ã‚Â¨m) trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºc khi gÃƒÂ¡Ã‚Â»Ã‚Â­i."))
    if not frappe.db.exists("Department", doc.department): frappe.throw(_("PhÃƒÆ’Ã‚Â²ng ban khÃƒÆ’Ã‚Â´ng hÃƒÂ¡Ã‚Â»Ã‚Â£p lÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡. Vui lÃƒÆ’Ã‚Â²ng chÃƒÂ¡Ã‚Â»Ã‚Ân phÃƒÆ’Ã‚Â²ng ban tÃƒÂ¡Ã‚Â»Ã‚Â« danh sÃƒÆ’Ã‚Â¡ch."))
    if doc.budget_period_type not in ("Annual", "Monthly"): frappe.throw(_("LoÃƒÂ¡Ã‚ÂºÃ‚Â¡i kÃƒÂ¡Ã‚Â»Ã‚Â³ ngÃƒÆ’Ã‚Â¢n sÃƒÆ’Ã‚Â¡ch khÃƒÆ’Ã‚Â´ng hÃƒÂ¡Ã‚Â»Ã‚Â£p lÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡."))
    try:
        if any(float(doc.get(f)) < 0 for f in amounts): frappe.throw(_("CÃƒÆ’Ã‚Â¡c giÃƒÆ’Ã‚Â¡ trÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¹ ngÃƒÆ’Ã‚Â¢n sÃƒÆ’Ã‚Â¡ch khÃƒÆ’Ã‚Â´ng thÃƒÂ¡Ã‚Â»Ã†â€™ lÃƒÆ’Ã‚Â  sÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ ÃƒÆ’Ã‚Â¢m."))
    except (TypeError, ValueError): frappe.throw(_("CÃƒÆ’Ã‚Â¡c giÃƒÆ’Ã‚Â¡ trÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¹ ngÃƒÆ’Ã‚Â¢n sÃƒÆ’Ã‚Â¡ch phÃƒÂ¡Ã‚ÂºÃ‚Â£i lÃƒÆ’Ã‚Â  sÃƒÂ¡Ã‚Â»Ã¢â‚¬Ëœ."))
    date = getdate(doc.period_start)
    if doc.budget_period_type == "Annual" and (date.month != 1 or date.day != 1): frappe.throw(_("VÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºi kÃƒÂ¡Ã‚Â»Ã‚Â³ NÃƒâ€žÃ†â€™m (Annual), NgÃƒÆ’Ã‚Â y bÃƒÂ¡Ã‚ÂºÃ‚Â¯t Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚ÂºÃ‚Â§u phÃƒÂ¡Ã‚ÂºÃ‚Â£i lÃƒÆ’Ã‚Â  ngÃƒÆ’Ã‚Â y 1 thÃƒÆ’Ã‚Â¡ng 1 (01/01)."))
    if doc.budget_period_type == "Monthly" and date.day != 1: frappe.throw(_("VÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºi kÃƒÂ¡Ã‚Â»Ã‚Â³ ThÃƒÆ’Ã‚Â¡ng (Monthly), NgÃƒÆ’Ã‚Â y bÃƒÂ¡Ã‚ÂºÃ‚Â¯t Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚ÂºÃ‚Â§u phÃƒÂ¡Ã‚ÂºÃ‚Â£i lÃƒÆ’Ã‚Â  ngÃƒÆ’Ã‚Â y 1 cÃƒÂ¡Ã‚Â»Ã‚Â§a thÃƒÆ’Ã‚Â¡ng."))
    if doc.has_financial_risks == "Yes" and not (doc.financial_risk_details or "").strip(): frappe.throw(_("Vui lÃƒÆ’Ã‚Â²ng mÃƒÆ’Ã‚Â´ tÃƒÂ¡Ã‚ÂºÃ‚Â£ rÃƒÂ¡Ã‚Â»Ã‚Â§i ro tÃƒÆ’Ã‚Â i chÃƒÆ’Ã‚Â­nh khi chÃƒÂ¡Ã‚Â»Ã‚Ân 'Yes'."))

