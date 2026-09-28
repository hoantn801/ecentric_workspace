# Copyright (c) 2026, eCentric and contributors
"""EC Brand Weight Request - du lieu nghiep vu ty trong luong theo brand.
Trang thai duyet nam tren EC Approval Request (khong co approval_status o day).

Controller giu dung rule 4.1: hook chi goi service, khong chua if/for nghiep vu va
khong goi frappe.db. Khac voi ec_outside_work_request (viet truoc khi rule nay duoc
ap) - o day validate noi tai nam trong feature service de controller duoi tran 50 dong."""
from frappe.model.document import Document

from ecentric_workspace.approval_center.features.brand_weight.application.validation import (
    ValidateBrandWeightRequestService,
)


class ECBrandWeightRequest(Document):
    def validate(self):
        ValidateBrandWeightRequestService().execute(self)
