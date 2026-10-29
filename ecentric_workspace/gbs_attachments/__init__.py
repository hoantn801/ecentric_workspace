# Copyright (c) 2026, eCentric and contributors
"""GBS attachments: gui FILE GOC (khong phai link SharePoint) sang boxme.

Vi sao co module nay (29/10/2026): boxme (chi Vu Bich Hoa, nhom "GBS - EC: Doanh
thu chi phi") thong bao ERP cua ho mat du lieu file SharePoint cua EC, nen tu nay
file dinh kem dang link SharePoint bi AUTO-REJECT. Truoc do Step 2 cua Server
Script sync_gbs_so_outgoing / sync_gbs_po_outgoing tao ban ghi File ben boxme tro
toi link SharePoint an danh. Duong gui nhi phan (v17) bi tat tu 06/2026 vi Server
Script khong doc duoc bytes (make_get_request tra text) va tu ma hoa base64 bang
vong lap Python ton CPU.

Module nay chay ngoai sandbox (A48): tai bytes tu SharePoint qua Graph (app-only),
up len boxme bang /api/method/upload_file, xoa ban ghi link SharePoint cu.

Luong:
  Server Script (After Save) -> frappe.call(controllers.api.enqueue_push)
    -> frappe.enqueue(jobs.push_job.run)  (sau commit)
      -> application.push_service.PushOriginalsService.execute()

Nguon su that cho danh sach file van la `attachment_url` cua phieu EC.
"""
