# Copyright (c) 2026, eCentric and contributors
"""Doi rules_version moi khi sua Host QC Settings hoac Host QC Rule - may so so nay qua heartbeat de tai lai
bang nguong. Gia tri = thoi diem sua (de doc, tang dan)."""
from ecentric_workspace.host_qc.repositories.settings_repository import SettingsRepository
from ecentric_workspace.host_qc.utils.time import now


class BumpRulesVersionService:
    def __init__(self, settings=None, clock=now):
        self.settings = settings
        self.clock = clock

    def execute(self, settings_doc=None):
        version = self.clock().strftime("%Y-%m-%d %H:%M:%S.%f")
        if settings_doc is not None:          # dang luu chinh trang Settings: ghi vao doc truoc khi luu
            settings_doc.rules_version = version
        else:
            (self.settings or SettingsRepository()).set_rules_version(version)
        return version
