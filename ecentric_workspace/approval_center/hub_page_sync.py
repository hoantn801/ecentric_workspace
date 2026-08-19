"""Stable public alias for the Approval Center hub page sync."""
import sys
from ecentric_workspace.approval_center.ui.hub import page_sync as _implementation
sys.modules[__name__] = _implementation
