"""Compatibility alias for ecentric_workspace.approval_center.shared.workflow.holidays."""
import sys
from ecentric_workspace.approval_center.shared.workflow.holidays import *  # noqa: F401,F403
sys.modules[__name__] = sys.modules["ecentric_workspace.approval_center.shared.workflow.holidays"]

