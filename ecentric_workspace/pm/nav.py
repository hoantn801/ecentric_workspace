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
    ("pm.view.mywork", "Việc cần làm", "/pm#mywork", "inbox", 20),
    ("pm.view.assignments", "Được giao cho tôi", "/pm#received", "recv", 22),
    ("pm.view.given", "Tôi đã giao", "/pm#given", "send", 24),
    # Hotfix 23 (PO 27/11/2026, B2): "Lịch làm việc" + "Phòng họp" gộp thành MỘT màn "Lịch & phòng họp".
    ("pm.view.schedule", "Lịch & phòng họp", "/pm#schedule", "calendar", 25),
    # 05/11/2026: phòng họp văn phòng (lịch phòng từ Teams + đặt phòng) - pm.api.rooms. Hotfix 23: không còn dòng
    # riêng trên cột (sidebar_hidden); route /pm#rooms vẫn chạy = chế độ "Phòng họp" trong màn Lịch & phòng họp.
    ("pm.view.rooms", "Phòng họp", "/pm#rooms", "users", 26),
    ("pm.view.overview", "Điều phối", "/pm#coordinate", "grid", 30),
    ("pm.view.projects", "Dự án", "/pm#projects", "folder", 35),
    ("pm.view.work", "Tất cả việc", "/pm#work/list", "list", 40),
    ("pm.view.timesheet", "Timesheet", "/pm#timesheet", "clock", 50),
    ("pm.view.guide", "Hướng dẫn", "/pm#guide", "book", 80),
]


# Hotfix 16 (PO 17/11/2026): "Được giao cho tôi" + "Tôi đã giao" merged into "Việc cần làm" (tabs Việc tôi làm /
# Việc tôi giao / Tôi theo dõi; "Cần đồng ý" is the block on top of the queue). The ROUTES stay (notification
# links, #given/rep "Lặp lại", #given/done "Đã xong"); only the sidebar ROW goes (sidebar_hidden, so the
# shared rail does not drop them into "Mục khác").
MERGED_INTO_MYWORK = ("pm.view.assignments", "pm.view.given")
# Hotfix 23 (PO 27/11/2026): Phòng họp gộp vào "Lịch & phòng họp" (pm.view.schedule owns #rooms + #schedule/rooms).
MERGED_INTO_SCHEDULE = ("pm.view.rooms",)


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
            # #project/<id> (chi tiet du an) sang menu "Du an", khong roi ve muc dau "Viec cua toi"
            **({"hash_segments": ["project"]} if key == "pm.view.projects" else {}),
            **({"hash_segments": ["rooms"]} if key == "pm.view.schedule" else {}),
            **({"sidebar_hidden": True} if key in MERGED_INTO_MYWORK + MERGED_INTO_SCHEDULE else {}),
        })
    return out
