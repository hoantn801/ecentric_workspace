# Copyright (c) 2026, eCentric and contributors
"""EC KOL Acceptance - MOT dot nghiem thu (BBNT) cua hop dong KOL/KOC = mot phieu Approval Center
rieng (PO chot 24/11/2026, thiet ke claude/thiet-ke-bbnt-tung-dot.md): duyet Ke toan tong hop ->
Ke toan truong -> CEO, goi ky so rieng. Chi tao / sua qua features/contract_review/application/
kol_acceptance (the KOL tren form 27) - khong tao tay."""
import frappe
from frappe import _
from frappe.model.document import Document

FLAG = "ec_kol_round_write"


class ECKOLAcceptance(Document):
    def validate(self):
        if frappe.flags.get(FLAG) or frappe.flags.in_patch or frappe.flags.in_install:
            return
        frappe.throw(_("Đợt nghiệm thu chỉ tạo / sửa từ thẻ KOL của hợp đồng (form 27)."))

    def on_trash(self):
        # Xoa dot = chi dot NHAP CUOI qua the KOL (PO 17/11 + 24/11 cau 4) - khong qua "Xoa ban nhap"
        # chung cua Approval Center (lam nhay so dot da in tren BBNT).
        if frappe.flags.get(FLAG) or frappe.flags.in_patch:
            return
        frappe.throw(_("Chỉ xoá được đợt nghiệm thu nháp cuối, từ thẻ KOL của hợp đồng."))
