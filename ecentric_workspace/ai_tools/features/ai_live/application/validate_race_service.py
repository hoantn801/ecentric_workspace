# Copyright (c) 2026, eCentric and contributors
"""Khi luu EC AI Live Race (API hoac sua tren Desk): chuan hoa trang thai trao giai, dem so nguoi thang / da trao /
khong lien lac duoc de hien o danh sach."""
from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.domain import race_rules as RR


class ValidateRaceService:
    def execute(self, doc):
        rows = []
        for row in doc.winners or []:
            row.prize_status = RR.prize_label(row.prize_status) or C.PRIZE_STATUS[C.PRIZE_DEFAULT]
            row.note = str(row.note or "").strip()[:C.MAX_RACE_NOTE]
            rows.append({"status": row.prize_status})
        c = RR.counts(rows)
        doc.winners_n, doc.awarded_n, doc.unreachable_n = c["winners_n"], c["awarded_n"], c["unreachable_n"]
        return doc
