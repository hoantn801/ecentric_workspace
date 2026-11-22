# Copyright (c) 2026, eCentric and contributors
"""EC Discipline Case - ho so the do / den. Logic o hr/ky_luat (case/procedure/decision_service)."""
from frappe.model.document import Document

from ecentric_workspace.hr.ky_luat.infrastructure.doc_guard import require_service_write


class ECDisciplineCase(Document):
    def validate(self):
        require_service_write(self)
