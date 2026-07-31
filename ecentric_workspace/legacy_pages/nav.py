# Copyright (c) 2026, eCentric and contributors
"""Legacy workflow navigation provider (2B.1 urgent nav patch).

Routes/labels extracted VERBATIM from the legacy production sidebars
(/all-ticket ec-sb + /approval ec-sidebar, ground truth 20260716_004227 after
the mandatory latin-1 mojibake reversal). Do NOT invent or 'fix' URLs here:
PO Request is /form-po and REC Request is /form-rec (NOT /po-form or
/rec-form -- those are retired duplicates). Navigation visibility is UX only.
"""


def _item(key, label, route, group, order, keywords, icon="doc", children=None):
    it = {
        "key": key, "label": label, "route": route, "icon": icon,
        "group": group, "order": order, "active_patterns": [route],
        "visible_when": "internal", "keywords": keywords, "owner": "legacy_pages",
    }
    if children:
        it["children"] = children
    return it


def _child(key, label, route, order, keywords):
    return {
        "key": key, "label": label, "route": route, "icon": "doc", "order": order,
        "active_patterns": [route], "visible_when": "internal",
        "keywords": keywords, "owner": "legacy_pages",
    }


def items():
    return [
        _item("legacy.create_mso", "MSO Request", "/mso-form", "Tạo mới", 10,
              ["mso", "tao moi", "master service order"]),
        _item("legacy.create_so", "SO Request", "/so-form", "Tạo mới", 20,
              ["so", "service order", "tao moi"]),
        _item("legacy.create_po", "PO Request", "/form-po", "Tạo mới", 30,
              ["po", "procurement", "mua hang", "tao moi"]),
        # GD2 C2 scope: retire legacy.create_rec (/form-rec), legacy.create_vendor
        # (/vendor-request), gbs.po (/gbs-po-form), gbs.so (/gbs-so-form).
        # MSO/SO/PO kept on governed routes (/mso-form, /so-form, /form-po).
        #
        # "/others" submenu removed entirely: its children legacy.create_client
        # (/client-request) and legacy.create_contract (/contract-request) are
        # UNAVAILABLE in C2 scope — their submit endpoints
        # (ecentric_workspace.api.submit_client_request / submit_contract_request)
        # do not exist (HTTP 417 "Failed to get method"), so the forms cannot
        # submit. The two Web Pages are left at published=0 (page source/backend
        # NOT deleted); submit API is intentionally NOT implemented in C2. With no
        # children left, the /others parent is dropped (an empty toggle would
        # render a broken /others leaf link).
        # HƯỚNG DẪN: one collapsible parent (same minimal children mechanism as
        # Others). "/guides" is a non-navigable anchor route (button toggle).
        _item("docs.guides", "Hướng dẫn", "/guides", "Hướng dẫn", 10,
              ["huong dan", "docs", "tai lieu"], children=[
                  _child("docs.architecture", "Docs / Architecture", "/docs/architecture", 10,
                         ["docs", "tai lieu", "architecture"]),
                  _child("docs.gbsflow", "GBS Flow & Definitions", "/docs/gbs-flow", 20,
                         ["gbs flow", "dinh nghia", "docs"]),
              ]),
    ]
