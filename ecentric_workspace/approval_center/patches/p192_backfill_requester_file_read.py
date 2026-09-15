# Copyright (c) 2026, eCentric and contributors
"""Cap bu quyen DOC (DocShare) cho NGUOI DE NGHI cua moi phieu da ton tai (15/09).

Hoan hoi: "cai SIGNED file ay, cac ban trong luong sao khong co quyen mo a?"

DO DUOC TREN PROD, khong phai suy dien:
  * 30 phieu De nghi thanh toan da co ban ky `SIGNED-*.pdf`;
  * nguoi DUYET thieu quyen: 0;
  * nguoi DE NGHI thieu quyen: 30/30. Nam nguoi: dong.diep, hien.nguyen, trong.vo,
    uyen.tran, bao.nguyen.

Co che: `EC Payment Request` co Custom DocPerm cho System Manager + EC Finance, `if_owner=0`.
Nguoi de nghi khong o nhom nao va khong co DocShare, nen ho MO DUOC phieu (duong cua app co
luat rieng) nhung bam vao tep thi cong tep cua Frappe tra 403. Nguoi can ban ky nhat lai la
nguoi duy nhat khong lay duoc no.

Day la LAN THU BA cung mot lop loi: p163 cap bu cho nguoi duyet (08/09), p167 cho nguoi xu ly
(09/09), va ca hai lan deu bo sot chinh chu ho so.

PHAM VI RONG HON p163/p167 - CO Y, va day la ly do:
  Hai patch cu chi dung toi phieu CON MO ("khong moi lai quyen tren ho so da dong"). Cau do
  dung voi chung, va SAI voi ca nay: ban PDF da ky chi sinh ra khi luong da XONG. Gioi han o
  phieu con mo se bo qua dung 30 phieu dang bi loi. Nen o day quet MOI phieu, moi trang thai.
  Khong phai noi rong quyen: `can_view_request` cho nguoi de nghi xem ho so cua chinh minh tu
  dau; patch chi lam cong tep theo kip.

Khong gioi han mot loai phieu nao: loi nam o ham dung chung cua engine nen moi form deu dinh.

KHONG BAO GIO nem loi: patch chay trong migrate, mot exception lam chet ca lan deploy (p116).
"""
import frappe

from ecentric_workspace.approval_center.shared.workflow import transitions


def execute():
    try:
        reqs = frappe.get_all(
            "EC Approval Request",
            fields=["name", "reference_doctype", "reference_name", "requested_by"],
            limit_page_length=0) or []
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p192 cap bu: liet ke phieu THAT BAI")
        return

    cap = bo_qua = 0
    for r in reqs:
        u = r.get("requested_by")
        if not u or u == "Guest" or not r.get("reference_doctype") or not r.get("reference_name"):
            continue
        try:
            # Kiem truoc khi ghi: `_engine_grant_read` cung tu bo qua neu da co, nhung doc
            # truoc thi chay lai patch tren mot site da sach se KHONG sinh mot lenh ghi nao -
            # va con so bao cao moi that ("da cap bao nhieu" chu khong phai "da duyet qua
            # bao nhieu dong").
            if frappe.db.exists("DocShare", {"share_doctype": r["reference_doctype"],
                                             "share_name": r["reference_name"], "user": u}):
                bo_qua += 1
                continue
            transitions._engine_grant_read(r["reference_doctype"], r["reference_name"], u)
            cap += 1
        except Exception:
            # Mot phieu hong khong duoc lam dung ca lan migrate - ghi lai roi di tiep.
            frappe.log_error(frappe.get_traceback(), "p192 cap bu %s" % r.get("name"))

    frappe.logger().info("p192: da cap %s, da co san %s, tong %s phieu" % (cap, bo_qua, len(reqs)))
