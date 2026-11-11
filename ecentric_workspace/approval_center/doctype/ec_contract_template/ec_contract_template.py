# Copyright (c) 2026, eCentric and contributors
"""EC Contract Template - mau .docx cho hop dong / BBNT KOL/KOC (Finance tu quan).

Luc luu: liet ke {{placeholder}} trong mau va bao ten ERP khong hieu, de mau sai ten bi bat
NGAY khi tai len chu khong phai luc hop dong da gui di ky. Logic o kol_files.inspect_template."""
from frappe.model.document import Document


class ECContractTemplate(Document):
    def validate(self):
        from ecentric_workspace.approval_center.features.contract_review.application.kol_files import (
            inspect_template)
        inspect_template(self)
