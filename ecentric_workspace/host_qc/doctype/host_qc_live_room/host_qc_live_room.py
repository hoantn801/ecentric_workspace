# Copyright (c) 2026, eCentric and contributors
"""Host QC Live Room - phong live; may studio chon phong trong Cai dat app, ERP giao phien theo phong."""
from frappe.model.document import Document

from ecentric_workspace.host_qc.services.validate_room_service import ValidateRoomService
from ecentric_workspace.host_qc.utils.desk import run


class HostQCLiveRoom(Document):
    def validate(self):
        run(ValidateRoomService(), self)
