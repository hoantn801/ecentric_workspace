"""Pure contract tests for the explicit immutable request-type registry."""
import ast
import os
import unittest
from dataclasses import FrozenInstanceError

from ecentric_workspace.approval_center.shared.requests.contracts import (
    ApprovalDefinition,
    validate_definition,
)
from ecentric_workspace.approval_center.shared.registry import (
    APPROVAL_DEFINITIONS,
    BUSINESS_DOCTYPE_DEFINITIONS,
    _build_registry,
    get_definition,
)


class TestRequestTypeRegistry(unittest.TestCase):
    def test_leave_is_explicitly_registered(self):
        expected = {
            "LEAVE_REQUEST": "EC Leave Request",
            "LATE_EARLY_OUT": "EC Late Early Out Request",
            "COMPENSATION_LEAVE": "EC Compensation Leave Request",
            "EMPLOYEE_REFERRAL": "EC Employee Referral Request",
            "EMPLOYEE_INFO_UPDATE": "EC Employee Information Update Request",
            "AFFILIATE_BONUS_REQUEST": "EC Affiliate Bonus Request",
            "BUDGET_SETTING": "EC Budget Setting Request",
            "PAYMENT_REQUEST": "EC Payment Request",
            "PURCHASE_REQUEST": "EC Purchase Request",
            "ASSET_REQUEST": "EC Asset Request",
            "DATA_REQUEST": "EC Data Request",
            "DOCUMENT_REQUEST": "EC Document Request",
            "RESIGNATION": "EC Resignation Request",
            "SYSTEM_REQUEST": "EC System Request",
            "AI_TOPUP": "EC AI Topup Request",
            "LIVESTREAM_SAMPLE": "EC Livestream Sample Request",
            "HR_ACTIVITY": "EC HR Activity Request",
            "ASSET_DAMAGE_LOSS": "EC Asset Damage Loss Request",
            "DAILY_TARGET": "EC Daily Target Request",
            "LATERAL_MOVE": "EC Lateral Move Request",
            "LIVESTREAM_SUPPLIES": "EC Livestream Supplies Request",
            "OUTSIDE_WORK": "EC Outside Work Request",
            "SERVICE_REFERRAL": "EC Service Referral Request",
            "HIRING_REQUEST": "EC Hiring Request",
            "PROMOTION_REQUEST": "EC Promotion Request",
            "SPECIAL_BONUS": "EC Special Bonus Request",
        }
        self.assertEqual(set(APPROVAL_DEFINITIONS), set(expected))
        for code, doctype in expected.items():
            definition = get_definition(code)
            self.assertEqual(definition.business_doctype, doctype)
            self.assertIs(APPROVAL_DEFINITIONS[definition.code], definition)
            self.assertIs(BUSINESS_DOCTYPE_DEFINITIONS[doctype], definition)

    def test_definition_is_frozen_and_contains_no_mutable_config(self):
        definition = get_definition("LEAVE_REQUEST")
        validate_definition(definition)
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            definition.code = "CHANGED"
        for fieldname in definition.__slots__:
            self.assertNotIsInstance(getattr(definition, fieldname), (list, dict, set))
        with self.assertRaises(TypeError):
            APPROVAL_DEFINITIONS["OTHER"] = definition

    def test_duplicate_code_and_doctype_fail_fast(self):
        original = get_definition("LEAVE_REQUEST")
        duplicate_code = ApprovalDefinition(
            code=original.code, business_doctype="Other Request",
            editable_fields=(), my_request_fields=(), approval_list_fields=(),
            status_labels=(), options_provider=lambda: {}, title_builder=lambda doc: "",
            submitter=lambda name: name, resubmitter=lambda name, actor=None: {})
        with self.assertRaisesRegex(ValueError, "duplicate approval code"):
            _build_registry((original, duplicate_code))
        duplicate_doctype = ApprovalDefinition(
            code="OTHER", business_doctype=original.business_doctype,
            editable_fields=(), my_request_fields=(), approval_list_fields=(),
            status_labels=(), options_provider=lambda: {}, title_builder=lambda doc: "",
            submitter=lambda name: name, resubmitter=lambda name, actor=None: {})
        with self.assertRaisesRegex(ValueError, "duplicate business DocType"):
            _build_registry((original, duplicate_doctype))

    def test_unknown_code_is_not_discovered_implicitly(self):
        with self.assertRaisesRegex(KeyError, "unregistered approval code"):
            get_definition("DOES_NOT_EXIST")


class TestStandardRequestPublicApiContract(unittest.TestCase):
    """Static lock: endpoint names/signatures survive without importing Frappe."""

    EXPECTED = {
        "get_bootstrap": [],
        "get_form_options": [],
        "list_my_requests": ["filters", "start", "page_length"],
        "list_need_my_approval": ["section"],
        "get_detail": ["name"],
        "save_draft": ["name", "payload"],
        "submit_request": ["name"],
        "approve": ["name", "comment"],
        "reject": ["name", "comment"],
        "request_information": ["name", "comment"],
        "resubmit": ["name", "payload"],
        "cancel": ["name", "reason"],
        "admin_approve_current_level": ["name", "reason"],
    }

    def test_endpoint_names_signatures_aliases_and_post_guards(self):
        for module in ("leave", "late_early_out", "compensation_leave",
                       "employee_referral", "livestream_sample", "hr_activity",
                       "asset_damage_loss"):
            path = os.path.abspath(os.path.join(
                os.path.dirname(__file__), "..", module, "api.py"))
            with open(path, encoding="utf-8") as handle:
                tree = ast.parse(handle.read())
            functions = {
                node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
            for name, arguments in self.EXPECTED.items():
                self.assertIn(name, functions, module)
                self.assertEqual(
                    [arg.arg for arg in functions[name].args.args], arguments,
                    module + "." + name)
            source = ast.unparse(tree)
            self.assertIn("list_my_approvals = list_need_my_approval", source, module)
            self.assertIn("get_request_detail = get_detail", source, module)
            for name in set(self.EXPECTED) - {
                    "get_bootstrap", "get_form_options", "list_my_requests",
                    "list_need_my_approval", "get_detail"}:
                decorators = ast.unparse(functions[name])
                self.assertIn("@frappe.whitelist(methods=['POST'])", decorators,
                              module + "." + name)

    def test_shared_does_not_import_public_api_or_concrete_features(self):
        core_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "shared"))
        forbidden = ("ecentric_workspace.approval_center.api",
                     "ecentric_workspace.approval_center.request_types")
        for root, _, files in os.walk(core_dir):
            for filename in files:
                if not filename.endswith(".py"):
                    continue
                path = os.path.join(root, filename)
                with open(path, encoding="utf-8") as handle:
                    source = handle.read()
                for prefix in forbidden:
                    self.assertNotIn(prefix, source, path + " imports " + prefix)

    def test_adapter_modules_bind_the_expected_registered_code(self):
        expected = {
            "daily_target": "DAILY_TARGET",
            "lateral_move": "LATERAL_MOVE",
            "livestream_supplies": "LIVESTREAM_SUPPLIES",
            "outside_work": "OUTSIDE_WORK",
            "service_referral": "SERVICE_REFERRAL",
            "hiring_request": "HIRING_REQUEST",
            "promotion": "PROMOTION_REQUEST",
            "special_bonus": "SPECIAL_BONUS",
            "employee_info_update": "EMPLOYEE_INFO_UPDATE",
            "affiliate_bonus": "AFFILIATE_BONUS_REQUEST",
            "budget_setting": "BUDGET_SETTING",
            "payment_request": "PAYMENT_REQUEST",
            "purchase_request": "PURCHASE_REQUEST",
        }
        module_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        for module, code in expected.items():
            with open(os.path.join(module_root, module, "api.py"), encoding="utf-8") as handle:
                source = handle.read()
            self.assertIn('globals().update(bind("%s"))' % code, source, module)

    def test_ai_topup_uses_stable_reexport_wrapper(self):
        path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "api", "ai_topup.py"))
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("approval_center.ai_topup.api import *", source)

    def test_all_26_business_apis_are_registry_backed(self):
        module_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        compatibility_root = os.path.join(module_root, "api")
        modules = [
            "affiliate_bonus", "ai_topup", "asset_damage_loss", "asset_request",
            "budget_setting", "compensation_leave", "daily_target", "data_request",
            "document_request", "employee_info_update", "employee_referral", "hiring_request",
            "hr_activity", "late_early_out", "lateral_move", "leave", "livestream_sample",
            "livestream_supplies", "outside_work", "payment_request", "promotion",
            "purchase_request", "resignation", "service_referral", "special_bonus",
            "system_request",
        ]
        self.assertEqual(len(modules), 26)
        markers = ("get_definition(", "bind(", "bind_fulfillment(")
        for module in modules:
            with open(os.path.join(module_root, module, "api.py"), encoding="utf-8") as handle:
                source = handle.read()
            self.assertTrue(any(marker in source for marker in markers), module)
            with open(os.path.join(compatibility_root, module + ".py"), encoding="utf-8") as handle:
                wrapper = handle.read()
            self.assertIn("approval_center.%s.api import *" % module, wrapper)


if __name__ == "__main__":
    unittest.main()

