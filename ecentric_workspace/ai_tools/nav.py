# Copyright (c) 2026, eCentric and contributors
"""Nhom "AI Tool" trong menu ben trai.

HAI muc tang mot:
  1. "AI Tool" -> /ai-tool, trang hub liet ke cac the cong cu.
  2. Moi cong cu dung rieng mot muc, children la cac man BEN TRONG no.

Truoc day cong cu la children cua hub. Doi vi shell CHI CHO HAI TANG
("nested children are not supported" trong shell/nav.py), ma AI Livestream
Script can hai man con (Ho so Brand, Bo luat) hien ra menu. De cong cu lam
children cua hub thi hai man do khong con cho de nam.

Them mot cong cu AI moi = them mot dict tang mot o day + mot the tren trang
hub. Khong dung toi shell/nav.py.

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
    },
    {
        # Bam thang vao muc cha = mo danh sach phien live (/ai-content), nen
        # KHONG co muc con "Phien live": trung route se bi validate tu choi.
        "key": "ai_tools.livestream",
        "label": "AI Livestream Script",
        "route": "/ai-content",
        "icon": "doc",
        "group": "",
        "order": 21,
        "active_patterns": ["/ai-content"],
        "visible_when": "internal",
        "keywords": ["script", "livestream", "live", "ai content",
                     "kich ban", "host", "phien live", "brand"],
        "owner": "ai_tools",
        "children": [
            {
                "key": "ai_tools.livestream.brand",
                "label": "Ho so Brand",
                "route": "/ai-content/ho-so-brand",
                "icon": "doc",
                "order": 10,
                "active_patterns": ["/ai-content/ho-so-brand"],
                "visible_when": "internal",
                "keywords": ["brand", "ho so brand", "tai lieu brand", "sku"],
                "owner": "ai_tools",
            },
            {
                "key": "ai_tools.livestream.rules",
                "label": "Bo luat",
                "route": "/ai-content/bo-luat",
                "icon": "gear",
                "order": 20,
                "active_patterns": ["/ai-content/bo-luat"],
                "visible_when": "internal",
                "keywords": ["luat", "bo luat", "rule pack", "tu cam",
                             "phien am", "thoi luong"],
                "owner": "ai_tools",
            },
        ],
    },
]


def items():
    return [dict(it) for it in AI_TOOL_ITEMS]
