"""Compatibility alias for the shared Approval Center workflow implementation."""
import sys

from ecentric_workspace.approval_center.shared.workflow import transitions as _implementation

sys.modules[__name__] = _implementation
