# Copyright (c) 2026, eCentric and contributors
"""EC Brand Weight Request Detail - bang con (brand, ty trong).
Validate dong (tong 100, khong trung brand) chay o phieu cha qua
features.brand_weight.application.validation.

File nay BAT BUOC ton tai du khong co logic: Frappe import module cua moi DocType
khi migrate (on_doctype_update). Thieu no, migrate 25/09 dung o 69% va rollback."""
from frappe.model.document import Document


class ECBrandWeightRequestDetail(Document):
    pass
