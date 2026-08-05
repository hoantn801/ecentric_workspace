# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the LEGACY /mso-plan-form Web Page.

This is the MSO plan creation/edit form. Reached from the sidebar ('MSO
Request') and from /approval when a KAM opens an MSO for editing; /mso-form
301-redirects here.

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

ROUTE = "mso-plan-form"
NAME = "mso-plan-form"
TITLE = "MSO Plan Form"  # exact live title -- required for the first sync to be "unchanged"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# sha256 of main_section.html as it ships in this commit == the live
# main_section_html at import time (5adb8dc45511b2182cfa4a1d64648f07377247239c85c79e0c0f714e3c9d60b2).
#
# upsert_web_page REFUSES to write (and changes nothing) when live hashes to
# none of the accepted values. This page has a history of being edited straight
# on the site, so without the lock a stray call to the endpoint below would
# silently revert those edits to whatever the repo happened to hold.
#
# Deliberate update = edit main_section.html, bump BASELINE_SHA256, and move the
# value it replaced into SUPERSEDES_SHA256 -- all in the same commit.
BASELINE_SHA256 = "bed58f7c2907097d4641cbaaaeb7227a007628911fa05e5c191fe6efa19bd8ee"
SUPERSEDES_SHA256 = (
    # bytes ban dau khi repo-hoa trang nay (#61). Live tren team.ecentric.vn da
    # duoc ghi thang len BASELINE_SHA256 ngay 2026-08-04 (round feedback MSO 1:
    # bo Channel, GMV -> NMV, preview chuoi duyet doc tu ec_mso_lookups.chain),
    # nen sync dau tien o do tra ve "unchanged"; entry nay de cac moi truong
    # chua nhan ban ghi do van sync tien len duoc.
    "5adb8dc45511b2182cfa4a1d64648f07377247239c85c79e0c0f714e3c9d60b2",
    # bytes cua round feedback MSO 1 truoc khi sua lai card "Chuoi duyet"
    # (fb round 1b, 2026-08-04). Ban render fb#3 nhet ten cap + email + ghi chu
    # thanh 3 con flex ngang nhau trong .cp-step (display:flex), cot email co lai
    # ~40px, cong word-break:break-all -> email bi be theo tung ky tu
    # ("lam.n / guyen / @ece / ntric.v / n"). Ban nay quay lai dung khung san co
    # cua trang (.cp-num + .cp-step-info), doi sang word-break:break-word +
    # overflow-wrap:anywhere, va cap nao co nhieu nguoi (Finance dang 4 nguoi) thi
    # hien bubble chu cai dau, tro chuot vao ra full mail -- giong cach lam o
    # trang duyet. Live team.ecentric.vn da duoc ghi thang len BASELINE_SHA256
    # cung ngay nen sync dau tien o do tra ve "unchanged".
    "eddcf6d7522c5bf210894d9c26f0c38d760823d5498afc7530a5b81534f2d6f0",
    # bytes truoc round feedback MSO 2 (2026-08-04): round do BO HAN loai phi
    # '% GMV' / '% NMV' khoi form. KAM go thang so tien vao o Amount; may chu
    # khong con tinh amount = fee_percent * forecast_gmv / 100 nua (nhanh do da
    # bi go khoi ec_mso_before_save v3.5). Bang ngan sach mat 2 cot 'Loai phi'
    # va '%'. Live team.ecentric.vn da duoc ghi thang len BASELINE_SHA256 cung
    # ngay nen sync dau tien o do tra ve "unchanged".
    "161cd7a8dfa5273cb9720de650deb7a31ab3116c296e240d96c7d9bad3e38ab7",  # pre-mso-fb-2
    # bytes truoc round feedback MSO 3 (2026-08-05): dong dau tien cua dropdown
    # Team / Khoan muc la <option value=""></option> -- value rong VA text rong,
    # trinh duyet ve ra mot dong trang o dau danh sach. Round nay dat nhan that
    # ("-- Chon team --" / "-- Chon khoan muc --") va them script
    # ec-mso-searchable-dropdowns: combobox co o tim kiem dung dung mau UI/UX cua
    # ec-gbs-searchable-dropdowns tren /gbs-so-form-v2 va /gbs-po-form-v2, ap dung
    # cho #brand va 3 cot Team / Nhom / Khoan muc. Select goc van nam trong DOM
    # (an di) va van nhan value nen readRows()/fillCats()/submit khong doi. Live
    # team.ecentric.vn da duoc ghi thang len BASELINE_SHA256 cung ngay nen sync
    # dau tien o do tra ve "unchanged".
    "51135084243aa8819a56c6e4776dc99c142ecdcdf28e052fc8f1ffc43bc3ad38",  # pre-mso-fb-3
    # bytes cua ban combobox v1 (2026-08-05, cung ngay). v1 con 2 loi UI:
    # (1) o hien thi la <input readonly> nen dinh .f-control[readonly] ->
    # background var(--bg) + color var(--muted), o DA CHON cung bi to xam nhu
    # o khong nhap duoc; (2) panel dat position:absolute trong o cua bang nen
    # bi .bl-wrap{overflow-x:auto} (media max-width:1024px) cat cut danh sach.
    # v2 ghi de lai mau cho [readonly] (chi o CHUA chon moi xam) va doi panel
    # sang position:fixed render o document.body, tu lat len tren khi thieu
    # cho, cong tooltip khi chu bi cat ngang. Live team.ecentric.vn da duoc ghi
    # thang len BASELINE_SHA256 cung ngay nen sync dau tien o do tra ve
    # "unchanged".
    "9afb4ae3369be56ccd368ba5f246de5d4bef317f8e634351377573368c7a74b2",  # mso-fb-3 v1
    # bytes cua ban combobox v2 (2026-08-05, cung ngay). v2 van chua het loi "o
    # bi to xam": v2 gan class f-control cho o hien thi (de .field.has-error
    # .f-control cua validate() con chay) va ghi de mau bang selector class
    # .ec-cb .ec-cb-display[readonly]. Nhung chinh trang nay, khoi "Phase 8.14 --
    # Form polish fixes", co rule
    #     #ec-shell .f-control[readonly] { background:#f3f4f6 !important;
    #       color:#9ca3af !important; cursor:not-allowed !important;
    #       border-style:dashed !important }
    # vua co #id vua co !important -> moi selector class deu thua, o DA CHON van
    # xam + vien dut. v3 khong leo thang !important ma bo goc re: o hien thi doi
    # tu <input readonly> sang <button type="button">, khong con thuoc tinh
    # readonly nen rule tren khong con khop; .value/.placeholder doi sang
    # .textContent + bien curPlaceholder. Live team.ecentric.vn da duoc ghi thang
    # len BASELINE_SHA256 cung ngay nen sync dau tien o do tra ve "unchanged".
    "11c71d930fd836b22150b27cae7fc8261a5d36f2905c4e90f3b69e963ccf61d9",  # mso-fb-3 v2
    # bytes cua ban combobox v3 (2026-08-05, cung ngay). v3 chua het xam nhung
    # de lo mot he qua: bang .bl-table dung table-layout mac dinh (auto), be rong
    # cot phu thuoc noi dung. O hien thi cu la <input> nen be rong noi tai nho,
    # bang tu can bang; doi sang <button> thi be rong noi tai = do dai chu, cot
    # "Khoan muc" (REV_MKT_PACKAGES -- Goi Marketing TMDT (GBS thu brand)...)
    # phinh ra va day 2 cot Amount / Ghi chu tran ra ngoai khung. v4 dat
    # table-layout:fixed cho .bl-table -- be rong lay dung theo % da khai san o
    # <th> -- va can lai ty le cot 15/15/32/18/17/3 cho khop noi dung that. Chu
    # dai bi cat da co ellipsis + tooltip khi ro chuot san tu v2. Live
    # team.ecentric.vn da duoc ghi thang len BASELINE_SHA256 cung ngay nen sync
    # dau tien o do tra ve "unchanged".
    "a3589bd4e64ffb97f62a9771a52374093567d20dd596dcd220ab7d20f6301196",  # mso-fb-3 v3
    # bytes cua ban v4 (2026-08-05, cung ngay). v4 khoa be rong cot nhung cot
    # "Khoan muc" van hep vi bang phai chia cho ca cot "Team". v5 BO HAN cot Team
    # khoi bang ngan sach: team cua mot dong duoc quyet dinh boi hang tieu de nhom
    # ma dong do nam duoi, va moi hang tieu de team gio co nut "+ Them dong" ben
    # phai de them dong thang vao dung team do. Gia tri team van di theo dong qua
    # o an <input type="hidden" class="bl-team"> nen readRows() / validate() /
    # payload() / saveDraft() doc y nguyen, khong phai sua. Bang con 5 cot voi ty
    # le 17/40/20/20/3 -- cot Khoan muc rong tu 32% len 40%. He qua chap nhan:
    # khong doi team cua mot dong tai cho duoc nua, phai xoa dong roi them lai o
    # nhom dung. Nut duoi bang doi nhan thanh "+ Them dong chua gan team" va tao
    # dong o nhom "Khac". Live team.ecentric.vn da duoc ghi thang len
    # BASELINE_SHA256 cung ngay nen sync dau tien o do tra ve "unchanged".
    "4871550ecf514c2675185822f4d41506cec395c2bc53d4706b47c61d59aafa9e",  # mso-fb-3 v4
    # bytes cua ban v5 (2026-08-05, cung ngay). v5 bo cot Team nen team cua mot
    # dong hoan toan do hang tieu de quyet dinh -- nhung prefillTemplate() chi
    # dung hang tieu de cho team NAO CO item mac dinh (ec_mso_default), tren live
    # la 4 team: Media 3, Service 3, E-commerce Operation 2, Production 1. Bon
    # team con lai (Merchandise Content & Design / Operation Data & System / HR /
    # Finance & Accounting) khong co hang tieu de nao -> khong con cach nao cap
    # ngan sach cho ho. Cong voi ec_so_before_save v11 (siet tran theo team) thi
    # tran cua 4 team do = 0 va moi SO cua ho deu Out of Budget + bat giai trinh.
    # v6 dung hang tieu de cho DU 8 team trong LK.teams ke ca team chua co khoan
    # muc mac dinh; team khong dung thi de trong, dong trong/0 tu bo qua khi gui.
    # Nhom "Khac" (team rong) chi hien khi that su co item mac dinh khong gan
    # team, khong con tu bay ra mot hang tieu de rong. cleanupHeads() giu san
    # hang tieu de cua team nam trong LK.teams nen 8 hang nay khong bi don di.
    # Live team.ecentric.vn da duoc ghi thang len BASELINE_SHA256 cung ngay nen
    # sync dau tien o do tra ve "unchanged".
    "c642c7847d6a042e3fd6f08795272f64cf10b7596a7ce43b9618a1b6ec9b6f2d",  # mso-fb-3 v5
    # bytes cua ban v6 (2026-08-05, cung ngay). v7 BO NOT cot "Nhom": nhom cua
    # mot khoan muc da duoc quy dinh san o Item (item_group) nen bat KAM chon lai
    # vua thua vua de chon lech voi Item. Dropdown "Khoan muc" gio gom CA HAI
    # nhom (LK.items_ops + LK.items_fee) trong mot danh sach; nhom cua dong duoc
    # suy ra tu khoan muc qua map GRP_OF va ghi vao o an <input type="hidden"
    # class="bl-group"> nen readRows() / recompute() / payload() / saveDraft()
    # doc y nguyen, khong phai sua. Listener 'change' doi tu .bl-group sang
    # .bl-cat (goi syncRowGroup + recompute); upgradeRows() cua combobox khong
    # con nham .bl-group nua vi no khong con la <select>. Bang con 4 cot voi ty
    # le 52/22/23/3 va colspan cua hang tieu de team giam tu 5 xuong 4. Live
    # team.ecentric.vn da duoc ghi thang len BASELINE_SHA256 cung ngay nen sync
    # dau tien o do tra ve "unchanged".
    "6a4aff420f931cbf3b24f7094c673bd79988f4d28b27fcd10dd237179cd7d9f3",  # mso-fb-3 v6
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
def sync_mso_plan_form_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /mso-plan-form page."), frappe.PermissionError)
    return sync()
