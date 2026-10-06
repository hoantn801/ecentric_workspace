# chat/ — Chat nội bộ (Raven gắn vào ERP)

PO chốt 05/10/2026: **A + C**. Quyết định: `01_DECISION_LOG.md` A70 (cài Raven) + A71 (lối vào).
Brief: `NHIEU_LOP/brief_chat_noi_bo_raven.md`. Mockup: artifact "Chat nội bộ Raven — 3 mockup".

Module này **không sửa gì của Raven** và **không tự viết chat**. Nó chỉ:

| Phần | Ở đâu | Làm gì |
|---|---|---|
| **A** — trang `/chat` | `www/chat`, `chat/pages.py`, `public/css/ec_chat_page.css` | Raven trong `<iframe>` (cùng tên miền, `X-Frame-Options: SAMEORIGIN`) nằm trong vỏ shell ERP. `?c=<kênh>` mở thẳng kênh/DM — chỉ khi kênh có trong danh sách Raven trả cho chính người đó. |
| **C** — ô Tin nhắn trên thanh trên | `shell/fallback.render_chat_slot`, `shell/server_nav.rebuild_tbright`, `ec_shell.js renderHeaderRight` | Một **liên kết** `/chat` (không JS vẫn dùng được), đứng trước hộp "Việc của tôi". Góc phải dưới để cho eC Mate. |
| Khay thả xuống + huy hiệu | `public/js/ec_chat.js`, `public/css/ec_chat.bundle.css` | Bấm ô (màn ≥ 641px) → khay 380px, 8 cuộc trò chuyện gần nhất, lọc Chưa đọc / Tất cả. Tô huy hiệu ở ô và ở mục menu "Chat nội bộ". |
| Mục menu | `shell/nav.py` `home.portal.chat` | Nhóm Workspace, `badge_source: chat.unread` (ec_chat.js tô, shell bỏ qua khoá này). |
| API | `chat/api.py` | `get_unread_total`, `get_inbox` — GET, đọc **dưới phiên**, trả `{success, message, data}`. |
| Cổng vào Raven | `chat/gateway.py` | Gọi đúng 3 hàm công khai của Raven: `get_all_channels`, `get_unread_count_for_channels`, `raven_users.get_list`. Kênh riêng / DM do Raven lọc. Chỉ lấy `full_name` + `user_image` của người dùng. |
| Lõi thuần | `chat/inbox.py` | Sắp xếp, xem trước tin cuối, đường dẫn iframe, trạng thái truy cập. Không import frappe. |

## Vì sao ô Tin nhắn chỉ thêm LÚC RENDER

Vùng phải thanh trên được nướng sẵn vào **62 file trang**. Sửa bản nướng = 62 file + 62 dòng manifest +
patch resync, va chạm với mọi nhánh đang mở. Thay vào đó: bản nướng giữ nguyên 2 ô (cổng vỏ shell
không đổi), hook `update_website_context` (`server_nav.fill_shell_mount`) thêm ô chat vào HTML lúc
render — cùng cơ chế A65 đang dùng để dựng lại menu trái. Trang www (`/gop-y`, `/tin-noi-bo`,
`/tai-lieu`, `/bang-tin`, `/chat`) gọi `render_topbar_inner(..., chat=chat_enabled())`.
`ec_shell.js` vẽ lại đúng cùng markup (test `test_js_emits_identical_slot_markup`) → không nhảy.

## Bật / tắt

- Tắt khẩn: `site_config` → `"ec_chat_disabled": 1`. Ô Tin nhắn biến mất, `/chat` báo "tạm tắt",
  API trả `state: disabled`. Trang Web Page có cache HTML → xoá cache website sau khi bật/tắt.
- Raven chưa cài → như tắt (`state: not_installed`).
- Người chưa có role **Raven User** → vẫn thấy ô/mục menu (HTML dùng chung cache), bấm vào thấy
  hướng dẫn xin quyền. Cấp quyền hàng loạt: `/raven` → Settings → Users → Add users
  (hàm `raven.api.raven_users.add_users_to_raven`; site không dùng Role Profile nên không bị bỏ sót).

## Kiểm

```
python -m unittest ecentric_workspace.chat.tests.test_chat        # 27 test, gồm node harness ec_chat.js
python -m unittest discover -s ecentric_workspace/shell/tests -t . -p "test_*.py"
python tools/ci/check.py
```

Đột biến (05/10): mở kênh ngoài danh sách, lộ trường Raven User, bỏ escape tiêu đề, bỏ qua kill
switch, hiện kênh lưu trữ — 5/5 bị bắt.

## Không kiểm được ngoài site thật

- Raven trong iframe: đăng nhập, gửi file, mở link chứng từ, service worker `/raven/sw.js`.
- Realtime `raven:unread_channel_count_updated` tới trang ERP (nếu socket trang chưa nối, còn vòng
  hỏi 2 phút).
- Đổi tên hàm Raven ở bản sau → API trả "Không tải được tin nhắn", Error Log `ec_chat` (tối đa
  1 lần / 10 phút). Bench Raven đang theo nhánh `main`.
