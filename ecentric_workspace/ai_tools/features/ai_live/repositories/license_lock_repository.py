# Copyright (c) 2026, eCentric and contributors
"""Khoa dong + giao dich cho Ban quyen AI Live.
MariaDB GET_LOCK theo guid_h / dist_id - CUNG khoa cho license_request, license_checkin va nut Duyet / Khoa:
2 ban chep cung goi mo cung luc khong cung thanh "may dau tien"; 3 app cung may gui cung luc khong tao trung may;
nut Duyet va app dang xin khong giam len nhau. GET_LOCK khong tu nha khi commit -> service commit TRUOC roi moi unlock.
Ten khoa co ma site (GET_LOCK dung chung ca may chu MariaDB)."""
import hashlib

from ecentric_workspace.ai_tools.features.ai_live import license_constants as L


class LicenseLockRepository:
    def _lock_name(self, key):
        import frappe
        site = hashlib.sha1(str(frappe.conf.db_name or frappe.local.site).encode()).hexdigest()[:8]
        return (L.LOCK_PREFIX + site + ":" + key)[:64]

    def lock(self, keys):
        import frappe
        got = []
        for k in sorted(set(keys)):
            r = frappe.db.sql("SELECT GET_LOCK(%s, %s)", (self._lock_name(k), L.LOCK_WAIT_S))
            if not r or r[0][0] != 1:
                self.unlock(got)
                return False
            got.append(k)
        return True

    def unlock(self, keys):
        import frappe
        for k in keys:
            try:
                frappe.db.sql("SELECT RELEASE_LOCK(%s)", (self._lock_name(k),))
            except Exception:
                pass

    def commit(self):
        import frappe
        frappe.db.commit()

    def rollback(self):
        import frappe
        frappe.db.rollback()
