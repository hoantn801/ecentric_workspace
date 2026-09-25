# Copyright (c) 2026, eCentric and contributors
"""Endpoint DO cho phan SharePoint cua Contract Review - chay tay khi can chan doan.

Vi sao nam o `infrastructure/` chu khong phai `controllers/`: day la cong cu van hanh, va
`test_feature_architecture` cam `controllers/` nhac toi `infrastructure/`. Cac endpoint van
hanh khac (`setup.py`, `activation.py`) cung dat o day.

Vi sao van giu sau khi tinh nang da chay: sandbox cua Claude KHONG goi duoc
`graph.microsoft.com`, nen moi thay doi phan Graph deu phai do tay tren tenant that truoc. Ba
lan do dau (14/09) bat duoc ba loi ma doc code khong ra loi nao.
"""
import frappe

from ecentric_workspace.approval_center.shared.integrations import sharepoint_mirror as sp

_DT = "EC Contract Review Request"


def _chan_ngoai_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(frappe._("Chi System Manager duoc chay phep do nay."), frappe.PermissionError)


def _bao(che_do):
    return {"che_do": che_do, "buoc": []}


def _buoc(bao, ten, ok, chi_tiet=""):
    bao["buoc"].append({"buoc": ten, "ok": bool(ok), "chi_tiet": str(chi_tiet)[:400]})
    return ok


@frappe.whitelist()
def thu_sharepoint(name=None, apply=0):
    """`apply=0`: chi kiem nhung thu doc duoc, KHONG ghi gi len SharePoint.
    `apply=1`: dua TAT CA dinh kem cua phieu len - dung dung mot duong voi luong gui that."""
    _chan_ngoai_sm()
    ghi = int(apply or 0) == 1
    bao = _bao("ghi that" if ghi else "chi doc")

    try:
        token = sp.wr_sp.get_app_token()
        _buoc(bao, "lay token app-only", bool(token), "do dai=%d" % len(token or ""))
    except Exception as e:
        _buoc(bao, "lay token app-only", False, e)
        return bao

    if not name:
        _buoc(bao, "chon phieu", False, "truyen ?name=EC-CTR-...")
        return bao
    if not _buoc(bao, "doc phieu", bool(frappe.db.exists(_DT, name)), name):
        return bao

    tep = sp._dinh_kem(_DT, name)
    if not _buoc(bao, "co dinh kem", bool(tep), "%d tep" % len(tep)):
        return bao
    bao["tep"] = [t.file_name for t in tep]
    bao["duong_dan_se_dung"] = sp.duong_dan(_DT, name, tep[0].file_name)

    if not ghi:
        _buoc(bao, "DUNG o day (apply=0)", True, "them ?apply=1 de thuc su tai len")
        return bao

    kq = sp.dong_bo_phieu(_DT, name)
    _buoc(bao, "dua dinh kem len SharePoint", not kq["hong"],
          "xong: %s | hong: %s" % (", ".join(kq["xong"]) or "(khong)",
                                   ", ".join(kq["hong"]) or "(khong)"))
    lien = frappe.get_all(sp.LINK_DT, filters={"business_name": name},
                          fields=["sp_web_url", "sp_last_modified"], limit_page_length=1)
    if lien:
        bao["web_url"] = lien[0].sp_web_url
        _buoc(bao, "luu lien ket trong ERP", True, lien[0].sp_last_modified)
    else:
        _buoc(bao, "luu lien ket trong ERP", False, "khong thay ban ghi nao")
    return bao


@frappe.whitelist()
def thu_quyen(name=None):
    """Liet ke quyen HIEN CO tren tep. CHI DOC - khong cap quyen cho ai.

    Giu lai sau khi da bo buoc cap quyen vi no tra loi duoc mot cau hoi van hay phai hoi:
    "nguoi nay mo khong duoc tep, la do quyen o dau?". Cau tra loi nam o thanh vien site."""
    _chan_ngoai_sm()
    bao = _bao("chi doc quyen dang co")
    lien = frappe.db.get_value(sp.LINK_DT, {"business_doctype": _DT, "business_name": name},
                               ["sp_item_id", "sp_web_url"], as_dict=True)
    if not lien or not lien.sp_item_id:
        _buoc(bao, "tim ban ghi lien ket", False,
              "Chua co ban ghi nao cho %s - chay thu_sharepoint?apply=1 truoc." % name)
        return bao
    _buoc(bao, "tim ban ghi lien ket", True, lien.sp_item_id)
    bao["web_url"] = lien.sp_web_url
    try:
        bao["quyen_dang_co"] = sp.doc_quyen(lien.sp_item_id)
        _buoc(bao, "doc quyen dang co", True, "%d muc" % len(bao["quyen_dang_co"]))
    except Exception as e:
        _buoc(bao, "doc quyen dang co", False, e)
    return bao
