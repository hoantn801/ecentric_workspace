# Copyright (c) 2026, eCentric and contributors
"""Deterministic in-memory mock provider (NO frappe import, NO network). Drives S2A
tests and gate-closed dry runs. Behavior knobs via settings['site'] tokens:
  'fail:create'   -> create_document raises retryable ProviderError
  'fail:accept'   -> approve_and_sign raises retryable ProviderError
  'never:sign'    -> acceptance succeeds but the signer never reaches 'signed'
  'wrong:signer'  -> the signature is recorded under a DIFFERENT user id
                     (simulates SCTS finding C for verification tests)
"""
import itertools

from ecentric_workspace.approval_center.esign.providers.base import (
    NormalizedDocState, ProviderError, SignatureProviderAdapter,
)

_counter = itertools.count(1)


class MockAdapter(SignatureProviderAdapter):
    STORE = {}  # class-level: {document_id: {"files": [...], "signers": {uid: {...}}}}

    @classmethod
    def reset(cls):
        cls.STORE.clear()

    # -- helpers -------------------------------------------------------------
    def _mode(self):
        site = (self.settings.get("site") if isinstance(self.settings, dict)
                else getattr(self.settings, "site", "")) or ""
        return site

    # -- session ---------------------------------------------------------------
    def authenticate(self):
        return {"token": "mock-token", "expiresInMinutes": 525600}

    def refresh_or_get_token(self):
        return "mock-token"

    def test_connection(self):
        return {"ok": True, "provider": "Mock"}

    # -- documents ---------------------------------------------------------------
    def create_document(self, package_ctx):
        if "fail:create" in self._mode():
            raise ProviderError("mock_create_failed", "mock: create failure", retryable=True)
        doc_id = "MOCK-DOC-%05d" % next(_counter)
        files = [{"order": f.get("order"), "file_id": "MOCK-FILE-%05d" % next(_counter),
                  "name": f.get("name")} for f in package_ctx.get("files") or []]
        self.STORE[doc_id] = {"files": files, "signers": {}, "status": "in_progress"}
        return {"document_id": doc_id, "files": files}

    def get_document(self, document_id):
        return self.STORE.get(document_id)

    def get_pdf(self, document_id, document_file_id):
        return b"%PDF-1.4 mock signed pdf for " + document_file_id.encode() + b"\n%%EOF"

    def list_user_signatures(self, provider_user_id):
        return [{"id": "SIG-%s" % provider_user_id, "signerId": provider_user_id,
                 "type": "mock", "company": "MockCo"}]

    # -- actions -----------------------------------------------------------------
    def approve_and_sign(self, instance_ids, provider_user_id, signature_id, transition_type=None):
        if "fail:accept" in self._mode():
            raise ProviderError("mock_accept_failed", "mock: accept failure", retryable=True)
        for doc_id in instance_ids:
            doc = self.STORE.get(doc_id)
            if not doc:
                continue  # partial success semantics: invalid item never blocks others
            if "never:sign" in self._mode():
                doc["signers"][provider_user_id] = {"status": "pending", "signature_id": signature_id}
            elif "wrong:signer" in self._mode():
                doc["signers"]["INTRUDER-USER"] = {"status": "signed", "signature_id": signature_id,
                                                   "signed_at": "2026-01-01 00:00:00"}
            else:
                doc["signers"][provider_user_id] = {"status": "signed", "signature_id": signature_id,
                                                    "signed_at": "2026-01-01 00:00:00"}
        return {"bulk_job_transaction_id": "MOCK-BULK-%05d" % next(_counter)}

    def execute_transition(self, instance_id, transition_id, meta=None):
        doc = self.STORE.get(instance_id)
        if not doc:
            raise ProviderError("mock_unknown_document", "mock: unknown document", retryable=False)
        doc["last_transition"] = transition_id
        return {"ok": True, "transition_id": transition_id}

    # -- status --------------------------------------------------------------------
    def poll_status(self, document_id):
        doc = self.STORE.get(document_id)
        if not doc:
            raise ProviderError("mock_unknown_document", "mock: unknown document", retryable=False)
        signers = [{"user_id": uid, "signature_id": s.get("signature_id"),
                    "status": s.get("status"), "signed_at": s.get("signed_at"),
                    "is_external": False} for uid, s in doc["signers"].items()]
        return NormalizedDocState(document_id, doc.get("status"), signers=signers,
                                  files=doc["files"], raw={})

    def normalize_error(self, exc_or_response):
        if isinstance(exc_or_response, ProviderError):
            return exc_or_response
        return ProviderError("mock_error", str(exc_or_response), retryable=False)
