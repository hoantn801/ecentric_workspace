"""Compatibility alias for ecentric_workspace.approval_center.shared.requests.capabilities."""
import sys
from ecentric_workspace.approval_center.shared.requests.capabilities import *  # noqa: F401,F403
sys.modules[__name__] = sys.modules["ecentric_workspace.approval_center.shared.requests.capabilities"]

