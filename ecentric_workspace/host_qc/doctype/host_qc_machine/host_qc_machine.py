# Copyright (c) 2026, eCentric and contributors
"""Host QC Machine - may studio chay app AI Host QC (token, nhip, micro tren may)."""
from frappe.model.document import Document

from ecentric_workspace.host_qc.services.validate_machine_service import ValidateMachineService
from ecentric_workspace.host_qc.utils.desk import run


class HostQCMachine(Document):
    def validate(self):
        run(ValidateMachineService(), self)
