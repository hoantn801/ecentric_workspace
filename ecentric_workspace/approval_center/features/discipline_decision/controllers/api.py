"""Stable compatibility API cho Discipline Decision (23/11/2026)."""
from ecentric_workspace.approval_center.shared.api_adapter import bind

globals().update(bind("DISCIPLINE_DECISION"))
