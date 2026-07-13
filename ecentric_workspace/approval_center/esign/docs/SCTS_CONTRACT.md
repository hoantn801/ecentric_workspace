# SCTS eSign — Provider Contract & Fail-Closed Boundaries

Every SCTS endpoint the adapter uses, its safe/sensitive fields, retry class, ambiguous-write
handling, audit event, and confirmation status. **Do not invent inner AddDocument or
Document/pdf fields.** Where a contract is UAT-unconfirmed the adapter stays fail-closed and
the exact mapping lives in one function (`providers/scts.py`), with deterministic contract
tests and an opt-in redacted UAT probe.

| # | Route | Method | Safe request fields | Sensitive | Response ids | Retry | Ambiguous write | Audit event | Status |
|---|-------|--------|--------------------|-----------|--------------|-------|-----------------|-------------|--------|
| 1 | `/api/Auth/login` | POST | username | password (encrypted, never logged) | bearer token (cached, encrypted) | net/5xx bounded retry; single 401 re-login | n/a (read) | — | **Confirmed** shape; token TTL UAT-observed |
| 2 | `/api/SignerSignature/GetSignatures/{userId}` | GET | userId (server-resolved from mapping) | — | signature id/type/company | net/5xx bounded retry | n/a (read) | SignatureOwnershipValidated/Rejected | **Confirmed** enough for ownership binding |
| 3 | `/api/AddDocument` | POST | workflowDefinitionId, documentTypeId, companyId, departmentId, documentTemplateId (all from Profile); Documents[]; Signatures[]; ExternalHandlers[]=[] | file bytes / Base64 (never logged) | document id, file ids | **single attempt, NO retry** | net/timeout/5xx ⇒ `create_outcome_unknown`; never auto-recreate; SM reconcile only | CreateOutcomeUnknown / CreateReconciled / CreateReconcileRejected | **Inner field names UAT-UNCONFIRMED** — fail-closed |
| 4 | `/api/Workflow/bulk-process` | POST | instanceIds[], userId, SignerSignatureId, transitionType="approve" (server-derived) | — | bulk job transaction id (maybe) | **single attempt, NO retry** | net/timeout/5xx ⇒ `scts_bulk_outcome_unknown` ⇒ DSR Verifying, poll-only, never resend | BulkOutcomeUnknown | **Single-instance confirmed**; multi-instance batching UAT-UNCONFIRMED |
| 5 | `/api/Document/{id}` | GET | document id | — | status, signers[], files[], identity | net/5xx bounded retry | n/a (read) | Verified / VerificationMismatch | **Confirmed** for polling/verify |
| 6 | `/api/Document/pdf` | GET | document id (+ file id) | — | signed PDF bytes | safe GET retry | n/a (read) | SignedFileRetrieved/Stored/HashMismatch | **Route params + response envelope UAT-UNCONFIRMED** — magic/size/sha validated, bytes never logged |
| 7 | Workflow transition endpoints | POST | server-derived transitionType | — | — | as bulk-process | as bulk-process | (per action) | Reuses bulk-process semantics |

## Fail-closed invariants
* transitionType is server-derived (`{"Sign":"approve"}`), never numeric, never from frontend.
* userId / SignerSignatureId / document ids are resolved from persisted DSR + verified mapping.
* AddDocument and bulk-process are each ONE attempt; an ambiguous outcome parks the record for
  governed reconciliation and is never auto-retried.
* base_url is netguard-validated (https, non-private host, optional allowlist) before any call.
* No provider-specific payload leaks above the adapter boundary; tokens/passwords/bytes/Base64
  are never logged.

## Exact UAT evidence still required
1. `/api/AddDocument` inner request field names + success/failure envelope.
2. `/api/Document/pdf` exact route params and response shape (binary vs base64-JSON field name).
3. `/api/Workflow/bulk-process` multi-instance semantics (whether one call may carry N
   instanceIds and how per-instance results are returned) before enabling true batch signing.
4. Token TTL + refresh contract under sustained UAT load.
