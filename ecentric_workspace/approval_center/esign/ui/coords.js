/* Copyright (c) 2026, eCentric and contributors
 * Canonical placement coordinate math for the bundled PDF placement editor.
 * This is a 1:1 mirror of esign/coords.py. Canonical = TOP-LEFT origin, PDF points,
 * unrotated mediabox. Viewport = PDF.js rendered (rotated) canvas, CSS px at scale S.
 * The backend re-validates authoritatively; this is a deterministic display transform.
 * Exposed as window.ECoords (browser) and module.exports (node test).
 */
(function (root) {
  "use strict";
  var ROT = [0, 90, 180, 270];

  function normalizeRotation(r) {
    var v = parseInt(r || 0, 10);
    if (isNaN(v)) return 0;
    v = ((v % 360) + 360) % 360;
    return ROT.indexOf(v) >= 0 ? v : 0;
  }
  function renderedPageSize(pagePt, rotation) {
    var w = +pagePt[0], h = +pagePt[1], r = normalizeRotation(rotation);
    return (r === 90 || r === 270) ? [h, w] : [w, h];
  }
  function canonicalPointToRendered(cx, cy, pagePt, rotation) {
    var w = +pagePt[0], h = +pagePt[1], r = normalizeRotation(rotation);
    if (r === 0) return [cx, cy];
    if (r === 90) return [h - cy, cx];
    if (r === 180) return [w - cx, h - cy];
    return [cy, w - cx]; // 270
  }
  function renderedPointToCanonical(rx, ry, pagePt, rotation) {
    var w = +pagePt[0], h = +pagePt[1], r = normalizeRotation(rotation);
    if (r === 0) return [rx, ry];
    if (r === 90) return [ry, h - rx];
    if (r === 180) return [w - rx, h - ry];
    return [w - ry, rx]; // 270
  }
  function rectFromCorners(ax, ay, bx, by) {
    return { x: Math.min(ax, bx), y: Math.min(ay, by),
             width: Math.abs(bx - ax), height: Math.abs(by - ay) };
  }
  function round3(v) { return Math.round(v * 1000) / 1000; }

  function viewportRectToCanonical(rectPx, pagePt, scale, rotation) {
    var s = +scale;
    if (!(s > 0)) throw new Error("scale must be > 0");
    var rx1 = rectPx.x / s, ry1 = rectPx.y / s;
    var rx2 = (rectPx.x + rectPx.width) / s, ry2 = (rectPx.y + rectPx.height) / s;
    var c1 = renderedPointToCanonical(rx1, ry1, pagePt, rotation);
    var c2 = renderedPointToCanonical(rx2, ry2, pagePt, rotation);
    var o = rectFromCorners(c1[0], c1[1], c2[0], c2[1]);
    return { x: round3(o.x), y: round3(o.y), width: round3(o.width), height: round3(o.height) };
  }
  function canonicalRectToViewport(rectPt, pagePt, scale, rotation) {
    var s = +scale;
    if (!(s > 0)) throw new Error("scale must be > 0");
    var cx1 = rectPt.x, cy1 = rectPt.y, cx2 = rectPt.x + rectPt.width, cy2 = rectPt.y + rectPt.height;
    var r1 = canonicalPointToRendered(cx1, cy1, pagePt, rotation);
    var r2 = canonicalPointToRendered(cx2, cy2, pagePt, rotation);
    var o = rectFromCorners(r1[0] * s, r1[1] * s, r2[0] * s, r2[1] * s);
    return { x: round3(o.x), y: round3(o.y), width: round3(o.width), height: round3(o.height) };
  }
  function isWithinPage(rectPt, pagePt, tol) {
    tol = tol === undefined ? 1.0 : tol;
    var w = +pagePt[0], h = +pagePt[1];
    if (!(rectPt.width > 0) || !(rectPt.height > 0)) return false;
    return rectPt.x >= -tol && rectPt.y >= -tol &&
           (rectPt.x + rectPt.width) <= (w + tol) && (rectPt.y + rectPt.height) <= (h + tol);
  }

  var API = { normalizeRotation: normalizeRotation, renderedPageSize: renderedPageSize,
    canonicalPointToRendered: canonicalPointToRendered,
    renderedPointToCanonical: renderedPointToCanonical,
    viewportRectToCanonical: viewportRectToCanonical,
    canonicalRectToViewport: canonicalRectToViewport, isWithinPage: isWithinPage };
  if (typeof module !== "undefined" && module.exports) module.exports = API;
  root.ECoords = API;
})(typeof window !== "undefined" ? window : this);
