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
        "key": "hr.leave",
        "label": "Nghỉ phép",
        "route": "/ec-hr/leave",
        "icon": "calendar",
        "group": "Nhân sự",
        "order": 15,
        "active_patterns": ["/ec-hr/leave"],
        "visible_when": "internal",
        "keywords": ["nghi phep", "leave", "xin nghi", "phep nam", "nghi om"],
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
    {
        "key": "hr.install_guide",
        "label": "Cài app lên điện thoại",
        "route": "/ec-hr/huong-dan-cai-app",
        "icon": "book",
        "group": "Nhân sự",
        "order": 90,
        "active_patterns": ["/ec-hr/huong-dan-cai-app"],
        "visible_when": "internal",
        "keywords": ["huong dan", "cai app", "cai dat", "install", "pwa",
                     "iphone", "android", "man hinh chinh"],
        "owner": "hr",
    },
]


def items():
    return list(HR_ITEMS)
