# Copyright (c) 2026, eCentric and contributors
"""Cam bo nap widget %SLA vao trang chu (Web Page `/home`).

PHAN LOAI: di tru du lieu. Khong doi schema. Ban ghi Web Page cua trang chu bi
sua - them DUNG MOT the <script src=...>.

LAM THEO DUNG CACH `pm.patches.p021_home_calendar_widget` va
`notification_center.patches.p001_homepage_notification_bell` da lam, khong
nghi ra cach thu ba:

  * Logic nam trong TAI SAN cua app (`public/js/sla_home_card.js`), o day chi
    cam mot bo nap nho. Sua widget sau nay la cap nhat tai san, khong phai sua
    lai ban ghi Web Page mot lan nua. Trang chu la trang duy nhat cua he thong
    KHONG co ban HTML trong repo (xem legacy_pages/home/page_sync.py) - moi lan
    ghi vao no la mot lan khong hoan tac duoc bang git.
  * CONG THEM va KHONG CAN MOC. Bo nap duoc noi vao CUOI truong, khong bam vao
    mot dau moc nao. Ban p021 truoc do tung gia dinh moc cua notification center
    co san va da lam hong ca lan migrate khi moc do khong co.
  * Chay lai duoc: da co moc thi bo qua truong do.
  * Khong co token Jinja trong bo nap, nen no khong the lam hong buoc render
    cua trang.

FAIL-SAFE - KHAC p021 MOT DIEM CO Y. Ban p021 nem `frappe.ValidationError` khi
khong tim thay trang chu. O day thi khong: mot patch nem loi la CHAN CA BAN
DEPLOY, va o SLA tren trang chu la thu trang tri - khong dang de no chan mot
dot deploy co nhung thu khac quan trong hon. Hong thi ghi Error Log roi di
tiep; duong sua la chay lai patch hoac goi tay.
"""
import frappe

WP_ROUTE = "home"
WP_NAME_KNOWN = "ecentric-workspace"

MARKER = '<script id="ec-sla-home-card-loader"'
LOADER = (
    '<script id="ec-sla-home-card-loader" '
    'src="/assets/ecentric_workspace/js/sla_home_card.js" '
    'defer></script>'
    '<!-- /ec-sla-home-card-loader -->'
)

TARGET_FIELDS = ("main_section", "main_section_html")


def _resolve_wp_name():
    if frappe.db.exists("Web Page", WP_NAME_KNOWN):
        return WP_NAME_KNOWN
    rows = frappe.get_all("Web Page", filters={"route": WP_ROUTE},
                          fields=["name"], limit_page_length=1)
    return rows[0]["name"] if rows else None


def execute():
    try:
        _run()
    except Exception:
        frappe.log_error(title="p006 cam widget SLA vao trang chu",
                         message=frappe.get_traceback())


def _run():
    name = _resolve_wp_name()
    if not name:
        frappe.log_error(title="p006 cam widget SLA vao trang chu",
                         message="khong tim thay Web Page trang chu "
                                 "(name=%s, route=%s)" % (WP_NAME_KNOWN, WP_ROUTE))
        return

    wp = frappe.get_doc("Web Page", name)
    changed = []
    for f in TARGET_FIELDS:
        val = getattr(wp, f, None) or ""
        if not val:
            continue
        if MARKER in val:
            continue
        setattr(wp, f, val + LOADER)
        changed.append(f)

    if not changed:
        frappe.log_error(title="p006 cam widget SLA vao trang chu",
                         message="da co san bo nap, khong sua gi (%s)" % name)
        return

    # save() chu khong phai db.set_value: de hook on_update cua Web Page chay
    # dung mot lan, giong het hai ban patch trang chu truoc do.
    wp.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.log_error(title="p006 cam widget SLA vao trang chu",
                     message="da cam vao %s cua %s" % (", ".join(changed), name))
