# Copyright (c) 2026, eCentric and contributors
"""Alert Center navigation provider (context `alert_center`).

Mirrors the module's own live sidebar IA 1:1 (5 real routes). The legacy
in-page hash quick-link /alerts#al-alert-list is NOT a registry item (hash
deep-links stay functional; matchActive strips hashes)."""

ITEMS = [
    {"key": "alerts.dashboard", "label": "Dashboard", "route": "/alerts", "icon": "bell",
     "group": "Alert Center", "order": 10, "active_patterns": ["/alerts"],
     "visible_when": "internal", "owner": "alerts",
     "keywords": ["alert", "canh bao", "alert center"]},
    {"key": "alerts.policies", "label": "Policies", "route": "/alerts/policies", "icon": "doc",
     "group": "Alert Center", "order": 20, "active_patterns": ["/alerts/policies"],
     "visible_when": "internal", "owner": "alerts", "keywords": ["policy", "chinh sach alert"]},
    {"key": "alerts.rules", "label": "Rules", "route": "/alerts/rules", "icon": "target",
     "group": "Alert Center", "order": 30, "active_patterns": ["/alerts/rules"],
     "visible_when": "internal", "owner": "alerts", "keywords": ["rule", "luat"]},
    {"key": "alerts.locks", "label": "Locks", "route": "/alerts/locks", "icon": "gear",
     "group": "Alert Center", "order": 40, "active_patterns": ["/alerts/locks"],
     "visible_when": "internal", "owner": "alerts", "keywords": ["lock", "khoa ton"]},
    {"key": "alerts.health", "label": "Integration Health", "route": "/alerts/integration-health",
     "icon": "activity", "group": "Alert Center", "order": 50,
     "active_patterns": ["/alerts/integration-health"],
     "visible_when": "internal", "owner": "alerts", "keywords": ["integration", "health"]},
]


def items():
    return list(ITEMS)
