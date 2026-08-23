# Global Notification Center Shell — Status Report (round 2)

**Branch:** `fix/global-notification-center-shell` (from `origin/main` @ `aa0b5ae`)
**Commits:** `b59d60d` (global loader + badge) → **`d7be123`** (retire homepage loader + prove handler)
**Status:** implemented ✅ · tested ✅ (55/55) · committed ✅ · **not pushed / not deployed**

---

## 1. Retire the homepage-only loader — done (one-time migrate required)

**Was the asset double-loading on `/home`?** With the new global include, yes it would: once
from the homepage Web Page record (the `<script>` that patch `p001` inserted) and once from
`web_include_js`. The install guard is **not** treated as the fix.

**Fix:** new cleanup patch
`ecentric_workspace/notification_center/patches/p002_retire_homepage_bell_loader.py`:

- removes exactly the block `p001` inserted —
  `<script id="ec-notification-center" …></script><!-- /ec-notification-center -->` — from the
  homepage Web Page record;
- **Action Center untouched** (asserts the `<!-- /ec-action-center-widget -->` anchor count is
  unchanged; aborts otherwise);
- **idempotent** (no marker → no-op; safe to re-run; safe if `p001` never ran);
- registered in `patches.txt` **after** `p001`. It is the **single** architecture-migration
  patch — **no per-page patches**.

**Deployment:** because `p001` already ran in production, editing it is not enough — this needs a
**one-time `bench migrate`** to run `p002`. After migrate, `/home` (like every other page) loads
the Notification Center asset **exactly once**.

## 2. Legacy "Tính năng đang phát triển" handler — exact mechanism + proof

**Mechanism (in `notification_center.js`, function `adoptBell` + the bell click handler):**

| Legacy form | How it is neutralised |
|---|---|
| inline `onclick="…"` attribute | `clone.removeAttribute('onclick')` on the adopted clone |
| property handler `bell.onclick = fn` | `cloneNode(true)` does **not** copy DOM properties → dropped |
| `addEventListener('click', fn)` | `cloneNode(true)` does **not** copy listeners → dropped |
| document-level **delegated** handler | `ev.stopPropagation()` + `stopImmediatePropagation()` on **every** bell click → event never reaches `document` |

The bell is **adopted** (`cloneNode(true)` + `parentNode.replaceChild`) so the original node — with
all its bound/inline/property handlers — is detached. Native nav is preserved for
modifier/middle-click because we only `preventDefault()` on a plain left-click.

**Proof (executed, not string-only):** `tests/bell_click_check.js` runs the **real asset**
against a mini-DOM that models event **bubbling**, the `onclick` property, the inline `onclick`
attribute, `addEventListener` and a document-delegated handler. Per route **`/home`,
`/overview`, `/approval`** it asserts:

- plain left-click → **opens the dropdown**, fires **no** legacy handler (all four forms), and
  cancels native nav;
- **Ctrl-click / middle-click** → does **not** open the dropdown, keeps native
  `/app/notification-log` nav, fires no legacy handler;
- Frappe Desk `/app/*` and a public no-bell page → fully inert, no error.

→ 41 click-behaviour assertions, all pass.

## 3. Global loading verification

**Exact hook (`hooks.py`):**

```python
web_include_js = ["/assets/ecentric_workspace/js/notification_center.js"]
```

Verified (executed in `tests/dom_runtime_check.js` + `bell_click_check.js`):

- **website custom pages** receive the asset (loads on `/home`, `/overview`, `/approval`, …);
- **Frappe Desk `/app`** is **not** bound — `web_include_js` is website-only (not
  `app_include_js`), and the asset itself bails on `/app` and `/app/…`;
- **login / public pages** with no eCentric bell load the asset **without error** and stay inert;
- **`/approval` is not mistaken for `/app`** — the guard matches only `=== '/app'` or
  `indexOf('/app/') === 0` (this exact bug was caught by the runtime harness and fixed).

---

## Final deliverable

1. **Files changed (7)** vs `origin/main`:
   - `ecentric_workspace/hooks.py` (+15) — `web_include_js`
   - `ecentric_workspace/public/js/notification_center.js` (+79/−15) — global guard, bell adopt, badge
   - `ecentric_workspace/notification_center/patches/p002_retire_homepage_bell_loader.py` (+105, new)
   - `ecentric_workspace/patches.txt` (+1) — register p002
   - `ecentric_workspace/notification_center/tests/test_notification_center.py` (+174)
   - `ecentric_workspace/notification_center/tests/dom_runtime_check.js` (+201, new)
   - `ecentric_workspace/notification_center/tests/bell_click_check.js` (+185, new)
   - **Untouched:** NC backend/API, permissions, Weekly Report, Alert Center, p001.
2. **Cleanup patch?** Yes — one: `p002_retire_homepage_bell_loader` (single migration).
3. **Migrate needed?** **Yes, one-time** `bench migrate` (after `bench build`).
4. **Tests:** **55 pass** = 36 original + 19 new. Both node harnesses execute the real asset.
5. **Browser verification:** runtime-executed across `/home`, `/overview`, `/approval` (above).
   A standalone real-browser harness — `nc-browser-verify.html` — is in this folder (mock shell +
   real legacy handler + real asset embedded) for a click-through in a real browser.
   ⚠️ Verification against the **actual deployed** pages needs the gated `bench build` + `bench
   migrate` and a site URL — I can drive that via Chrome once you approve deploy and share the URL.
6. **Per page after migrate:** exactly **one** asset load, **one** badge, **one** dropdown,
   **one** effective click handler (proven: single-install guard + idempotent mount/build +
   p002 removes the homepage `<script>`; harness asserts a single badge/dropdown and one bell
   handler).
7. **New commit hash:** `d7be123` (`d7be123feb3a9e2634d4d012f39555c856c1278b`).

**Not pushed / not deployed.** Deploy order when approved: `bench build` → `bench migrate`
(runs p002) → `bench clear-cache`.

## Environment note (unchanged)
Your local `C:\dev\ecentric_workspace\.git` is degraded (a crashed git process null-corrupted
`config`+`index`; the mount blocks `unlink`). All git work was done in a clean clone of
`origin/main`; the patch above applies onto a healthy checkout, or I can push the branch on your
go-ahead.
