# Copyright (c) 2026, eCentric and contributors
"""Host QC Session. Ket qua phien (diem, mau, dem loi) ghi bang set_value: app gui lien tuc trong phien,
khong sinh Version va khong doi `modified` cua form Production dang mo."""
import frappe

from ecentric_workspace.host_qc.constants import doctypes as DT

BRIEF = ["name", "session_id", "machine", "live_room", "status", "started_at", "planned_start", "platform", "format"]


class SessionRepository:
    def get_brief(self, session_id):
        row = frappe.db.get_value(DT.SESSION, session_id, BRIEF, as_dict=True)
        return dict(row) if row else None

    def get_full(self, session_id):
        if not frappe.db.exists(DT.SESSION, session_id):
            return None
        return frappe.get_doc(DT.SESSION, session_id).as_dict(no_default_fields=False)

    def ready_for_machine(self, machine_id, start_from, start_to, status):
        return frappe.get_all(DT.SESSION, filters={"machine": machine_id, "status": status,
                                                   "planned_start": ["between", [start_from, start_to]]},
                              fields=["name", "planned_start"], order_by="planned_start asc")

    def ready_for_room(self, room_id, start_from, start_to, status):
        return frappe.get_all(DT.SESSION, filters={"live_room": room_id, "status": status,
                                                   "planned_start": ["between", [start_from, start_to]]},
                              fields=["name", "planned_start", "machine"], order_by="planned_start asc")

    def for_rooms(self, room_ids, statuses, start_from, start_to):
        return frappe.get_all(DT.SESSION, filters={"live_room": ["in", list(room_ids)], "status": ["in", list(statuses)],
                                                   "planned_start": ["between", [start_from, start_to]]},
                              fields=["live_room", "status", "planned_start", "platform", "brand", "tiktok_username"],
                              order_by="planned_start asc")

    def hosts(self, session_id):
        return frappe.get_all(DT.SESSION_HOST, filters={"parent": session_id, "parenttype": DT.SESSION},
                              fields=["host_id", "host_name"])

    def create(self, values, from_machine=False):
        doc = frappe.get_doc(dict(values, doctype=DT.SESSION))
        doc.flags.ignore_permissions = True
        doc.flags.from_machine = from_machine
        doc.insert()
        return doc.name

    def update(self, session_id, values):
        if values:
            frappe.db.set_value(DT.SESSION, session_id, values, update_modified=False)
