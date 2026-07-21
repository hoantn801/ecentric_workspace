# Copyright (c) 2026, eCentric and contributors
"""HR employee-facing navigation provider for the Shared ERP Shell registry.

Employee-facing ONLY. Do NOT register unfinished HR admin/backoffice routes
here -- CnB uses native Frappe Desk for MVP.

`no_prerender: True` on the salary item is an EXPLICIT security exclusion: the
shell must never prerender/prefetch/warm the salary route (handled in
shell/api.py serialization + public/js/ec_shell.js prerenderUrls/knownNavRoutes).
The salary route stays session-only + server-side permission enforced regardless.
"""

HR_ITEMS = [
    {
        "key": "hr.attendance",
        "label": "Chấm công",
        "route": "/ec-hr/attendance",
        "icon": "check",
        "group": "Nhân sự",
        "order": 10,
        "active_patterns": ["/ec-hr/attendance"],
        "visible_when": "internal",
        "keywords": ["cham cong", "attendance", "checkin", "check-in", "nghi phep", "leave"],
        "owner": "hr",
    },
    {
        "key": "hr.salary",
        "label": "Phiếu lương",
        "route": "/ec-hr/salary",
        "icon": "doc",
        "group": "Nhân sự",
        "order": 20,
        "active_patterns": ["/ec-hr/salary"],
        "visible_when": "internal",
        "keywords": ["phieu luong", "salary", "luong", "payslip"],
        "owner": "hr",
        # SECURITY: never prerender / prefetch / warm the salary route.
        "no_prerender": True,
    },
]


def items():
    return list(HR_ITEMS)
