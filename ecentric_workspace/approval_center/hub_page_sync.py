"""Compatibility alias for ecentric_workspace.approval_center.hub.page_sync."""
import sys
from ecentric_workspace.approval_center.hub import page_sync as _implementation
sys.modules[__name__] = _implementation
