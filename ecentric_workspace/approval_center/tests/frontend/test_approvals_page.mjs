// Headless behavior tests for the /approvals page (Node + jsdom).
// Run: (cd where jsdom installed) node .../tests/frontend/test_approvals_page.mjs
// Verifies data-driven rendering, states, search, category filter, and
// per-status clickability. Frontend is NOT the security boundary (server is).
import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dir = path.dirname(fileURLToPath(import.meta.url));
const HTML = fs.readFileSync(path.join(__dir, "..", "..", "frontend", "approvals.main_section.html"), "utf8");
const [markup, rest] = HTML.split('<script id="ec-approval-center">');
const JS = rest.replace(/<\/script>\s*$/, "");

let fails = 0;
function ok(cond, name){ if(cond){ console.log("  ok:", name); } else { console.log("  FAIL:", name); fails++; } }
const flush = () => new Promise(r => setTimeout(r, 5));

const FIX = {
  is_admin: true,
  categories: [
    { category_code:"HR", category_name:"Nhan su", icon:"users", sort_order:10 },
    { category_code:"FIN", category_name:"Tai chinh", icon:"wallet", sort_order:20 },
  ],
  types: [
    { approval_code:"A_ACTIVE", approval_title:"Active Flow", description:"desc active", icon:"", category_code:"HR", category_name:"Nhan su", category_icon:"users", card_status:"Active", process_status:"Live", route:"/approvals/active-flow", sort_order:10, category_sort_order:10 },
    { approval_code:"A_NOROUTE", approval_title:"Active NoRoute", description:"x", icon:"", category_code:"HR", category_name:"Nhan su", category_icon:"users", card_status:"Active", process_status:"Live", route:null, sort_order:20, category_sort_order:10 },
    { approval_code:"A_COMING", approval_title:"Coming Thing", description:"soon", icon:"", category_code:"HR", category_name:"Nhan su", category_icon:"users", card_status:"Coming Soon", process_status:"Discovery", route:null, sort_order:30, category_sort_order:10 },
    { approval_code:"A_MIGR", approval_title:"Migrating Thing", description:"m", icon:"", category_code:"FIN", category_name:"Tai chinh", category_icon:"wallet", card_status:"Migrating", process_status:"Building", route:null, sort_order:10, category_sort_order:20 },
    { approval_code:"A_DIS", approval_title:"Disabled Thing", description:"d", icon:"", category_code:"FIN", category_name:"Tai chinh", category_icon:"wallet", card_status:"Disabled", process_status:"Retired", route:null, sort_order:20, category_sort_order:20 },
  ],
};

function boot(){
  const dom = new JSDOM('<!DOCTYPE html><html><body>' + markup + '</body></html>',
    { runScripts: "outside-only", pretendToBeVisual:true, url:"https://x.test/approvals" });
  const w = dom.window;
  return { dom, w };
}

async function run(){
  // --- scenario 1: loading -> success render (data-driven) ---
  let dom = boot(); let w = dom.w;
  let pending; w.frappe = { call: () => new Promise((res)=>{ pending = res; }) };
  w.eval(JS); await flush();
  ok(!!w.ApprovalCenter, "window.ApprovalCenter exposed");
  ok(w.document.querySelector(".skel"), "loading state shows skeletons");
  pending({ message: FIX }); await flush(); await flush();
  const grid = w.document.querySelector(".apc-grid");
  ok(!!grid, "grid renders after success");
  ok(w.document.querySelectorAll(".card").length === 5, "renders 5 cards from API (admin, no disabled filter here)");

  // no hardcoded list: cards came only from FIX
  ok(!HTML.includes("AI_TOPUP") && !HTML.includes("RESIGNATION"), "no seeded approval codes hardcoded in page source");

  // shortcut to /approval present and not a card
  ok(!!w.document.querySelector('.ec-sidebar a[href="/approval"]'), "'/approval' (Duyệt chứng từ) is a sidebar sibling");
  ok(!w.document.querySelector(".btn-inbox"), "header inbox button removed (no duplicate)");
  { const sb = w.document.querySelector(".ec-sidebar").textContent;
    ok(/Yêu cầu nội bộ/.test(sb) && /Duyệt chứng từ/.test(sb), "sidebar labels: Yêu cầu nội bộ + Duyệt chứng từ"); }

  // --- status clickability ---
  const byCode = (c)=> w.document.querySelector('.card[data-code="'+c+'"]');
  ok(byCode("A_ACTIVE").classList.contains("clickable"), "Active+route is clickable");
  ok(!!byCode("A_ACTIVE").querySelector('a.card-cta.go[href="/approvals/active-flow"]'), "Active card CTA links to API route");
  ok(!byCode("A_NOROUTE").classList.contains("clickable"), "Active without route is NOT clickable");
  ok(!!byCode("A_NOROUTE").querySelector(".card-cta.disabled"), "Active without route shows disabled CTA");
  ok(!byCode("A_COMING").classList.contains("clickable"), "Coming Soon not clickable");
  ok(!byCode("A_MIGR").classList.contains("clickable"), "Migrating not clickable");
  ok(!byCode("A_DIS").classList.contains("clickable") && byCode("A_DIS").classList.contains("dim"), "Disabled not clickable (dim)");
  // no card exposes a route except the active-with-route one
  const routed = [...w.document.querySelectorAll(".card")].filter(c=>c.getAttribute("data-route"));
  ok(routed.length === 1 && routed[0].getAttribute("data-code")==="A_ACTIVE", "only Active-with-route exposes a route");

  // --- category filter ---
  w.document.querySelector('.chip[data-cat="FIN"]').click(); await flush();
  let codes = [...w.document.querySelectorAll(".card")].map(c=>c.getAttribute("data-code"));
  ok(codes.length===2 && codes.every(c=>["A_MIGR","A_DIS"].includes(c)), "category chip filters to that category");

  // back to all
  w.document.querySelector('.chip[data-cat="__all__"]').click(); await flush();
  ok(w.document.querySelectorAll(".card").length===5, "'Tat ca' shows all");

  // --- search + combined ---
  const q = w.document.getElementById("apc-q");
  q.value = "coming"; q.dispatchEvent(new w.Event("input")); await flush();
  codes = [...w.document.querySelectorAll(".card")].map(c=>c.getAttribute("data-code"));
  ok(codes.length===1 && codes[0]==="A_COMING", "search matches title");
  // combined: search 'thing' + category FIN -> A_MIGR, A_DIS (both titles contain 'Thing')
  q.value = "thing"; q.dispatchEvent(new w.Event("input"));
  w.document.querySelector('.chip[data-cat="FIN"]').click(); await flush();
  codes = [...w.document.querySelectorAll(".card")].map(c=>c.getAttribute("data-code")).sort();
  ok(JSON.stringify(codes)===JSON.stringify(["A_DIS","A_MIGR"]), "search + category combine correctly");
  // no-results
  q.value = "zzzznomatch"; q.dispatchEvent(new w.Event("input")); await flush();
  ok(/Không có kết quả/.test(w.document.getElementById("apc-body").textContent), "no-results state shown");

  // --- empty catalog ---
  dom = boot(); w = dom.w;
  w.frappe = { call: () => Promise.resolve({ message: { is_admin:false, categories:[], types:[] } }) };
  w.eval(JS); await flush(); await flush(); await flush();
  ok(/Chưa có phê duyệt/.test(w.document.getElementById("apc-body").textContent), "empty catalog state shown");

  // --- error + retry ---
  dom = boot(); w = dom.w;
  let mode = "reject";
  w.frappe = { call: () => mode==="reject" ? Promise.reject(new Error("x")) : Promise.resolve({ message: FIX }) };
  w.eval(JS); await flush(); await flush(); await flush();
  ok(!!w.document.querySelector('[data-apc="retry"]'), "API error shows retry button");
  mode = "resolve";
  w.document.querySelector('[data-apc="retry"]').click(); await flush();
  ok(w.document.querySelectorAll(".card").length===5, "retry recovers and renders cards");

  console.log(fails===0 ? "\nALL FRONTEND BEHAVIOR TESTS PASSED" : ("\nFAILURES: "+fails));
  process.exit(fails===0?0:1);
}
run();
