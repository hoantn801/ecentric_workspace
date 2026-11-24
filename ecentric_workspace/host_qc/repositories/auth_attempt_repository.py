# Copyright (c) 2026, eCentric and contributors
"""Dem so lan sai token theo IP trong frappe.cache (khong luu DB)."""
import frappe

from ecentric_workspace.host_qc.constants.rules import AUTH_FAIL_WINDOW_S


class AuthAttemptRepository:
    @staticmethod
    def _key(ip):
        return "host_qc:authfail:%s" % (ip or "-")

    def failures(self, ip):
        return int(frappe.cache().get_value(self._key(ip)) or 0)

    def add_failure(self, ip):
        key = self._key(ip)
        n = int(frappe.cache().get_value(key) or 0) + 1
        frappe.cache().set_value(key, n, expires_in_sec=AUTH_FAIL_WINDOW_S)
        return n
