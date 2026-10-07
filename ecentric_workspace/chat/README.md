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

## "Ruột" Raven: tiếng Việt + màu ERP (06/10/2026)

Không sửa Raven. Hai hook trong `chat/boot.py`, chỉ đụng trang `/raven` (cả khi nhúng trong `/chat`):

- `extend_bootinfo`: phủ `chat/raven_vi.json` (1.684 chuỗi giao diện web Raven 3.0.0 → tiếng Việt) vào
  `boot.__messages`. Không đổi ngôn ngữ tài khoản: Desk, HRMS, email giữ nguyên.
- `after_request`: chèn vào HTML trang `/raven` một `<link>` tới `public/css/ec_chat_raven_skin.css`
  (nút chính + kênh đang mở màu navy, logo eCentric) và một `<script src>` tới
  `public/js/ec_raven_boot.js`, ngay sau thẻ script boot của Raven.
- Vì sao cần `ec_raven_boot.js`: Raven 3.0.0 dịch bằng `window.frappe._messages` nhưng chỉ gán biến
  này ở chế độ dev/offline, nên trên site thật mọi chuỗi luôn tiếng Anh. Script nối nó vào boot, và
  chọn sẵn giao diện sáng cho người chưa tự chọn (ERP chỉ có giao diện sáng).
- Raven đổi template (mất mốc `frappe.boot = JSON.parse(`) → trang giữ nguyên bản gốc, không vỡ.
  Raven thêm chữ mới → chữ đó hiện tiếng Anh tới khi bổ sung vào `raven_vi.json`.
- Vẫn tiếng Anh vì Raven viết cứng, không qua `_()`: ngày giờ ("6th October 2026", "3:19 pm"),
  "Failed to load messages", bộ lọc "Participating" / "AI Agents" ở trang Luồng.
- Tắt: `site_config` → `"ec_chat_skin_disabled": 1` (Raven về nguyên bản tiếng Anh, không cần deploy).
- `/chat` chừa ~80px dưới khung: góc phải dưới là chỗ của eC Mate, nút Gửi của Raven nằm đúng góc đó.

## Phiếu trong chat (07/10/2026)

PO: "mọi người có thể gửi phiếu qua lại trong chat cho tiện". `chat/phieu.py` (thuần) + `chat/phieu_gateway.py`.
Không sửa Raven, không sửa Approval Center: chỉ đọc registry loại phiếu + `EC Approval Type.route`, nghe 2 sự kiện.

- **Dán link phiếu** (`https://team.ecentric.vn/approvals/<loại>?id=<số phiếu>`) vào chat → tin nhắn tự
  mang **thẻ phiếu** của Raven (doc_events `Raven Message.before_insert` gán `link_doctype/link_document`,
  tắt xem trước web vì link nội bộ chỉ ra trang đăng nhập). Chỉ gắn khi NGƯỜI GỬI xem được phiếu;
  người xem thẻ cũng do Raven kiểm quyền riêng (không có quyền → chỉ thấy số phiếu).
- **Thẻ phiếu mở trang duyệt ERP** chứ không mở Desk: hook `raven_document_link_override`. Áp cả cho
  thẻ tạo bằng nút "Đính kèm chứng từ" của Raven.
- **Dòng trên thẻ**: patch `chat/patches/p001_the_phieu_preview` bật `in_preview` (Property Setter) cho
  người đề nghị, phòng ban, ngày gửi, số tiền của mọi loại phiếu. Không có patch này Raven hiện mọi
  trường bắt buộc (lý do dài, số tài khoản ngân hàng…).
- **Bot "Phiếu duyệt"** nhắn riêng mỗi thông báo phê duyệt (cần duyệt / đã duyệt / từ chối / cần bổ sung /
  huỷ) — cùng lúc với chuông ERP, nghe dòng `erp` của `EC Notification Delivery Log` (event
  `approval_required`), gửi bằng job nền sau commit. Kèm thẻ phiếu + link. Chỉ gửi cho người có chat.
  Bot tự tạo ở lần gửi đầu. Teams vẫn nhận như cũ (chưa tắt kênh nào).
- Tắt: `ec_chat_bot_disabled` (chỉ bot) / `ec_chat_phieu_disabled` (cả ba). Không cần deploy.
- Duyệt NGAY trong chat: chưa làm — nút chuyển trạng thái trên thẻ của Raven chỉ chạy với Frappe
  Workflow, phiếu của ta chạy engine riêng; làm được thì phải sửa Raven.

## Kiểm

```
python -m unittest ecentric_workspace.chat.tests.test_chat        # 45 test, gồm node harness ec_chat.js + ec_raven_boot.js
python -m unittest ecentric_workspace.chat.tests.test_phieu       # 15 test phiếu trong chat
python -m unittest discover -s ecentric_workspace/shell/tests -t . -p "test_*.py"
python tools/ci/check.py
```

Đột biến (05/10): mở kênh ngoài danh sách, lộ trường Raven User, bỏ escape tiêu đề, bỏ qua kill
switch, hiện kênh lưu trữ — 5/5 bị bắt. Đột biến (06/10, lớp ruột): khớp nhầm `/ravenx`, sửa dict boot
tại chỗ, chèn 2 lần, chèn sai chỗ, bỏ escape, bỏ kiểm đường dẫn / status / mimetype / kill switch, ghi đè
`_messages` có sẵn, ghi đè chủ đề người dùng đã chọn — 11/11 bị bắt.

## Không kiểm được ngoài site thật

- Raven trong iframe: đăng nhập, gửi file, mở link chứng từ, service worker `/raven/sw.js`.
- Realtime `raven:unread_channel_count_updated` tới trang ERP (nếu socket trang chưa nối, còn vòng
  hỏi 2 phút).
- Đổi tên hàm Raven ở bản sau → API trả "Không tải được tin nhắn", Error Log `ec_chat` (tối đa
  1 lần / 10 phút). Bench Raven đang theo nhánh `main`.
