"""Compatibility alias for ecentric_workspace.approval_center.shared.catalog_api."""
import sys
from ecentric_workspace.approval_center.shared import catalog_api as _implementation
sys.modules[__name__] = _implementation
