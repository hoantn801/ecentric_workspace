# Copyright (c) 2026, eCentric and contributors
"""Luu toan bo khung gio cua 1 phien tu man Lich live (keo tao / keo doi / xoa / chep tuan).
fix10g: chi ghi vao BAN NHAP (SaveDraftService) - app nhan khi bam Phat hanh tren man Dong bo."""
from ecentric_workspace.ai_tools.features.ai_live.application.save_draft_service import SaveDraftService


class SaveSlotsService:
    def __init__(self, sessions=None, machines=None, clock=None):
        self.draft = SaveDraftService(sessions, machines, clock)

    def execute(self, roles, name, slots, user=""):
        return self.draft.execute(user, roles, name, slots=slots if slots is not None else [])
