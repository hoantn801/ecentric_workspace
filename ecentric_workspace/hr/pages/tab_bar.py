# Copyright (c) 2026, eCentric and contributors
"""Governed patch: the mobile tab bar's 4th tab becomes "Việc của tôi".

WHAT IT REPLACES
  The /ec-hr pages ship a 5-slot bottom tab bar whose 4th real tab was a
  disabled "Trợ lý" placeholder (`<a class="soon" href="#">`). It never did
  anything. Meanwhile the action feed was only reachable through a floating
  header inbox button that, on a phone, sat on top of the week strip and
  opened an overlay covering the screen it floated over.

  So: the dead tab becomes the inbox, and the floating button is hidden on
  phones for these three pages (it stays on desktop, where the drawer is
  genuinely nicer than a page load).

WHY A REPO MODULE AND NOT A CONSOLE ONE-LINER
  Same reason as hr/pages/shell_boundary.py: the live bytes cannot be pulled
  into the sandbox, so the repo governs the TRANSFORM. The anchor must match
  EXACTLY ONCE or the patch refuses -- it can never half-apply, and re-running
  it is a no-op once the marker is present.

THE BADGE IS NOT COUNTED HERE
  The tab's badge node carries `data-ec-shell-reminder-badge="1"`, the shell's
  existing contract attribute. ec_shell.js (>= v1.20.0) writes the SAME
  derived attention count into every node carrying it. This page counts
  nothing and calls nothing extra.
"""
import frappe
from frappe import _

MARKER = "ec-tab-mywork-v1"

#: the dead placeholder tab, verbatim from the live pages (2026-08-21).
OLD_TAB = (
    '<a class="soon" href="#" onclick="return false">'
    '<svg viewBox="0 0 24 24"><path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 '
    '10.9c.4.3.5.7.5 1.1h6c0-.4.1-.8.5-1.1A6 6 0 0 0 12 3z"/></svg>'
    "<span>Trợ lý</span></a>"
)

#: same inbox glyph the header button uses (ec_shell.js ICONS.inbox), so the
#: tab and the desktop header read as the same thing.
NEW_TAB = (
    '<a class="ec-tab-mywork" href="/viec-cua-toi">'
    '<svg viewBox="0 0 24 24"><path d="M4 13h4l2 3h4l2-3h4"/>'
    '<path d="M4 13V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v7"/>'
    '<path d="M4 13v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5"/></svg>'
    "<span>Việc của tôi</span>"
    '<i class="ec-tab-badge" data-ec-shell-reminder-badge="1" hidden></i></a>'
)

STYLE = (
    '<style id="' + MARKER + '">\n'
    ".ec-tab-mywork{position:relative}\n"
    ".ec-tab-badge{position:absolute; top:3px; left:calc(50% + 5px);\n"
    "  min-width:17px; height:17px; padding:0 4px; border-radius:999px;\n"
    "  background:#D7263D; color:#fff; font-size:10px; font-weight:700;\n"
    "  line-height:17px; font-style:normal; text-align:center;\n"
    "  box-shadow:0 0 0 2px #fff;\n"
    "  font-variant-numeric:tabular-nums; pointer-events:none}\n"
    ".ec-tab-badge[hidden]{display:none}\n"
    "/* The tab bar now owns the inbox on phones, so the floating header\n"
    "   button next to it would be a second door to the same room -- and it\n"
    "   sat on top of the week strip. Desktop keeps it (drawer > page load). */\n"
    "@media (max-width:900px){\n"
    "  .ec-hr-main .ec-shell-topbar [data-ec-shell-action-slot=\"1\"]{display:none}\n"
    "}\n"
    "</style>"
)

ROUTES = ("ec-hr/attendance", "ec-hr/leave", "ec-hr/salary")


def transform(ms, route):
    """Pure: returns the patched html. Raises ValueError on any guard failure."""
    if MARKER in ms:
        return ms                      # already applied -> idempotent no-op
    if ms.count(OLD_TAB) != 1:
        raise ValueError("Tab anchor not found exactly once on %s (found %d)"
                         % (route, ms.count(OLD_TAB)))
    new = ms.replace(OLD_TAB, NEW_TAB, 1) + "\n" + STYLE
    if new.count(NEW_TAB) != 1 or OLD_TAB in new:
        raise ValueError("Tab replacement did not settle on %s" % route)
    if new.count('id="' + MARKER + '"') != 1:
        raise ValueError("Marker not written exactly once on %s" % route)
    return new


def upgrade(route):
    name = frappe.db.get_value("Web Page", {"route": route}, "name")
    if not name:
        return {"action": "skipped", "reason": "page missing", "route": route}
    ms = frappe.db.get_value("Web Page", name, "main_section") or ""
    try:
        new = transform(ms, route)
    except ValueError as e:
        frappe.throw(_(str(e)))
    if new == ms:
        return {"action": "unchanged", "route": route, "name": name}
    doc = frappe.get_doc("Web Page", name)
    doc.main_section = new
    doc.main_section_html = new
    doc.save(ignore_permissions=True)
    return {"action": "updated", "route": route, "name": name,
            "len_before": len(ms), "len_after": len(new)}


@frappe.whitelist(methods=["POST"])
def sync_mywork_tab():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may patch the HR tab bar."),
                     frappe.PermissionError)
    return {"results": [upgrade(r) for r in ROUTES]}


# ---------------------------------------------------------------------------
# ec-tabbar-shared-v1 -- thanh tab cho trang CHUA CO thanh nao (/viec-cua-toi).
#
# WHY THIS COPIES INSTEAD OF EMBEDDING
#   The bar is not a small blob: ~3.2 KB of mobile app-shell CSS, ~1.8 KB of
#   markup and a ~2.5 KB <script id="ec-cradle-js"> that DRAWS the notch (the
#   <path d=""> ships empty) and lights the active tab from location.pathname.
#   Pasting 7.5 KB of it in here would give the repo a second copy that drifts
#   from the live pages the moment anyone restyles the bar -- the exact failure
#   that made the home tile say 9 while the attendance ring said 1.
#
#   So this module keeps doing what its docstring promises: it governs the
#   TRANSFORM, not the bytes. The bar is lifted from ONE canonical page at sync
#   time. If the anchors ever stop matching exactly once, it refuses loudly
#   instead of writing half a tab bar.
SOURCE_ROUTE = "ec-hr/salary"       # smallest page carrying the finished bar
BAR_MARKER = "ec-tabbar-shared-v1"

CSS_ANCHOR = ".ec-tabwrap{display:none}"
MQ_ANCHOR = "@media (max-width:900px){"
HTML_OPEN = '<div class="ec-tabwrap">'
HTML_CLOSE = "</span></div></div>"
JS_OPEN = '<script id="ec-cradle-js">'
JS_CLOSE = "</" + "script>"
SOURCE_ROOT = "#ec-hr-sal-root"     # page-specific selector inside the CSS

#: route -> the page's own root selector, which the copied CSS must be
#: re-pointed at (it sets the bottom padding that keeps content off the bar).
INSERT_TARGETS = {"viec-cua-toi": "#ec-mywork-root"}

#: What the copied bar does NOT bring with it, learned the hard way on the
#: first real insert:
#:   * the badge markup travels with the bar, but its CSS lives in the
#:     ec-tab-mywork-v1 block that only the three /ec-hr pages carry. Without
#:     position:absolute the <i> drops out of the corner and renders as a bare
#:     "9+" under the label.
#:   * a page with no theme-color lets Android paint the toolbar its default
#:     blue, which reads as a different app next to the /ec-hr pages.
EXTRAS_MARKER = "ec-tabbar-extras-v1"
THEME_COLOR = "#F4F6FB"

EXTRAS = (
    "\n"
    '<style id="' + EXTRAS_MARKER + '">\n'
    ".ec-tab-mywork{position:relative}\n"
    ".ec-tab-badge{position:absolute; top:3px; left:calc(50% + 5px);\n"
    "  min-width:17px; height:17px; padding:0 4px; border-radius:999px;\n"
    "  background:#D7263D; color:#fff; font-size:10px; font-weight:700;\n"
    "  line-height:17px; font-style:normal; text-align:center;\n"
    "  box-shadow:0 0 0 2px #fff;\n"
    "  font-variant-numeric:tabular-nums; pointer-events:none}\n"
    ".ec-tab-badge[hidden]{display:none}\n"
    "/* Standing ON the inbox page, the count on that tab is just an echo of\n"
    "   what is already open -- hide it. Every other page keeps its badge. */\n"
    ".ec-tab a.on .ec-tab-badge{display:none}\n"
    "</style>\n"
    "<script>\n"
    "(function(){var m=document.querySelector('meta[name=\"theme-color\"]');\n"
    'if(!m){m=document.createElement("meta");m.setAttribute("name","theme-color");document.head.appendChild(m);}\n'
    'm.setAttribute("content","' + THEME_COLOR + '");})();\n'
    "</" + "script>\n"
)


#: the 4th tab shipped WITHOUT data-p, so it never lit up as the active tab.
MYWORK_A = '<a class="ec-tab-mywork" href="/viec-cua-toi">'
MYWORK_A_ACTIVE = '<a class="ec-tab-mywork" href="/viec-cua-toi" data-p="/viec-cua-toi">'


def _exactly_once(hay, needle, what, where):
    n = hay.count(needle)
    if n != 1:
        raise ValueError("%s: expected %s exactly once, found %d" % (where, what, n))
    return hay.index(needle)


def _css_block(src):
    """The bar's CSS plus the mobile app-shell rules it depends on, ending at
    the close of the @media block. Brace-matched rather than string-matched:
    the block nests, so a naive search for '}' cuts it in half."""
    i = _exactly_once(src, CSS_ANCHOR, "css anchor", SOURCE_ROUTE)
    j = src.index(MQ_ANCHOR, i)
    depth = 0
    for pos in range(src.index("{", j), len(src)):
        c = src[pos]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[i:pos + 1]
    raise ValueError("%s: tab bar css block never closes" % SOURCE_ROUTE)


def _html_block(src):
    i = _exactly_once(src, HTML_OPEN, "bar markup", SOURCE_ROUTE)
    return src[i:src.index(HTML_CLOSE, i) + len(HTML_CLOSE)]


def _js_block(src):
    i = _exactly_once(src, JS_OPEN, "cradle script", SOURCE_ROUTE)
    return src[i:src.index(JS_CLOSE, i) + len(JS_CLOSE)]


def _with_active_hook(html):
    """Give the 4th tab the data-p the cradle script matches on."""
    if 'data-p="/viec-cua-toi"' in html:
        return html
    _exactly_once(html, MYWORK_A, "mywork tab", "bar markup")
    return html.replace(MYWORK_A, MYWORK_A_ACTIVE, 1)


def extract_bar():
    name = frappe.db.get_value("Web Page", {"route": SOURCE_ROUTE}, "name")
    if not name:
        raise ValueError("source page %s is missing" % SOURCE_ROUTE)
    src = frappe.db.get_value("Web Page", name, "main_section") or ""
    return _css_block(src), _with_active_hook(_html_block(src)), _js_block(src)


def insert_transform(ms, route, root_sel):
    """Pure: append the shared bar to a page that has none."""
    if BAR_MARKER in ms:
        return ms                       # idempotent
    if HTML_OPEN in ms:
        raise ValueError("%s already carries a tab bar -- refusing to add a second" % route)
    css, html, js = extract_bar()
    css = css.replace(SOURCE_ROOT, root_sel)
    if SOURCE_ROOT in css:
        raise ValueError("%s: source root selector survived the rewrite" % route)
    new = (ms + '\n<style id="' + BAR_MARKER + '">\n' + css + "\n</style>\n"
           + html + "\n" + js + "\n" + EXTRAS)
    if new.count(HTML_OPEN) != 1 or new.count(JS_OPEN) != 1:
        raise ValueError("%s: bar did not settle" % route)
    if new.count('id="' + BAR_MARKER + '"') != 1:
        raise ValueError("%s: marker not written exactly once" % route)
    if new.count('id="' + EXTRAS_MARKER + '"') != 1:
        raise ValueError("%s: extras marker not written exactly once" % route)
    return new


def active_hook_transform(ms, route):
    """Pure: add the missing data-p to an ALREADY patched page."""
    if 'data-p="/viec-cua-toi"' in ms:
        return ms
    if MYWORK_A not in ms:
        return ms                       # page has no mywork tab yet
    _exactly_once(ms, MYWORK_A, "mywork tab", route)
    return ms.replace(MYWORK_A, MYWORK_A_ACTIVE, 1)


def _save(route, transform_fn):
    name = frappe.db.get_value("Web Page", {"route": route}, "name")
    if not name:
        return {"action": "skipped", "reason": "page missing", "route": route}
    ms = frappe.db.get_value("Web Page", name, "main_section") or ""
    try:
        new = transform_fn(ms)
    except ValueError as e:
        frappe.throw(_(str(e)))
    if new == ms:
        return {"action": "unchanged", "route": route, "name": name}
    doc = frappe.get_doc("Web Page", name)
    doc.main_section = new
    doc.main_section_html = new
    doc.save(ignore_permissions=True)
    return {"action": "updated", "route": route, "name": name,
            "len_before": len(ms), "len_after": len(new)}


def upgrade_active_hook(route):
    return _save(route, lambda ms: active_hook_transform(ms, route))


def upgrade_insert(route, root_sel):
    return _save(route, lambda ms: insert_transform(ms, route, root_sel))


def extras_transform(ms, route):
    """Pure: give a page that ALREADY carries the bar the styling it shipped
    without. Separate from insert_transform so the first page -- patched before
    this gap was known -- can be repaired without re-inserting the bar."""
    if EXTRAS_MARKER in ms:
        return ms
    if BAR_MARKER not in ms:
        return ms                       # no bar here, nothing to dress
    return ms + EXTRAS


def upgrade_extras(route):
    return _save(route, lambda ms: extras_transform(ms, route))


@frappe.whitelist(methods=["POST"])
def sync_tabbar_everywhere():
    """One entry point: replace the dead tab, give it its active hook, then put
    the same bar on the pages that never had one. Order matters -- the bar is
    copied FROM a page in ROUTES, so those must be correct first."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may patch the tab bar."),
                     frappe.PermissionError)
    out = [upgrade(r) for r in ROUTES]
    out += [upgrade_active_hook(r) for r in ROUTES]
    out += [upgrade_insert(r, sel) for r, sel in INSERT_TARGETS.items()]
    out += [upgrade_extras(r) for r in INSERT_TARGETS]
    return {"results": out}
