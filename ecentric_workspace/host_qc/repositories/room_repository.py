# Copyright (c) 2026, eCentric and contributors
"""Host QC Live Room - phong live duoi studio (moi phong 1 may QC)."""
import frappe

from ecentric_workspace.host_qc.constants import doctypes as DT


class RoomRepository:
    def active(self):
        return frappe.get_all(DT.LIVE_ROOM, filters={"active": 1}, fields=["room_id", "room_name"],
                              order_by="room_name asc")

    def get(self, room_id):
        row = frappe.db.get_value(DT.LIVE_ROOM, room_id, ["room_id", "room_name", "active"], as_dict=True)
        return dict(row) if row else None
