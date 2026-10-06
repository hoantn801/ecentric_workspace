# Copyright (c) 2026, eCentric and contributors
"""Sua du lieu sau hai loi engine tim ra 06/10/2026 (code da sua cung dot).

1. Administrator bi giai vao luong duyet: tu 05/10 13:10 Administrator mang role EC CnB / HOF /
   CEO / Finance, nen moi phieu gui tu do co mot ghe "Pending" cua Administrator. Engine nay
   da loai Administrator (_is_active_system_user). Patch: ghe Pending cua Administrator tren
   cac phieu CON MO -> Skipped (co ghi lich su). Khong dong vao ghe da quyet dinh.

2. Gui lai sau "yeu cau bo sung" khong ap lai luat trung-nguoi: EC-SPBN-2026-00006
   (EC-APR-2026-00567) - lan dau cap Quan ly truc tiep (anh Lam) duoc bo qua vi anh duyet o cap
   CEO; CnB tra lai, Vinh gui lai -> anh Lam bi bat duyet cap 1. Engine da sua (resubmit ap lai
   luat). Patch: ap lai DUNG luat do cho phieu nay, dong ToDo cap 1 cua anh Lam, di tiep sang
   CnB. Chi phieu nay (lap danh sach tay, da do 06/10) - hai phieu Contract Review test cua
   Hoan cung dang ket the nhung khong tu day di de khoi ban thong bao cho phieu test.
Idempotent; moi phan mot try; ket qua ghi Error Log. KHONG nem loi."""
import frappe
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.shared.workflow import transitions as T

_FIX_RESUBMIT = ("EC-APR-2026-00567",)
_OPEN = ("Pending", "Information Required")


def _bo_administrator(ket):
    rows = frappe.get_all("EC Approval Request Approver",
                          filters={"approver": "Administrator", "status": "Pending"},
                          fields=["name", "approval_request", "level_no"]) or []
    n = 0
    for r in rows:
        if frappe.db.get_value("EC Approval Request", r.approval_request, "approval_status") not in _OPEN:
            continue
        frappe.db.set_value("EC Approval Request Approver", r.name,
                            {"status": "Skipped", "decided_at": now_datetime()})
        T.log_action(r.approval_request, "Skipped", "Administrator", r.level_no,
                     comment="Administrator khong phai nguoi duyet (sua 06/10)",
                     related_user="Administrator", previous_status="Pending", new_status="Skipped")
        n += 1
    ket.append("Bo %d ghe Administrator dang Pending" % n)


def _ap_lai_luat(name, ket):
    req = frappe.get_doc("EC Approval Request", name)
    if req.approval_status != "Pending":
        ket.append("%s: khong con Pending (%s) - bo qua" % (name, req.approval_status))
        return
    cur = req.current_level
    T._skip_earlier_duplicate_levels(req, from_level=cur)
    if not T._is_level_skipped(req.name, cur):
        ket.append("%s: cap %s khong thuoc dien bo - giu nguyen" % (name, cur))
        return
    # Cap nay DA kich hoat (co ToDo + dong ho SLA cua anh Lam) - dong ca hai, khong de dong ho
    # chay thanh "Missed" cho mot cap khong con ton tai.
    for u in frappe.get_all("EC Approval Request Approver", pluck="approver",
                            filters={"approval_request": name, "level_no": cur}) or []:
        try:
            T._sla().on_approver_removed(request_doctype=req.reference_doctype,
                                         request_name=req.reference_name, level_no=cur, user=u,
                                         reason="Bo qua cap trung nguoi duyet (sua 06/10)")
        except Exception:
            ket.append("%s: SLA %s loi (bo qua)" % (name, u))
    T.close_todos(req.reference_doctype, req.reference_name)
    T._advance_past_level(frappe.get_doc("EC Approval Request", name), cur)
    ket.append("%s: bo cap %s, di tiep cap %s" % (
        name, cur, frappe.db.get_value("EC Approval Request", name, "current_level")))


def execute():
    ket = []
    try:
        _bo_administrator(ket)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("LOI bo Administrator\n" + frappe.get_traceback())
    for name in _FIX_RESUBMIT:
        try:
            _ap_lai_luat(name, ket)
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            ket.append("LOI %s\n%s" % (name, frappe.get_traceback()))
    frappe.log_error(title="p266 sua gui lai bo qua cap trung", message="\n".join(ket))
