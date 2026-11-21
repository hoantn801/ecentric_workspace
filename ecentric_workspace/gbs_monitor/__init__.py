# Copyright (c) 2026, eCentric and contributors
"""Canh bao som khi tich hop GBS (boxme) sap/da bi chan vi IP.

19/11/2026: boxme whitelist IP cho khoa API cua user tich hop `commercial@ecentric.vn`. Site chay tren
server DUNG CHUNG cua Frappe Cloud (f21-singapore) -> IP goi ra KHONG tinh (docs Frappe Cloud: muon IP
tinh phai co server rieng). Neu Frappe doi server, IP doi, boxme tra 401/403 va moi dong bo SO/PO dung.

Job moi gio:
  1. hoi IP goi ra hien tai cua server (dich vu cong khai);
  2. goi thu boxme `frappe.auth.get_logged_user` bang khoa trong GBS Settings;
  3. IP khac lan truoc  -> bao ngay (truoc ca khi boxme chan) kem IP moi de gui GBS whitelist;
     boxme 401/403      -> bao khan kem IP hien tai.
Nguoi nhan: site_config `ec_gbs_monitor_recipients` (list email); trong thi nguoi giu role System Manager.
Tat: site_config `ec_gbs_monitor_disabled = 1`.
"""
