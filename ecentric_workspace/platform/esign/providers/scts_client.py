# Copyright (c) 2026, eCentric and contributors
"""Low-level SCTS HTTP client (NO frappe import - unit-testable with an injected
transport, never touches the network in CI).

Responsibilities: HTTP mechanics ONLY - authentication, token expiry handling, safe
single re-login on 401, configurable timeout, bounded retry for network / 5xx errors,
NO retry for validation / auth / security errors, and normalization of every failure
into base.ProviderError (retryable flag drives Retryable vs Permanent Failure upstream).

It knows the SCTS eContract endpoints (docs: econtract.scts.com.vn/API, 2026-08):
    POST /api/Auth/login
    GET  /api/SignerSignature/GetSignatures/{userId}
    POST /api/Workflow/bulk-process
    POST /api/Workflow/transition   (portal path: carries `toUsers` = next handler)
    GET  /api/Document/{documentId}
    POST /api/AddDocument                (create document; docs page says Document/Submit but the
                                          live backend 405s it - probed 2026-08-22, AddDocument=400)
    GET  /api/Document/pdf?DocumentId=&DocumentFileId=   (signed PDF, confirmed contract)

It returns PARSED JSON (dict/list); provider->ERP field normalization lives in the
adapter (scts.py). Secrets (token, password, Authorization header, file content) are
NEVER logged or echoed into ProviderError messages.
"""
import base64
import json
import time

from ecentric_workspace.platform.esign.providers.base import ProviderError

# HTTP status classes we treat distinctly.
_AUTH_STATUSES = (401, 403)
_NO_RETRY_4XX = (400, 401, 403, 404, 409, 422)  # validation / auth / security -> never retry


class SctsHttpError(Exception):
    """Internal: an HTTP response with a non-2xx status. Carries status + safe body."""

    def __init__(self, status, body=""):
        super().__init__("http_%s" % status)
        self.status = int(status)
        self.body = body


def _default_transport(method, url, headers=None, json_body=None, timeout=30, verify_tls=True):
    """Real transport (requests). Imported lazily so the module imports with no network
    stack and tests never hit it."""
    import requests  # bundled with frappe
    resp = requests.request(method, url, headers=headers or {}, json=json_body,
                            timeout=timeout, verify=verify_tls)
    return resp


class SctsClient(object):
    """Stateful only in that it holds the last obtained bearer token in-process. Token
    PERSISTENCE across workers is the adapter's job (encrypted settings cache); this
    client just performs login and attaches the token it is given / obtains."""

    def __init__(self, base_url, timeout=30, retry_limit=2, verify_tls=True,
                 transport=None, sleeper=None, backoff_base=0.5, preflight=None):
        if not base_url:
            raise ProviderError("scts_base_url_missing", "SCTS base_url is not configured",
                                retryable=False)
        self.base_url = base_url.rstrip("/")
        self.timeout = int(timeout or 30)
        self.retry_limit = max(0, int(retry_limit if retry_limit is not None else 2))
        self.verify_tls = bool(verify_tls)
        # `preflight(method, url)` runs immediately before EVERY request (fail-closed SSRF /
        # DNS-rebinding revalidation). It raises to abort the request before any bytes leave.
        self._preflight = preflight
        real = transport or _default_transport
        if preflight is not None:
            def _guarded(method, url, **kw):
                preflight(method, url)
                return real(method, url, **kw)
            self._transport = _guarded
        else:
            self._transport = real
        self._sleep = sleeper if sleeper is not None else time.sleep
        self._backoff_base = backoff_base

    # -- url ------------------------------------------------------------------
    def _url(self, path):
        return "%s/%s" % (self.base_url, path.lstrip("/"))

    # -- core request with bounded retry -------------------------------------
    def _request(self, method, path, token=None, json_body=None, _label="request"):
        """One logical call with bounded retry. Retries ONLY transport errors and 5xx;
        4xx (validation/auth/security) raise immediately. Returns parsed JSON."""
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer %s" % token
        attempt = 0
        last_exc = None
        while attempt <= self.retry_limit:
            try:
                resp = self._transport(method, self._url(path), headers=headers,
                                       json_body=json_body, timeout=self.timeout,
                                       verify_tls=self.verify_tls)
            except Exception as e:  # transport-level (connection/timeout/DNS): retryable
                last_exc = ProviderError("scts_network_error",
                                         "network error during %s" % _label, retryable=True)
                attempt += 1
                if attempt > self.retry_limit:
                    raise last_exc
                self._sleep(self._backoff_base * attempt)
                continue
            status = int(getattr(resp, "status_code", 0))
            if 200 <= status < 300:
                return self._parse(resp, _label)
            if status >= 500:  # server error: bounded retry
                last_exc = ProviderError("scts_server_error_%s" % status,
                                         "SCTS server error (%s) during %s" % (status, _label),
                                         retryable=True)
                attempt += 1
                if attempt > self.retry_limit:
                    raise last_exc
                self._sleep(self._backoff_base * attempt)
                continue
            # 4xx: validation / auth / security -> NEVER retry (fail closed).
            raise SctsHttpError(status, self._safe_body(resp))
        raise last_exc or ProviderError("scts_unknown_error", "unknown error during %s" % _label,
                                        retryable=True)

    @staticmethod
    def _parse(resp, _label):
        try:
            return resp.json()
        except Exception:
            raise ProviderError("scts_malformed_response",
                                "SCTS returned a non-JSON / malformed body during %s" % _label,
                                retryable=False)

    @staticmethod
    def _safe_body(resp):
        """A short, non-sensitive, INFORMATIVE slice of the error body.

        A blind 200-char slice is useless for the shape providers actually return: an
        RFC 9110 problem document puts the boilerplate ("type", "title") first and the part
        that names the offending fields last, so the slice cut off exactly the answer. When
        an `errors` object is present we render it compactly as `field=message` pairs, which
        both fits and says which field the provider disliked. Never returns tokens.
        """
        try:
            txt = resp.text or ""
        except Exception:
            txt = ""
        low = txt.lower()
        if any(s in low for s in ("token", "bearer", "authorization", "password", "base64")):
            return "(body withheld - sensitive markers)"
        try:
            data = json.loads(txt)
            errs = data.get("errors") if isinstance(data, dict) else None
            if isinstance(errs, dict) and errs:
                parts = []
                for field, msgs in errs.items():
                    if isinstance(msgs, (list, tuple)):
                        msgs = "; ".join(str(m) for m in msgs)
                    parts.append("%s=%s" % (field, msgs))
                return ("errors: " + " | ".join(parts))[:400]
        except Exception:
            pass
        return txt[:200]

    # -- endpoints ------------------------------------------------------------
    def login(self, site, username, password):
        """POST /api/Auth/login with the confirmed SCTS contract body
        {"Site": ..., "Username": ..., "Password": ...} (exact key casing) -> raw provider
        auth payload (parsed JSON). The adapter extracts token + expiry. 4xx is a
        non-retryable auth failure. Site is REQUIRED - a blank Site fails closed BEFORE any
        network call. The request body (which contains the password) is never logged."""
        if not site:
            raise ProviderError("scts_site_missing",
                                "SCTS Site is required for login", retryable=False)
        try:
            return self._request("POST", "/api/Auth/login",
                                 json_body={"Site": site, "Username": username,
                                            "Password": password},
                                 _label="login")
        except SctsHttpError as e:
            raise ProviderError("scts_auth_failed",
                                "SCTS authentication failed (HTTP %s)" % e.status,
                                retryable=False)

    def get_signatures(self, user_id, token):
        """GET /api/SignerSignature/GetSignatures/{userId} -> raw list/dict."""
        try:
            return self._request("GET", "/api/SignerSignature/GetSignatures/%s" % user_id,
                                 token=token, _label="get_signatures")
        except SctsHttpError as e:
            if e.status in _AUTH_STATUSES:
                raise ProviderError("scts_auth_error_%s" % e.status,
                                    "SCTS rejected credentials on get_signatures (HTTP %s)"
                                    % e.status, retryable=False)
            raise ProviderError("scts_signatures_rejected_%s" % e.status,
                                "SCTS refused get_signatures (HTTP %s)" % e.status,
                                retryable=False)

    def transition(self, instance_id, user_id, to_users, transition_id, transition_name,
                   process_action, sign_type, signature_id, signature_name, comment, token,
                   signature_image=None):
        """POST /api/Workflow/transition -> raw payload.

        This is what the eContract PORTAL itself calls, captured from the browser on
        2026-08-27. It differs from bulk-process in the one field that matters for
        governance: `toUsers` names WHO handles the document next. Without it the workflow
        falls back to notifying the whole role pool - which is how a colleague who was not
        the designated approver signed EC-PAYR-2026-00026 forty seconds after it was
        submitted.

        Same non-idempotent write semantics as bulk_process: exactly ONE attempt, never an
        automatic retry; network/5xx is AMBIGUOUS (the action may have been applied) and is
        normalized to `scts_bulk_outcome_unknown` so the caller polls instead of resending.
        """
        body = {
            "instanceId": instance_id,
            "userId": user_id,
            "toUsers": list(to_users or []),
            # The portal sends transitionId as a STRING ("-2"), not a number. eContract rejected
            # the numeric form with a bare HTTP 400, so mirror the captured payload exactly.
            "transitionId": str(transition_id),
            "transitionName": transition_name,
            "processAction": process_action,
            "signType": sign_type,
            # eContract doi CA ANH trong signatureInfo, khong chi id + ten. Bo ra thi 400:
            #   errors: SignatureInfo.Image=The Image field is required.
            # (Doc duoc 27/08 sau khi error_digest thoi cat mat doan cuoi cua thong diep.)
            # Cung chinh thong diep do bac bo gia thuyet cu cua minh: ASP.NET liet ke MOI
            # field khong hop le cung luc, ma no chi keu dung mot field -> instanceId = ma
            # chung tu la DUNG.
            "signatureInfo": {"id": signature_id, "name": signature_name,
                              "image": signature_image or ""},
            "comment": comment or "",
        }
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer %s" % token
        try:
            resp = self._transport("POST", self._url("/api/Workflow/transition"),
                                   headers=headers, json_body=body, timeout=self.timeout,
                                   verify_tls=self.verify_tls)
        except Exception:
            raise ProviderError("scts_bulk_outcome_unknown",
                                "transition outcome unknown (network/timeout)",
                                retryable=False, ambiguous=True)
        status = int(getattr(resp, "status_code", 0))
        if 200 <= status < 300:
            return self._parse(resp, "transition")
        if status in _AUTH_STATUSES:
            raise ProviderError("scts_auth_error_%s" % status,
                                "SCTS rejected credentials on transition (HTTP %s)" % status,
                                retryable=False)
        if status >= 500:
            raise ProviderError("scts_bulk_outcome_unknown",
                                "transition outcome unknown (HTTP %s)" % status,
                                retryable=False, ambiguous=True)
        # A bare status code is not diagnosable: echo the provider's own message (trimmed and
        # sanitized) so the next 400 says WHICH field it disliked instead of costing a round trip.
        raise ProviderError("scts_transition_rejected_%s" % status,
                            "SCTS rejected transition (HTTP %s): %s"
                            % (status, self._safe_body(resp)), retryable=False)

    def bulk_process(self, instance_ids, user_id, signature_id, transition_type, token):
        """POST /api/Workflow/bulk-process -> raw payload. ASYNC ACCEPTED semantics:
        a 2xx means only that SCTS queued the job (bulkJobTransactionId). It is NEVER
        proof of signing - the caller must poll + verify Document/{id}.

        NON-IDEMPOTENT WRITE: exactly ONE HTTP attempt, NO automatic retry. A network
        error, timeout or 5xx is AMBIGUOUS - the provider may already have accepted the
        signing action - so it is normalized to `scts_bulk_outcome_unknown` (ambiguous,
        non-retryable); the caller transitions to Verifying and polls Document/{id}
        rather than resending. Only a definite 4xx is a hard rejection.

        Field contract (confirmed SCTS UAT): the signature is sent as `SignerSignatureId`."""
        body = {"instanceIds": list(instance_ids), "userId": user_id,
                "SignerSignatureId": signature_id}
        if transition_type is not None:
            body["transitionType"] = transition_type
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer %s" % token
        try:
            resp = self._transport("POST", self._url("/api/Workflow/bulk-process"),
                                   headers=headers, json_body=body, timeout=self.timeout,
                                   verify_tls=self.verify_tls)
        except Exception:
            # transport-level (connection/timeout/DNS): outcome UNKNOWN, never resend.
            raise ProviderError("scts_bulk_outcome_unknown",
                                "bulk-process outcome unknown (network/timeout)",
                                retryable=False, ambiguous=True)
        status = int(getattr(resp, "status_code", 0))
        if 200 <= status < 300:
            return self._parse(resp, "bulk_process")
        if status in _AUTH_STATUSES:
            raise ProviderError("scts_auth_error_%s" % status,
                                "SCTS rejected credentials on bulk-process (HTTP %s)" % status,
                                retryable=False)
        if status >= 500:
            # server error on a non-idempotent write: AMBIGUOUS, never resend.
            raise ProviderError("scts_bulk_outcome_unknown",
                                "bulk-process outcome unknown (HTTP %s)" % status,
                                retryable=False, ambiguous=True)
        # definite 4xx: a real rejection (not accepted) -> permanent, no retry.
        raise ProviderError("scts_bulk_rejected_%s" % status,
                            "SCTS rejected bulk-process (HTTP %s)" % status, retryable=False)

    def convert_pdf_file(self, workflow_definition_id, pdf_b64, token, file_type="pdf"):
        """POST /api/AddDocument/ConvertPdfFile -> the workflow sign-template's signature AREA
        definitions (signatureId/title/role/...). Read-only template lookup: the converted
        content is ignored by our flow. NOTE: the vendor DTO field is literally
        'WordflowDefinitionId' (sic, docs + live). Bounded retry (safe read)."""
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer %s" % token
        payload = {"WordflowDefinitionId": workflow_definition_id, "Base64": pdf_b64,
                   "FileType": file_type, "JsonFields": []}
        attempt = 0
        last_exc = None
        while attempt <= self.retry_limit:
            try:
                resp = self._transport("POST", self._url("/api/AddDocument/ConvertPdfFile"),
                                       headers=headers, json_body=payload, timeout=self.timeout,
                                       verify_tls=self.verify_tls)
            except Exception:
                last_exc = ProviderError("scts_network_error",
                                         "network error during convert_pdf_file", retryable=True)
                attempt += 1
                if attempt > self.retry_limit:
                    raise last_exc
                self._sleep(self._backoff_base * attempt)
                continue
            status = int(getattr(resp, "status_code", 0))
            if 200 <= status < 300:
                raw = self._parse(resp, "convert_pdf_file")
                data = raw.get("data") if isinstance(raw, dict) else None
                jd = data.get("jsonData") if isinstance(data, dict) else None
                if isinstance(jd, str):
                    try:
                        return json.loads(jd)
                    except ValueError:
                        raise ProviderError("scts_malformed_response",
                                            "convert_pdf_file jsonData was not valid JSON",
                                            retryable=False)
                return jd if isinstance(jd, list) else []
            if status in _AUTH_STATUSES:
                raise ProviderError("scts_auth_error_%s" % status,
                                    "SCTS rejected credentials on convert_pdf_file (HTTP %s)" % status,
                                    retryable=False)
            if status >= 500:
                last_exc = ProviderError("scts_server_error_%s" % status,
                                         "SCTS server error (%s) during convert_pdf_file" % status,
                                         retryable=True)
                attempt += 1
                if attempt > self.retry_limit:
                    raise last_exc
                self._sleep(self._backoff_base * attempt)
                continue
            raise ProviderError("scts_convert_rejected_%s" % status,
                                "SCTS refused convert_pdf_file (HTTP %s)" % status, retryable=False)

    def add_document(self, payload, token):
        """POST /api/AddDocument (eContract). The 2026-08 docs list /api/Document/Submit but the
        live backend rejects it with 405 while /api/AddDocument validates (probed 2026-08-22);
        the payload is the eContract shape from the docs. `data` may carry the DocumentId. V1
        contract (workflowDefinitionId / documentTypeId / companyId / departmentId /
        Documents[] / Signatures[] / ExternalHandlers[]). NON-IDEMPOTENT write: exactly ONE HTTP
        attempt, NO retry. A network error, timeout or 5xx is AMBIGUOUS - the document may
        already have been created provider-side - normalized to `scts_create_outcome_unknown`
        (ambiguous, non-retryable) so the caller reconciles before ever recreating. Only a
        definite 4xx is a hard rejection. The payload carries base64 PDF bytes and is NEVER
        logged."""
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer %s" % token
        try:
            resp = self._transport("POST", self._url("/api/AddDocument"),
                                   headers=headers, json_body=payload, timeout=self.timeout,
                                   verify_tls=self.verify_tls)
        except Exception:
            raise ProviderError("scts_create_outcome_unknown",
                                "AddDocument outcome unknown (network/timeout)",
                                retryable=False, ambiguous=True)
        status = int(getattr(resp, "status_code", 0))
        if 200 <= status < 300:
            return self._parse(resp, "add_document")
        if status in _AUTH_STATUSES:
            raise ProviderError("scts_auth_error_%s" % status,
                                "SCTS rejected credentials on AddDocument (HTTP %s)" % status,
                                retryable=False)
        if status >= 500:
            raise ProviderError("scts_create_outcome_unknown",
                                "AddDocument outcome unknown (HTTP %s)" % status,
                                retryable=False, ambiguous=True)
        raise ProviderError("scts_create_rejected_%s" % status,
                            "SCTS rejected AddDocument (HTTP %s)" % status, retryable=False)

    # Candidate JSON field names that may carry a base64-encoded PDF. The exact SCTS V1
    # Document/pdf response shape is UNCONFIRMED [UAT] - this list is tried in order and
    # the boundary FAILS CLOSED (raises scts_signed_pdf_contract_unresolved) if none match.
    _PDF_B64_FIELDS = ("fileBase64", "pdfBase64", "base64", "fileContent", "content",
                       "data", "file", "signedFileBase64", "documentBase64")

    def get_pdf(self, document_id, document_file_id, token, route=None):
        """GET the signed PDF. Route/params/response-shape are [UAT-UNCONFIRMED]; handled
        FAIL-CLOSED. Returns RAW PDF BYTES (base64-decoded if the provider wraps it).
        Bounded retry for SAFE read failures only (network/5xx). Bytes are NEVER logged."""
        path = route or ("/api/Document/pdf?DocumentId=%s&DocumentFileId=%s"
                         % (document_id, document_file_id if document_file_id is not None else ""))
        headers = {"Accept": "application/pdf, application/json"}
        if token:
            headers["Authorization"] = "Bearer %s" % token
        attempt = 0
        last_exc = None
        while attempt <= self.retry_limit:
            try:
                resp = self._transport("GET", self._url(path), headers=headers,
                                       json_body=None, timeout=self.timeout,
                                       verify_tls=self.verify_tls)
            except Exception:
                last_exc = ProviderError("scts_network_error",
                                         "network error during get_pdf", retryable=True)
                attempt += 1
                if attempt > self.retry_limit:
                    raise last_exc
                self._sleep(self._backoff_base * attempt)
                continue
            status = int(getattr(resp, "status_code", 0))
            if 200 <= status < 300:
                return self._extract_pdf_bytes(resp)
            if status in _AUTH_STATUSES:
                raise ProviderError("scts_auth_error_%s" % status,
                                    "SCTS rejected credentials on get_pdf (HTTP %s)" % status,
                                    retryable=False)
            if status >= 500:
                last_exc = ProviderError("scts_server_error_%s" % status,
                                         "SCTS server error (%s) during get_pdf" % status,
                                         retryable=True)
                attempt += 1
                if attempt > self.retry_limit:
                    raise last_exc
                self._sleep(self._backoff_base * attempt)
                continue
            raise ProviderError("scts_signed_pdf_rejected_%s" % status,
                                "SCTS refused get_pdf (HTTP %s)" % status, retryable=False)
        raise last_exc or ProviderError("scts_signed_pdf_unknown",
                                        "unknown error during get_pdf", retryable=True)

    def _extract_pdf_bytes(self, resp):
        """Interpret the signed-PDF response fail-closed: binary application/pdf ->
        resp.content; JSON -> decode a recognized base64 field; otherwise raise
        scts_signed_pdf_contract_unresolved (never guesses silently, never logs bytes)."""
        headers = getattr(resp, "headers", None) or {}
        ct = ""
        try:
            ct = (headers.get("Content-Type") or headers.get("content-type") or "").lower()
        except Exception:
            ct = ""
        content = getattr(resp, "content", None)
        if ("application/pdf" in ct) or ("octet-stream" in ct):
            if not content:
                raise ProviderError("scts_signed_pdf_empty",
                                    "SCTS returned an empty signed PDF body", retryable=False)
            return bytes(content)
        # JSON envelope with a base64 file field
        payload = None
        try:
            payload = resp.json()
        except Exception:
            payload = None
        if isinstance(payload, dict):
            data = payload.get("data") if isinstance(payload.get("data"), dict) else None
            for src in (payload, data or {}):
                for k in self._PDF_B64_FIELDS:
                    v = src.get(k)
                    if isinstance(v, str) and v:
                        try:
                            return base64.b64decode(v)
                        except Exception:
                            raise ProviderError("scts_signed_pdf_bad_base64",
                                                "SCTS signed-PDF base64 field was undecodable",
                                                retryable=False)
            raise ProviderError("scts_signed_pdf_contract_unresolved",
                                "Document/pdf JSON had no recognized file field "
                                "(UAT contract unconfirmed)", retryable=False)
        # last resort: a raw binary body without a JSON/PDF content-type
        if content and bytes(content[:5]) == b"%PDF-":
            return bytes(content)
        raise ProviderError("scts_signed_pdf_contract_unresolved",
                            "Document/pdf response shape not recognized "
                            "(UAT contract unconfirmed)", retryable=False)

    def get_workflow_instance(self, instance_id, user_id, token):
        """GET /api/Workflow/{instanceId}?userid={userId} -> the LIVE workflow state.

        Captured from the portal on 2026-08-28. This is what ends three nights of guessing:
        it returns `currentStateId`, the `history` of transitions already taken, and -
        crucially - `availableTransitions`, each carrying its own transitionId,
        processAction, signType, isSigned and transitionType.

        Those values are NOT derivable. The four "Phe duyet" edges of one workflow turned out
        to be -9, -10, -11 and -4, and the last one needs processAction WfFunctionRunSignedA
        with signType ky-chinh while the others need WfFunctionRunSignedOther with
        ky-tham-gia. Any scheme that configures one value per stage - which is what we were
        doing - is wrong on at least one step of every document.
        """
        return self._request("GET", "/api/Workflow/%s?userid=%s" % (instance_id, user_id),
                             token=token, _label="get_workflow_instance")

    def get_document(self, document_id, token):
        """GET /api/Document/{documentId} -> raw document payload (status/signers/files)."""
        try:
            return self._request("GET", "/api/Document/%s" % document_id, token=token,
                                 _label="get_document")
        except SctsHttpError as e:
            if e.status in _AUTH_STATUSES:
                raise ProviderError("scts_auth_error_%s" % e.status,
                                    "SCTS rejected credentials on get_document (HTTP %s)"
                                    % e.status, retryable=False)
            if e.status == 404:
                raise ProviderError("scts_document_not_found",
                                    "SCTS document not found (HTTP 404)", retryable=False)
            raise ProviderError("scts_document_error_%s" % e.status,
                                "SCTS refused get_document (HTTP %s)" % e.status,
                                retryable=False)
