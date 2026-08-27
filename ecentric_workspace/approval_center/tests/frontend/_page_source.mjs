// Copyright (c) 2026, eCentric and contributors
//
// Locate a page's main_section.html for the headless tests.
//
// Why this exists: the 2026-08 reorg moved every page from a flat
// approval_center/frontend/<slug>.main_section.html into either
// features/<slug>/ui/main_section.html (per-form pages) or ui/<slug>/main_section.html
// (the shared hub, dashboard and all-requests pages). The 29 suites in this folder kept
// reading the old flat path, so every one of them died on ENOENT before its first
// assertion. Nobody noticed, because nobody was running them.
//
// So this resolver does two things deliberately:
//   1. it SEARCHES the known layouts instead of hard-coding one, and
//   2. when it finds nothing it throws with the slug and every path it tried, so the next
//      move produces a readable failure rather than a stack trace inside fs.
//
// Aliases exist only where the test slug and the folder name genuinely differ.
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const APP = path.join(HERE, "..", "..");          // -> approval_center

const ALIASES = {
  approvals: ["ui/hub"],
  approvals_dashboard: ["ui/dashboard"],
  all_requests: ["ui/all_requests"],
};

export function pageSource(slug) {
  const tried = [];
  const candidates = (ALIASES[slug] || []).concat([
    "features/" + slug + "/ui",
    "ui/" + slug,
  ]);
  for (const c of candidates) {
    const p = path.join(APP, c, "main_section.html");
    tried.push(p);
    if (fs.existsSync(p)) return fs.readFileSync(p, "utf8");
  }
  throw new Error(
    "main_section.html cho trang '" + slug + "' khong tim thay. Da thu:\n  " +
    tried.join("\n  ") +
    "\nNeu trang vua duoc di chuyen, cap nhat _page_source.mjs — dung sua tung bo test."
  );
}
