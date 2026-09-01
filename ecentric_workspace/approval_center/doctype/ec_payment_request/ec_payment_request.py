# Copyright (c) 2026, eCentric and contributors
"""EC Payment Request - business data only. Approval STATE on EC Approval Request.
Direct Manager -> Finance -> HOF -> CEO (sequential; no fulfillment)."""
import frappe
from frappe import _
from frappe.model.document import Document


class ECPaymentRequest(Document):
    def validate(self):
        self._department_snapshot_lock()

    def _department_snapshot_lock(self):
        """Phong ban la BAN CHUP luc gui duyet - doi sau khi gui la doi luat choi giua chung.

        Vi sao khoa. `department` lai HAI thu: EC Viewer Permission (ai duoc nhin thay phieu)
        va viec dinh tuyen cap duyet L1 (truong bo phan nao duyet). Trong khi do `save_draft`
        van chay duoc o trang thai "Information Required" va ghi moi truong trong
        editable_fields - nen mot phieu bi tra lai co the doi phong ban roi gui lai, va
        `department` KHONG nam trong MATERIAL_FIELDS nen viec doi do khong lam duyet lai tu
        dau. Ket qua: phieu di tiep tren mot chuoi duyet da duoc chot cho phong ban KHAC, va
        nguoi le ra khong duoc xem thi nhin thay, nguoi le ra phai duyet thi khong.

        8/27 form da khoa tu truoc (data_request, ai_topup...). Payment Request la form chi
        tien nen thuoc nhom can khoa nhat - ra soat 01/09 phat hien no van mo.

        Chi khoa SAU khi da gui (co approval_request). Ban nhap thi doi thoai mai.
        """
        if self.is_new() or not self.approval_request:
            return
        before = self.get_doc_before_save()
        if before and before.department and before.department != self.department:
            frappe.throw(_("Phòng ban là bản chụp lúc gửi duyệt và không thể thay đổi sau "
                           "khi gửi. Nếu cần đổi phòng ban, hãy Từ chối rồi dùng “Tạo phiếu "
                           "mới từ phiếu này”."))
