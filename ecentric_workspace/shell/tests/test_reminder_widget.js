// Homepage "Việc cần làm" badge must bind to the shared feed.total (Phase 1b).
'use strict';
const fs = require('fs'); const path = require('path');
const W = fs.readFileSync(path.join(__dirname, '..', '..', 'public', 'js', 'action_center_widget.js'), 'utf8');
let failures = 0;
function ok(c, m) { if (!c) { failures++; console.error('FAIL: ' + m); } else { console.log('ok  - ' + m); } }

ok(/function renderBadge\(total\)/.test(W), 'widget has renderBadge(total)');
ok(W.indexOf('msg.total') >= 0, 'badge reads feed.total from the shared provider');
ok(/panel\.querySelector\('\.approval-list'\)/.test(W), 'still renders into .approval-list panel');
ok(/data-ec-ac-badge="1"/.test(W), 'targets the widget-owned [data-ec-ac-badge] placeholder');
ok(/badge.hidden = false/.test(W), 'badge shown only when total > 0');
ok(/badge.textContent = String\(n\)/.test(W), 'badge text set from feed total (n), not a global count');
ok(W.indexOf('items.length') >= 0, 'list still uses page items');
ok(/n === 0/.test(W) && /badge.hidden = true/.test(W), 'badge HIDDEN (not removed) when total is 0');
// Phase 1b.2 follow-up: aggregate "Xem thêm N việc" link REMOVED from the widget.
// Assert against EXECUTABLE code only -- strip // line comments so the checks
// aren't fooled by documentation that names the removed route on purpose.
const Wc = W.replace(/\/\/.*$/gm, '');
ok(!/\/app\/todo\/view\/list/.test(Wc), 'widget: no /app/todo/view/list Desk-list route');
ok(!/ec-ac-more/.test(Wc), 'widget: no ec-ac-more aggregate anchor (incl. CSS) remains');
ok(!/Xem thêm/.test(Wc), 'widget: aggregate "Xem thêm" link absent');
ok(!/allocated_to=/.test(Wc), 'widget: no ToDo-list query string built');
ok(/it\.action_url/.test(W) && /href="' \+ esc\(href\)/.test(W),
   'widget: individual cards still bind the server-provided canonical action_url');

ok(/function renderKpi\(sourceCounts\)/.test(W), 'widget has renderKpi(sourceCounts)');
ok(/sourceCounts.approval/.test(W), 'KPI binds to source_counts.approval');
ok(/data-ec-ac-kpi="approval"/.test(W), 'KPI targets the widget-owned placeholder');
ok(/yêu cầu cần phản hồi/.test(W), 'meta uses session-scoped wording');
ok(/msg.source_counts/.test(W), 'reads source_counts from the shared feed');
// Phase 1b.2: drawer footer "Xem tất cả" REMOVED (full /action-center is
// Phase 2); act_now shows as "Đang xử lý" (internal key kept).
const S = fs.readFileSync(path.join(__dirname, '..', '..', 'public', 'js', 'ec_shell.js'), 'utf8');
ok(!/Xem tất cả/.test(S), 'drawer footer "Xem tất cả" removed (no aggregate link)');
ok(!/ec-shell-rm-all/.test(S), 'no rm-all footer anchor rendered');
ok(/foot = '';/.test(S), "footer intentionally empty (no placeholder path)");
ok(/\['act_now', 'Đang xử lý'/.test(S), "act_now bucket labelled 'Đang xử lý'");
ok(/\['act_now'/.test(S), "internal bucket key 'act_now' kept (backward-compatible)");
ok(!/\/app\/todo\/view\/list/.test(S), 'no /app/todo Desk path (permission-safe)');

console.log(failures === 0 ? '\nALL CHECKS PASSED' : '\n' + failures + ' FAILURES');
process.exit(failures ? 1 : 0);
