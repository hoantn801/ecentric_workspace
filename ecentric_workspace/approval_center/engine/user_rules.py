"""Compatibility alias for the Approval Center core workflow implementation."""
import sys

from ecentric_workspace.approval_center.shared.workflow import user_rules as _implementation

sys.modules[__name__] = _implementation
