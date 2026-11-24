# Copyright (c) 2026, eCentric and contributors
"""24/11/2026 (PO chot C - claude/thiet-ke-bbnt-tung-dot.md): moi dot nghiem thu (BBNT) cua hop dong
KOL/KOC la MOT phieu `EC KOL Acceptance` voi chuoi duyet rieng.

1. Seed EC Approval Type KOL_ACCEPTANCE (tu seed/approval_types_seed.json).
2. Chep moi dong con `acceptances` (EC Contract Acceptance) cua hop dong sang mot ban ghi EC KOL Acceptance
   (giu so dot, trang thai, tep, han; KHONG tao yeu cau duyet cho dong cu). Danh dau `legacy_row` - chay
   lai thi bo qua dong da chep. Dong con GIU NGUYEN lam lich su (khong xoa du lieu tren prod); truong
   bang con tren form 27 an + chi doc tu ban nay, code khong doc / ghi no nua.
3. Dung KOL_ACCEPTANCE-V1 (Draft) roi bat: L1 Ke toan tong hop = lien.vu@ecentric.vn (PO 24/11 cau 2),
   L2 Ke toan truong + L3 CEO chep tu CONTRACT_REVIEW dang Active. Khong qua validate -> process o Draft,
   ly do o Error Log; System Manager chay lai setup / activate sau.
Moi buoc mot khoi try, ket qua ghi Error Log "p520 bbnt tung dot". Khong nem loi (migrate)."""
import json
import os

import frappe

CODE = "KOL_ACCEPTANCE"
CR_DT = "EC Contract Review Request"
DT = "EC KOL Acceptance"
CHILD_DT = "EC Contract Acceptance"
#: PO 24/11 cau 2 - tham so setup (nguoi cu the), khong nam trong code nghiep vu.
KTTH = "lien.vu@ecentric.vn"
DEFAULTS = {"card_status": "Coming Soon", "process_status": "Building",
            "visibility_mode": "All Internal Users", "legacy_source": "ERP"}
_F = "ecentric_workspace.approval_center.features.kol_acceptance.infrastructure."
_COPY = ("description", "acceptance_date", "amount", "status", "bbnt_file", "signed_file", "completed_at",
         "completed_by", "due_date", "check_note", "verified_by")


def _seed_row():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "seed", "approval_types_seed.json"), encoding="utf-8") as fh:
        return next((r for r in json.load(fh) if r.get("approval_code") == CODE), None)


def _seed_type(ket):
    if frappe.db.exists("EC Approval Type", CODE):
        ket.append("type da co")
        return
    row = dict(_seed_row() or {"approval_code": CODE, "approval_title": "BBNT hợp đồng KOL/KOC"})
    if row.get("category") and not frappe.db.exists("EC Approval Category", row["category"]):
        ket.append("thieu category %s -> bo trong" % row.pop("category"))
    doc = frappe.new_doc("EC Approval Type")
    doc.update(DEFAULTS)
    doc.update(row)
    doc.insert(ignore_permissions=True)
    ket.append("da tao type %s" % CODE)


def migrate_rows():
    """-> (so dong da chep, so dong bo qua). Goi lai an toan."""
    done = skipped = 0
    rows = frappe.get_all(CHILD_DT, filters={"parenttype": CR_DT, "parentfield": "acceptances"},
                          fields=["name", "parent", "idx"] + list(_COPY), order_by="parent asc, idx asc",
                          limit_page_length=0, ignore_permissions=True)
    for r in rows:
        if frappe.db.exists(DT, {"legacy_row": r.name}):
            skipped += 1
            continue
        head = frappe.db.get_value(CR_DT, r.parent, ["name", "contract_no", "creator", "creator_name", "brand",
                                                     "company", "department", "requested_by", "owner"],
                                   as_dict=True)
        if not head:
            skipped += 1
            continue
        values = {k: r.get(k) for k in _COPY}
        if values.get("completed_by") and not frappe.db.exists("User", values["completed_by"]):
            values["completed_by"] = None
        no = int(r.idx or 0)
        doc = frappe.get_doc(dict(values, **{
            "doctype": DT, "approval_type": CODE, "contract": head.name, "round_no": no,
            "contract_no": head.contract_no, "creator": head.creator, "creator_name": head.creator_name,
            "brand": head.brand, "company": head.company, "department": head.department,
            "requested_by": head.requested_by or head.owner, "legacy_row": r.name,
            "request_title": ("BBNT đợt %s - %s - %s" % (no, head.contract_no or head.name,
                                                         head.creator_name or "")).strip(" -")[:140]}))
        doc.flags.ignore_links = True
        doc.insert(ignore_permissions=True)
        done += 1
    return done, skipped


def execute():
    if not frappe.db.exists("DocType", DT):
        return
    ket = []
    try:
        _seed_type(ket)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("type LOI\n" + frappe.get_traceback())
    try:
        done, skipped = migrate_rows()
        ket.append("chep dong BBNT: %s moi, %s bo qua" % (done, skipped))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("chep LOI\n" + frappe.get_traceback())
    try:
        r1 = frappe.get_module(_F + "setup").setup_kol_acceptance_v1(ktth=KTTH, dry_run=0, apply=1) or {}
        ket.append("setup: %s errors=%s warnings=%s notes=%s" % (r1.get("result"), r1.get("errors"),
                                                                 r1.get("warnings"), r1.get("notes")))
        if r1.get("result") != "BLOCKED":
            r2 = frappe.get_module(_F + "activation").activate_kol_acceptance(dry_run=0, apply=1) or {}
            ket.append("activate: %s blockers=%s type=%s" % (r2.get("result"), r2.get("blockers"), r2.get("type")))
    except Exception:
        frappe.db.rollback()
        ket.append("process LOI\n" + frappe.get_traceback())
    frappe.log_error(title="p520 bbnt tung dot", message="\n".join(ket))
