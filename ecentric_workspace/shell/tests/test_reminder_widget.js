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
ok(/total - DISPLAY_LIMIT/.test(W), 'Xem thêm uses feed.total, not page length');

console.log(failures === 0 ? '\nALL CHECKS PASSED' : '\n' + failures + ' FAILURES');
process.exit(failures ? 1 : 0);
