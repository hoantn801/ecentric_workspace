"""Compatibility alias for the shared Approval Center navigation provider."""
import sys

from ecentric_workspace.approval_center.shared import navigation as _implementation

sys.modules[__name__] = _implementation
