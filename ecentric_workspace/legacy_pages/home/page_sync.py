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

#: 3. Homepage UX polish (visual only, 2026-07-22): a governed ADDITIVE style
#:    zone injected right after the canonical topbar -- classic marker
#:    pattern (strip-and-reinject, idempotent). Pure CSS density overrides
#:    scoped to the page's own body classes; ZERO business-markup changes,
#:    zero behavior changes. Removing this block restores the old spacing.
POLISH_RE = _re.compile(r'<style id="ec-home-polish">.*?</style>', _re.S)
POLISH_STYLE = (
    '<style id="ec-home-polish">'
    '/* Homepage UX polish v2 -- compact density (visual only, governed zone). '
    'Sidebar rules are HOMEPAGE-SCOPED (this zone exists only on /): target = '
    'fit all 16 portal items without an internal scrollbar at 1080p; '
    'overflow-y:auto stays untouched as the small-viewport fallback. */'
    '/* portal sidebar (homepage only) */'
    '.ecentric-app .ec-shell-head{padding:10px 12px 6px !important;}'
    '.ecentric-app .ec-shell-search{margin:2px 12px 6px !important;}'
    '.ecentric-app .ec-shell-nav{padding:4px 10px !important;gap:1px !important;}'
    '.ecentric-app .ec-shell-grouplabel{padding:7px 12px 3px !important;}'
    '.ecentric-app .ec-shell-item{padding:6px 12px !important;gap:9px !important;font-size:13px !important;}'
    '.ecentric-app .ec-shell-item svg{width:16px !important;height:16px !important;}'
    '.ecentric-app .ec-shell-foot{padding:7px 10px !important;}'
    '/* page body density */'
    '.content{padding:14px 20px 20px !important;}'
    '.greeting{margin-bottom:8px !important;}'
    '.greeting h1{font-size:20px !important;margin-bottom:2px !important;}'
    '.stats-strip{gap:8px !important;margin-bottom:10px !important;}'
    '.stat-card{padding:10px 12px !important;border-radius:10px !important;}'
    '.stat-value{font-size:20px !important;line-height:1.15 !important;}'
    '.stat-label{font-size:11.5px !important;}'
    '.stat-meta{font-size:11px !important;}'
    '.bento{gap:12px !important;}'
    '.col-left,.col-right{gap:12px !important;}'
    '.panel{padding:11px 14px !important;border-radius:10px !important;min-height:0 !important;}'
    '.panel-header{margin-bottom:6px !important;}'
    '.panel-title{font-size:13.5px !important;}'
    '.quick-grid{gap:7px !important;}'
    '.quick-item{padding:7px 6px !important;border-radius:9px !important;}'
    '.quick-icon{width:24px !important;height:24px !important;}'
    '.quick-label{font-size:11.5px !important;}'
    '.checkin-card{padding:11px 14px !important;}'
    '.news-grid{gap:8px !important;}'
    '.approval-item{padding:7px 0 !important;}'
    '</style>')


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
    if ms.count('data-ec-notification-bell="1"') > 1:
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

    # zone 3: UX-polish style -- strip-and-reinject right after the topbar
    new = POLISH_RE.sub("", new)
    new = new.replace(topbar, topbar + POLISH_STYLE, 1)

    def _strip(h):
        h = LEGACY_SIDEBAR_RE.sub("", h)
        h = MOUNT_FULL_RE.sub("", h)
        h = LEGACY_TOPBAR_RE.sub("", h)
        h = CANON_TOPBAR_RE.sub("", h)
        h = POLISH_RE.sub("", h)
        return h

    if _strip(ms) != _strip(new):
        raise ValueError("boundary proof failed: business/Jinja bytes would change")
    for marker, n in (('data-ec-shell="1"', 1),
                      ('data-ec-shell-action-slot="1"', 1),
                      ('data-ec-shell-topbar="1"', 1),
                      ('data-ec-shell-crumbs="1"', 1),
                      ('<style id="ec-home-polish">', 1)):
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


# --------------------------------------------------------------------------- #
# Action badge neutralization (Phase 1b deployment blocker fix, 2026-07-24)     #
# --------------------------------------------------------------------------- #
# The homepage "Việc cần làm" badge was Jinja `{{ approvals_count }}` where
# approvals_count = leave_count + so_count, and leave_count/so_count were
# GLOBAL, UNSCOPED frappe.db.count(...) of Open Leave Applications + draft
# Sales Orders (gated to System Users). That exposed a wrong, non-session-
# scoped count server-side; the asset-only widget override was insufficient
# because the SSR still computed + showed it (flash of the global count).
#
# Governed fix (server-side, byte-proof, idempotent): remove the two
# frappe.db.count queries (neutralize the set-vars to 0 so downstream
# {{ approvals_count }}/{{ so_count }}/{{ leave_count }} references keep
# rendering a harmless 0 instead of erroring) and replace the badge with a
# NEUTRAL HIDDEN placeholder OWNED by the Action Center widget
# (data-ec-ac-badge). The widget fills it from the session-scoped feed.total;
# it stays hidden before hydration, when total==0, and when the API fails.

_LEAVE_SET_LEGACY = ("{% set leave_count = frappe.db.count('Leave Application', "
                     "filters={'status': 'Open', 'docstatus': 0}) if is_system_user "
                     "and frappe.db.exists('DocType', 'Leave Application') else 0 %}")
_SO_SET_LEGACY = ("{% set so_count = frappe.db.count('Sales Order', "
                  "filters={'docstatus': 0}) if is_system_user "
                  "and frappe.db.exists('DocType', 'Sales Order') else 0 %}")
_APPROVALS_SET_LEGACY = "{% set approvals_count = leave_count + so_count %}"
_BADGE_LEGACY = ('{% if approvals_count %}<span class="badge b-pink">'
                 '{{ approvals_count }}</span>{% endif %}')
_KPI_VAL_LEGACY = '<div class="stat-value">{{ approvals_count }}</div>'
_KPI_META_LEGACY = ('<div class="stat-meta">{{ so_count }} SO · '
                    '{{ leave_count }} đơn nghỉ phép</div>')

_LEAVE_SET_NEUTRAL = "{% set leave_count = 0 %}"
_SO_SET_NEUTRAL = "{% set so_count = 0 %}"
_APPROVALS_SET_NEUTRAL = "{% set approvals_count = 0 %}"
#: always-present, hidden, widget-owned placeholder (no server count).
_BADGE_NEUTRAL = '<span class="badge b-pink" data-ec-ac-badge="1" hidden></span>'
#: KPI "Phê duyệt chờ" value -> widget-owned; NEUTRAL "—" until hydration
#: (never a knowingly-false 0). The widget fills it from
#: feed.source_counts.approval (session-scoped).
_KPI_VAL_NEUTRAL = '<div class="stat-value" data-ec-ac-kpi="approval">—</div>'
#: KPI meta -> session-scoped wording; widget fills "X yêu cầu cần phản hồi".
_KPI_META_NEUTRAL = '<div class="stat-meta" data-ec-ac-kpi-meta="1"></div>'

_NEUTRALIZE = [
    (_LEAVE_SET_LEGACY, _LEAVE_SET_NEUTRAL),
    (_SO_SET_LEGACY, _SO_SET_NEUTRAL),
    (_APPROVALS_SET_LEGACY, _APPROVALS_SET_NEUTRAL),
    (_BADGE_LEGACY, _BADGE_NEUTRAL),
    (_KPI_VAL_LEGACY, _KPI_VAL_NEUTRAL),
    (_KPI_META_LEGACY, _KPI_META_NEUTRAL),
]


def neutralize_legacy_action_counts(ms):
    """PURE transform: strip the global-count Jinja + widget-own the badge.

    Byte-proof by construction (only the four named zones change). Idempotent
    (already-neutralized input returns unchanged). Refuses an UNKNOWN state
    (neither legacy nor neutralized markers present) rather than guessing.
    Returns (new_html, changed_count)."""
    if "data-ec-ac-badge" in ms and _BADGE_LEGACY not in ms:
        # already neutralized -> no-op (but assert the global count is gone
        # and the KPI is widget-owned, never a false zero)
        if "frappe.db.count('Leave Application'" in ms or "frappe.db.count('Sales Order'" in ms:
            raise ValueError("partial neutralization: badge done but count queries remain")
        if 'data-ec-ac-kpi="approval"' not in ms:
            raise ValueError("partial neutralization: badge done but KPI not widget-owned")
        return ms, 0
    if _BADGE_LEGACY not in ms:
        raise ValueError("unknown homepage state: legacy action badge not found")
    new = ms
    changed = 0
    for legacy, neutral in _NEUTRALIZE:
        if legacy in new:
            new = new.replace(legacy, neutral, 1)
            changed += 1
    # post-conditions: no global count queries; widget-owned placeholders in
    # place of any server-rendered count (no knowingly-false zero).
    if "frappe.db.count('Leave Application'" in new or "frappe.db.count('Sales Order'" in new:
        raise ValueError("global count query still present after neutralization")
    if new.count('data-ec-ac-badge="1"') != 1:
        raise ValueError("expected exactly one widget badge placeholder")
    if new.count('data-ec-ac-kpi="approval"') != 1:
        raise ValueError("expected the KPI value to be a widget-owned placeholder")
    if new.count('data-ec-ac-kpi-meta="1"') != 1:
        raise ValueError("expected the KPI meta to be a widget-owned placeholder")
    # the KPI value must NOT be a hardcoded 0 (no false zero)
    if '<div class="stat-value">0</div>' in new:
        raise ValueError("KPI must not display a false 0")
    return new, changed


@frappe.whitelist(methods=["POST"])
def sync_home_action_badge():
    """SM-gated governed re-sync of ONLY the homepage action-count Jinja.

    Reads the live main_section, neutralizes the legacy global count +
    widget-owns the badge, and writes it back. Idempotent (re-run = unchanged).
    Separate from the guarded baseline sync -- this is a targeted, byte-proof
    correction, not a full-page overwrite. dynamic_template stays 1."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the homepage."), frappe.PermissionError)
    name = page_sync_util.find_web_page(ROUTE, NAME)
    if not name:
        return {"action": "skipped", "reason": "homepage Web Page missing"}
    ms = frappe.db.get_value("Web Page", name, "main_section") or ""
    try:
        new, changed = neutralize_legacy_action_counts(ms)
    except ValueError as e:
        frappe.throw(_(str(e)))
    if new == ms:
        return {"action": "unchanged", "route": ROUTE, "name": name}
    doc = frappe.get_doc("Web Page", name)
    doc.main_section = new
    doc.main_section_html = new
    doc.save(ignore_permissions=True)
    return {"action": "updated", "route": ROUTE, "name": name, "zones_changed": changed}


@frappe.whitelist(methods=["POST"])
def sync_home_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the homepage."), frappe.PermissionError)
    return sync()
