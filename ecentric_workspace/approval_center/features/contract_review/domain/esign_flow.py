# Copyright (c) 2026, eCentric and contributors
"""Quy trinh ky cua mot phieu Contract Review (truong `esign_flow`, chot 12/11/2026 voi anh Hoan
+ chat Ky so).

Gia tri la NHAN nghiep vu (khong phai id quy trinh tren cong): moi gia tri ung voi mot
`EC Digital Signature Profile` ben nen tang ky so, ho so giu id quy trinh / loai chung tu
(cong sap chuyen SCTS -> CMC; ERP khong ghi cung id hay dia chi cong).

  KOL/KOC - CEO ky roi doi tac ky   -> WF09 (anh Hoan chot 11/11; KHONG dung "HD KOL/KOC NEW")
  KOL/KOC - doi tac da ky           -> trinh ky HD KOL/KOC doi tac da ky
  QD/HD - doi tac da ky             -> ky QD/HD, file doi tac da ky
  Bien ban nghiem thu 3 ben          -> BBNT 3 ben
  Hop dong lao dong                  -> HD lao dong (CnB tao -> doi tac ky -> CnB trinh -> CEO ky)
  Khong ky tren cong                 -> ky ngoai, tai ban ky len nhu hien nay

BBNT tung dot cua hop dong KOL luon di WF09 (khong theo truong nay): ho so rieng BBNT_FLOW.
"""

from ecentric_workspace.approval_center.features.contract_review.domain.kol import KOL_CONTRACT_TYPE

LABOR_CONTRACT_TYPE = "Labor / Hợp đồng lao động (EC)"

KOL_CEO_THEN_PARTNER = "KOL/KOC - CEO ký rồi đối tác ký"
KOL_PARTNER_SIGNED = "KOL/KOC - đối tác đã ký"
PARTNER_SIGNED = "QĐ/HĐ - đối tác đã ký"
ACCEPTANCE_3_PARTIES = "Biên bản nghiệm thu 3 bên"
LABOR = "Hợp đồng lao động"
OFFLINE = "Không ký trên cổng"

FLOWS = (KOL_CEO_THEN_PARTNER, KOL_PARTNER_SIGNED, PARTNER_SIGNED, ACCEPTANCE_3_PARTIES, LABOR, OFFLINE)
# Ho so ky cho BBNT tung dot (WF09, chung loai chung tu "Hop Dong KOL/KOC"); khong phai lua chon tren phieu.
BBNT_FLOW = "BBNT KOL/KOC"

DEFAULTS = {KOL_CONTRACT_TYPE: KOL_CEO_THEN_PARTNER, LABOR_CONTRACT_TYPE: LABOR}


def default_flow(contract_type):
    """Mac dinh theo loai hop dong; loai khac -> None (nguoi lap phai chon truoc khi gui ky)."""
    return DEFAULTS.get(contract_type)


def apply_default(doc):
    """Dien mac dinh khi o con trong. Gia tri nguoi dung da chon thi giu. Gia tri la (vd sua tay
    qua API) thi xoa de bat chon lai, khong de ho so ky bi chon theo chuoi rac."""
    cur = doc.get("esign_flow")
    if cur and cur not in FLOWS:
        cur = None
    if not cur:
        cur = default_flow(doc.get("contract_type"))
    doc.esign_flow = cur
    return cur


def needs_brand(contract_type):
    """Hop dong lao dong khong gan brand."""
    return contract_type != LABOR_CONTRACT_TYPE


def needs_value(contract_type):
    """Hop dong lao dong khong bat nhap gia tri (luong la thong tin nhay cam, nam trong tep)."""
    return contract_type != LABOR_CONTRACT_TYPE
