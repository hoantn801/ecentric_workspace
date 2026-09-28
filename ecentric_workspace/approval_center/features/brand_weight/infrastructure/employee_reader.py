# Copyright (c) 2026, eCentric and contributors
"""Doc duy nhat nhung gi luong duyet can biet ve nguoi nop. Tang duy nhat trong
feature nay duoc goi frappe.db (rule 4.3) - service ben tren khong biet den DB."""
import frappe


def lead_user(employee):
    """User cua quan ly truc tiep (Employee.reports_to), chi tra ve neu con dung duoc."""
    if not employee:
        return None
    reports_to = frappe.db.get_value("Employee", employee, "reports_to")
    if not reports_to:
        return None
    user = frappe.db.get_value("Employee", reports_to, "user_id")
    return user if _usable(user) else None


def inactive_brands(brand_names):
    """Brand khong con Active - chan ngay luc nop thay vi de PnL cong vao brand chet."""
    if not brand_names:
        return []
    rows = frappe.get_all("Brand", filters={"name": ["in", list(brand_names)]},
                          fields=["name", "ec_status"])
    found = {r["name"]: (r.get("ec_status") or "") for r in rows}
    bad = [b for b in brand_names if found.get(b) != "Active"]
    return bad


def _usable(user):
    if not user or user == "Guest":
        return False
    row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")
