"""Stable compatibility API cho Clearance Request (29/09/2026)."""
from ecentric_workspace.approval_center.shared.api_adapter import bind

globals().update(bind("CLEARANCE_REQUEST"))
