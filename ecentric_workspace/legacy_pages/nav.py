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
        _item("legacy.create_rec", "REC Request", "/form-rec", "Tạo mới", 40,
              ["rec", "reconciliation", "doi soat", "tao moi"]),
        # "/others" is a NON-NAVIGABLE anchor route (unique, never rendered as a
        # link -- the submenu toggle is a button). Low-frequency creation routes.
        _item("legacy.others", "Others", "/others", "Tạo mới", 50,
              ["khac", "others"], children=[
                  _child("legacy.create_client", "Client Request", "/client-request", 10,
                         ["client", "khach hang"]),
                  _child("legacy.create_vendor", "Vendor Request", "/vendor-request", 20,
                         ["vendor", "nha cung cap"]),
                  _child("legacy.create_contract", "Contract Request", "/contract-request", 30,
                         ["contract", "hop dong"]),
              ]),
        _item("gbs.po", "GBS Purchase Order", "/gbs-po-form", "GBS", 10,
              ["gbs", "purchase order", "boxme"]),
        _item("gbs.so", "GBS Sales Order", "/gbs-so-form", "GBS", 20,
              ["gbs", "sales order", "boxme"]),
        _item("docs.architecture", "Docs / Architecture", "/docs/architecture", "Hướng dẫn", 10,
              ["docs", "tai lieu", "architecture"]),
        _item("docs.gbsflow", "GBS Flow & Definitions", "/docs/gbs-flow", "Hướng dẫn", 20,
              ["gbs flow", "dinh nghia", "docs"]),
    ]
