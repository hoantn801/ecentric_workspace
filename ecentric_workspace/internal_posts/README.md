# Tin nội bộ (`/tin-noi-bo`)

HR / Admin soạn và đăng bài cho nhân viên đọc, ngay trên ERP, không cần deploy mỗi bài.
PO Hoàn chốt 01/10/2026, thiết kế = mockup v5 (artifact FcTCyxQHztUqAjPbeBHVxY).

## Trang

| Route | Ai | Nội dung |
|---|---|---|
| `/tin-noi-bo` | mọi nhân viên | Bố cục "Chuyên mục": bài ghim + 3 bài mới, mỗi chuyên mục một hàng. `?chuyen-muc=`, `?chua-xem=1`, `?q=`, `?trang=` |
| `/tin-noi-bo/<slug>` | người trong phạm vi | Bài: bìa, nội dung, cột phải (mục lục, lượt xem, tệp, cảm xúc, hộp HR) |
| `/tin-noi-bo/viet-bai` (`?bai=`) | HR | Soạn / sửa: ảnh bìa (màu nền / tải ảnh / AI), phạm vi, chuông, popup, tệp |
| `/tin-noi-bo/quan-ly` | HR | Đang hiện / Nháp / Hết hạn, lượt xem, Gỡ / Xoá nháp |
| `/huong-dan` | | chuyển 302 về `?chuyen-muc=huong-dan`; bài `/huong-dan/<slug>` giữ nguyên |

Thư mục www không được có gạch ngang → `www/tin_noi_bo/` + 4 `website_route_rules`.
Mọi trang `no_cache = 1` (cache_html của Frappe lưu theo đường dẫn, dùng chung mọi người).

## Luật (PO chốt)

- Người soạn: System Manager, HR Manager, HR User — đăng thẳng, không bước duyệt.
- Phạm vi theo phòng ban, trống = toàn công ty; phòng cha gồm phòng con (nested set lft/rgt).
  Người ngoài phạm vi mở link vẫn bị chặn (`permissions.has_permission`).
- Không có nút xác nhận: mở bài = đã xem (`EC Read Receipt`, dùng chung `platform/read_receipt.py`).
  Ai cũng thấy con số; tên người CHƯA xem chỉ HR thấy.
- Hết hạn ("Hiện đến ngày"): rút khỏi danh sách + trang chủ, link vẫn mở được.
- Báo tin khi đăng (một lần, sửa bài không gửi lại): chuông cho người trong phạm vi;
  popup trang chủ 7 ngày chỉ cho bài toàn công ty (`home_today/announce_service.py`).
- Ảnh bìa + ảnh trong bài: công khai. Tệp đính kèm: riêng tư, tải được khi đọc được bài.
  Ảnh / tệp phải là File gắn vào CHÍNH bài đó (chặn dán đường dẫn tệp của hồ sơ khác).
- AI tạo ảnh bìa: đọc tiêu đề + tóm tắt + nội dung đang nhập, 3 phương án / lần,
  **tối đa 5 lần / bài / ngày**. Ảnh không được chọn bị xoá sau 3 ngày (job daily).
- Cảm xúc dùng lại `EC Home Reaction` (target `post:<tên>`).

## Lớp

`constants` → `domain` (thuần) → `repository` (chỗ DUY NHẤT chạm DB) → `service` (người đọc) /
`editor_service` (HR) / `cover_ai` / `notify` → `api.py` (whitelist, user lấy từ phiên, trả
`{success, message, data}`) và `www/tin_noi_bo/*.py`. `lifecycle.py` = controller DocType.

Đường chờ "mạng xã hội nội bộ": lượt xem / cảm xúc khoá theo (doctype, tên); bài của nhân viên
sau này là DocType riêng dùng lại `read_receipt`, `announce_service`, hàm phạm vi `domain.in_scope`.

## Test

    python -m unittest ecentric_workspace.internal_posts.tests.test_internal_posts

Chạy thật domain / service / quyền / AI trên repo giả và render 4 trang bằng jinja2.
