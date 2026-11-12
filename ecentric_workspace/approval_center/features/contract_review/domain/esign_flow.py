# Copyright (c) 2026, eCentric and contributors
"""Quy trinh ky cua mot phieu Contract Review (truong `esign_flow`, chot 12/11/2026 voi anh Hoan
+ chat Ky so, xem ERP Website/THIETKE_ky_so_hop_dong.md).

Gia tri la MA ngan (luu tren phieu, ho so ky chon theo `selector_value`); nhan tieng Viet chi de
hien thi. Id quy trinh / loai chung tu tren cong nam o ho so ky ben nen tang ky so - ERP khong ghi
cung id hay dia chi cong (cong sap chuyen SCTS -> CMC). KHONG dung quy trinh "HD KOL/KOC NEW"
(6DF7FE12): anh Hoan chot 11/11 KOL/KOC va BBNT di WF09.

BBNT tung dot cua hop dong KOL luon di WF09; ho so ky BBNT chon theo `purpose` ("bbnt:<row>"),
khong theo truong nay.
"""
from ecentric_workspace.approval_center.features.contract_review.domain.kol import KOL_CONTRACT_TYPE

LABOR_CONTRACT_TYPE = "Labor / Hợp đồng lao động (EC)"

KOL_WF09 = "kol_wf09"
KOL_PARTNER_SIGNED = "kol_doi_tac_da_ky"
PARTNER_SIGNED = "qd_hd_doi_tac_da_ky"
ACCEPTANCE_3_PARTIES = "bbnt_3_ben"
LABOR = "hd_lao_dong"
OFFLINE = "khong_ky_cong"

LABELS = {
    KOL_WF09: "KOL/KOC – CEO ký rồi đối tác ký (WF09)",
    KOL_PARTNER_SIGNED: "KOL/KOC – đối tác đã ký (WF07)",
    PARTNER_SIGNED: "QĐ/HĐ – đối tác đã ký (WF05)",
    ACCEPTANCE_3_PARTIES: "Biên bản nghiệm thu 3 bên (WF08)",
    LABOR: "Hợp đồng lao động (WF03)",
    OFFLINE: "Không ký trên cổng",
}
FLOWS = tuple(LABELS)
# Quy trinh co doi tac ky tren cong (can ho ten / email / dien thoai nguoi ky phia doi tac).
WITH_PARTNER = (KOL_WF09, ACCEPTANCE_3_PARTIES, LABOR)

DEFAULTS = {KOL_CONTRACT_TYPE: KOL_WF09, LABOR_CONTRACT_TYPE: LABOR}


def default_flow(contract_type):
    """Mac dinh theo loai hop dong; loai khac -> None (nguoi lap phai chon truoc khi gui ky)."""
    return DEFAULTS.get(contract_type)


def apply_default(doc):
    """Dien mac dinh khi o con trong. Gia tri nguoi dung da chon thi giu, TRU KHI no la mac dinh cua
    mot loai hop dong KHAC (doi loai sau khi luu: KOL -> Mua vao thi khong giu WF09 - QC7). Gia tri
    la (sua tay qua API) thi xoa de bat chon lai."""
    cur = doc.get("esign_flow")
    mine = default_flow(doc.get("contract_type"))
    if cur and (cur not in FLOWS or (cur in DEFAULTS.values() and cur != mine)):
        cur = None
    doc.esign_flow = cur or mine
    return doc.esign_flow


def label(code):
    return LABELS.get(code or "", code or "")


def needs_partner(code):
    return code in WITH_PARTNER


def needs_brand(contract_type):
    """Hop dong lao dong khong gan brand."""
    return contract_type != LABOR_CONTRACT_TYPE


def clean_labor(doc):
    """Hop dong lao dong: khong luu gia tri (luong) tren phieu - phieu hien o danh sach / tab Tat ca /
    tom tat cho nguoi duyet; luong chi nam trong tep (QC7)."""
    if doc.get("contract_type") == LABOR_CONTRACT_TYPE:
        doc.contract_value = None


def needs_value(contract_type):
    """Hop dong lao dong khong bat nhap gia tri (luong la thong tin nhay cam, nam trong tep)."""
    return contract_type != LABOR_CONTRACT_TYPE
