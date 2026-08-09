# Copyright (c) 2026, eCentric and contributors
"""Tao / dong bo Web Page /pnl-dashboard (Dashboard PnL - giai doan 1 doanh thu).

Idempotent: page_sync co drift lock (expect_sha), nen chay lai chi tra ve
"unchanged" khi live dung bang snapshot repo, hoac "refused" khi live da bi sua
tay -- khong bao gio ghi de mat thay doi tren live.
"""
from ecentric_workspace.reporting.pnl_dashboard import page_sync


def execute():
    page_sync.sync()
