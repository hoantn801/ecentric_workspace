"""Compatibility alias for shared definition helpers."""
import sys
from ecentric_workspace.approval_center.shared import definition_support as _implementation
sys.modules[__name__] = _implementation
