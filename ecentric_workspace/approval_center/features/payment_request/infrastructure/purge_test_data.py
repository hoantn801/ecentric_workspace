# Copyright (c) 2026, eCentric and contributors
"""[TEMP-WORKAROUND 2026-09-04] Xoa DU LIEU TEST Payment Request truoc khi go-live.

Hoan yeu cau 04/09: "xoa toan bo payment request, chua ai dung". 27 phieu, tat ca do
hoan.tran / hien.nguyen / Administrator tao trong luc dung ky so.

Bang audit (EC Approval Action, EC Digital Signature Event) la APPEND-ONLY co chu y - on_trash
nem loi. Cong cu nay bo qua bang `frappe.db.delete` (khong qua controller). Do la vi pham co
y thuc, chi chap nhan duoc cho du lieu test truoc go-live, va vi the:

  - CHI xoa phieu cua nhung owner duoc khai (`owners`); gap owner khac -> tu choi CA DOT,
    khong xoa gi. Day la chot bao ve du lieu that neu ai lo bam sau nay.
  - Phai co `confirm` dung cau; `dry_run=1` mac dinh - chi dem va liet ke.
  - HET HAN 2026-09-30: sau ngay do tu choi chay. Go-live xong thi XOA file nay (ghi o
    03_BUGS_AND_NEXT_STEPS.md).
  - Ghi Error Log tieu de "PURGE payment request test data" liet ke ten da xoa (khong tien).
  - Chung tu ben SCTS KHONG xoa duoc qua API - Hoan huy tay tren cong neu muon.

Thu tu xoa: con truoc, cha sau (Event -> DSR -> Placement -> DS File -> Package ->
Action -> Approver -> Level -> Approval Request -> File dinh kem -> Payment Request).
"""
import frappe
from frappe import _
from frappe.utils import getdate, nowdate

PR = "EC Payment Request"
AR = "EC Approval Request"
CONFIRM_PHRASE = "XOA TOAN BO PAYMENT REQUEST TEST"
EXPIRES_ON = "2026-09-30"
DEFAULT_OWNERS = "hoan.tran@ecentric.vn,hien.nguyen@ecentric.vn,Administrator"


def _names(dt, filters):
    return frappe.get_all(dt, filters=filters, pluck="name", limit_page_length=100000)


def _plan(owners):
    prs = frappe.get_all(PR, fields=["name", "owner"], limit_page_length=100000)
    foreign = sorted({p.owner for p in prs if p.owner not in owners})
    pr_names = [p.name for p in prs]
    ars = _names(AR, {"reference_doctype": PR, "reference_name": ["in", pr_names or [""]]})
    pkgs = _names("EC Digital Signature Package",
                  {"business_doctype": PR, "business_name": ["in", pr_names or [""]]})
    dsrs = _names("EC Digital Signature Request", {"package": ["in", pkgs or [""]]})
    plan = {
        "EC Digital Signature Event": _names("EC Digital Signature Event", {"package": ["in", pkgs or [""]]}),
        "EC Digital Signature Request": dsrs,
        "EC Digital Signature Placement": _names("EC Digital Signature Placement", {"package": ["in", pkgs or [""]]}),
        "EC Digital Signature File": _names("EC Digital Signature File", {"package": ["in", pkgs or [""]]}),
        "EC Digital Signature Package": pkgs,
        "EC Approval Action": _names("EC Approval Action", {"approval_request": ["in", ars or [""]]}),
        "EC Approval Request Approver": _names("EC Approval Request Approver", {"approval_request": ["in", ars or [""]]}),
        "EC Approval Request Level": _names("EC Approval Request Level", {"approval_request": ["in", ars or [""]]}),
        AR: ars,
        "File": _names("File", {"attached_to_doctype": PR, "attached_to_name": ["in", pr_names or [""]]}),
        PR: pr_names,
    }
    # su kien khong gan package (vi du UserTokenLinked) GIU LAI - chung khong thuoc phieu nao
    return plan, foreign, {p.name: p.owner for p in prs}


def purge(confirm, dry_run=1, owners=DEFAULT_OWNERS):
    from ecentric_workspace.platform.esign import permissions as perms
    perms.assert_system_manager()
    if getdate(nowdate()) > getdate(EXPIRES_ON):
        frappe.throw(_("Công cụ xoá dữ liệu test đã hết hạn (%s). Xoá file purge_test_data.py.")
                     % EXPIRES_ON)
    owner_set = {o.strip() for o in (owners or "").split(",") if o.strip()}
    plan, foreign, by_owner = _plan(owner_set)
    counts = {dt: len(v) for dt, v in plan.items()}
    if foreign:
        frappe.throw(_("Có Payment Request của người KHÔNG trong danh sách test: %s. Không xoá gì cả.")
                     % ", ".join(foreign))
    if int(dry_run or 0):
        return {"dry_run": True, "counts": counts,
                "payment_requests": [{"name": n, "owner": by_owner[n]} for n in plan[PR]]}
    if (confirm or "").strip() != CONFIRM_PHRASE:
        frappe.throw(_("Sai câu xác nhận. Phải gõ đúng: %s") % CONFIRM_PHRASE)
    deleted = {}
    for dt, names in plan.items():          # dict giu thu tu khai bao: con truoc, cha sau
        if not names:
            deleted[dt] = 0
            continue
        if dt in ("EC Digital Signature Event", "EC Approval Action"):
            # append-only theo thiet ke; bo qua controller CO Y THUC (xem docstring)
            frappe.db.delete(dt, {"name": ["in", names]})
        else:
            for n in names:
                frappe.delete_doc(dt, n, force=True, ignore_permissions=True, delete_permanently=False)
        deleted[dt] = len(names)
    frappe.log_error("PURGE by %s: %s\nPR: %s" % (frappe.session.user, deleted, ", ".join(plan[PR])),
                     "PURGE payment request test data")
    return {"dry_run": False, "deleted": deleted}
