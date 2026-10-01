# Copyright (c) 2026, eCentric and contributors
"""Cho DUY NHAT cua module Khao sat duoc cham frappe.db / get_all / get_doc.

Hai file con theo mang du lieu - survey_store (khao sat, phieu, nguoi tham gia) va org_store
(nhan su, phong ban, tep, thong bao) - gop lai o day thanh MOT doi tuong "repo" ma service
nhan qua tham so. Test thay ca module nay bang repository gia (tests/test_services.py).
"""
from ecentric_workspace.surveys.infrastructure.org_store import *  # noqa: F401,F403
from ecentric_workspace.surveys.infrastructure.survey_store import *  # noqa: F401,F403
