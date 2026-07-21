# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the HOMEPAGE Web Page (/ -> Web Page `ecentric-workspace`,
route `home` -- Website Settings home_page stays untouched).

Phase 2C.2 Daily Cockpit: this page REPLACES the legacy portal content
(legacy .ecentric-app sidebar, 4 hardcoded-zero KPI cards, 10 coming-soon
tiles, Jinja greeting, static Tin/Lich/Chinh-sach panels, the
`ec-action-center-widget` script tag) with the Shared-Shell cockpit. The
new markup is authored in-repo (NO snapshot import; no Jinja).

BUSINESS-SCRIPT PRESERVATION (server-side, byte-exact):
  `ec-chatbot-js` exists ONLY in the live Web Page (7KB, Phase 9 chatbot,
  gemini_chat). The browser export path cannot carry its bytes, so sync()
  extracts it from the CURRENT live main_section at sync time and re-appends
  it verbatim to the new content BEFORE upsert. If it is absent (fresh
  site), sync proceeds without it and reports `chatbot: "absent"`.
`ec-csrf-fetch-patch` is already authored in main_section.html (byte-exact
copy of the governed legacy-page script)."""
import os
import re

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "home"
NAME = "ecentric-workspace"
TITLE = "eCentric Workspace"

CHATBOT_RE = re.compile(r'<script id="ec-chatbot-js">.*?</script>', re.S)


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def _with_live_chatbot(html):
    """Append the live page's chatbot script verbatim (if present)."""
    existing = page_sync_util.find_web_page(ROUTE, NAME)
    if not existing:
        return html, "absent"
    current = frappe.db.get_value("Web Page", existing, "main_section") or ""
    m = CHATBOT_RE.search(current)
    if not m:
        return html, "absent"
    # inject before the final container close so it stays inside the page div
    marker = "</div>\n"
    if html.rstrip().endswith("</div>"):
        html = html.rstrip()[: -len("</div>")] + m.group(0) + "\n</div>\n"
        return html, "preserved"
    return html + m.group(0), "preserved"


def sync(html=None):
    html = html if html is not None else _html()
    html, chatbot = _with_live_chatbot(html)
    res = page_sync_util.upsert_web_page(ROUTE, NAME, TITLE, html)
    res["chatbot"] = chatbot
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
        from ecentric_workspace.legacy_pages import serving
        res.update(serving.ensure_static_serving(res["name"], html))
    return res


@frappe.whitelist(methods=["POST"])
def sync_home_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the homepage."), frappe.PermissionError)
    return sync()
