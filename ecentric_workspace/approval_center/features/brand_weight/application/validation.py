# Copyright (c) 2026, eCentric and contributors
"""Validate noi tai cua mot phieu ty trong luong brand.

Vi sao tong PHAI bang 100: PnL cong don chi phi luong theo ty trong nay. Neu tong la
80 thi 20% chi phi cua phong do bien mat khoi bao cao ma khong ai thay - sai kieu im
lang, khong sinh loi, khong ai doi chieu lai duoc. Ba thu duoc khoa o day:

1. KY PHAI DUNG YYYY-MM. Truoc day o ban Desk tu tao, `ky` la Data go tay: '2026-09',
   '09/2026', 'T9/2026' deu luu duoc va PnL group ra ba nhom rieng cho cung mot thang.
2. KHONG DUOC TRUNG BRAND trong cung mot phieu. Hai dong 'FLD-VN' 40% + 'FLD-VN' 20%
   van du 100 nhung phan bo thanh 60% - tong dung, ket qua sai.
3. TONG = 100, sai so 0.01 cho Percent lam tron.
"""
import re

import frappe
from frappe import _

PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
TOLERANCE = 0.01


class ValidateBrandWeightRequestService:
    def execute(self, doc):
        self._period(doc)
        self._rows(doc)
        self._total(doc)
        self._department_lock(doc)

    def _period(self, doc):
        if not PERIOD_RE.match((doc.period or "").strip()):
            frappe.throw(_("Kỳ phải đúng định dạng YYYY-MM, ví dụ 2026-09."))

    def _rows(self, doc):
        if not doc.details:
            frappe.throw(_("Phải có ít nhất một dòng phân bổ brand."))
        seen = set()
        for row in doc.details:
            if float(row.weight or 0) <= 0:
                frappe.throw(_("Dòng {0}: tỷ trọng phải lớn hơn 0.").format(row.idx))
            if row.brand in seen:
                frappe.throw(_("Brand {0} bị nhập hai lần trong cùng một phiếu.").format(row.brand))
            seen.add(row.brand)

    def _total(self, doc):
        total = sum(float(r.weight or 0) for r in doc.details)
        doc.total_weight = total
        if abs(total - 100.0) > TOLERANCE:
            frappe.throw(_("Tổng tỷ trọng đang là {0}%, phải bằng đúng 100%.")
                         .format(frappe.utils.flt(total, 2)))

    def _department_lock(self, doc):
        if doc.is_new() or not doc.approval_request:
            return
        before = doc.get_doc_before_save()
        if before and before.department and before.department != doc.department:
            frappe.throw(_("Phòng ban là bản chụp lúc gửi và không thể thay đổi sau khi gửi."))
