# Copyright (c) 2026, eCentric and contributors
"""Idempotent Web Page sync cho Dashboard PnL (giai doan 2: doanh thu + chi phi uoc tinh).

Route /pnl-dashboard. Record Web Page ten `doanh-thu-ecentric` -- Frappe
autoname theo TITLE luc tao, va Web Page KHONG cho rename ("Web Page not
allowed to be renamed"), nen ten record lech khoi slug route. Day la kieu lech
da co tien le tren site (vd /weekly-update -> `bao-cao-tuan`);
page_sync_util.find_web_page() tra theo ca route lan name nen van khop.

Logic nghiep vu KHONG nam trong repo: trang doc du lieu tu HAI Server Script API tren
live, moi API mot bo quyen rieng (ban sao doi chieu o ../server_scripts/):
  - `ec_pnl_data`    doanh thu (Sales Order)                    -> ec_pnl_data.py
  - `ec_pnl_chi_phi` quy luong UOC TINH tu ho so nhan su, headcount, tuyen dung, chi phi
                     Approval Center theo loai, kich ban brand  -> ec_pnl_chi_phi.py
  - `ec_pnl_phi_ql`  phi quan ly gian hang UOC TINH = NMV x bang phi -> ec_pnl_phi_ql.py
                     (11/09/2026) KHONG phai doanh thu co chung tu: ke toan xac nhan
                     REV_QL_TT la phi quan ly cong tren tung goi dich vu, va ra soat
                     toan bo Sales Order thi khong ma item nao la phi theo % NMV. Khoi
                     nay nam RIENG tren trang, co canh bao do, va KHONG duoc cong vao
                     tong doanh thu.
Hai DocType custom di kem (tao tren live qua REST, dinh nghia trong header cua
ec_pnl_chi_phi.py): `EC Nhan Su Brand` (ty trong nhan su x brand) va `EC Loai Chi Phi`
(danh muc loai chi phi cho de nghi thanh toan).
"""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util
from ecentric_workspace.legacy_pages import serving

ROUTE = "pnl-dashboard"
NAME = "doanh-thu-ecentric"
# 10/09/2026: doi tu "Doanh thu eCentric" sang "PnL eCentric" theo Hoan. Trang gio co ca
# chi phi va loi nhuan chu khong con rieng doanh thu. Tren site da doi truc tiep cung
# ngay, nen KHONG can patch rieng: p175 (da chay) goi sync() va se dat dung ten nay tren
# bat ky site nao dung lai tu dau.
TITLE = "PnL eCentric"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "frontend", "pnl_dashboard.main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# --- drift lock ---------------------------------------------------------------
# sha256 cua dung khoi HTML commit nay ship. Da doi chieu bang voi
# main_section_html tren team.ecentric.vn luc commit, nen lan sync dau tien sau
# khi deploy phai tra ve "unchanged".
#
# Sua co chu dich = sua file frontend, bump BASELINE_SHA256 sang sha moi, va day
# gia tri cu xuong SUPERSEDES_SHA256 -- tat ca trong CUNG mot commit.
BASELINE_SHA256 = "03c4588e53e4d732df1e72f79bd0338134e648131ec6fb6282d1f26d860de99b"
SUPERSEDES_SHA256 = (
    "d7803811ea6df96756f58a090178e04ca3110f839d5dfb12cff029ab8a7acca9",   # ban dau 2026-08-10
    "1936ee8870e35ae3b31eb4b7bbf2de2338f560754d44b0e6de9a49fb1cd8c812",   # sau khi Viet hoa thong bao tu choi quyen
    "91148d93594d80c010335c88f8b57cb1495b83d85055ca7b34dcb12fab12d907",   # sau khi vao dung contract luoi ERP shell
    "2452ea70cdeae38065739e83bd440a39b7ba4350d299d9b8ca933a8c4b3e4daa",   # sau khi siet quyen ve phong Management
    "2b5e41f5cbb09d130a80a4891d8698beaf1d64bf8d273a759f21d3fbcaedc5e2",   # sau khi lap day chieu ngang man rong
    "2ccce1d24666bd8ab432f8d45c84f115ec3f8e3fba7dc35497dc3e627ff65152",   # sau khi them nut chon moc thoi gian
    "3c2df2eff26ac553d7e4767eaaa72429fc5f9c24c390e81b99f5d3db90139333",   # ban chi co doanh thu (den 07/09)
    "0b289ae6adcdb72f1d5ed16f2fea55fc9364867bd72aa7ca7af4fff6954ea697",   # 08/09: them khoi Chi phi & loi nhuan (uoc tinh)
    "cdebf00ba1849f05dff69b6b4295ed945aca2af92647134a73940e32f3826165",   # 08/09: quy luong gom them luong du an
    # 09/09: chi phi khac gom theo NHOM / khoan muc tu `EC Loai Chi Phi`, canh bao phieu
    # chua phan loai, va khong cong khoan da tinh o khoi luong (chong dem trung).
    "2c8ebf6531240e3ea75fc4b3c02a5633f076183a512b101edd744ed6ec235339",   # 11/09: them khoi Phi quan ly gian hang (tinh tu NMV)
    "0350560847337792dc3508e6b997e2bfbe9e823543c89ddfcc50b5eb158a9558",   # 11/09: ban dau cua khoi phi QL, thieu ve lai sau khi doanh thu ve
    "193f5d22e6ad9b2dbfb963dca3a5e983a5d78b530e5f7802a320dea0a3e4fd5b",   # 11/09: ban con so sanh lech ky (phi 1 thang / doanh thu 5 thang)
    "3bdd15917f74aadf4092194fb690de268247515ea96ded556d8080ad90f3bcf4",   # 11/09: truoc khi chia trang thanh 5 dashboard
    "9e48d88bb1a26add829abcac0353634c9f89b40e689fd25ab22ab9f2ba44c0bc",   # 11/09: 5 tab, truoc khi bat thang thieu chi phi
    "a7dfd01ccfe7a80411cc797fc86cf3571eb5c4f29085ffe77c87b3c6915067c2",   # 11/09: truoc khi them 3 bieu do co cau
    "c55d0de1f8991c83d3321bc46f823b972a03474d272817e8c8d04bdea7cc91f5",   # 11/09: truoc khi hoan ve bieu do an + tu dong ap dung bo loc
    "4221252402f668363b4aef1db2c6f76f9a93e8ab4b1b412efb19fb821a6c5cbc",   # 11/09: truoc khi gan tab vao hash (sidebar phu cua trang)
)


def sync(html=None, force=0):
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish="preserve",
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )
    if res.get("action") != "refused" and res.get("name") \
            and frappe.db.exists("Web Page", res["name"]):
        # HTML thuan, khong co token Jinja -> phuc vu tinh (dynamic_template=0)
        # de website cache an duoc, giong cac trang legacy khac.
        res.update(serving.ensure_static_serving(res["name"], html))
    return res


@frappe.whitelist(methods=["POST"])
def sync_pnl_dashboard_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the PnL Dashboard page."), frappe.PermissionError)
    return sync()
