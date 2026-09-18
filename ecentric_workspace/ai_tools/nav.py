# Copyright (c) 2026, eCentric and contributors
"""Nhom "AI Tool" trong menu ben trai.

MOT muc cha tro toi trang hub /ai-tool (cac the cong cu), va cac cong cu la
children. Lam theo kieu nay vi so cong cu AI se tang dan: them mot cong cu =
them mot dict trong children + mot the tren trang hub, khong dung toi shell.

Cong cu dau tien: AI Livestream Script (/ai-content) - sinh script livestream
theo SKU, cham luat bang rule pack, luu phien theo brand. Trang tu gac quyen
bang role "EC AI Content" o phia server; muc menu de "internal" vi visible_when
chi la tro giup UX, khong phai bien gioi bao mat, va muc role:<Role> bi loai
khoi nav tinh (fallback) nen se khong bao gio hien o thanh ben duc san.
"""

AI_TOOL_ITEMS = [
    {
        "key": "ai_tools.hub",
        "label": "AI Tool",
        "route": "/ai-tool",
        "icon": "grid",
        "group": "",
        "order": 20,
        "active_patterns": ["/ai-tool"],
        "visible_when": "internal",
        "keywords": ["ai", "ai tool", "cong cu ai", "tro ly ai", "tool"],
        "owner": "ai_tools",
        "children": [
            {
                "key": "ai_tools.livestream",
                "label": "AI Livestream Script",
                "route": "/ai-content",
                "icon": "doc",
                "order": 10,
                "active_patterns": ["/ai-content"],
                "visible_when": "internal",
                "keywords": ["script", "livestream", "live", "ai content",
                             "kich ban", "host", "phien live", "brand"],
                "owner": "ai_tools",
            },
        ],
    },
]


def items():
    return [dict(it) for it in AI_TOOL_ITEMS]
