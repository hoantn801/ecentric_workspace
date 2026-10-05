// Chay ec_chat.js trong node (khong DOM): path /app -> khong boot, chi lay window.ECChat.
'use strict';
var fs = require('fs');
var path = require('path');
var assert = require('assert');
global.window = { location: { pathname: '/app/x' } };
var src = fs.readFileSync(path.join(__dirname, '..', '..', 'public', 'js', 'ec_chat.js'), 'utf8');
new Function(src)();
var E = global.window.ECChat;
assert.ok(E, 'ECChat exported');

assert.strictEqual(E.badgeText(0), '');
assert.strictEqual(E.badgeText(-3), '');
assert.strictEqual(E.badgeText(7), '7');
assert.strictEqual(E.badgeText(10), '9+');

var now = new Date(2026, 9, 5, 20, 0);
assert.strictEqual(E.timeLabel('2026-10-05 09:21:00.12', now), '09:21');
assert.strictEqual(E.timeLabel('2026-10-04 17:00:00', now), 'Hôm qua');
assert.strictEqual(E.timeLabel('2026-09-28 17:00:00', now), '28/09');
assert.strictEqual(E.timeLabel('', now), '');
assert.strictEqual(E.timeLabel('2026-10-01 00:00:00', new Date(2026, 9, 2, 1, 0)), 'Hôm qua');

// XSS: moi chuoi tu Raven deu duoc escape
var evil = { id: 'x', kind: 'channel', title: '<img src=x onerror=alert(1)>', is_private: false, unread: 2,
             last_at: '2026-10-05 09:00:00', preview: '"><script>1</script>', avatar: '',
             initials: 'X', href: '/chat?c=x" onmouseover="1' };
var row = E.rowHtml(evil, now);
assert.ok(row.indexOf('<img src=x') < 0, 'title escaped');
assert.ok(row.indexOf('<script>') < 0, 'preview escaped');
assert.ok(row.indexOf('" onmouseover') < 0, 'href escaped');
assert.ok(row.indexOf('ec-chat-row-unread') > 0);
var dm = E.rowHtml({ id: 'd', kind: 'dm', title: 'Lâm', avatar: '/files/a".png', initials: 'L', unread: 0,
                     href: '/chat?c=d', preview: '', last_at: '' }, now);
assert.ok(dm.indexOf('src="/files/a&quot;.png"') > 0, 'avatar escaped');
assert.ok(dm.indexOf('data-initials="L"') > 0, 'avatar keeps initials for broken-image fallback');
assert.ok(dm.indexOf('ec-chat-count') < 0, 'no count when 0');

// trang thai than khay
assert.ok(E.bodyHtml({ loading: true }, 'all', now).indexOf('Đang tải') > 0);
var err = E.bodyHtml({ error: '<b>Lỗi</b>' }, 'all', now);
assert.ok(err.indexOf('data-ec-chat-retry') > 0 && err.indexOf('<b>') < 0);
assert.ok(E.bodyHtml({ data: { state: 'no_access', message: 'Chưa có quyền' } }, 'all', now).indexOf('Chưa có quyền') > 0);
assert.ok(E.bodyHtml({ data: { state: 'ok', items: [] } }, 'unread', now).indexOf('Không có tin chưa đọc') > 0);
assert.ok(E.bodyHtml({ data: { state: 'ok', items: [] } }, 'all', now).indexOf('Chưa có cuộc trò chuyện') > 0);
var p = E.panelHtml({ data: { state: 'ok', items: [evil] } }, 'unread', now);
assert.ok(p.indexOf('data-ec-chat-filter="unread" aria-pressed="true"') > 0);
assert.ok(p.indexOf('data-ec-chat-filter="all" aria-pressed="false"') > 0);
assert.ok(p.indexOf('href="/chat">Mở Chat nội bộ') > 0);
console.log('ALL OK');
