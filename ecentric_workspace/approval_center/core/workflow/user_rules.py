"""Compatibility alias for ecentric_workspace.approval_center.shared.workflow.user_rules."""
import sys
from ecentric_workspace.approval_center.shared.workflow.user_rules import *  # noqa: F401,F403
sys.modules[__name__] = sys.modules["ecentric_workspace.approval_center.shared.workflow.user_rules"]

