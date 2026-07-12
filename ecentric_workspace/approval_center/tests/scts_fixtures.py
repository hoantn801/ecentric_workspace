# Copyright (c) 2026, eCentric and contributors
"""Deterministic SCTS test doubles (NOT a test module). A FakeTransport that speaks the
SctsClient transport contract without any network, plus recorded provider payloads and
a helper to build an SctsAdapter wired to the fake transport. Used by the committed
SCTS suite; the live UAT connectivity test uses a real transport + site secrets and is
opt-in only."""
import json


class FakeResponse(object):
    def __init__(self, status_code, payload=None, text=None, malformed=False,
                 content=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self._malformed = malformed
        self.content = content  # raw bytes (binary responses, e.g. signed PDF)
        self.headers = headers or ({"Content-Type": "application/json"} if payload is not None else {})
        self.text = text if text is not None else (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._malformed or self._payload is None:
            raise ValueError("malformed body")
        return self._payload


class FakeTransport(object):
    """Callable matching (method, url, headers, json_body, timeout, verify_tls). Routes by
    URL suffix + method. `script` maps a route key to either a FakeResponse, a list of
    FakeResponses (consumed in order), an Exception instance (raised = network error), or
    a callable(request)->FakeResponse. Records every call for assertions."""

    def __init__(self, script=None):
        self.script = script or {}
        self.calls = []

    @staticmethod
    def _key(method, url):
        if "/api/Auth/login" in url:
            return "login"
        if "/api/SignerSignature/GetSignatures/" in url:
            return "get_signatures"
        if "/api/Workflow/bulk-process" in url:
            return "bulk_process"
        if "/api/AddDocument" in url:
            return "add_document"
        if "/api/Document/" in url:
            return "get_document"
        return "%s %s" % (method, url)

    def __call__(self, method, url, headers=None, json_body=None, timeout=30, verify_tls=True):
        key = self._key(method, url)
        self.calls.append({"key": key, "method": method, "url": url,
                           "headers": dict(headers or {}), "body": json_body})
        rule = self.script.get(key)
        if rule is None:
            return FakeResponse(200, {})
        if isinstance(rule, list):
            item = rule.pop(0) if rule else FakeResponse(200, {})
        else:
            item = rule
        if isinstance(item, Exception):
            raise item
        if callable(item) and not isinstance(item, FakeResponse):
            return item({"method": method, "url": url, "body": json_body})
        return item

    def count(self, key):
        return sum(1 for c in self.calls if c["key"] == key)

    def last_body(self, key):
        for c in reversed(self.calls):
            if c["key"] == key:
                return c["body"]
        return None


# ---- recorded provider payloads (shapes per Phase-2 design; field variants covered) ----
def login_ok(token="jwt-uat-abc", minutes=525600):
    return FakeResponse(200, {"token": token, "expiresInMinutes": minutes})


def login_bad():
    return FakeResponse(401, {"error": "invalid_credentials"}, text="unauthorized")


def signatures_for(user_id, signature_id=None, active=True):
    sig = signature_id or ("SIG-" + user_id)
    return FakeResponse(200, [{"id": sig, "signerId": user_id, "type": "USB Token",
                               "company": "eCentric", "isActive": bool(active)}])


def document(doc_id, signer_user=None, signature_id=None, status="signed", files=2):
    signers = []
    if signer_user:
        signers.append({"userId": signer_user, "signatureId": signature_id,
                        "status": status, "signedAt": "2026-07-12T09:00:00"})
    return FakeResponse(200, {"id": doc_id, "status": "in_progress",
                              "signers": signers,
                              "files": [{"documentFileId": "F%d" % i, "fileName": "f%d.pdf" % i}
                                        for i in range(files)]})


def bulk_ok(txn="BULK-TXN-1"):
    return FakeResponse(200, {"bulkJobTransactionId": txn})


def add_document_ok(doc_id="SCTS-DOC-1", file_count=2):
    return FakeResponse(200, {"documentId": doc_id,
                              "documentFiles": [{"order": i, "documentFileId": "F%d" % i}
                                                for i in range(file_count)]})


def make_scts_settings(name="EC-DSPS-SCTS-UAT", base_url="https://scts.uat.local",
                       environment="UAT"):
    """A settings dict shaped like frappe.db.get_value(..., '*', as_dict=True)."""
    return {"name": name, "provider": "SCTS", "environment": environment,
            "base_url": base_url, "username": "erp-bot", "request_timeout": 30,
            "integration_enabled": 1, "allow_signing": 1, "allow_production_signing": 0,
            "allowed_signing_users": "", "token_expires_at": None}


def make_adapter(transport, settings=None):
    """Build an SctsAdapter over a fake transport, bypassing frappe credential/token I/O
    (patched by the caller's test where a frappe context is available)."""
    from ecentric_workspace.approval_center.esign.providers.scts import SctsAdapter
    return SctsAdapter(settings or make_scts_settings(), transport=transport,
                       sleeper=lambda *_: None)


def pdf_binary_response(content=b"%PDF-1.4 signed\n%%EOF"):
    """Signed PDF returned as a binary application/pdf body."""
    return FakeResponse(200, content=content, headers={"Content-Type": "application/pdf"})


def pdf_base64_response(content=b"%PDF-1.4 signed\n%%EOF", field="fileBase64"):
    """Signed PDF returned as base64 inside a JSON envelope."""
    import base64 as _b64
    return FakeResponse(200, {field: _b64.b64encode(content).decode("ascii")})
