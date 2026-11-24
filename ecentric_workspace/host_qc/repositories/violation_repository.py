# Copyright (c) 2026, eCentric and contributors
"""Host QC Violation + Lich su duyet."""
import frappe

from ecentric_workspace.host_qc.constants import doctypes as DT

SCORE_FIELDS = ["name", "violation_id", "code", "group", "severity", "review", "start_time", "end_time",
                "host_id", "host_name"]


class ViolationRepository:
    def get(self, violation_id):
        row = frappe.db.get_value(DT.VIOLATION, violation_id, "*", as_dict=True)
        return dict(row) if row else None

    def insert(self, values):
        doc = frappe.get_doc(dict(values, doctype=DT.VIOLATION))
        doc.flags.ignore_permissions = True
        doc.insert()
        return doc.name

    def update(self, violation_id, values):
        if values:
            frappe.db.set_value(DT.VIOLATION, violation_id, values)

    def for_scoring(self, session_id):
        return frappe.get_all(DT.VIOLATION, filters={"session": session_id}, fields=SCORE_FIELDS,
                              order_by="start_time asc")

    def reviewed(self, session_id):
        return frappe.get_all(DT.VIOLATION, filters={"session": session_id, "reviewed_at": ["is", "set"]},
                              fields=["violation_id", "review", "reviewed_by", "review_note", "reviewed_at"],
                              order_by="reviewed_at asc")

    def add_review_log(self, violation_id, entry):
        idx = frappe.db.count(DT.REVIEW_LOG, {"parent": violation_id, "parenttype": DT.VIOLATION}) + 1
        doc = frappe.get_doc(dict(entry, doctype=DT.REVIEW_LOG, parent=violation_id, parenttype=DT.VIOLATION,
                                  parentfield="review_log", idx=idx))
        doc.db_insert()
