# Copyright (c) 2026, eCentric and contributors
"""Cap bu: phieu Contract Review da gui nhung chua co ban ghi lien ket SharePoint.

VI SAO CAN. Tu 14/09 luong gui da tu dua dinh kem len SharePoint, nhung tu do den 15/09 buoc
LUU LIEN KET nem `NameError: now_datetime` (dong import bi danh roi luc chuyen module sang
`shared/integrations/`). Hau qua la cac phieu gui trong khoang do co tep NAM THAT tren
SharePoint ma ERP khong biet - man hinh chi hien "Mo" thay vi "Mo online". Vi du:
EC-CTR-2026-00014 (tai len 14:31:59 va 14:32:01 deu xanh, chi buoc luu lien ket do).

CACH LAM: KHONG goi Graph ngay trong migrate. Mot lan deploy khong duoc phu thuoc vao viec
mang ra ngoai cong ty co thong hay khong, va `bench migrate` ma treo o mot lenh HTTP la ca lan
deploy treo theo. Patch nay chi DAT VIEC vao hang doi; worker chay sau, va `dong_bo_nen` da tu
nuot moi loi.

Idempotent: chi dat viec cho phieu CO dinh kem va CHUA co ban ghi lien ket nao. Chay lai sau
khi da cap bu xong thi khong con phieu nao thoa dieu kien -> khong dat viec nao.

KHONG BAO GIO nem loi: patch chay trong migrate, mot exception lam chet ca lan deploy (p116).
"""
import frappe

BUSINESS_DT = "EC Contract Review Request"
LINK_DT = "EC SharePoint File Link"
#: Tran an toan. Neu mot ngay nao do con so nay bi cham toi thi co chuyen khac dang xay ra -
#: log se noi ro, va nguoi doc quyet dinh, chu khong de patch lang le quet ca bang.
TRAN = 200


def execute():
    try:
        if not frappe.db.exists("DocType", LINK_DT):
            frappe.log_error("chua co %s -> bo qua" % LINK_DT, "p194 backfill sharepoint")
            return

        co_tep = {r.attached_to_name for r in frappe.get_all(
            "File", filters={"attached_to_doctype": BUSINESS_DT, "attached_to_name": ["is", "set"]},
            fields=["attached_to_name"], limit_page_length=0) if r.attached_to_name}
        if not co_tep:
            frappe.log_error("khong phieu nao co dinh kem", "p194 backfill sharepoint")
            return

        da_co = {r.business_name for r in frappe.get_all(
            LINK_DT, filters={"business_doctype": BUSINESS_DT}, fields=["business_name"],
            limit_page_length=0) if r.business_name}

        # Chi phieu DA GUI: ban nhap chua gui thi luong gui se tu lo khi nguoi dung bam Gui.
        da_gui = {r.name for r in frappe.get_all(
            BUSINESS_DT, filters={"approval_request": ["is", "set"]}, fields=["name"],
            limit_page_length=0)}

        can_bu = sorted((co_tep & da_gui) - da_co)
        if len(can_bu) > TRAN:
            frappe.log_error("co %d phieu can bu, vuot tran %d - chi lam %d dau, chay lai de "
                             "lam tiep" % (len(can_bu), TRAN, TRAN), "p194 backfill sharepoint")
            can_bu = can_bu[:TRAN]

        for ten in can_bu:
            frappe.enqueue(
                "ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror.dong_bo_nen",
                queue="long", enqueue_after_commit=True,
                business_doctype=BUSINESS_DT, business_name=ten)
        frappe.log_error("da dat %d viec cap bu: %s" % (len(can_bu), ", ".join(can_bu) or "(khong)"),
                         "p194 backfill sharepoint")
    except Exception:
        # Thieu ban tren SharePoint thi nguoi duyet van mo duoc tep trong ERP (tai ve), chi
        # mat viec mo online. Khong dang doi bang ca lan deploy.
        frappe.log_error(frappe.get_traceback(), "p194 backfill sharepoint THAT BAI")
