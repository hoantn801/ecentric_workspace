# Copyright (c) 2026, eCentric and contributors
"""Menu Cong cu dung chung (ngu canh `shared_tools`) - Cong ty › Cong cu › Kalodata dung chung.

visible_when chi la tro giup UX (shell/nav.py), KHONG phai bien gioi bao mat: moi API trong
shared_tools/controllers/api.py tu kiem quyen (service.load_tool).
"""
from ecentric_workspace.shared_tools import constants as C

ITEMS = [
    {"key": "shared_tools.kalodata", "label": "Kalodata dùng chung", "route": "/" + C.ROUTE, "icon": "chart",
     "group": "", "order": 10, "active_patterns": ["/" + C.ROUTE],
     "visible_when": "internal", "owner": "shared_tools",
     "keywords": ["kalodata", "tiktok shop", "san pham", "creator", "kol", "nghien cuu thi truong",
                  "dung chung", "tai khoan chung", "hang doi"]},
]


def items():
    return [dict(it) for it in ITEMS]
