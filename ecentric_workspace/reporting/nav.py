# Copyright (c) 2026, eCentric and contributors
"""Reporting navigation provider (context `reporting`)."""

ITEMS = [
    {"key": "reporting.weekly", "label": "Báo cáo tuần", "route": "/weekly-update",
     "icon": "chart", "group": "Báo cáo & Phân tích", "order": 10,
     "active_patterns": ["/weekly-update"],   # ?week= deep links: query is
     # stripped by matchActive -- same entry, never a separate item
     "visible_when": "internal", "owner": "reporting",
     "keywords": ["bao cao tuan", "weekly", "wtu"]},
    {"key": "reporting.pulse", "label": "Team Pulse", "route": "/team-pulse",
     "icon": "activity", "group": "Báo cáo & Phân tích", "order": 20,
     "active_patterns": ["/team-pulse"],
     "visible_when": "internal", "owner": "reporting", "keywords": ["team pulse", "pulse"]},
]


def items():
    return list(ITEMS)
