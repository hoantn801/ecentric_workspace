# SCTS eSign — UAT, Release & Rollback Runbook

Governed activation for the SCTS digital-signature integration. **All gates ship OFF.**
Production, callback, external-signer and bulk gates stay OFF until explicitly approved in a
later phase. Nothing here enables a gate automatically.

## 1. Architecture & security invariants
* One Approval Engine. The esign layer is a signing capability ON it, never a second engine.
* Backend-authoritative: identity, level, package, placements, transition and bounds are all
  resolved and re-validated server-side under lock. Frontend numbers are display-only.
* Fail-closed everywhere: missing evidence blocks; ambiguous provider writes park for
  governed reconciliation and never auto-retry.
* Immutable, sanitized audit (append-only events; no token/password/header/Base64/bytes).
* Least privilege: provider credentials + UAT control + mapping verification are SM-only;
  signing is the active-approver-only predicate; Administrator/SM role is never a bypass.

## 2. Configuration checklist (per environment)
* `EC Digital Signature Provider Settings` (provider=SCTS, environment=UAT): base_url (https,
  public host), username + password (encrypted), request_timeout; optional
  `base_url_allowlist`; all gate flags OFF initially.
* `EC Digital Signature Profile` for the exact approval_type: provider=SCTS, environment=UAT,
  workflow_definition_id, document_type_id, company_id, department_id, document_template_id,
  levels[] with requires_signature + mandatory_placements_per_file, enabled=1.
* One `EC SCTS User Mapping` (frappe_user ↔ scts_user_id + signature_id), verified via
  `verify_mapping` (pulls provider signatures, confirms ownership).
* UAT allowlist: add exactly one tester to `allowed_signing_users` (empty list = nobody).

## 3. Gate activation order (governed)
1. Deploy code with ALL gates OFF. 2. Verify regressions green. 3. Configure UAT provider
settings. 4. Configure the exact profile. 5. Configure one mapping + verify it. 6. Allowlist
one user. 7. Create a VOID/UAT/TEST-named Payment Request. 8. Enable `integration_enabled`.
9. Enable `allow_document_creation`; verify AddDocument via readiness/probe apply=1.
10. Enable `allow_signing`. 11. Run one controlled signature (Duyệt & Ký). 12. Poll status.
13. Verify Approval level completes. 14. Retrieve signed PDF. 15. Verify audit timeline.
16. Close gates after the test if required. **Production stays OFF.**

## 4. Test-data requirements
* One requester + one manager (level-1 approver) with an Employee record so roles resolve.
* One VOID/UAT/TEST-named Payment Request with at least one signable PDF + mandatory
  placements complete + a locked, hash-valid package.
* The verified mapping's SCTS user must own the signature id used.

## 5. One-user pilot steps (SM)
Open the UAT Pilot Control Panel → enter the PR → Refresh readiness (all green) → Preview
(apply=0, redacted, no provider call) → confirm → Run probe apply=1 (one UAT provider write;
never auto-repeated) → poll → verify completion → retrieve signed PDF → inspect audit.

## 6. Expected provider request sequence
login → (GetSignatures for ownership) → AddDocument (once) → bulk-process (once,
transitionType=approve) → Document/{id} poll until terminal-signed → Document/pdf retrieve.

## 7. Safe evidence to capture
Sanitized event timeline, DSR state transitions, package hash + version, provider document id
(where safe), signed-file SHA-256 + retrieval timestamp, readiness checklist snapshot. Never
capture tokens, passwords, raw payloads, Base64, or private file URLs.

## 8. Failure / recovery matrix
| Condition | System behaviour | Operator action |
|---|---|---|
| AddDocument network/timeout/5xx | `create_outcome_unknown`; no auto-recreate | SM `reconcile_document_creation` after locating the doc in SCTS |
| bulk-process ambiguous | DSR→Verifying; poll-only; never resend | wait for poll; if truly lost, governed re-queue path only |
| Signed file hash mismatch | candidate stored; accepted pointer kept; review ToDo | SM resolve_signed_file_review accept/reject/keep |
| Partial bulk outcome | each DSR reconciled independently; failed items stay governed | poll each; one failure never rolls back another |
| Package hash drift | signing blocked (VerificationMismatch) | requester creates a new package version |
| Worker crash post-acceptance | terminal state preserved by conditional updates | re-run poll; no duplicate action/ToDo/File |

## 9. Rollback plan
All gates are data flags: set `integration_enabled`/`allow_document_creation`/`allow_signing`
= 0 to halt all provider activity instantly (schedulers then build no adapter, zero network).
Code rollback = revert the stacked branch commits via Git (no data migration is destructive;
new fields/options are additive). No signed/original files are deleted on rollback.

## 10. Production-readiness checklist (NOT satisfied yet)
- [ ] Real SCTS UAT contract test for AddDocument inner fields + Document/pdf envelope.
- [ ] Real Frappe v16 runtime + migration evidence (fields/options/DocPerm) on a real bench.
- [ ] Multi-instance bulk-process contract confirmed before enabling true batch signing.
- [ ] Vendored PDF.js dist present + SHA-pinned.
- [ ] Full DB test suite green on the bench.
- [ ] Security review of production gate enablement + credential rotation policy.

## 11. Known unresolved SCTS contracts
See `SCTS_CONTRACT.md` §"Exact UAT evidence still required".

## 12. Bench test commands
```
bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_coords
bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_esign_netguard
bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_signing_ui_state
bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_signing_inbox
bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_bulk_sign
bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_signed_file_review
bench --site <site> run-tests --app ecentric_workspace   # full regression
```

## 13. Frappe Cloud deployment checklist
1. Merge only after PR#147 and this stack are reviewed. 2. `bench build --app
ecentric_workspace` (bundles ui assets incl. vendored PDF.js). 3. `bench --site <site>
migrate` (adds the 2 DSF fields + Event options — additive). 4. Verify regressions.
5. Configure UAT provider/profile/mapping/allowlist. 6. Follow the gate activation order.
Gates remain OFF through deploy.
