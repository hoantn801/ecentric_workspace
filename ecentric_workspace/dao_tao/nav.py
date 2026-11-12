# Copyright (c) 2026, eCentric and contributors
"""Menu trai cua module Dao tao (ngu canh `dao_tao`) - Cong ty › Dao tao (Hoan chot mockup D).

  * "Học" (/dao-tao) - moi nhan vien. Trang bai (/dao-tao/bai) sang den muc nay.
  * "Quiz trực tiếp" (/quiz) - ai cung vao choi; Ban dao tao / HR thay them bo quiz + mo phong
    (quyen kiem o server, trang tu an phan quan ly).
  * "Quản lý bài học" (/dao-tao/quan-ly) - chi hien voi role EC Training Host. HR Manager /
    HR User / System Manager van vao duoc (server kiem quyen) qua nut tren trang Hoc.
    visible_when chi la tro giup UX (shell/nav.py), khong phai bien gioi bao mat.
Mau "/dao-tao/*" o muc Hoc la CO CHU Y (giong surveys/nav.py): resolve_context() cham diem tren
menu KHONG co role, thieu mau nay thi /dao-tao/quan-ly roi ve ngu canh mac dinh.
Trang /quiz/choi va /quiz/chieu la toan man hinh (khong co menu) nhung van thuoc ngu canh nay.
"""
from ecentric_workspace.dao_tao import constants as C

ITEMS = [
    {"key": "dao_tao.learn", "label": "Học", "route": "/" + C.ROUTE_LEARN, "icon": "book",
     "group": "", "order": 10, "active_patterns": ["/" + C.ROUTE_LEARN, "/" + C.ROUTE_LEARN + "/*"],
     "visible_when": "internal", "owner": "dao_tao",
     "keywords": ["dao tao", "hoc", "bai hoc", "training", "ai", "claude", "thuc hanh", "binh chon"]},
    {"key": "dao_tao.quiz", "label": "Quiz trực tiếp", "route": "/" + C.ROUTE_QUIZ, "icon": "target",
     "group": "", "order": 20, "active_patterns": ["/" + C.ROUTE_QUIZ, "/" + C.ROUTE_QUIZ + "/*"],
     "visible_when": "internal", "owner": "dao_tao",
     "keywords": ["quiz", "kahoot", "quizizz", "do vui", "ma phong", "choi"]},
    {"key": "dao_tao.admin", "label": "Quản lý bài học", "route": "/" + C.ROUTE_LESSON_ADMIN,
     "icon": "gear", "group": "", "order": 30, "active_patterns": ["/" + C.ROUTE_LESSON_ADMIN],
     "visible_when": "role:" + C.ROLE_HOST, "owner": "dao_tao",
     "keywords": ["soan bai", "quan ly dao tao", "bai thuc hanh"]},
]


def items():
    return [dict(it) for it in ITEMS]
