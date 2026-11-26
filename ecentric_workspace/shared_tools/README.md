# Kalodata dùng chung (`shared_tools`)

Trang `/kalodata`: một tài khoản Kalodata, một người dùng một lúc, xếp hàng trên ERP. Giao diện theo mockup PO
duyệt 26/11/2026 (3 trạng thái: đang xếp hàng / đến lượt / đang dùng).

Trình duyệt Kalodata chạy trên **máy 24/7** (bộ `kalodata-host-poc`: Chromium kiosk + Guacamole + Cloudflare
Tunnel, thư mục `ERP Website\SHARED_TOOLS`). ERP chỉ giữ hàng đợi và gọi broker trên máy đó. ERP không bao
giờ thấy mật khẩu Kalodata, cookie hay mật khẩu VNC.

## Luồng

1. Nhân viên bấm **Vào hàng đợi**. Không ai giữ lượt thì đến lượt ngay.
2. Đến lượt: chuông thông báo ERP + trang đổi sang màu vàng, có **3 phút** để bấm **Mở Kalodata**.
3. Bấm Mở: ERP gọi broker `/ec/grant` (ký HMAC) → broker xoay mật khẩu VNC, trả link Guacamole sống 60 s →
   trang mở thẳng tab mới. Link không hiện ra, không lưu, không ghi log.
4. Lượt **30 phút**. Không ai chờ và còn dưới 10 phút thì **gia hạn 15 phút**.
5. Hết giờ / bấm Kết thúc sớm / **để yên 10 phút** (không ai xem màn hình, hoặc không chạm chuột-phím)
   → ERP gọi `/ec/revoke` → người tiếp theo đến lượt.
6. File xuất (nút Xuất bảng của extension, hoặc Export gốc của Kalodata) được ERP kéo về mỗi phút
   (và mỗi 10 s khi trang đang mở). Chỉ người xuất tải được; tự xoá sau 7 ngày.

Máy 24/7 không trả lời được thì **không** kết thúc lượt vì "để yên" (không biết thật hay không);
hết giờ vẫn kết thúc bình thường. Thu hồi lỗi → vòng dọn sau tự thu hồi lại (broker còn giữ user mà ERP
không còn lượt Đang dùng của người đó).

## File

| Phần | File |
| --- | --- |
| Luật hàng đợi (hàm thuần, test không cần bench) | `queue_rules.py` |
| Truy cập dữ liệu (nơi duy nhất gọi `frappe.db`) | `repository.py` |
| Lệnh: vào / rời hàng, mở, gia hạn, kết thúc, dọn hàng đợi | `service.py` |
| Đọc cho trang | `views.py` |
| File xuất: kéo về, tải, xoá | `exports.py` |
| Gọi broker máy 24/7 (HMAC) | `broker_client.py` |
| API | `controllers/api.py` |
| Tác vụ nền | `jobs.py` — mỗi phút dọn hàng đợi + kéo file; 03:20 xoá file quá 7 ngày |
| Trang | `pages/kalodata/` + `public/shared_tools/` |
| Menu | `nav.py` + `shell/nav.py` (ngữ cảnh `shared_tools`, khu Công ty › Công cụ) |

DocType: `EC Shared Tool` (cấu hình, bản ghi `kalodata`), `EC Shared Tool Queue` (mỗi lượt một dòng),
`EC Shared Tool Event` (nhật ký, chỉ thêm), `EC Shared Tool Export` (file xuất, file đính kèm riêng tư).

Quyền: mọi nhân viên (System User) dùng được. Muốn giới hạn → điền `allowed_role` trên bản ghi `kalodata`.
Role `EC Shared Tool Manager` (và System Manager): kết thúc lượt của người khác, sửa cấu hình.

## Cài đặt

1. Merge + deploy. Patch `shared_tools.p001_setup` tạo role, bản ghi `kalodata`, trang `/kalodata`.
2. **site_config** (Frappe Cloud › Site › Site Config, không để trong repo):
   - `ec_kalodata_broker_url` = `https://kalodata-gw.ecentric.asia/ec`
   - `ec_kalodata_broker_secret` = khoá trong `.env` máy 24/7 (`add_broker_secret.ps1` chép vào clipboard)
3. Cloudflare Tunnel `ec-kalodata-host`: thêm route `kalodata-gw.ecentric.asia`, path `^/ec/` → `http://broker:8088`,
   đặt TRÊN route catch-all sang Guacamole.
4. Máy 24/7: bản kit v3.5 (`broker_server.py`), `up -d --build broker`.

Chưa cấu hình (bước 2–4) thì trang vẫn chạy, nhãn "Chưa nối máy", nút Mở báo lỗi rõ ràng.

Test: `python -m unittest ecentric_workspace.shared_tools.tests.test_queue ecentric_workspace.shared_tools.tests.test_page`

Đổi CSS/JS → `python -m ecentric_workspace.shared_tools.pages.assets --stamp` → thêm patch resync trang.
