# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the LEGACY /gbs-so-form-v2 Web Page.

This is the GBS Sales Order creation/edit form. /so-form 301-redirects here.
Also the landing page for 'Sua & Submit lai' (?edit=<name>) after a Finance
send-back or a GBS/boxme rejection.

#61 repo-ization (2026-08-03): main_section.html was imported VERBATIM from
live team.ecentric.vn -- main_section == main_section_html, sha-verified -- so
this page stops being site-only. Until now it existed on the server and nowhere
else: a rebuild would have lost it, and nothing in review could see what it
contained. The first sync against unchanged live content MUST return
{"action": "unchanged"}; that is the drift-detection dry run.

The page ships HTML only. Every action it performs (create/edit/submit, the
GBS/boxme push, the resubmit round-trip) is executed by live Server Scripts and
whitelisted endpoints, which this module does not touch."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "gbs-so-form-v2"
NAME = "gbs-so-form-v2"
TITLE = "gbs-so-form-v2"  # exact live title -- required for the first sync to be "unchanged"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# sha256 of main_section.html as it ships in this commit == the live
# main_section_html at import time (01da088994cd5c4479d83b47b7f59b74989cc3721d39554a979de3f01abb6efc).
#
# upsert_web_page REFUSES to write (and changes nothing) when live hashes to
# none of the accepted values. This page has a history of being edited straight
# on the site, so without the lock a stray call to the endpoint below would
# silently revert those edits to whatever the repo happened to hold.
#
# Deliberate update = edit main_section.html, bump BASELINE_SHA256, and move the
# value it replaced into SUPERSEDES_SHA256 -- all in the same commit.
BASELINE_SHA256 = "575b1aae7b6b3e8b0840b33d3401874e1dd076d10503356bcaaaa3e15cb1121a"
SUPERSEDES_SHA256 = (
    # bytes truoc FIX 8 (2026-08-07): file dinh kem cua SO so EC chi len SharePoint
    # theo phien upload, Sales Order chi luu ma phien (ec_attach_session) -> trang
    # /approval doc bang File nen luon "Khong co file dinh kem". Sua: giu lai doi
    # tuong File luc upload va sau khi tao SO thi dinh kem NATIVE
    # (/api/method/upload_file, is_private=1) vao chinh SO. Duong SharePoint giu
    # nguyen. Chi nhanh direct goi ham nay; nhanh gbsrev khong doi hanh vi.
    "5629b18fd902f7e6de40afdba6becd60567b651a3bf12d1977c9398a08f46499",
    # bytes truoc FIX 6a/6b (2026-08-07): sau khi trinh duyet, form dung yen o trang
    # tao (nhanh direct / SO so EC) hoac nhay ve /approval TRONG khong kem id (nhanh
    # gbsrev / GBS SO). Ca hai deu bat nguoi gui tu di tim lai phieu vua tao de xem
    # chuoi duyet va dinh kem -- trong khi /mso-plan-form da mo thang phieu tu
    # 2026-08-05. Sua: mo /approval?id=<ten>&type=so cho SO so EC va
    # /approval?id=<ten>&type=gbs_so cho GBS SO. Nhanh GBS giu nguyen duong cu
    # (/approval khong id) neu backend khong tra ve ten.
    "bd831d4757ee98a44541ff53042c232ce120199cfc6f81fe747fdc2504ddf73e",
    # bytes truoc FIX 5c (2026-08-06): moveBack() tra 3 o (ec-store, transaction_date,
    # delivery_date) ve cho cu bang insertBefore(el, next). Nhung ca 3 duoc chuyen di
    # trong cung mot vong lap nen `next` cua o truoc chinh la o sau -- da bi chuyen
    # noi khac -> insertBefore nem NotFoundError, setMode() chet giua chung va KHONG
    # doi duoc tu "Brand truc tiep" ve "GBS thu Brand". Da bat duoc tren Chrome that:
    # "NotFoundError: Failed to execute 'insertBefore' ... at moveBack ... at setMode".
    # Sua: tra lai theo thu tu nguoc, bo qua moc `next` khong con hop le.
    "6710bce4d4970cba85a00ac83b43a40b4cd31e35e7140d1731c2a425c6b3e076",
    # bytes truoc FIX 5b (2026-08-06): dropdown "Store (Platform)" o so EC hien 92 dong
    # -- 4 san (Shopee/Lazada/TikTok/Khac) CONG 88 store cua GBS/boxme (vd "DUTCHLADY
    # -- Dutchlady (SHP), GBS_FCV, Shopee"). Nguyen nhan la dua vao THU TU tra ve:
    # vong lap dien store boxme append thang vao #ec-store bat ke mode, con loi goi
    # window._ecSyncStoreOptions() ngay sau do bi guard early-return chan lai vi
    # attribute data-ec-store-mode da = 'direct'. Da tai hien tren Chrome that: sau
    # khi append tay 88 option roi goi _ecSyncStoreOptions() -> 93 option. Sua bang
    # tham so force: syncStoreOptions(force) bo qua guard, va cho boxme goi force=1.
    # Nhanh GBS ve lai y het tu window._ecBoxmeStores nen khong doi gi.
    "bde88156516f31b45d738c3da55f9337ed7bc9005d0522d2567a51d672fa1782",
    # bytes truoc FIX 1c (2026-08-06): cung mot loai loi voi `_mt`. Bien `_msoState`
    # duoc GAN ('ok' / 'none') trong doRefreshMso() va DOC trong guard luc submit,
    # nhung khong he duoc khai bao o dau. Block script nay chay "use strict" nen
    # gan vao bien chua khai bao cung nem ReferenceError -> nhanh has_mso cua
    # doRefreshMso() chet ngay dong dau tien, roi thang vao catch va in "Khong kiem
    # tra duoc ngan sach MSO (loi ket noi)" mac du API /api/method/ec_so_budget_check
    # tra ve 200 kem mso=MSO-2026-08-EC. Da xac minh bang cach hook window.fetch
    # tren Chrome that: request 200, body co has_mso=true, nhung o ma van rong.
    # Them dung mot dong `var _msoState = '';`.
    "97739385cf9bcf0bcb59e97d4cee3baf5eeb2ef261ffccfe5c6aed49e3580940",
    # bytes truoc FIX 1b (2026-08-06, cung ngay): bien `_mt` dung trong
    # `refreshMso(){ clearTimeout(_mt); _mt = setTimeout(doRefreshMso,350); }`
    # CHUA BAO GIO duoc khai bao trong file. Doc mot bien chua khai bao nem
    # ReferenceError ngay, nen refreshMso() hong tu dau -> (a) o "MA MSO" khong bao
    # gio duoc dien, va (b) setMode() goi refreshMso() o gan cuoi nen MOI dong dat
    # sau no trong setMode khong chay, ke ca `window.EC_SO_MODE = m` -> khung xem
    # truoc chain o sidebar mac ket o recipe so GBS du dang o che do Brand truc tiep.
    # Da xac minh bang console that tren Chrome: "ReferenceError: _mt is not defined
    # at refreshMso ... at setMode". Them dung mot dong `var _mt = null;`.
    "2f15491dceff1e118eb7caf58baa5064aa250c1f6f72d9fdd19f7ed1b2554679",
    # bytes truoc dot sua 5 diem cua form SO so EC (2026-08-06). Gom:
    #  (1) O "MA MSO" khong hien du MSO da duyet ton tai: truoc day chi goi lai
    #      ec_so_budget_check khi co su kien 'change' tren Brand/Thang. Brand duoc
    #      dien BANG CODE (loadBrands + window._pendingBrand khi khoi phuc nhap,
    #      hoac setMode) thi khong ban su kien nao -> o ma dung yen o trang thai
    #      rong. Ban nay theo doi thang gia tri Brand|Thang|Department moi 600ms.
    #  (2) "Hop dong tham chieu": doctype Contract dang rong (0 ban ghi) nen
    #      dropdown chi con 1 option trong, ec-cb ve ra thanh xam khong chu. Doi
    #      placeholder thanh "Chua co hop dong nao tren he thong".
    #  (3) Khung xem truoc chain o sidebar luon ve theo recipe cua so GBS (ca 11
    #      brand deu la "GBS Finance Only (1 level)") ke ca khi dang o so EC, trong
    #      khi Workflow "EC SO Approval" tren site di 4 cap Manager -> Finance ->
    #      HOF -> CEO voi ec_channel != "GBS". Them nhanh rieng cho MODE 'direct'
    #      (qua window.EC_SO_MODE / window._gbsRenderChain); nhanh GBS giu nguyen.
    #  (4) Bang chon khoan muc o so EC bao "cho load tu boxme" - sai vi so EC lay
    #      item tu master Item qua ec_so_lookups. Doi cau chu theo mode.
    #  (5) "Store (Platform)": brand ban truc tiep (BBT-VN, FES-VN, HNW-VN) khong
    #      co ban ghi Store ben GBS nen dropdown rong. Che do 'direct' nay dung
    #      danh sach san Shopee / Lazada / TikTok / Khac; che do GBS van dung danh
    #      sach boxme (luu o window._ecBoxmeStores va tra lai nguyen ven khi doi
    #      mode). Van dung chung o #ec-store nen rang buoc bat buoc luc submit,
    #      payload ec_store va viec chuyen o len "Thong tin chung" khong doi.
    # Live team.ecentric.vn da duoc ghi thang len BASELINE_SHA256 cung ngay.
    "5762d691ccf31e77810a09e6824b38f74c9f46a687ff84fd8dfaac513bfdede2",
    "252629aa972b5b2c1a18986fb424bb9dfcf526e53d36151ca80b54818f889665",
    "01da088994cd5c4479d83b47b7f59b74989cc3721d39554a979de3f01abb6efc",
    "894d84f7d03ce39664b6edbd319d3803bace6ae3431ed6b907898d11c41d4ed5",
    # bytes truoc khi SIET NGAN SACH THEO TEAM (2026-08-05). Truoc do o ngan sach
    # tren form goi /api/method/ec_so_budget_check chi voi {brand, month} nen so
    # hien ra la tong CA BRAND, trong khi ec_so_before_save v11 da chuyen sang
    # cong tran tu cac dong `MSO Budget Line` cua DUNG team -> man hinh va ket
    # luan luc luu lech nhau. Ban nay gui them team (lay tu #department, chi
    # nhanh MODE==='direct'; nhanh 'gbsrev' giu nguyen brand-wide), in ten team
    # vao dong note xanh va vao cau giai trinh khi vuot tran, va them listener
    # 'change' tren #department goi refreshMso() -- truoc day doi team khong
    # tinh lai ngan sach. Live team.ecentric.vn da duoc ghi thang len
    # BASELINE_SHA256 cung ngay nen sync dau tien o do tra ve "unchanged".
    "ad8f81ea40a4b6a943c481d04e77bffcb2f259beb3b64118712eea3e7d1b5aab",  # pre-team-budget
)


def sync(html=None, force=0):
    """Guarded sync. publish=None never re-publishes a page an operator
    un-published; expect_sha refuses (writes nothing) on live drift.
    force=1 drops only the drift lock -- it never force-publishes."""
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish=None,
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )
    if res.get("action") == "refused":
        return res
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
        from ecentric_workspace.legacy_pages import serving
        res.update(serving.ensure_static_serving(res["name"], html))
    return res


@frappe.whitelist(methods=["POST"])
def sync_gbs_so_form_v2_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /gbs-so-form-v2 page."), frappe.PermissionError)
    return sync()
