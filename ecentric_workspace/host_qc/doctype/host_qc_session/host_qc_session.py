# Copyright (c) 2026, eCentric and contributors
"""Host QC Session - mot phien QC: cau hinh (Production nhap truoc phien) + ket qua (app ghi, ERP cham lai)."""
from frappe.model.document import Document

from ecentric_workspace.host_qc.services.validate_session_service import ValidateSessionService
from ecentric_workspace.host_qc.utils.desk import run


class HostQCSession(Document):
    def validate(self):
        run(ValidateSessionService(), self)
