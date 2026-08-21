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
