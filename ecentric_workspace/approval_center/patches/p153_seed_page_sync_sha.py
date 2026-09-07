# Copyright (c) 2026, eCentric and contributors
"""Gieo `ec_page_sync_sha` cho MOI trang Approval Center (07/09, Hoan) - go min truoc khi no no.

Toi 07/09 p152 lam CHET migrate voi action=refused tren ca 5 trang. Live khong he bi sua tay:
da doc main_section_html tu production va bam lai, khop tung byte voi nguon. Loi la hang
`BASELINE_SHA256` trong page_sync.py da lac hau so voi chinh file main_section.html cua no,
nen luc bump thu bi day xuong SUPERSEDES la mot HANG DA CU chu khong phai sha cua noi dung
truoc do -> live khong khop gia tri nao -> upsert tu choi ghi -> patch raise.

Ra soat sau do: 20/26 trang deu dang o dung tinh trang nay. Nghia la BAT KY ai sua giao dien
mot trong 20 form do deu se lam chet mot lan deploy, dung y het toi nay.

Cach chua khong phai chep tay 20 con sha. `upsert_web_page` da chap nhan mot gia tri thu ba:
`ec_page_sync_sha:<route>` - sha live ghi lai o lan sync truoc, sinh ra chinh vi may chu
sanitize HTML nen live khong bao gio bam ra dung bytes repo. Patch nay chi GIEO gia tri do
cho moi trang tu trang thai live hien tai. Khong ghi mot byte noi dung nao.

Danh doi phai noi ro: sau khi gieo, khoa chong troi chap nhan hien trang live cua tung trang.
Neu ai do da sua tay mot trang trong so nay thi ban sua do se khong con duoc bao ve, va lan
resync sau se de len. Da doi chieu live voi nguon repo trong dot ra soat 07/09 va chung khop
o hau het cac trang, nen rui ro nay la nho va co y chap nhan - doi lai la khong con ca lop
loi "sua giao dien -> chet deploy".

Tu lan nay ve sau moi page_sync.sync() deu tu goi record_live_sha, nen khoa tu bao tri.
KHONG BAO GIO nem loi: mot exception trong migrate lam chet ca lan deploy (da dinh voi p116).
"""
import os

import frappe

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

_MODULE = "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync"


def _features_dir():
    here = os.path.dirname(os.path.abspath(__file__))          # .../approval_center/patches
    return os.path.join(os.path.dirname(here), "features")


def execute():
    seeded, skipped, failed = [], [], []
    try:
        base = _features_dir()
        feats = sorted(os.listdir(base)) if os.path.isdir(base) else []
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p153 seed sha FAILED (liet ke feature)")
        return
    for feat in feats:
        if not os.path.isfile(os.path.join(base, feat, "infrastructure", "page_sync.py")):
            continue
        try:
            mod = frappe.get_module(_MODULE % feat)
            route = getattr(mod, "ROUTE", None)
            if not route or not getattr(mod, "BASELINE_SHA256", None):
                skipped.append("%s (khong co khoa chong troi)" % feat)
                continue
            page = page_sync_util.find_web_page(route, getattr(mod, "NAME", None))
            if not page:
                skipped.append("%s (chua co Web Page)" % feat)
                continue
            sha = page_sync_util.record_live_sha(route, page)
            seeded.append("%s=%s" % (route, (sha or "?")[:12]))
        except Exception:
            failed.append(feat)
            frappe.log_error(frappe.get_traceback(), "p153 seed sha: %s" % feat)
    frappe.log_error(
        "p153 gieo %d trang | bo qua %d | loi %d\nGIEO: %s\nBO QUA: %s\nLOI: %s"
        % (len(seeded), len(skipped), len(failed),
           ", ".join(seeded), ", ".join(skipped), ", ".join(failed)),
        "p153 seed page sync sha")
