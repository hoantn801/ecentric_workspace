# Copyright (c) 2026, eCentric and contributors
"""Shared, ORM-only, idempotent upsert for Approval Center Web Pages.

Frappe names a Web Page after its route slug (route 'approvals/system-request' ->
name 'system-request'). A create-then-save therefore collides on the PRIMARY key if
a page with that slug already exists (e.g. from a partial/failed migrate or a prior
sync). This helper looks a page up by (1) the canonical name, (2) the exact route,
and (3) the route slug Frappe would assign, then UPDATES it in place; it only inserts
when no such page exists. Re-running is always safe (no DuplicateEntryError). Never
deletes a page; never uses raw SQL; never publishes a catalog card."""
import frappe


def _slug(route):
    return (route or "").rsplit("/", 1)[-1]


def find_web_page(route, name=None):
    """Return the name of the existing Web Page for this route (or None). Checks the
    canonical name, the exact route, and the route slug (defends against a page created
    under Frappe's slug naming by a partial migrate)."""
    if name and frappe.db.exists("Web Page", name):
        return name
    found = frappe.get_all("Web Page", filters={"route": route}, pluck="name")
    if found:
        return found[0]
    slug = _slug(route)
    if slug and frappe.db.exists("Web Page", slug):
        return slug
    return None


def upsert_web_page(route, name, title, html):
    """Idempotent create-or-update. Returns {action: created|updated|unchanged|skipped, route, name}."""
    if not frappe.db.exists("DocType", "Web Page"):
        return {"action": "skipped", "reason": "Web Page DocType missing", "route": route, "name": name}
    existing = find_web_page(route, name)
    doc = frappe.get_doc("Web Page", existing) if existing else frappe.new_doc("Web Page")
    if existing and (doc.main_section or "") == html and (doc.main_section_html or "") == html \
            and doc.published and doc.title == title and doc.route == route:
        return {"action": "unchanged", "route": route, "name": doc.name}
    doc.route = route            # set before save so a new page autonames correctly; also normalises a
    doc.title = title            # page previously found by slug/name whose route drifted
    doc.published = 1            # controlled/direct UAT; catalog card stays inactive
    doc.content_type = "HTML"
    doc.main_section = html
    doc.main_section_html = html
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    action = "updated" if existing else "created"
    frappe.logger("approval_center").info("page_sync upsert: %s Web Page /%s (name=%s)" % (action, route, doc.name))
    return {"action": action, "route": route, "name": doc.name}


# --- Legacy Web Page shim cleanup (meta-driven; never accesses a column that does not exist) ---
_SHIM_MARKERS = ("SHIM cho Web Page", "frappe.db.get_doc", "frappe.db.get_value", "frappe.client")
_TEXT_FIELDTYPES = {"Data", "Small Text", "Text", "Long Text", "Text Editor",
                    "Code", "HTML", "HTML Editor", "Markdown Editor"}
_MANAGED_FIELDS = {"main_section", "main_section_html"}


def strip_legacy_shims(name):
    """Remove a legacy Desk-style shim from whatever real text field holds it on this site.
    Inspects Web Page meta (never a hardcoded/possibly-missing column). main_section/
    main_section_html are owned by upsert_web_page (replaced with clean source), so they are
    not blanked here. Clears only fields whose value contains an unambiguous shim marker.
    ORM-only, non-destructive. Returns diagnostics."""
    inspected, stripped = [], []
    try:
        meta = frappe.get_meta("Web Page")
        doc = frappe.get_doc("Web Page", name)
    except Exception:
        return {"inspected_fields": inspected, "shim_fields_stripped": stripped, "has_legacy_shim": False}
    for df in meta.fields:
        if df.fieldtype not in _TEXT_FIELDTYPES or df.fieldname in _MANAGED_FIELDS:
            continue
        inspected.append(df.fieldname)
        val = doc.get(df.fieldname)
        if val and any(m in val for m in _SHIM_MARKERS):
            frappe.db.set_value("Web Page", name, df.fieldname, "")
            stripped.append(df.fieldname)
    if stripped:
        frappe.db.commit()
        frappe.logger("approval_center").info("page_sync: stripped legacy shim from %s" % stripped)
    return {"inspected_fields": inspected, "shim_fields_stripped": stripped, "has_legacy_shim": bool(stripped)}
