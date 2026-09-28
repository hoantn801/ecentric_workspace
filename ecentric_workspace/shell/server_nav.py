# Copyright (c) 2026, eCentric and contributors
"""Menu chung do SERVER dung luc render (A65 / NHIEU_LOP giai doan 1.1, 28/09/2026).

VI SAO. Moi Web Page mang mot ban menu "nuong" vao HTML luc sync
(`fallback.render_mount_inner`, goi tu page_sync va cac transform alerts / reporting /
hr / pm). Registry doi la trang lech cho toi khi duoc sync lai -- va khong ai sync lai.
Do 28/09 tren live: 7 kieu lech tren 59 trang (thieu muc moi, "Tong quan" tro route cu,
/pnl-dashboard nuong sai ngu canh, /ai-tool va /reports de mount rong...). Nguoi dung
thay menu cu mot nhip roi menu that de len: dung cai "nhieu lop" PO chup duoc.

CACH LAM. Hook `update_website_context` dung lai DUNG vung `.ec-shell-mount` trong
`context.main_section` tu registry HIEN HANH. Frappe 16.35.0 (da doc ma nguon):
hook chay trong `post_process_context`, tuc SAU `WebPage.get_context` (da gan
main_section) va TRUOC khi render template + `@cache_html`.
- Khong sua file trang nao, khong can sync lai trang nao.
- Menu o day KHONG theo nguoi (`roles=None`, giong fallback): HTML giong nhau voi moi
  nguoi nen van dung chung cache trang cua Frappe nhu truoc. Muc theo quyen, the ten,
  badge van do ec_shell.js va TAI CHO.
- The mo mount mang `data-ec-context` (ngu canh server chon bang `nav.resolve_context`,
  co tinh ca muc sidebar_hidden) va `data-ec-nav-sig` (chu ky danh sach muc).
  ec_shell.js dung ngu canh do thay vi tu doan -- sua loi /viec-cua-toi bi ve menu Phe
  duyet -- va KHONG ve lai menu khi chu ky trung.
- Chi thay vung giua the mo `<aside class="ec-shell-mount" ...>` va `</aside>` dau tien
  sau no; moi byte khac cua trang giu nguyen (cung nguyen tac "cat dung vung" voi
  shell/boundary.py). Trang co 0 hoac >= 2 mount, mount khong co `data-ec-shell="1"`,
  mount long `<aside>` ben trong, hoac khong dong -> de nguyen, khong doan.
- Loi bat ky -> tra None: trang giu menu nuong cu, dung hanh vi truoc hook nay. Error
  Log ghi toi da 1 lan / gio de khong ngap log.

Kill switch (khong can deploy): site_config `ec_shell_server_nav_disabled: 1`.
"""
import re

import frappe

from ecentric_workspace.shell import fallback as fb
from ecentric_workspace.shell import nav as shell_nav

KILL_SWITCH = "ec_shell_server_nav_disabled"
MOUNT_OPEN = '<aside class="ec-shell-mount"'
MOUNT_CLOSE = "</aside>"
OPT_IN = 'data-ec-shell="1"'
ATTR_CONTEXT = "data-ec-context"
ATTR_SIG = "data-ec-nav-sig"
LOG_TITLE = "ec_shell_server_nav"
LOG_THROTTLE_KEY = "ec_shell_server_nav_logged"
LOG_THROTTLE_SEC = 3600


def nav_signature(context_name, items, active_key):
    """Chu ky cua danh sach muc menu: ngu canh | muc dang chon | cac key theo thu tu ve.

    ec_shell.js navSig() tinh DUNG cong thuc nay tren boot cua nguoi dung. Trung nhau =
    DOM server da ve dung menu nguoi nay can -> client giu nguyen, khong ve lai.
    Chi dung key (khong dung nhan/route): key on dinh qua cac lan doi nhan, va boot cu
    trong sessionStorage khong duoc phep keo menu server moi hon ve ban cu."""
    keys = []
    for it in items:
        keys.append(it["key"])
        for ch in it.get("children") or []:
            keys.append(ch["key"])
    return "%s|%s|%s" % (context_name or "", active_key or "", ",".join(keys))


def _set_attr(tag, name, value):
    """Dat (hoac thay) mot thuoc tinh tren THE MO `tag`. Idempotent."""
    tag = re.sub(r'\s%s="[^"]*"' % re.escape(name), "", tag)
    return tag[:-1] + ' %s="%s">' % (name, fb.esc_live(value))


def rebuild_mount(ms, route):
    """main_section moi voi vung `.ec-shell-mount` dung lai tu registry, hoac None
    khi trang khong thuoc dien (de nguyen, khong doan)."""
    if not ms or ms.count(MOUNT_OPEN) != 1:
        return None
    start = ms.index(MOUNT_OPEN)
    tag_end = ms.find(">", start)
    if tag_end < 0:
        return None
    open_tag = ms[start:tag_end + 1]
    if OPT_IN not in open_tag:
        return None
    close = ms.find(MOUNT_CLOSE, tag_end)
    if close < 0 or "<aside" in ms[tag_end + 1:close]:
        return None
    context_name = shell_nav.resolve_context(route)
    items = shell_nav.compose(context_name)
    active = fb.match_active(items, route)
    new_tag = _set_attr(open_tag, ATTR_CONTEXT, context_name)
    new_tag = _set_attr(new_tag, ATTR_SIG, nav_signature(context_name, items, active))
    return ms[:start] + new_tag + fb.mount_inner_html(items, active, live=True) + ms[close:]


def _route_of(context):
    route = context.get("route") or context.get("path") or ""
    if not route:
        request = getattr(frappe.local, "request", None)
        route = getattr(request, "path", "") or ""
    return "/" + str(route).lstrip("/")


def _log_once():
    try:
        cache = frappe.cache()
        if cache.get_value(LOG_THROTTLE_KEY):
            return
        cache.set_value(LOG_THROTTLE_KEY, 1, expires_in_sec=LOG_THROTTLE_SEC)
        frappe.log_error(title=LOG_TITLE)
    except Exception:
        pass


def fill_shell_mount(context):
    """hooks.update_website_context. Tra {"main_section": ...} hoac None. Khong bao gio nem."""
    try:
        if frappe.conf.get(KILL_SWITCH):
            return None
        ms = context.get("main_section")
        if not isinstance(ms, str) or MOUNT_OPEN not in ms:
            return None
        new = rebuild_mount(ms, _route_of(context))
        if new is None or new == ms:
            return None
        return {"main_section": new}
    except Exception:
        _log_once()
        return None
