# Copyright (c) 2026, eCentric and contributors
"""Mot lan: xoa DUNG cac phieu Clo tao de test sau deploy 24/11/2026 (Hoan cho phep:
"minh cho ban quyen tao test va duyet thu xong xoa (chi xoa ban test do nhe)").

VI SAO LA PATCH (giong p121): `EC Approval Action` la nhat ky chi-ghi-them, on_trash nem loi,
nen API khong xoa duoc - dung nhu thiet ke. Patch chay mot lan, co Patch Log, nam trong git.

PHAM VI: chi cac ten go tay duoi day. Khong bo loc theo ngay / nguoi / tieu de. New Staff
Preparation (neu "Tao lai" sau hotfix Each Group da sinh ra) duoc tim theo `offer_request` =
DUNG ten Offer test, khong theo gi khac. Site khong co cac ten nay -> moi buoc no-op.

TRANG THAI LUC VIET: EC-ADHOC-2026-00003 da xoa do dang qua API (Level / Approver / Watcher /
ToDo / Comment da di, con Action + Notification Log + phieu + ho so duyet). Patch chay tiep
tren trang thai do.

CO CHE: `EC Approval Action` -> frappe.db.delete (append-only). Moi thu khac -> delete_doc
(con dau vet Deleted Document). Con truoc cha; NSP truoc Offer truoc Hiring.
"""
import frappe

#: (doctype nghiep vu, ten) - thu tu xoa. NSP chen vao dau luc chay (tim theo Offer test).
PHIEU_TEST = [
    ("EC Offer Request", "EC-OFFR-2026-00012"),
    ("EC Hiring Request", "EC-HIRE-2026-00019"),
    ("EC Adhoc Approval Request", "EC-ADHOC-2026-00003"),
]

#: Ho so duyet cua tung phieu luc tao (phong khi truong approval_request da bi xoa / doi).
HO_SO_DUYET = {
    "EC-HIRE-2026-00019": "EC-APR-2026-01302",
    "EC-OFFR-2026-00012": "EC-APR-2026-01303",
    "EC-ADHOC-2026-00003": "EC-APR-2026-01304",
}

#: Tep CV gia (PNG 1x1) tai len cho Offer test.
TEP_TEST = ["a1359e7d95"]

OFFER_TEST = "EC-OFFR-2026-00012"

#: Bang con tro toi EC Approval Request (khong ke Action - xu ly rieng).
CON_CUA_HO_SO = (
    ("EC Approval Request Approver", "approval_request"),
    ("EC Approval Request Level", "approval_request"),
    ("EC Approval Request Watcher", "approval_request"),
    ("EC Approval Access Log", "approval_request"),
    ("EC SharePoint Snapshot", "approval_request"),
    ("EC Approval Link Grant", "target_request"),
    ("EC Approval Link", "host_request"),
    ("EC Approval Link", "target_request"),
)


def execute():
    dem = {"phieu": 0, "hanh_dong": 0, "ban_ghi": 0, "bo_qua": 0}
    danh_sach = _nsp_cua_offer_test() + list(PHIEU_TEST)
    for biz, ten in danh_sach:
        ar = HO_SO_DUYET.get(ten)
        if frappe.db.exists(biz, ten):
            ar = frappe.db.get_value(biz, ten, "approval_request") or ar
        elif not (ar and frappe.db.exists("EC Approval Request", ar)):
            dem["bo_qua"] += 1
            continue
        if ar and frappe.db.exists("EC Approval Request", ar):
            _xoa_ho_so_duyet(ar, dem)
        for dt, name in ((biz, ten), ("EC Approval Request", ar)):
            if name:
                _xoa_phu(dt, name, dem)
        _xoa(biz, ten, dem)
        if ar:
            _xoa("EC Approval Request", ar, dem)
        dem["phieu"] += 1
    for f in TEP_TEST:
        _xoa("File", f, dem)
    print("[p520] xoa %d phieu test, %d hanh dong duyet, %d ban ghi khac; bo qua %d."
          % (dem["phieu"], dem["hanh_dong"], dem["ban_ghi"], dem["bo_qua"]))


def _nsp_cua_offer_test():
    if not frappe.db.table_exists("EC New Staff Preparation"):
        return []
    names = frappe.get_all("EC New Staff Preparation", filters={"offer_request": OFFER_TEST},
                           pluck="name") or []
    if names and frappe.db.exists("EC Offer Request", OFFER_TEST):
        # Offer tro toi NSP -> go truoc de xoa NSP khong vap lien ket.
        frappe.db.set_value("EC Offer Request", OFFER_TEST, "new_staff_preparation", None,
                            update_modified=False)
    return [("EC New Staff Preparation", n) for n in names]


def _xoa_ho_so_duyet(ar, dem):
    n = frappe.db.count("EC Approval Action", {"approval_request": ar})
    if n:
        frappe.db.delete("EC Approval Action", {"approval_request": ar})
    dem["hanh_dong"] += n
    for dt, field in CON_CUA_HO_SO:
        if not frappe.db.table_exists(dt):
            continue
        for name in frappe.get_all(dt, filters={field: ar}, pluck="name"):
            _xoa(dt, name, dem)


def _xoa_phu(dt, name, dem):
    for todo in frappe.get_all("ToDo", filters={"reference_type": dt, "reference_name": name},
                               pluck="name"):
        _xoa("ToDo", todo, dem)
    for f in frappe.get_all("File", filters={"attached_to_doctype": dt, "attached_to_name": name},
                            pluck="name"):
        _xoa("File", f, dem)
    for c in frappe.get_all("Comment", filters={"reference_doctype": dt, "reference_name": name},
                            pluck="name"):
        _xoa("Comment", c, dem)
    for nl in frappe.get_all("Notification Log", filters={"document_type": dt, "document_name": name},
                             pluck="name"):
        _xoa("Notification Log", nl, dem)


def _xoa(doctype, name, dem):
    if not name or not frappe.db.exists(doctype, name):
        return
    frappe.delete_doc(doctype, name, force=True, ignore_permissions=True,
                      ignore_on_trash=False, delete_permanently=False)
    dem["ban_ghi"] += 1
