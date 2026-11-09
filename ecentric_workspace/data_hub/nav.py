# Copyright (c) 2026, eCentric and contributors
"""Menu trai cua Trung tam Du lieu (ngu canh `data_hub`, khu "Bao cao" tren thanh - luat A73).

Bon muc, nhom "Dữ liệu" trong cot khu Bao cao (shell/nav.py RAIL_LAYOUTS["reports"]):
  * Yêu cầu dữ liệu (/du-lieu)           - moi nhan vien. Mau "/du-lieu/*" CO CHU Y: resolve_context()
    cham diem tren menu KHONG co role, thieu mau nay thi /du-lieu/dieu-phoi roi ve ngu canh mac dinh.
  * Data availability (/du-lieu/san-co)  - moi nhan vien (dot 2; dot 1 hien "Sắp có").
  * Điều phối (/du-lieu/dieu-phoi)       - chi role team Data (UX; trang tu kiem quyen o server).
  * Quy tắc thời hạn (/du-lieu/quy-tac)  - chi role team Data (nguoi duyet quy tac mo bang link /
    tab tren trang; trang tu kiem quyen).
visible_when chi la tro giup UX (shell/nav.py), khong phai bien gioi bao mat.
"""
from ecentric_workspace.data_hub import constants as C

_TEAM = "role:" + C.DEFAULT_DATA_TEAM_ROLE

ITEMS = [
    {"key": "data_hub.requests", "label": "Yêu cầu dữ liệu", "route": C.ROUTE, "icon": "list",
     "group": "Dữ liệu", "order": 10, "active_patterns": [C.ROUTE, C.ROUTE + "/*"],
     "visible_when": "internal", "owner": "data_hub",
     "keywords": ["yeu cau du lieu", "data request", "trung tam du lieu", "power bi", "crawl", "dashboard",
                  "team data", "du lieu"]},
    {"key": "data_hub.availability", "label": "Data availability", "route": C.ROUTE_AVAIL, "icon": "grid",
     "group": "Dữ liệu", "order": 20, "active_patterns": [C.ROUTE_AVAIL],
     "visible_when": "internal", "owner": "data_hub",
     "keywords": ["data availability", "du lieu san co", "sharepoint", "data warehouse"]},
    {"key": "data_hub.ops", "label": "Điều phối", "route": C.ROUTE_OPS, "icon": "grid",
     "group": "Dữ liệu", "order": 30, "active_patterns": [C.ROUTE_OPS],
     "visible_when": _TEAM, "owner": "data_hub", "keywords": ["dieu phoi du lieu", "team data"]},
    {"key": "data_hub.rules", "label": "Quy tắc thời hạn", "route": C.ROUTE_RULES, "icon": "clock",
     "group": "Dữ liệu", "order": 40, "active_patterns": [C.ROUTE_RULES],
     "visible_when": _TEAM, "owner": "data_hub", "keywords": ["quy tac thoi han", "sla du lieu"]},
]


def items():
    return [dict(it) for it in ITEMS]
