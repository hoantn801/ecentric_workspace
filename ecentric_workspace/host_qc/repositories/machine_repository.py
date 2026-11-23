# Copyright (c) 2026, eCentric and contributors
"""Host QC Machine + bang con "Micro tren may".

Nhip tim 30 giay / may: ghi bang frappe.db.set_value (khong doc.save) de khong sinh Version, khong doi
`modified` cua form dang mo (tranh "da bi sua" khi Production luu form may)."""
import frappe

from ecentric_workspace.host_qc.constants import doctypes as DT

HB_FIELDS = ("last_seen", "app_version", "state", "load_level", "obs_connected", "obs_streaming",
             "obs_skipped_pct")


class MachineRepository:
    def get_auth(self, machine_id):
        row = frappe.db.get_value(DT.MACHINE, machine_id, ["name", "machine_id", "enabled", "token_hash"],
                                  as_dict=True)
        return dict(row) if row else None

    def exists(self, machine_id):
        return bool(frappe.db.exists(DT.MACHINE, machine_id))

    def set_token(self, machine_id, token_hash, by, at):
        frappe.db.set_value(DT.MACHINE, machine_id, {"token_hash": token_hash, "token_issued_by": by,
                                                     "token_issued_at": at})

    def update_heartbeat(self, machine_id, values):
        frappe.db.set_value(DT.MACHINE, machine_id, {k: values[k] for k in HB_FIELDS if k in values},
                            update_modified=False)

    def mics(self, machine_id):
        return frappe.get_all(DT.MACHINE_MIC, filters={"parent": machine_id, "parenttype": DT.MACHINE},
                              fields=["name", "device_name", "hostapi", "channels", "last_seen", "idx"],
                              order_by="idx asc")

    def touch_mic(self, row_name, channels, at):
        frappe.db.set_value(DT.MACHINE_MIC, row_name, {"channels": channels, "last_seen": at},
                            update_modified=False)

    def add_mic(self, machine_id, idx, device_name, hostapi, channels, at):
        doc = frappe.get_doc({"doctype": DT.MACHINE_MIC, "parent": machine_id, "parenttype": DT.MACHINE,
                              "parentfield": "mics", "idx": idx, "device_name": device_name,
                              "hostapi": hostapi, "channels": channels, "last_seen": at})
        doc.db_insert()

    def set_current_session(self, machine_id, session_id):
        frappe.db.set_value(DT.MACHINE, machine_id, "current_session", session_id, update_modified=False)

    def current_session(self, machine_id):
        return frappe.db.get_value(DT.MACHINE, machine_id, "current_session")
