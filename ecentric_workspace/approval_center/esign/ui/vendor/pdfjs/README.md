# Vendored PDF.js (local, no CDN) — pdfjs-dist@4.10.38 (CVE-2024-4367 patched)

The bundled placement editor loads PDF.js **only** from
`/assets/ecentric_workspace/vendor/pdfjs/` (served from `ecentric_workspace/public/vendor/pdfjs/`).
No CDN or remote host is ever contacted.

**Pinned build:** `pdfjs-dist@4.10.38` **legacy ESM** build (`legacy/build/pdf.mjs` +
`pdf.worker.mjs`). This version is **not** affected by CVE-2024-4367 / GHSA-wgrm-67xf-hhpq
(which affects `<= 4.1.392`; first patched `4.2.67`). `npm audit` for `4.10.38` reports 0
advisories. The previous 3.11.174 build has been removed entirely.

The editor loads the module via **ESM dynamic `import()`** (no CDN, no `window` global, no
eval-based shim), sets `GlobalWorkerOptions.workerSrc` to the local `pdf.worker.mjs`, and
calls `getDocument({ ..., isEvalSupported: false })` as defence in depth.

Committed under `ecentric_workspace/public/vendor/pdfjs/`:
`pdf.mjs`, `pdf.worker.mjs`, `LICENSE` (Apache-2.0, upstream, unmodified), and
`PINNED.sha256` (package/version/npm-integrity/tarball-shasum/per-asset SHA-256/license/
retrieval-date/upstream). `verify_pdfjs.py` (build/CI + `tests/test_pdfjs_assets.py`) fails
closed if the version is below 4.2.67, the LICENSE is missing, any asset is missing or its
SHA-256 does not match, or a legacy `pdf.min.js`/`pdf.worker.min.js` remains — so the dist
cannot be silently swapped and deployment is not a manual copy step.

If the assets are ever absent the editor does not reach out remotely — it falls back to the
governed numeric coordinate-entry mode.
