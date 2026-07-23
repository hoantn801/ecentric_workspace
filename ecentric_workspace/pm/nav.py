# Copyright (c) 2026, eCentric and contributors
"""PM navigation provider (context `pm`).

`pm.app` (/pm) is the SINGLE canonical, discoverable PM entry -- it owns
resolve_context, global search/discovery and the homepage portal alias.

The 7 items below are the PM SPA's internal views, surfaced as FLAT sidebar
entries with the SPA's own hash routes (/pm#overview ...). They carry
`view: True`, which excludes them from compose_all()/search/warm (they are
intra-page views of /pm, not separate destinations); `#` routes are also
outside every warm path by the existing no-hash rule. Clicking one only
mutates the hash on /pm -> the existing PM router (`hashchange` -> go())
switches the view with ZERO document reload."""

APP = {"key": "pm.app", "label": "Công việc", "route": "/pm", "icon": "briefcase",
       "group": "Quản lý dự án", "order": 5, "active_patterns": ["/pm"],
       "visible_when": "internal", "owner": "pm",
       "keywords": ["cong viec", "task", "project", "pm", "du an"],
       # canonical discoverable PM entry (resolve_context + global search +
       # portal alias target); NOT a sidebar row -- the 7 views ARE the nav.
       "sidebar_hidden": True}

VIEWS = [
    ("pm.view.overview", "Tổng quan", "/pm#overview", "grid", 10),
    ("pm.view.mywork", "Việc của tôi", "/pm#mywork", "inbox", 20),
    ("pm.view.projects", "Dự án", "/pm#projects", "folder", 30),
    ("pm.view.work", "Công việc", "/pm#work/list", "list", 40),
    ("pm.view.timesheet", "Timesheet", "/pm#timesheet", "clock", 50),
    ("pm.view.recurring", "Recurring", "/pm#recurring", "repeat", 60),
    ("pm.view.assignments", "Yêu cầu giao việc", "/pm#assignments/in", "inbox2", 70),
]


def items():
    out = [dict(APP)]
    for key, label, route, icon, order in VIEWS:
        out.append({
            "key": key, "label": label, "route": route, "icon": icon,
            "group": "Quản lý dự án", "order": order,
            # active_patterns keep "/pm" so resolve_context still maps here;
            # hash-aware active selection happens client-side.
            "active_patterns": ["/pm"],
            "visible_when": "internal", "owner": "pm", "view": True,
        })
    return out
