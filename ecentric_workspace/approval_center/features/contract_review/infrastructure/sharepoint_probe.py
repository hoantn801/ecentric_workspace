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

from ecentric_workspace.approval_center.features.contract_review.domain import kol
from ecentric_workspace.approval_center.shared.integrations import sharepoint_mirror as sp

_DT = "EC Contract Review Request"


def _chan_ngoai_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(frappe._("Chi System Manager duoc chay phep do nay."), frappe.PermissionError)


def _phuong_thuc():
    req = getattr(frappe.local, "request", None)
    return (getattr(req, "method", None) or "").upper()


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
    if ghi and _phuong_thuc() != "POST":
        # 03/11/2026: Frappe ROLLBACK cuoi moi request GET. `apply=1` qua GET (dan URL vao trinh
        # duyet, hay mot <img src> tren trang khac khi SM dang dang nhap) = tep DA len SharePoint
        # nhung ban ghi EC SharePoint File Link bi rollback -> lan dong bo sau tai them mot ban.
        _buoc(bao, "apply=1 phai goi bang POST", False,
              "GET bi rollback cuoi request - dung POST (vd fetch voi X-Frappe-CSRF-Token)")
        return bao

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
    try:
        # Lao dong / KOL chua cau hinh thu muc han che -> duong_dan nem (26/11).
        bao["duong_dan_se_dung"] = sp.duong_dan(_DT, name, tep[0].file_name)
    except Exception as e:
        _buoc(bao, "phieu duoc dua len SharePoint", False, e)
        return bao

    if not ghi:
        _buoc(bao, "DUNG o day (apply=0)", True, "them ?apply=1 de thuc su tai len")
        return bao

    kq = sp.dong_bo_phieu(_DT, name)
    _buoc(bao, "dua dinh kem len SharePoint", not kq["hong"],
          "xong: %s | giu ban song: %s | hong: %s" % (
              ", ".join(kq["xong"]) or "(khong)",
              ", ".join(kq.get("giu_ban_song") or []) or "(khong)",
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


# --------------------------------------------------------------------------- #
# DONG BO LAI HOP DONG KOL (26/11/2026, PO Hoan, "huong 2" - thu muc han che).
#
# KHONG phai patch tu chay khi migrate: IT phai dung thu muc + ngat ke thua quyen TRUOC. Chay tay
# sau khi IT bao xong: goi mot lan voi dry_run=1 (mac dinh) de xem thu muc da dat chua + danh sach
# phieu, roi POST dry_run=0 de xep viec. `dong_bo_nen` idempotent - goi lai khong tao ban trung.
# --------------------------------------------------------------------------- #
@frappe.whitelist()
def dong_bo_lai_kol(dry_run=1, trang_thai=None, limit=500):
    """Liet ke hop dong KOL DANG MO co dinh kem chua co ban SharePoint; dry_run=0 thi xep viec dong bo.

    CHI System Manager. `dry_run=1` (mac dinh): chi DOC (quyen thu muc + danh sach phieu), khong ghi
    gi, khong xep viec. `dry_run=0`: bat buoc POST (GET bi rollback) va thu muc phai AN TOAN o lan
    kiem tuoi ngay luc goi - khong thi khong xep viec nao.
    `trang_thai`: danh sach trang thai phieu duyet, cach nhau dau phay (mac dinh: con cho duyet)."""
    _chan_ngoai_sm()
    chay_that = str(dry_run).strip().lower() in ("0", "false", "no")
    bao = _bao("ghi that" if chay_that else "chay thu (khong ghi)")
    thu_muc = sp._thu_muc_cau_hinh(sp.THU_MUC_HAN_CHE[_DT][2])
    if not _buoc(bao, "site_config %s" % sp.THU_MUC_HAN_CHE[_DT][2], bool(thu_muc),
                 thu_muc or "chua cau hinh - KOL giu nguyen khong len SharePoint"):
        return bao
    bao["thu_muc"] = thu_muc
    ok, ly_do, quyen = sp.kiem_quyen_thu_muc(thu_muc)
    sp.ghi_nho_an_toan(thu_muc, ok, ly_do)
    bao["quyen_thu_muc"] = quyen
    _buoc(bao, "thu muc ton tai + chi co quyen rieng", ok, ly_do or "dat")
    tt = tuple(t.strip() for t in str(trang_thai or "").split(",") if t.strip()) or sp.TRANG_THAI_CON_CHO
    phieu = kol_chua_len_sharepoint(tt, int(limit or 500))
    bao["phieu"] = phieu
    _buoc(bao, "phieu KOL (%s) chua co ban SharePoint" % ", ".join(tt), True, "%d phieu" % len(phieu))
    if not chay_that:
        _buoc(bao, "DUNG o day (dry_run=1)", True, "POST dry_run=0 de xep viec dong bo")
        return bao
    if _phuong_thuc() != "POST":
        _buoc(bao, "dry_run=0 phai goi bang POST", False, "GET bi rollback cuoi request")
        return bao
    if not ok:
        _buoc(bao, "khong xep viec: thu muc chua an toan", False, ly_do)
        return bao
    xep = []
    for r in phieu:
        frappe.enqueue(
            "ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror.dong_bo_nen",
            queue="long", business_doctype=_DT, business_name=r["name"], enqueue_after_commit=True)
        xep.append(r["name"])
    _buoc(bao, "xep viec dong bo", True, ", ".join(xep) or "(khong co phieu nao)")
    return bao


def kol_chua_len_sharepoint(trang_thai, limit=500):
    """[{name, trang_thai, tep_thieu}] - phieu KOL co phieu duyet o `trang_thai` va co dinh kem (tru
    ban doi chung) chua co ban ghi lien ket SharePoint CUA CHINH phieu do. Chi doc."""
    ra = []
    for r in frappe.get_all(_DT, filters={"contract_type": kol.KOL_CONTRACT_TYPE,
                                          "approval_request": ["is", "set"]},
                            fields=["name", "approval_request"], order_by="creation desc",
                            limit_page_length=0) or []:
        tt = frappe.db.get_value("EC Approval Request", r.get("approval_request"), "approval_status")
        if tt not in trang_thai:
            continue
        tep = sp._dinh_kem(_DT, r.get("name"))
        if not tep:
            continue
        co = set(frappe.get_all(sp.LINK_DT, filters={"business_doctype": _DT,
                                                     "business_name": r.get("name"),
                                                     "sp_item_id": ["is", "set"]},
                                pluck="file_url") or [])
        thieu = [t.get("file_name") for t in tep if t.get("file_url") not in co]
        if thieu:
            ra.append({"name": r.get("name"), "trang_thai": tt, "tep_thieu": thieu})
            if len(ra) >= limit:
                break
    return ra
