# Copyright (c) 2026, eCentric and contributors
"""Shared fixtures for esign S2A tests (NOT a test module - no test_ prefix).
Builds: Payment Request 4-level process (mirrors test_payment_request), Mock/UAT
provider settings (gates OPEN for tests only), an enabled Payment Request signing
profile, verified mappings, and a Draft->Locked->Active package with placements."""
import frappe

from ecentric_workspace.approval_center.api import payment_request as papi
from ecentric_workspace.approval_center.tests import erp_fixtures as erp
from ecentric_workspace.approval_center.esign import package as pkgsvc
from ecentric_workspace.approval_center.esign.providers.mock import MockAdapter
from ecentric_workspace.approval_center.payment_request import setup as psetup

PFX = "zzesn_"  # lowercase: frappe lowercases User.name on insert; mixed-case
# emails would desync frappe.set_user(session) vs stored owner fields.
FIN = PFX + "fin@example.com"
HOF = PFX + "hof@example.com"
CEO = PFX + "ceo@example.com"

def _make_pdf():
    """Deterministic minimal-but-VALID PDF (correct xref offsets + startxref):
    newer frappe validates uploaded PDFs with pypdf on File insert."""
    objs = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += (b"%d 0 obj" % i) + body + b"endobj\n"
    xref_pos = len(out)
    out += b"xref\n0 4\n0000000000 65535 f \n"
    for off in offsets:
        out += ("%010d 00000 n \n" % off).encode()
    out += b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n" + str(xref_pos).encode() + b"\n%%EOF"
    return bytes(out)


PDF = _make_pdf()



def user(email, roles=("Employee",)):
    return erp.make_user(email, roles)


def company():
    return erp.make_company("ZZESN Co", "ZZESNC")


def employee(u, reports_to=None):
    return erp.make_employee(u, company(), reports_to=reports_to)


def ensure_process():
    # Fresh disposable sites carry no seeds (patches are marked-completed on new
    # installs) -> create the required Category before the Type (category is reqd).
    if not frappe.db.exists("EC Approval Category", "ZZESN_CAT"):
        frappe.get_doc({"doctype": "EC Approval Category", "category_code": "ZZESN_CAT",
                        "category_name": "ZZESN Test"}).insert(ignore_permissions=True)
    if not frappe.db.exists("EC Approval Type", "PAYMENT_REQUEST"):
        frappe.get_doc({"doctype": "EC Approval Type", "approval_code": "PAYMENT_REQUEST",
                        "approval_title": "Payment Request", "card_status": "Coming Soon",
                        "process_status": "Discovery",
                        "category": "ZZESN_CAT"}).insert(ignore_permissions=True)
    user(FIN); user(HOF); user(CEO)
    psetup.setup_payment_request_v1(finance=[FIN], hof=[HOF], ceo=[CEO], apply=1)
    # Force OUR approvers even when the process pre-exists as Active: psetup skips
    # on ALREADY_ACTIVE, and its frappe.db.commit() makes participant state bleed
    # across test modules on a shared site (each module must be self-contained).
    psetup._upsert({2: [FIN], 3: [HOF], 4: [CEO]})
    frappe.db.set_value("EC Approval Process", "PAYMENT_REQUEST-V1", "status", "Active")


def ensure_settings(allowed_users=(), site="", environment="UAT", enabled=True):
    """Mock provider settings row. Gates OPEN only inside tests."""
    name = frappe.db.get_value("EC Digital Signature Provider Settings",
                               {"provider": "Mock", "environment": environment}, "name")
    vals = {"base_url": "http://mock.local", "site": site,
            "integration_enabled": 1 if enabled else 0,
            "allow_document_creation": 1 if enabled else 0,
            "allow_signing": 1 if enabled else 0,
            "allowed_signing_users": "\n".join(allowed_users)}
    if name:
        doc = frappe.get_doc("EC Digital Signature Provider Settings", name)
        doc.update(vals)
        doc.save(ignore_permissions=True)
        return name
    return frappe.get_doc(dict({"doctype": "EC Digital Signature Provider Settings",
                                "provider": "Mock", "environment": environment}, **vals)
                          ).insert(ignore_permissions=True).name


def ensure_profile(levels=(1, 2, 3, 4), enabled=True,
                   trigger="Before First Signing Level"):
    code = "ZZESN_PAYR"
    if frappe.db.exists("EC Digital Signature Profile", code):
        frappe.delete_doc("EC Digital Signature Profile", code, ignore_permissions=True,
                          force=True)
    doc = frappe.get_doc({
        "doctype": "EC Digital Signature Profile", "profile_code": code,
        "title": "ZZESN Payment Request", "business_doctype": "EC Payment Request",
        "approval_type": "PAYMENT_REQUEST", "provider": "Mock", "environment": "UAT",
        "enabled": 1 if enabled else 0, "provider_creation_trigger": trigger,
        "doc_code_source": "name", "title_source": "request_title",
        "amount_source": "payment_amount", "description_source": "reason",
        "levels": [{"level_no": n, "requires_signature": 1,
                    "mandatory_placements_per_file": 1} for n in levels],
        "transitions": [{"action": "Reject", "transition_id": -16},
                        {"action": "Cancel", "transition_id": -8}],
    }).insert(ignore_permissions=True)
    return doc.name


def ensure_mapping(u, verified=True):
    name = frappe.db.get_value("EC SCTS User Mapping",
                               {"frappe_user": u, "environment": "UAT"}, "name")
    if name:
        return name
    # signature_id mirrors what the provider's GetSignatures returns for this user
    # (MockAdapter -> "SIG-" + scts_user_id): a mapping is only ever created from
    # real provider signature output, so the two must agree for the live
    # signature-ownership binding (esign.binding.assert_outbound_binding).
    doc = frappe.get_doc({"doctype": "EC SCTS User Mapping", "frappe_user": u,
                          "environment": "UAT", "scts_user_id": "SCTS-" + u,
                          "signature_id": "SIG-SCTS-" + u, "active": 1,
                          "mapping_status": "Draft"}).insert(ignore_permissions=True)
    if verified:
        doc.db_set({"mapping_status": "Verified", "verified_at": frappe.utils.now_datetime(),
                    "verified_by": "Administrator"})
    return doc.name


def draft_payment_request(requester, **over):
    frappe.set_user(requester)
    payload = {"reason": "esign test", "payment_amount": 1000000, "payment_date": "2026-10-01",
               "payee_full_name": "ESIGN Ltd", "account_bank": "VCB",
               "bank_account_number": "9999", "has_purchase_request": "No",
               "no_purchase_request_reason": "test", "is_cost_valid": "Yes",
               "details_and_attachments_correct": "Yes",
               "request_attachment": "/private/files/esign-test.pdf"}
    payload.update(over)
    name = papi.save_draft(payload=frappe.as_json(payload))["name"]
    frappe.set_user("Administrator")
    return name


def build_package(biz_name, requester, signable=1, supporting=1, levels=(1, 2, 3, 4)):
    """Draft package with files + one placement per (level x signable file)."""
    profile = frappe.db.get_value("EC Digital Signature Profile", "ZZESN_PAYR", "name")
    frappe.set_user(requester)
    pkg = pkgsvc.get_or_create_draft("EC Payment Request", biz_name, profile)
    for i in range(signable):
        pkgsvc.add_file(pkg.name, "sign_%d.pdf" % i, PDF, requires_signature=1)
    for i in range(supporting):
        pkgsvc.add_file(pkg.name, "evidence_%d.pdf" % i, PDF, is_supporting_document=1)
    rows = pkgsvc.package_files(pkg.name)
    placements = []
    for f in rows:
        if not f.requires_signature:
            continue
        for lvl in levels:
            placements.append({"signature_file": f.name, "page_index": 1,
                               "x": 50, "y": 50 + 30 * lvl, "width": 120, "height": 40,
                               "level_no": lvl, "signature_type": "mock"})
    pkgsvc.save_placements(pkg.name, placements)
    frappe.set_user("Administrator")
    return pkg.name


def submit_and_lock(biz_name, requester, pkg_name):
    """ERP submit (engine) + package lock, mirroring the S2C submit-hook contract."""
    frappe.set_user(requester)
    papi.submit_request(biz_name)
    frappe.set_user("Administrator")
    ar = frappe.db.get_value("EC Payment Request", biz_name, "approval_request")
    pkgsvc.lock_package(pkg_name, ar)
    # Both creation triggers pass through Active; 'Before First Signing Level' mode
    # activates without a provider document (worker creates lazily).
    from ecentric_workspace.approval_center.esign import events
    events.set_package_status(pkg_name, "Active")
    return ar


def full_stack(requester_email=PFX + "req@example.com", mgr_email=PFX + "mgr@example.com",
               allowed=None, site="", levels=(1, 2, 3, 4)):
    """Everything up to Active package + submitted request. Returns dict of handles."""
    MockAdapter.reset()
    ensure_process()
    mgr = user(mgr_email)
    req_user = user(requester_email)
    employee(req_user, reports_to=employee(mgr))
    approvers = [mgr, FIN, HOF, CEO]
    ensure_settings(allowed_users=allowed if allowed is not None else approvers, site=site)
    ensure_profile(levels=levels)
    for u in approvers:
        ensure_mapping(u)
    biz = draft_payment_request(req_user)
    pkg = build_package(biz, req_user, levels=levels)
    ar = submit_and_lock(biz, req_user, pkg)
    return {"biz": biz, "pkg": pkg, "ar": ar, "requester": req_user,
            "mgr": mgr, "approvers": approvers}


def run_worker_for_latest(ar):
    """Run the background worker synchronously for the newest DSR of the request."""
    from ecentric_workspace.approval_center.esign import tasks
    dsr = frappe.get_all("EC Digital Signature Request", filters={"approval_request": ar},
                         order_by="creation desc", limit_page_length=1, pluck="name")
    assert dsr, "no signature request found"
    tasks.process_signing_request(dsr[0])
    return dsr[0]
