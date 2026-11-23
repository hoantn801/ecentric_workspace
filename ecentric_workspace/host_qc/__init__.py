# Copyright (c) 2026, eCentric and contributors
"""AI Host QC - phan ERP (dot 1, 24/11/2026). Spec: C:\\dev\\eCentric AI Live\\HostQC\\host_qc_erp_spec_2311.md.

ERP la dau nao: giu cau hinh phien + bang nguong, nhan ket qua tu app tren may studio, cho QC duyet,
cham lai diem. Tach biet hoan toan voi eLive (EC AI Live *) - anh Vinh chot.

Cay thu muc (frappe-rules, gom trong module - anh Vinh chot 24/11):
    constants/      ten DocType, trang thai, role, thong diep, hang so luat
    repositories/   NOI DUY NHAT goi frappe.db / frappe.get_doc
    services/       1 file = 1 use-case, entry execute()
    api/v1.py       NOI DUY NHAT co @frappe.whitelist (+ _envelope, _guard)
    doctype/ page/  Frappe khoa vi tri
    patches/ seeds/ role + 13 ma luat khoi tao
"""
