"""Stable compatibility API backed by the shared request application layer."""
from ecentric_workspace.approval_center.shared.api_adapter import bind

globals().update(bind("SPECIAL_BONUS"))
