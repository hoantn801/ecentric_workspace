"""Stable compatibility API cho KOL Acceptance (BBNT tung dot, 24/11/2026)."""
from ecentric_workspace.approval_center.shared.api_adapter import bind

globals().update(bind("KOL_ACCEPTANCE"))
