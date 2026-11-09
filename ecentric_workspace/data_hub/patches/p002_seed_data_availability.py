# Copyright (c) 2026, eCentric and contributors
"""p002: seed 52 dong Data availability tu file Excel cua PO (09/11/2026).

Cot: Team | Loai du lieu | San | SharePoint | DW | Power BI | Front can gap. Ten san chuan hoa
("Tiktok" -> "TikTok", avail_domain.norm_platform). Dong (team, loai, san) da co -> GIU NGUYEN (team Data
co the da sua tren trang) - chay lai bao nhieu lan cung duoc. FAIL-SAFE: moi dong trong try, loi -> Error
Log, khong bao gio chan migrate; khong xoa / ghi de du lieu.
"""
import frappe

from ecentric_workspace.data_hub import constants as C

TITLE = "data_hub p002 seed availability"

#: (team, loai du lieu, san, SharePoint, DW, Power BI, Front can gap) - dung thu tu file Excel.
ROWS = """
Commercial|Product|Shopee|1|1|1|0
Commercial|Product|Tiktok|1|1|1|0
Commercial|Product|Lazada|1|1|1|0
Commercial|Orderline|Shopee|1|1|1|0
Commercial|Orderline|Tiktok|1|1|1|0
Commercial|Orderline|Lazada|1|1|1|0
Commercial|Store|Shopee|1|1|1|0
Commercial|Store|Tiktok|1|1|1|0
Commercial|Store|Lazada|1|1|1|0
Commercial|Finance|Shopee|1|1|0|0
Commercial|Finance|Tiktok|1|1|0|0
Commercial|Finance|Lazada|1|1|0|0
Commercial|Product traffic|Shopee|1|1|1|0
Commercial|Product traffic|Tiktok|1|1|1|0
Commercial|Product traffic|Lazada|0|0|0|0
Commercial|Product Rating|Shopee|1|1|0|0
Commercial|Product Rating|Tiktok|1|1|0|0
Commercial|Product Rating|Lazada|0|0|0|0
Commercial|Product assortment|Shopee|1|1|1|0
Commercial|Product assortment|Tiktok|1|1|1|0
Commercial|Product assortment|Lazada|1|1|1|0
Commercial|Live|Shopee|1|1|0|0
Commercial|Live|Tiktok|1|1|0|0
Commercial|Live|Lazada|0|0|0|0
Commercial|Video|Shopee|0|0|0|0
Commercial|Video|Tiktok|0|0|0|0
Commercial|Video|Lazada|0|0|0|0
Commercial|Voucher & Flashsale|Shopee|0|0|0|0
Commercial|Voucher & Flashsale|Tiktok|0|0|0|0
Commercial|Voucher & Flashsale|Lazada|0|0|0|0
Commercial|Shipping fee|Lazada|1|1|0|0
Commercial|Boxme Purchase Order|Boxme|1|1|1|0
Service|Affiliate order|Shopee|1|1|0|0
Service|Affiliate order|Tiktok|0|0|0|0
Service|Affiliate order|Lazada|0|0|0|0
Service|Traffic affiliate|Shopee|1|1|1|0
Service|Traffic affiliate|Tiktok|1|1|1|0
Service|Traffic affiliate|Lazada|0|0|0|0
Service|Affiliate creator orders|Tiktok|0|0|0|0
Service|Affiliate partner orders|Tiktok|0|0|0|0
Media|CPC Ads|Shopee|1|1|0|0
Media|GMV Max|Tiktok|1|1|0|0
Media|Manual Ads|Tiktok|1|1|0|0
Media|CPAS Ads|Shopee|1|1|0|0
Media|CPC Ads Group Camp|Shopee|1|1|0|0
Media|Sponsor Max|Lazada|1|1|0|0
Finance Data|e-Invoice GOV|GOV|1|1|0|0
Finance Data|Finance - Misa|Misa|1|1|0|0
Boxme Data|Stock Report|Oms Boxme|1|1|1|0
Boxme Data|Product|Oms Boxme|1|1|1|1
Boxme Data|Orderline|Omisell|1|1|1|1
Boxme Data|Orderline|Oms Boxme|1|1|1|1
"""


def rows():
    """-> [dict truong DocType] (thuan - test dem duoc 52 dong, khong can frappe)."""
    from ecentric_workspace.data_hub import avail_domain as A
    out = []
    for line in ROWS.strip().splitlines():
        team, dtype, plat, sp, dw, bi, front = [x.strip() for x in line.split("|")]
        out.append({"team": team, "data_type": dtype, "platform": A.norm_platform(plat), "in_sharepoint": int(sp),
                    "in_dw": int(dw), "in_powerbi": int(bi), "front_priority": int(front)})
    return out


def _key(r):
    return (str(r.get("team") or "").strip().lower(), str(r.get("data_type") or "").strip().lower(),
            str(r.get("platform") or "").strip().lower())


def execute():
    try:
        if not frappe.db.exists("DocType", C.AVAIL_DT):
            return
        have = {_key(r) for r in frappe.get_all(C.AVAIL_DT, fields=["team", "data_type", "platform"],
                                                 limit_page_length=0)}
        seed = rows()
    except Exception:
        frappe.log_error(title=TITLE, message=frappe.get_traceback())
        return
    for r in seed:
        if _key(r) in have:
            continue
        try:
            frappe.get_doc(dict(r, doctype=C.AVAIL_DT)).insert(ignore_permissions=True)
            have.add(_key(r))
        except Exception:
            frappe.log_error(title="%s: %s" % (TITLE, "|".join(_key(r))), message=frappe.get_traceback())
