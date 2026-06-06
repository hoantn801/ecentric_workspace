"""Whitelisted Alert Center endpoints - Phase C: controlled mock testing only.

Security (decision D2 + Phase C rule 9):
  * Both endpoints are SYSTEM MANAGER ONLY for MVP (frappe.only_for) - mock
    ingestion writes audit records and must not be public.
  * POST-only (Frappe GET write auto-rollback footgun).
  * Brand-scoped KAM/manager/leader read APIs come in Phase E, built on
    ecentric_workspace.alerts.permissions.
"""
import json

import frappe

from ecentric_workspace.alerts.services import action_queue, ingestion


@frappe.whitelist(methods=["POST"])
def ingest_mock_orders(payload=None):
    """payload: JSON string or object - either a list of normalized orders or
    {"orders": [...]}. See services/ingestion.py docstring for the schema.
    Runs ingestion + rules engine + dry-run action queue processing."""
    frappe.only_for("System Manager")
    data = payload
    if isinstance(data, str):
        data = json.loads(data or "[]")
    orders = data.get("orders") if isinstance(data, dict) else data
    if not isinstance(orders, list) or not orders:
        frappe.throw("payload must contain a non-empty list of orders")
    results = ingestion.ingest_orders(orders)
    queue = action_queue.process_pending_actions()
    return {"orders": results, "action_queue": queue}


@frappe.whitelist(methods=["POST"])
def process_action_queue():
    """Manually drain Pending Stock Safety Lock actions (dry-run era)."""
    frappe.only_for("System Manager")
    return action_queue.process_pending_actions()
