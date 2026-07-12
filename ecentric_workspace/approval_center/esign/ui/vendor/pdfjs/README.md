# Vendored PDF.js (local, no CDN)

The bundled placement editor (`pdf_placement_editor.html`) loads PDF.js **only** from
`/assets/ecentric_workspace/vendor/pdfjs/` — never from a CDN or any remote host. The
binary dist is intentionally **not** committed here (it is a large third-party build); the
operator vendors it once during deployment.

## Vendoring step (operator, offline-capable)

1. Download the **legacy** UMD build of a pinned PDF.js release (Mozilla, Apache-2.0), e.g.
   `pdfjs-dist@4.x` `legacy/build/pdf.min.js` + `legacy/build/pdf.worker.min.js`.
2. Copy both files into this directory:
   - `vendor/pdfjs/pdf.min.js`
   - `vendor/pdfjs/pdf.worker.min.js`
3. Record the SHA-256 of each file in `vendor/pdfjs/PINNED.sha256` and verify it on deploy.
4. `bench build --app ecentric_workspace` so the assets are served under
   `/assets/ecentric_workspace/vendor/pdfjs/`.

## Fail-closed behaviour

If the assets are absent, the editor **does not** reach out to any remote host — it shows a
clear message and falls back to the numeric coordinate-entry mode, which is fully
functional and governed by the same backend validation. No CDN, remote script, remote font,
or third-party runtime asset is ever loaded.

## Why legacy build

The legacy UMD build avoids ES-module/worker-type constraints and integrates as a single
`<script>` with a classic `workerSrc`, keeping the editor self-contained.
