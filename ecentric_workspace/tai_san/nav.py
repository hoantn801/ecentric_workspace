# Copyright (c) 2026, eCentric and contributors
"""Menu trai cua module Quan ly tai san (ngu canh `tai_san`) - Cong ty › Tai san & thiet bi.

visible_when chi la tro giup UX (shell/nav.py), KHONG phai bien gioi bao mat: moi API trong
tai_san/controllers/api.py tu kiem quyen (access.Ctx). Cac muc quan ly hien "internal" o day; cot
rail (RAIL_LAYOUTS khu "company") loc them theo role. Truong phong khong co role rieng nen khong
thay muc menu nhung van mo duoc /tai-san (server loc theo phong cua ho).
Moi trang con co mau rieng va moi muc deu "internal" (27/11: Cap phat / Kiem ke tung la role-only ->
vo tinh khong thay chung, duong dan khop nham mau "/tai-san/*" cua Tong quan, tieu de ghi sai
"Tong quan"). An voi nhan vien thuong nam o "roles" cua RAIL_LAYOUTS, khong o day.
"""
from ecentric_workspace.tai_san import constants as C

ITEMS = [
    {"key": "tai_san.home", "label": "Tổng quan", "route": "/" + C.ROUTE_HOME, "icon": "chart",
     "group": "", "order": 10, "active_patterns": ["/" + C.ROUTE_HOME],
     "visible_when": "internal", "owner": "tai_san",
     "keywords": ["tai san", "thiet bi", "laptop", "may tinh", "khau hao", "asset", "kho may"]},
    {"key": "tai_san.list", "label": "Danh sách thiết bị", "route": "/" + C.ROUTE_LIST, "icon": "list",
     "group": "", "order": 20, "active_patterns": ["/" + C.ROUTE_LIST],
     "visible_when": "internal", "owner": "tai_san",
     "keywords": ["danh sach may", "laptop", "pc", "linh kien", "ram", "ssd", "serial", "tag"]},
    {"key": "tai_san.moves", "label": "Cấp phát & thu hồi", "route": "/" + C.ROUTE_MOVES, "icon": "repeat",
     "group": "", "order": 30, "active_patterns": ["/" + C.ROUTE_MOVES],
     "visible_when": "internal", "owner": "tai_san",
     "keywords": ["cap phat may", "thu hoi may", "ban giao", "nhan su moi", "nghi viec", "clearance"]},
    {"key": "tai_san.repairs", "label": "Sửa chữa", "route": "/" + C.ROUTE_REPAIRS, "icon": "gear",
     "group": "", "order": 40, "active_patterns": ["/" + C.ROUTE_REPAIRS],
     "visible_when": "internal", "owner": "tai_san",
     "keywords": ["sua may", "bao hanh", "hong", "bao hong"]},
    {"key": "tai_san.licenses", "label": "Bản quyền phần mềm", "route": "/" + C.ROUTE_LICENSES, "icon": "doc",
     "group": "", "order": 45, "active_patterns": ["/" + C.ROUTE_LICENSES],
     "visible_when": "internal", "owner": "tai_san",
     "keywords": ["ban quyen", "license", "phan mem", "microsoft 365", "adobe", "het han", "gia han"]},
    {"key": "tai_san.count", "label": "Kiểm kê", "route": "/" + C.ROUTE_COUNT, "icon": "check",
     "group": "", "order": 50, "active_patterns": ["/" + C.ROUTE_COUNT],
     "visible_when": "internal", "owner": "tai_san",
     "keywords": ["kiem ke", "doi chieu", "kiem tra may"]},
    {"key": "tai_san.mine", "label": "Tài sản của tôi", "route": "/" + C.ROUTE_MINE, "icon": "folder",
     "group": "", "order": 60, "active_patterns": ["/" + C.ROUTE_MINE],
     "visible_when": "internal", "owner": "tai_san",
     "keywords": ["may cua toi", "laptop cua toi", "xac nhan nhan may", "bao hong may"]},
]


def items():
    return [dict(it) for it in ITEMS]
