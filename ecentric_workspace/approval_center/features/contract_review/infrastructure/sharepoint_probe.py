# Copyright (c) 2026, eCentric and contributors
"""Endpoint DO cho phan SharePoint cua Contract Review - chay tay truoc khi noi vao luong gui.

Vi sao nam o `infrastructure/` chu khong phai `controllers/`: day la cong cu van hanh, va
`test_feature_architecture` cam `controllers/` import `infrastructure/`. Ban dau viet nham vao
controllers - bai test do ngay tren main sau khi merge 14/09. Cac endpoint van hanh khac
(`setup.py`, `activation.py`) cung dat o day, nen cho nay moi la cho dung theo le cua nha.

Vi sao can endpoint do: sandbox cua Claude KHONG goi duoc `graph.microsoft.com`, nen toan bo
phan Graph duoc viet ma chua chay thu lan nao. Do tung buoc tren tenant that roi moi noi vao
luong gui - dot do dau tien (14/09) bat duoc ngay hai loi that.
"""
import frappe

from ecentric_workspace.approval_center.features.contract_review.application.service import (
    BUSINESS_DT, nguoi_duoc_xem)
from ecentric_workspace.approval_center.features.contract_review.infrastructure import (
    sharepoint_sync as sp)


@frappe.whitelist()
def thu_sharepoint(name=None, apply=0):
    """Endpoint DO, danh cho System Manager chay tay truoc khi bat tinh nang.

    Vi sao co ham nay: sandbox cua Claude KHONG goi duoc Microsoft Graph, nen toan bo phan
    Graph duoc viet ma CHUA chay thu lan nao. Thay vi noi vao luong gui roi hy vong, ta do
    truoc tren tenant that: `apply=0` chi kiem nhung thu doc duoc (token, duong dan, danh sach
    nguoi se duoc cap quyen) va KHONG ghi gi len SharePoint; `apply=1` moi thuc su tai mot tep.

    Tra ve tung buoc mot, buoc nao hong thi thay ngay buoc do chu khong phai mot chu "loi".
    """
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(frappe._("Chi System Manager duoc chay phep do nay."), frappe.PermissionError)

    ghi = int(apply or 0) == 1
    bao = {"che_do": "ghi that" if ghi else "chi doc", "buoc": []}

    def buoc(ten, ok, chi_tiet=""):
        bao["buoc"].append({"buoc": ten, "ok": bool(ok), "chi_tiet": str(chi_tiet)[:400]})
        return ok

    try:
        token = sp.wr_sp.get_app_token()
        buoc("lay token app-only", bool(token), "do dai=%d" % len(token or ""))
    except Exception as e:
        buoc("lay token app-only", False, e)
        return bao

    if not name:
        buoc("chon phieu", False, "truyen ?name=EC-CTR-...")
        return bao

    row = frappe.db.get_value(BUSINESS_DT, name, ["name", "requested_by", "approval_request"], as_dict=True)
    if not buoc("doc phieu", bool(row), name):
        return bao

    tep = frappe.get_all("File", filters={"attached_to_doctype": BUSINESS_DT, "attached_to_name": name},
                         fields=["file_name", "file_url"], order_by="creation asc")
    if not buoc("co dinh kem", bool(tep), "%d tep" % len(tep)):
        return bao

    nguoi = nguoi_duoc_xem(name, row)
    buoc("danh sach nguoi se duoc cap quyen", bool(nguoi), ", ".join(nguoi))

    t = chon_tep_office(tep)
    bao["tep_thu"] = t.file_name
    bao["duong_dan_se_dung"] = sp.duong_dan(name, t.file_name)
    if not ghi:
        buoc("DUNG o day (apply=0)", True, "them ?apply=1 de thuc su tai len")
        return bao

    try:
        kq = sp.tai_len(t.file_url, t.file_name, name, token=token)
        buoc("tai len SharePoint", bool(kq.get("item_id")), kq.get("web_url"))
    except Exception as e:
        buoc("tai len SharePoint", False, e)
        return bao
    da = []
    try:
        r = sp.cap_quyen(kq["item_id"], nguoi, token=token)
        da = r["da_cap"]
        chi = ", ".join(da)
        if r["bo_qua"]:
            chi += "  | bo qua (tai khoan dich vu): " + ", ".join(r["bo_qua"])
        buoc("cap quyen sua cho dung nguoi", True, chi)
    except Exception as e:
        buoc("cap quyen sua cho dung nguoi", False, e)
    try:
        sp.ghi_lien_ket(t.file_url, name, kq, da)
        buoc("luu lien ket trong ERP", True, kq.get("web_url"))
    except Exception as e:
        buoc("luu lien ket trong ERP", False, e)
    bao["web_url"] = kq.get("web_url")
    return bao


#: Tep Office mo duoc bang Word/Excel/PowerPoint Online. PDF thi SharePoint chi xem, khong
#: sua duoc - ma muc dich cua ca viec nay la review va comment ONLINE.
DUOI_OFFICE = (".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt")


def chon_tep_office(tep):
    """Chon tep de do: uu tien tep Office, khong lay PDF neu con lua chon khac.

    Lan do dau (14/09) ham nay chua co nen no lay tep cu nhat - dung vao ban PDF, trong khi
    phieu co ca ban .docx. Do xong van khong biet Word Online co mo duoc khong, tuc phep do
    khong tra loi duoc cau hoi no sinh ra de tra loi."""
    for t in tep:
        if (t.file_name or "").lower().endswith(DUOI_OFFICE):
            return t
    return tep[0]


@frappe.whitelist()
def thu_quyen(name=None, apply=0):
    """Do RIENG buoc cap quyen tren tep DA tai len, tach khoi buoc tai len.

    Tach ra vi hai buoc hong vi hai ly do khac han nhau; gop chung thi moi lan thu lai phai
    tai len lai mot lan nua ma khong hoc them duoc gi.

    `apply=0`: CHI DOC - liet ke quyen dang co tren tep. Day la cau tra loi cho "moi nguoi da
    vao duoc san chua", thu quyet dinh buoc cap quyen co can ton tai khong.
    `apply=1`: thu cap quyen that bang createLink scope=users; neu hong thi thu lai voi DUNG
    MOT nguoi de tach bach "app-only khong resolve duoc ai" voi "mot dia chi trong danh sach
    lam hong ca lo".
    """
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(frappe._("Chi System Manager duoc chay phep do nay."), frappe.PermissionError)

    ghi = int(apply or 0) == 1
    bao = {"che_do": "thu cap quyen" if ghi else "chi doc quyen dang co", "buoc": []}

    def buoc(ten, ok, chi_tiet=""):
        bao["buoc"].append({"buoc": ten, "ok": bool(ok), "chi_tiet": str(chi_tiet)[:400]})
        return ok

    lien = frappe.db.get_value("EC SharePoint File Link",
                               {"business_doctype": BUSINESS_DT, "business_name": name},
                               ["name", "sp_item_id", "sp_web_url"], as_dict=True)
    if not lien or not lien.sp_item_id:
        buoc("tim ban ghi lien ket", False,
             "Chua co ban ghi nao cho %s - chay thu_sharepoint?apply=1 truoc." % name)
        return bao
    buoc("tim ban ghi lien ket", True, lien.sp_item_id)
    bao["web_url"] = lien.sp_web_url

    try:
        token = sp.wr_sp.get_app_token()
    except Exception as e:
        buoc("lay token app-only", False, e)
        return bao

    try:
        dang_co = sp.doc_quyen(lien.sp_item_id, token=token)
        bao["quyen_dang_co"] = dang_co
        buoc("doc quyen dang co", True, "%d muc" % len(dang_co))
    except Exception as e:
        buoc("doc quyen dang co", False, e)

    nguoi = nguoi_duoc_xem(name)
    giu, bo = sp.loc_nguoi_that(nguoi)
    buoc("loc tai khoan dich vu", True,
         "cap cho %d nguoi; bo qua: %s" % (len(giu), ", ".join(bo) or "(khong co)"))
    if not ghi:
        buoc("DUNG o day (apply=0)", True, "them ?apply=1 de thu cap quyen that")
        return bao

    try:
        r = sp.cap_quyen(lien.sp_item_id, nguoi, token=token)
        buoc("createLink scope=users cho ca danh sach", True, ", ".join(r["da_cap"]))
        bao["link_chia_se"] = r.get("link")
    except Exception as e:
        buoc("createLink scope=users cho ca danh sach", False, e)
        mot = [frappe.session.user] if frappe.session.user in giu else giu[:1]
        try:
            r1 = sp.cap_quyen(lien.sp_item_id, mot, token=token)
            buoc("thu lai voi DUNG MOT nguoi (%s)" % ", ".join(mot), True,
                 "mot nguoi thi duoc => danh sach co dia chi khong resolve duoc")
            bao["link_chia_se"] = r1.get("link")
        except Exception as e1:
            buoc("thu lai voi DUNG MOT nguoi (%s)" % ", ".join(mot), False,
                 "%s => app-only KHONG cap quyen theo nguoi duoc tren tenant nay" % e1)

    try:
        bao["quyen_sau_khi_cap"] = sp.doc_quyen(lien.sp_item_id, token=token)
        buoc("doc lai quyen sau khi cap", True, "%d muc" % len(bao["quyen_sau_khi_cap"]))
    except Exception as e:
        buoc("doc lai quyen sau khi cap", False, e)
    return bao


