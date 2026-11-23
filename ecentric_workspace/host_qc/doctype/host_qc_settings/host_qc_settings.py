# Copyright (c) 2026, eCentric and contributors
"""Host QC Settings - cau hinh chung (diem, nguong, khoa AI, SharePoint/Teams). Luu -> doi rules_version."""
from frappe.model.document import Document

from ecentric_workspace.host_qc.services.bump_rules_version_service import BumpRulesVersionService
from ecentric_workspace.host_qc.utils.desk import run


class HostQCSettings(Document):
    def validate(self):
        BumpRulesVersionService().execute(self)
