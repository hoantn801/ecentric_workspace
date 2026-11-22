# Copyright (c) 2026, eCentric and contributors
"""EC HR Notice - the vang (nhac nho noi bo). Logic o hr/ky_luat (notice_service)."""
from frappe.model.document import Document

from ecentric_workspace.hr.ky_luat.infrastructure.doc_guard import require_service_write


class ECHRNotice(Document):
    def validate(self):
        require_service_write(self)
