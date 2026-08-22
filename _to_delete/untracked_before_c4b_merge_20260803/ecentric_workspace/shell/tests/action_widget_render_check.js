// Phase 1b.2 follow-up: RENDER-LEVEL proof for the Homepage action widget.
// Drives the real widget (action_center_widget.js) with a minimal fake DOM and
// a stubbed frappe.call, then asserts the produced HTML:
//   - individual Approval / Weekly Update / PM Task cards render with the
//     server-provided canonical action_url (no client route-building);
//   - the aggregate "Xem thêm N việc" link is GONE even when total > 4;
//   - no /app/todo/view/list Desk-list route appears anywhere.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

let failures = 0;
function ok(c, m) { if (!c) { failures++; console.error('FAIL: ' + m); } else { console.log('ok  - ' + m); } }

const SRC = fs.readFileSync(
  path.join(__dirname, '..', '..', 'public', 'js', 'action_center_widget.js'), 'utf8');

// ---- minimal fake DOM ------------------------------------------------------
function makeEl(extra) {
  const el = Object.assign({
    innerHTML: '', textContent: '', hidden: false,
    className: '', style: {},
    setAttribute() {}, appendChild() {}, addEventListener() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
  }, extra || {});
  return el;
}

const listEl = makeEl();                       // .approval-list (captures innerHTML)
const titleEl = makeEl({ textContent: 'Việc cần làm', querySelector() { return null; } });
const panel = makeEl({
  querySelector(sel) {
    if (sel === '.panel-title') return titleEl;
    if (sel === '.approval-list') return listEl;
    return null;
  },
});

const document = {
  readyState: 'complete',
  getElementById() { return { }; },            // truthy -> skip CSS injection branch
  createElement() { return makeEl(); },
  createTextNode() { return {}; },
  head: makeEl(),
  addEventListener() {},
  querySelector() { return null; },            // KPI placeholders absent
  querySelectorAll(sel) { return sel === '.panel' ? [panel] : []; },
};

// items: one of each first-class source + fillers so total (10) > DISPLAY_LIMIT(4)
const ITEMS = [
  { source_label: 'PHÊ DUYỆT', title: 'PO one', priority: 'High',
    modified: '2026-07-27 10:00:00', action_url: '/approval?id=PO-1&type=po_request' },
  { source_label: 'BÁO CÁO TUẦN', title: 'Báo cáo tuần', priority: 'Medium',
    modified: '2026-07-27 10:00:00', action_url: '/weekly-update?week=2026-W30' },
  { source_label: 'CÔNG VIỆC', title: 'Do X', priority: 'Low',
    modified: '2026-07-27 10:00:00', action_url: '/pm#task/TASK-1' },
  { source_label: 'VIỆC', title: 'extra', priority: 'Medium',
    modified: '2026-07-27 10:00:00', action_url: '/app/todo/td-9' },
];

const win = {
  _ecActionCenterInstalled: false,
  frappe: {
    session: { user: 'emp@ecentric.vn' },
    call(opts) {                                // synchronous stub
      opts.callback({ message: { success: true, total: 10, items: ITEMS, source_counts: {} } });
    },
  },
};

const sandbox = {
  window: win, document, console: { log() {}, error() {} },
  setInterval() { return 0; }, clearInterval() {},
};
sandbox.globalThis = sandbox;

vm.createContext(sandbox);
vm.runInContext(SRC, sandbox);                 // IIFE boots -> init -> loadItems -> renderCards

const html = listEl.innerHTML;
ok(html.length > 0, 'widget rendered card HTML');
// individual canonical links present (esc() turns & into &amp;, so match substrings)
ok(html.indexOf('/approval?id=PO-1') >= 0, 'Approval card uses canonical /approval action_url');
ok(html.indexOf('/weekly-update?week=2026-W30') >= 0, 'Weekly Update card uses canonical /weekly-update action_url');
ok(html.indexOf('/pm#task/TASK-1') >= 0, 'PM Task card uses canonical /pm#task action_url');
ok((html.match(/class="ec-ac-card"/g) || []).length === 4, 'renders DISPLAY_LIMIT cards');
// aggregate link + Desk list route gone even though total(10) > DISPLAY_LIMIT(4)
ok(html.indexOf('Xem thêm') < 0, 'no aggregate "Xem thêm" link rendered (total > limit)');
ok(html.indexOf('/app/todo/view/list') < 0, 'no /app/todo/view/list route in rendered HTML');
ok(html.indexOf('ec-ac-more') < 0, 'no ec-ac-more aggregate anchor in rendered HTML');

console.log(failures === 0 ? '\nALL CHECKS PASSED' : '\n' + failures + ' FAILURES');
process.exit(failures ? 1 : 0);
