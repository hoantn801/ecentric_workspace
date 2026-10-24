# Copyright (c) 2026, eCentric and contributors
"""Xuat CSV cuoc dua vit theo bo loc cua trang (1 dong / nguoi thang, co BOM cho Excel)."""
from ecentric_workspace.ai_tools.features.ai_live.application.list_races_service import ListRacesService
from ecentric_workspace.ai_tools.features.ai_live.domain import race_rules as RR


class ExportRacesCsvService:
    def __init__(self, races=None, clock=None):
        self.lister = ListRacesService(races=races, clock=clock)

    def execute(self, roles, brand=None, live=None, date_from=None, date_to=None, outcome=None, prize=None):
        rows, d0, d1, truncated = self.lister.query(roles, brand, live, date_from, date_to, outcome, prize)
        name = "dua_vit_%s_%s%s.csv" % (d0.isoformat(), d1.isoformat(), ("_" + (live or brand)) if (live or brand) else "")
        return {"filename": name, "csv": RR.to_csv(rows), "rows": sum(max(1, len(r["winners"])) for r in rows),
                "truncated": truncated}
