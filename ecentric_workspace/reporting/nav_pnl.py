# Copyright (c) 2026, eCentric and contributors
"""PnL navigation provider (context `pnl`).

Trang /pnl-dashboard gom 5 dashboard trong MOT trang, truoc day chuyen bang
mot hang tab o dau trang. Hoan 11/09: tu Trung tam Bao cao bam vao "Doanh thu
(PnL)" thi trang nen co SIDEBAR PHU RIENG liet ke 5 dashboard do.

Cach lam giong het pm/nav.py: `pnl.app` la muc canonical (resolve_context +
tim kiem toan cuc) nhung KHONG hien trong sidebar - 5 view moi la nav. Moi
view mang `view: True` nen bi loai khoi compose_all()/search/warm (chung la
view trong cung mot trang, khong phai diem den rieng), va route co `#` nen tu
dong nam ngoai moi duong warm theo luat no-hash san co.

Bam mot view chi doi hash tren /pnl-dashboard -> trang tu doi dashboard, KHONG
tai lai trang. ec_shell.js da co san hashActiveKey() nen viec to sang muc dang
xem khong can them code.

QUYEN: `internal` o day chi la hien thi. Server Script `ec_pnl_data` van tu
chan (System Manager / EC Viewer Permission / phong Management - EC), va card
trong Trung tam Bao cao van gioi han rieng. Sidebar nay chi xuat hien khi
nguoi dung DANG O /pnl-dashboard - vao duoc trang do nghia la da qua cong.
"""

APP = {
    "key": "pnl.app", "label": "Doanh thu (PnL)", "route": "/pnl-dashboard",
    "icon": "wallet", "group": "Doanh thu & Lợi nhuận", "order": 5,
    "active_patterns": ["/pnl-dashboard"],
    "visible_when": "internal", "owner": "reporting_pnl",
    "keywords": ["pnl", "doanh thu", "loi nhuan", "chi phi", "opex", "bao cao"],
    # canonical entry (resolve_context + tim kiem); KHONG phai mot dong sidebar
    # -- 5 view ben duoi MOI la nav, y het pm.app.
    "sidebar_hidden": True,
}

VIEWS = [
    ("pnl.view.tong_quan", "Tổng quan", "/pnl-dashboard#tong-quan", "grid", 10),
    ("pnl.view.brand", "Theo brand", "/pnl-dashboard#brand", "briefcase", 20),
    ("pnl.view.doanh_thu", "Cấu trúc doanh thu", "/pnl-dashboard#doanh-thu", "chart", 30),
    ("pnl.view.chi_phi", "Cấu trúc chi phí", "/pnl-dashboard#chi-phi", "wallet", 40),
    ("pnl.view.opex", "OPEX", "/pnl-dashboard#opex", "list", 50),
]


def items():
    out = [dict(APP)]
    for key, label, route, icon, order in VIEWS:
        out.append({
            "key": key, "label": label, "route": route, "icon": icon,
            "group": "Doanh thu & Lợi nhuận", "order": order,
            # giu "/pnl-dashboard" de resolve_context van tro ve day; viec chon
            # muc dang xem theo hash do client lam.
            "active_patterns": ["/pnl-dashboard"],
            "visible_when": "internal", "owner": "reporting_pnl", "view": True,
        })
    return out
