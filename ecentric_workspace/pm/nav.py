# Copyright (c) 2026, eCentric and contributors
"""PM navigation provider (context `pm`). ONE registry entry: the SPA owns
its internal view navigation (#pm-nav data-view router, preserved as the
module rail next to the shared shell mount)."""

ITEMS = [
    {"key": "pm.app", "label": "Công việc", "route": "/pm", "icon": "briefcase",
     "group": "Quản lý dự án", "order": 10, "active_patterns": ["/pm"],
     "visible_when": "internal", "owner": "pm",
     "keywords": ["cong viec", "task", "project", "pm", "du an"]},
]


def items():
    return list(ITEMS)
