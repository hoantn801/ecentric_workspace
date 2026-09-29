# Copyright (c) 2026, eCentric and contributors
"""Alert Center: 5 Web Page lay nguon TU REPO (29/09/2026, brief NHIEU_LOP/brief_alert_center.md).

Truoc day nguon la HTML dang song tren site: `alerts/pages.py` chi va hai vung khung (menu +
topbar) vao ban live. Sua mot dong JS nghia la sua tay tren Desk, khong ai review, khong co
lich su. Tu dot nay moi trang nam o `site_pages/<trang>/main_section.html`, dong bo bang
page_sync co KHOA CHONG TROI (BASELINE_SHA256 / SUPERSEDES_SHA256 + sha ghi lai sau moi lan
ghi), giong /pnl-dashboard va /sla.

Anh chup dau tien (commit dau cua dot nay) la BAN LIVE TUNG BYTE: sha256 cua ca 5 file khop
main_section_html tren team.ecentric.vn luc 29/09/2026. Vung `.ec-shell-mount` + topbar giu
nguyen byte do -- server dung lai menu luc render (shell/server_nav.py), khong ai sua tay.

  overview            /alerts                     alert-center
  policies            /alerts/policies            alert-center-policies
  rules               /alerts/rules               alert-center-rules
  locks               /alerts/locks               alert-center-locks
  integration_health  /alerts/integration-health  alert-center-integration-health
"""

#: Thu tu dong bo (va thu tu trong ket qua tra ve). Module nay KHONG import frappe: `assets`
#: (dau ?v=) va cac test chay duoc khong can bench. Phan ghi site nam o `sync.py`.
PAGE_MODULES = ("overview", "policies", "rules", "locks", "integration_health")
