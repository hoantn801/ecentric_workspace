# Copyright (c) 2026, eCentric and contributors
"""Approval Center -- module-owned nav provider for the ERP Shell registry.

UX visibility only. Labels/ordering are presentation; changing them never
changes any permission. Routes must stay in sync with the live Web Page
routes (see shell/README.md). No business data here -- ever.
"""


def items():
    return [
        {
            "key": "apc.catalog",
            "label": "Approval Center",
            "route": "/approvals",
            "icon": "check",
            "group": "Phê duyệt",
            "order": 10,
            # Matches the hub AND every /approvals/<slug> form page, so form
            # pages (e.g. /approvals/hr-activity) highlight this item -- fixing
            # the per-page hardcoded 'active' mismatch class of bugs.
            "active_patterns": ["/approvals", "/approvals/*"],
            "visible_when": "internal",
            "owner": "approval_center",
        },
        {
            "key": "apc.dashboard",
            "label": "Bảng điều hành",
            "route": "/approvals/dashboard",
            "icon": "chart",
            "group": "Phê duyệt",
            "order": 20,
            # Exact pattern outranks apc.catalog's prefix pattern (longest/most
            # specific wins in ec_shell.js matchActive).
            "active_patterns": ["/approvals/dashboard"],
            "visible_when": "internal",
            "owner": "approval_center",
        },
        {
            "key": "apc.legacy_tickets",
            "label": "Duyệt chứng từ",
            "route": "/approval",
            "icon": "doc",
            "group": "Phê duyệt",
            "order": 30,
            # Preserves the existing hub-sidebar affordance to the legacy
            # /approval?id=&type= detail page (T4; page itself untouched).
            "active_patterns": ["/approval"],
            "visible_when": "internal",
            "owner": "approval_center",
        },
    ]
