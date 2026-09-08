# Copyright (c) 2026, eCentric and contributors
"""Muc "Huong dan su dung" trong menu ben trai.

CHI MOT muc, tro toi trang muc luc /huong-dan. Tung bai KHONG len menu: menu la thu
nguoi dung nhin moi ngay, nhoi 24 bai vao do thi no dai vo tan va moi lan them form
lai phai sua menu. Loi vao "dung luc dang can" la icon "?" tren the o Approval Center
va tren chinh trang form (tro thang toi bai cua form do) - xem guides.registry.

Muc nay thuoc ca hai ngu canh dang dung (`approval_document` va `hr`) vi huong dan
khong thuoc rieng phong nao; provider dang ky mot lan o shell/nav.py.
"""

GUIDE_ITEMS = [
    {
        "key": "guides.index",
        "label": "Hướng dẫn sử dụng",
        "route": "/huong-dan",
        "icon": "book",
        "group": "Hướng dẫn",
        "order": 10,
        # "/huong-dan/*": moi BAI huong dan deu quy ve muc luc nay. Nho vay
        # breadcrumb cua mot bai la "Huong dan / Huong dan su dung / <ten bai>" -
        # cai o giua la mot LINK ve muc luc, tuc la khong bai nao bi bo vo du no
        # khong co dong menu rieng. Them bai moi khong phai sua nav.
        "active_patterns": ["/huong-dan", "/huong-dan/*"],
        "visible_when": "internal",
        "keywords": ["huong dan", "guide", "help", "tro giup", "cach dung",
                     "dnmh", "dntt", "ky so", "quy trinh"],
        "owner": "guides",
        # sidebar_hidden (08/09): muc nay CO trong registry (o tim kiem "Tim chuc
        # nang..." tim ra, breadcrumb va route resolution hoat dong) nhung CHUA ve
        # vao thanh ben. Ly do rat cu the: thanh ben tinh duoc DUC SAN vao HTML cua
        # tung trang (shell.fallback), nen them mot dong menu = 40 trang phai dung
        # lai + 40 muc ban ke ma bam + mot patch resync ca 40 - trong do co nhung
        # trang co khoa chong troi rieng. Do la mot dot deploy rieng, khong ghep
        # chung voi viec ra mat bai huong dan dau tien.
        # Bo co nay khi lam dot do; loi vao chinh hom nay la icon "?" tren the
        # Approval Center + nut trong trang phieu.
        "sidebar_hidden": True,
    },
]


def items():
    return list(GUIDE_ITEMS)
