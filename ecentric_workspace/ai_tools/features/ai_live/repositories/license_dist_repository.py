# Copyright (c) 2026, eCentric and contributors
"""EC License Dist: ma goi (eCentric_phan_phoi.json) - CHI tao cho goi co chu ky dung (verify_dist).
dist_id / kind / created_at la du lieu co chu ky tu laptop: khong sua. Chi nhan (label) sua duoc tren trang."""
from ecentric_workspace.ai_tools.features.ai_live import license_constants as L

_FIELDS = ["name", "dist_id", "label", "package_label", "kind", "package", "created_at", "first_machine", "first_seen",
           "issued_count", "creation"]


class LicenseDistRepository:
    def ensure(self, dist):
        """dist da kiem chu ky -> ten ban ghi (= dist_id). Tao neu chua co."""
        import frappe
        did = dist["dist_id"]
        if not frappe.db.exists(L.DIST, did):
            frappe.get_doc({"doctype": L.DIST, "dist_id": did, "label": dist.get("label") or "",
                            "package_label": dist.get("label") or "", "kind": dist.get("kind"),
                            "package": dist.get("package") or "", "created_at": dist.get("created_at") or "",
                            "issued_count": 0}).insert(ignore_permissions=True)
        return did

    def get(self, did):
        import frappe
        rows = frappe.get_all(L.DIST, filters={"name": did}, fields=_FIELDS, limit_page_length=1) if did else []
        return rows[0] if rows else None

    def set_first(self, did, machine, ts):
        """Ghi may dau tien (chi lan dau) + so may da cap."""
        import frappe
        from ecentric_workspace.ai_tools.features.ai_live.repositories.license_machine_repository import sys_dt
        if not frappe.db.get_value(L.DIST, did, "first_machine"):
            frappe.db.set_value(L.DIST, did, {"first_machine": machine, "first_seen": sys_dt(ts)}, update_modified=False)

    def set_count(self, did, n):
        import frappe
        frappe.db.set_value(L.DIST, did, "issued_count", int(n), update_modified=False)

    def set_label(self, did, label):
        import frappe
        doc = frappe.get_doc(L.DIST, did)
        doc.label = label
        doc.save(ignore_permissions=True)

    def all(self):
        import frappe
        return frappe.get_all(L.DIST, fields=_FIELDS, order_by="creation desc", limit_page_length=500)

    def labels(self, names):
        import frappe
        names = [n for n in set(names) if n]
        if not names:
            return {}
        return {r["name"]: r.get("label") or r["name"][:8]
                for r in frappe.get_all(L.DIST, filters={"name": ["in", names]}, fields=["name", "label"],
                                        limit_page_length=0)}
