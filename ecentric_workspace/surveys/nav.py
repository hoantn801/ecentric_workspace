# Copyright (c) 2026, eCentric and contributors
"""Menu trai cua module Khao sat (ngu canh `surveys`).

Hai muc:
  * "Khảo sát" (/khao-sat) - moi nhan vien: khao sat dang mo cho minh, da lam, bang vang.
    Trang lam bai (/khao-sat/lam) sang den muc nay.
  * "Quản lý khảo sát" (/khao-sat/quan-ly) - tao / soan / xem ket qua. Chi hien voi role
    EC Survey Creator: HR Manager / System Manager van tao duoc (trang tu kiem quyen o
    server) va vao bang nut "Quản lý khảo sát" tren trang /khao-sat. visible_when chi la tro
    giup UX (shell/nav.py), khong phai bien gioi bao mat.
Mau "/khao-sat/*" o muc hub la CO CHU Y: resolve_context() cham diem tren menu KHONG co role
(roles=None bo muc role:<Role>), nen thieu mau nay thi /khao-sat/quan-ly va /khao-sat/soan roi
ve ngu canh mac dinh (menu Phe duyet). Voi nguoi co role, muc "Quản lý" khop chinh xac (diem
cao hon) nen van duoc to dam dung.
Trang chu (ngu canh `home`) co muc alias tro toi /khao-sat - xem shell/nav.py HOME_PORTAL_ITEMS.
"""
from ecentric_workspace.surveys import constants as C

ITEMS = [
    {"key": "surveys.hub", "label": "Khảo sát", "route": "/" + C.ROUTE_HUB, "icon": "list",
     "group": "", "order": 30, "active_patterns": ["/" + C.ROUTE_HUB, "/" + C.ROUTE_HUB + "/*"],
     "visible_when": "internal", "owner": "surveys",
     "keywords": ["khao sat", "survey", "form", "bieu mau", "google form", "vong quay", "qua"]},
    {"key": "surveys.manage", "label": "Quản lý khảo sát", "route": "/" + C.ROUTE_MANAGE,
     "icon": "gear", "group": "", "order": 31,
     "active_patterns": ["/" + C.ROUTE_MANAGE, "/" + C.ROUTE_BUILDER],
     "visible_when": "role:" + C.ROLE_CREATOR, "owner": "surveys",
     "keywords": ["tao khao sat", "soan khao sat", "ket qua khao sat"]},
]


def items():
    return [dict(it) for it in ITEMS]
