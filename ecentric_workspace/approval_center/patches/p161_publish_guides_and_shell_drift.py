# Copyright (c) 2026, eCentric and contributors
"""Dua muc "Huong dan su dung" len site + vet lai hai trang bi troi khoi vo shell.

BON viec, cung mot lan chay vi ca bon deu la "ghi lai HTML tinh cua trang":

1. /huong-dan          - muc luc cac bai huong dan (trang MOI).
2. /huong-dan/dnmh-dntt- bai dau tien: De nghi mua hang -> De nghi thanh toan
                         (anh chup man hinh nhung base64 luc sync).
3. /approvals          - icon "?" tren the co bai huong dan. Day la LOI VAO
                         CHINH: no o dung cho nguoi ta dang dung lai tu hoi "cai
                         nay lam the nao", va no chi hien khi server bao co bai
                         (catalog tra `guide_route` tu guides.registry).
4. /viec-cua-toi va /approvals/payment-request - HAI trang da TROI khoi vo shell
   chuan tu truoc dot nay (phat hien 08/09 khi chay
   `shell.fallback.regenerate(check=True)` tren dung ban HEAD, chua co thay doi
   nao cua toi):
     * /viec-cua-toi con in dong menu "Cai app len dien thoai" - dong nay da bi
       danh `sidebar_hidden` tu 21/08 (mot cai dien thoai khong lien quan gi toi
       cai man hinh desktop dang mo). Cac trang khac deu da bo, rieng trang nay
       con.
     * /approvals/payment-request co the tai khoan o chan thanh ben tro toi
       "/me". 41 trang con lai deu tro "/app/user" - va ban dung la /app/user
       (xem shell/fallback.py). Mot lan sua tay lot vao roi o lai.
   Vet chung o day chu khong de rieng: ca hai chi lech o phan markup do CHINH
   trinh dung vo shell sinh ra, va cong `shell/tests/test_global_header.py` doi
   dung khong con trang nao lech. De lai thi cong do vinh vien, ma mot cai cong
   do vinh vien thi khong con canh duoc gi.

Breadcrumb cua ba trang cung duoc dung lai trong dot nay: `_crumb_target` gio hoi
registry KEM CA muc an (`include_hidden=True`), nen /viec-cua-toi va /huong-dan -
hai route hop le nhung khong ve dong menu - khong con hien breadcrumb TRONG.
"""
import frappe

from ecentric_workspace.action_center.pages.my_work import page_sync as my_work_sync
from ecentric_workspace.approval_center.features.payment_request.infrastructure import (
    page_sync as pr_sync,
)
from ecentric_workspace.approval_center.ui.hub import page_sync as hub_sync
from ecentric_workspace.guides.pages.dnmh_dntt import page_sync as guide_dnmh_sync
from ecentric_workspace.guides.pages.index import page_sync as guides_index_sync

#: route -> nhung chuoi PHAI co mat sau khi sync. Thieu mot cai = sync khong toi
#: noi, va mot patch bao "xong" trong khi trang van chay ma cu la thu da hai
#: chung ta 29/08 va 31/08.
_EXPECT = {
    "huong-dan": (
        'class="gcards"',                       # danh sach bai sinh tu registry
        'href="/huong-dan/dnmh-dntt"',          # bai dau tien co mat trong muc luc
        'class="ec-shell-crumb-current">Hướng dẫn sử dụng',
    ),
    "huong-dan/dnmh-dntt": (
        'data:image/jpeg;base64,',              # anh da nhung, khong phai link gay
        'href="/huong-dan"',                    # nut back ve muc luc
        'class="ec-shell-crumblink" href="/huong-dan"',
    ),
    "approvals": (
        'class="card-help"',                    # icon "?" da co mat trong ma the
        "c.guide_route",                        # va chi ve khi server bao co bai
    ),
    "viec-cua-toi": (
        'ec-shell-crumb-group">Workspace',
    ),
    "approvals/payment-request": (
        'ec-shell-usercard" href="/app/user"',
    ),
}

#: chuoi KHONG duoc con lai sau khi sync (cai da troi).
_FORBID = {
    "viec-cua-toi": ("/ec-hr/huong-dan-cai-app",),
    "approvals/payment-request": ('ec-shell-usercard" href="/me"',),
}


def _check(route):
    html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
    if not html:
        raise Exception("p161: khong doc duoc Web Page route=%s sau sync" % route)
    missing = [m for m in _EXPECT.get(route, ()) if m not in html]
    left = [m for m in _FORBID.get(route, ()) if m in html]
    if missing or left:
        raise Exception("p161: %s thieu=%s con-sot=%s" % (route, missing, left))


def execute():
    actions = {
        "huong-dan": guides_index_sync.sync(),
        "huong-dan/dnmh-dntt": guide_dnmh_sync.sync(),
        "approvals": hub_sync.sync(),
        "viec-cua-toi": my_work_sync.sync(),
        "approvals/payment-request": pr_sync.sync(),
    }
    frappe.log_error(
        "p161 sync=%s" % {k: (v or {}).get("action") for k, v in actions.items()},
        "p161 guides + shell drift")
    for route in actions:
        _check(route)
