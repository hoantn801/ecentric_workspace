# Copyright (c) 2026, eCentric and contributors
"""Hang so gbs_monitor."""

IP_SERVICES = ("https://api.ipify.org?format=json", "https://checkip.amazonaws.com/")
BOXME_WHOAMI = "/api/method/frappe.auth.get_logged_user"
TIMEOUT = (5, 20)

#: Luu trang thai ben vung (tabDefaultValue) - cache co the bi xoa.
KEY_IP = "ec_gbs_egress_ip"
KEY_STATUS = "ec_gbs_boxme_status"
KEY_CHECKED = "ec_gbs_monitor_checked_at"

#: IP da gui boxme whitelist 19/11/2026 (do bang fixDX). Lan chay dau so voi gia tri nay.
KNOWN_IP = "13.228.14.29"

CONF_RECIPIENTS = "ec_gbs_monitor_recipients"
CONF_DISABLED = "ec_gbs_monitor_disabled"
FALLBACK_ROLE = "System Manager"

EVENT_TYPE = "system_critical"
