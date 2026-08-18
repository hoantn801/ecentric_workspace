"""Compatibility alias for shared finance command helpers."""
import sys
from ecentric_workspace.approval_center.shared import finance_support as _implementation
sys.modules[__name__] = _implementation
