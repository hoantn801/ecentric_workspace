# Copyright (c) 2026, eCentric and contributors
"""PM navigation provider (context `pm`).

`pm.app` (/pm) is the SINGLE canonical, discoverable PM entry -- it owns
resolve_context, global search/discovery and the homepage portal alias.

The 9 items below are the PM SPA's internal views, surfaced as FLAT sidebar
entries with the SPA's own hash routes (/pm#mywork ...). They carry
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
       # portal alias target); NOT a sidebar row -- the 9 views ARE the nav.
       "sidebar_hidden": True}

VIEWS = [
    # PM lam lai (16/10/2026, SPEC _pm_redesign): 9 muc khu Cong viec. GIU key cu de khong vo
    # tham chieu (RAIL_LAYOUTS, test, ban ghi cu): pm.view.assignments = "Duoc giao cho toi",
    # pm.view.overview = "Dieu phoi", pm.view.work = "Tat ca viec". Bo pm.view.recurring
    # (trang Recurring -> tab Lap lai cua "Toi da giao"; route cu #recurring la alias).
    ("pm.view.mywork", "Việc của tôi", "/pm#mywork", "inbox", 20),
    ("pm.view.assignments", "Được giao cho tôi", "/pm#received", "recv", 22),
    ("pm.view.given", "Tôi đã giao", "/pm#given", "send", 24),
    ("pm.view.schedule", "Lịch làm việc", "/pm#schedule", "calendar", 25),
    ("pm.view.overview", "Điều phối", "/pm#coordinate", "grid", 30),
    ("pm.view.projects", "Dự án", "/pm#projects", "folder", 35),
    ("pm.view.work", "Tất cả việc", "/pm#work/list", "list", 40),
    ("pm.view.timesheet", "Timesheet", "/pm#timesheet", "clock", 50),
    ("pm.view.guide", "Hướng dẫn", "/pm#guide", "book", 80),
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
