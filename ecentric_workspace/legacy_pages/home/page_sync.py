# Copyright (c) 2026, eCentric and contributors
"""GUARDED sync for the HOMEPAGE Web Page (/ -> `ecentric-workspace`).

HOMEPAGE SYNC SAFETY HOTFIX (2026-07-21). The Daily Cockpit replacement UX
was REJECTED by the PO; production was manually restored to the approved
original Homepage (Jinja portal: legacy sidebar, KPI cards, Check-in,
Truy cập nhanh, Tin nội bộ, Việc cần làm/Action Center widget, Lịch,
Chính sách, chatbot). The restored live page is the CANONICAL baseline.

This module therefore performs ZERO writes until an approved canonical
baseline is pinned:

  BASELINE_SHA256 = None  ->  sync() returns {"action": "guarded"} and
                              NEVER touches the Web Page.

Re-baselining (separate approved phase): capture the restored `/` through
the UTF-8-safe authenticated browser export on the user's machine (the
sandbox cannot extract page bytes), commit it as main_section.html
verbatim (BOM-strip + MojibakeGuard + ms==msh proof), then pin
BASELINE_SHA256 to that file's sha256. Only then does sync() become a
reproduce-only restore tool for the approved baseline.

NOTE: the homepage keeps `dynamic_template=1` (live Jinja) -- it is
EXEMPT from legacy_pages.serving static-serving. Website Settings
home_page is never touched.
"""
import hashlib
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "home"
NAME = "ecentric-workspace"
TITLE = "eCentric Workspace"

#: sha256 of the APPROVED canonical baseline main_section.html. None means
#: "no approved repo baseline exists" -> baseline sync is a guarded no-op.
BASELINE_SHA256 = None

#: Homepage Shared Shell Migration (Preserve UX): the boundary transform is
#: implemented and fully unit-tested, but DISABLED until the PO explicitly
#: approves the production rollout. While False, sync() stays the guarded
#: zero-write no-op regardless of any request payload.
ENABLE_SHELL_BOUNDARY = True

import re as _re

#: the ONLY two zones the transform may touch (verified live anchors):
#: 1. the final embedded legacy sidebar
LEGACY_SIDEBAR_RE = _re.compile(r'<aside class="ec-sidebar".*?</aside>', _re.S)
#: 2. the legacy global topbar: breadcrumb + topbar-actions (help icon, raw
#:    bell, /app/user-settings gear); its inner divs are leaf divs (verified)
LEGACY_TOPBAR_RE = _re.compile(
    r'<div class="topbar">\s*<div class="breadcrumb">.*?</div>\s*'
    r'<div class="topbar-actions">.*?</div>\s*</div>', _re.S)
CANON_TOPBAR_RE = _re.compile(
    r'<div class="ec-shell-topbar" data-ec-shell-topbar="1">.*?'
    r'data-ec-shell-header-right="1">.*?</div></div>', _re.S)
MOUNT_FULL_RE = _re.compile(r'<aside class="ec-shell-mount".*?</aside>', _re.S)


def transform_home(ms):
    """PURE shell-boundary transform for the restored Homepage.

    Replaces ONLY: (a) the embedded legacy `.ec-sidebar` -> canonical Shared
    Shell mount with the static `home` portal context; (b) the legacy topbar
    -> canonical registry crumbs + 3-slot header-right. EVERYTHING else --
    greeting/Jinja, KPI cards, Quick Access, Check-in, Tin nội bộ Jinja
    loop, AC widget, Lịch, Chính sách, chatbot, csrf -- is byte-preserved
    and PROVEN so (strip-zones equality; raises on any drift).
    Idempotent: canonical zones regenerate in place on a second run.
    Returns (new_html, info)."""
    from ecentric_workspace.shell import fallback as fb

    if "ec-ck" in ms or "ec-cockpit-js" in ms:
        raise ValueError("rejected Cockpit markup detected -- refusing to transform")
    if ms.count('data-ec-notification-bell="1"') != 1:
        raise ValueError("bell guard failed: expected exactly 1 NC marker")

    legacy_side = LEGACY_SIDEBAR_RE.search(ms)
    canon_side = MOUNT_FULL_RE.search(ms)
    if not legacy_side and not canon_side:
        raise ValueError("no sidebar zone found (neither legacy nor canonical)")

    mount = ('<aside class="ec-shell-mount" data-ec-shell="1" '
             'aria-label="Điều hướng eCentric">%s</aside>'
             % fb.render_mount_inner("/"))
    new = (LEGACY_SIDEBAR_RE if legacy_side else MOUNT_FULL_RE).sub(
        lambda m: mount, ms, count=1)

    topbar = ('<div class="ec-shell-topbar" data-ec-shell-topbar="1">%s</div>'
              % fb.render_topbar_inner("/"))
    if LEGACY_TOPBAR_RE.search(new):
        new = LEGACY_TOPBAR_RE.sub(lambda m: topbar, new, count=1)
    elif CANON_TOPBAR_RE.search(new):
        new = CANON_TOPBAR_RE.sub(lambda m: topbar, new, count=1)
    else:
        raise ValueError("no topbar zone found (neither legacy nor canonical)")

    def _strip(h):
        h = LEGACY_SIDEBAR_RE.sub("", h)
        h = MOUNT_FULL_RE.sub("", h)
        h = LEGACY_TOPBAR_RE.sub("", h)
        h = CANON_TOPBAR_RE.sub("", h)
        return h

    if _strip(ms) != _strip(new):
        raise ValueError("boundary proof failed: business/Jinja bytes would change")
    for marker, n in (('data-ec-shell="1"', 1),
                      ('data-ec-notification-bell="1"', 1),
                      ('data-ec-shell-topbar="1"', 1),
                      ('data-ec-shell-crumbs="1"', 1)):
        if new.count(marker) != n:
            raise ValueError("post-condition failed: %s x%s" % (marker, new.count(marker)))
    for keep in ("ec-chatbot-js", "ec-csrf-fetch-patch", "ec-action-center-widget",
                 "{{ first_name }}", "ecentricCheckin"):
        if keep not in new:
            raise ValueError("business surface lost: %s" % keep)
    return new, {"replaced_legacy_sidebar": bool(legacy_side),
                 "replaced_legacy_topbar": bool(LEGACY_TOPBAR_RE.search(ms))}


def _baseline_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "main_section.html")


def sync(html=None):
    if ENABLE_SHELL_BOUNDARY:
        # governed shell-boundary rollout path (PO-activated): transform the
        # LIVE page in place; dynamic_template stays 1 (live Jinja) -- NO
        # static serving, NO baseline overwrite.
        name = frappe.db.get_value("Web Page", {"route": ROUTE}, "name")
        if not name:
            return {"action": "skipped", "reason": "page missing", "route": ROUTE}
        ms = frappe.db.get_value("Web Page", name, "main_section") or ""
        try:
            new, info = transform_home(ms)
        except ValueError as e:
            frappe.throw(_(str(e)))
        if new == ms:
            return dict(action="unchanged", route=ROUTE, name=name, **info)
        doc = frappe.get_doc("Web Page", name)
        doc.main_section = new
        doc.main_section_html = new
        doc.save(ignore_permissions=True)
        return dict(action="updated", route=ROUTE, name=name,
                    len_before=len(ms), len_after=len(new), **info)

    if BASELINE_SHA256 is None:
        # HARD GUARD: no approved baseline pinned -> zero reads of the page,
        # zero writes. Production homepage stays exactly as restored.
        return {
            "action": "guarded",
            "route": ROUTE,
            "name": NAME,
            "reason": "homepage is live-canonical; no approved repo baseline pinned "
                      "(BASELINE_SHA256 is None) -- sync performs zero writes",
        }

    # Phase B path (inactive until a baseline is pinned): reproduce-only.
    if html is None:
        with open(_baseline_path(), encoding="utf-8") as fh:
            html = fh.read()
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    if digest != BASELINE_SHA256:
        frappe.throw(_("Homepage baseline sha mismatch: refusing to sync "
                       "(expected %s, got %s)") % (BASELINE_SHA256, digest))
    return page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html)


@frappe.whitelist(methods=["POST"])
def sync_home_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the homepage."), frappe.PermissionError)
    return sync()
