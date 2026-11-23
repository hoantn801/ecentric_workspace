# Copyright (c) 2026, eCentric and contributors
"""Doc Host QC Rule + bang con. Cache theo rules_version: sua luat -> version doi -> khoa cache moi."""
import frappe

from ecentric_workspace.host_qc.constants import doctypes as DT
from ecentric_workspace.host_qc.constants.rules import RULES_CACHE_S

RULE_FIELDS = ["name", "code", "title", "group", "enabled", "severity", "default_review", "deduct_only_valid",
               "sort_order", "how", "default_text", "tune_tip"]


class RuleRepository:
    def list_all(self, version=None):
        key = "host_qc:rules:%s" % (version or "")
        if version:
            hit = frappe.cache().get_value(key)
            if hit is not None:
                return hit
        rules = frappe.get_all(DT.RULE, fields=RULE_FIELDS, order_by="sort_order asc, code asc")
        params = frappe.get_all(DT.RULE_PARAM, filters={"parenttype": DT.RULE},
                                fields=["parent", "key", "value", "unit", "description"], order_by="idx asc")
        fmts = frappe.get_all(DT.RULE_FORMAT, filters={"parenttype": DT.RULE},
                              fields=["parent", "format", "enabled", "key", "value"], order_by="idx asc")
        by = {r["name"]: r for r in rules}
        for r in rules:
            r["params"], r["format_overrides"] = [], []
        for p in params:
            if p["parent"] in by:
                by[p["parent"]]["params"].append({k: p[k] for k in ("key", "value", "unit", "description")})
        for f in fmts:
            if f["parent"] in by:
                by[f["parent"]]["format_overrides"].append({k: f[k] for k in ("format", "enabled", "key", "value")})
        if version:
            frappe.cache().set_value(key, rules, expires_in_sec=RULES_CACHE_S)
        return rules

    def exists(self, code):
        return bool(frappe.db.exists(DT.RULE, code))

    def insert(self, values):
        doc = frappe.get_doc(dict(values, doctype=DT.RULE))
        doc.flags.ignore_permissions = True
        doc.insert()
        return doc.name
