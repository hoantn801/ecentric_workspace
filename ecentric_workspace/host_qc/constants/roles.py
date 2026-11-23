# Copyright (c) 2026, eCentric and contributors
"""Role Host QC (spec muc 1). May studio khong co user - xac thuc bang token may."""
MANAGER = "Host QC Manager"     # Production, Host Management: sua cau hinh, nguong, duyet loi
VIEWER = "Host QC Viewer"       # Lead, Operations: xem
SYSTEM = "System Manager"

MANAGE = (MANAGER, SYSTEM)
VIEW = (MANAGER, VIEWER, SYSTEM)
