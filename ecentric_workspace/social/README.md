# Bảng tin + Câu lạc bộ (`/bang-tin`)

Mạng xã hội nội bộ. PO Hoàn duyệt mockup v2 "Bảng tin + Câu lạc bộ" ngày 04/10/2026.

## Trang

| Đường dẫn | File | Ai vào |
|---|---|---|
| `/bang-tin` (`?loc=tin-hr\|loi-khen\|phong-toi\|clb-cua-toi\|su-kien\|cua-toi`) | `www/bang_tin/index` | Nhân viên Active, HR |
| `/bang-tin/cau-lac-bo` | `www/bang_tin/cau_lac_bo` | như trên |
| `/bang-tin/cau-lac-bo/<slug>` (`?tab=bai-viet\|su-kien\|anh\|thanh-vien`) | `www/bang_tin/clb` | như trên |
| `/bang-tin/bai/<tên>` (link từ chuông) | `www/bang_tin/bai` | người thấy bài |
| `/bang-tin/quan-ly` (`?tab=bao-cao\|da-an\|clb`) | `www/bang_tin/quan_ly` | HR (`MODERATOR_ROLES`) |

## Luật đã chốt

1. Mọi nhân viên Active được đăng bài: chữ, tối đa 6 ảnh, gắn tên, khen đồng nghiệp, "Chỉ phòng tôi". Chống spam: 6 bài / 10 phút.
2. Bài lên thẳng, không chờ duyệt. Ai cũng "Báo cáo bài" được; HR ẩn bài ở `/bang-tin/quan-ly`.
   - Bài bị ẩn chỉ người đăng và HR còn thấy.
   - Bài đang bị báo cáo hoặc đã bị ẩn thì người đăng không tự xoá được.
3. Ảnh luôn là tệp private, xem qua `social.api.image` sau khi kiểm `can_see`. Trình duyệt thu nhỏ ảnh xuống 1600px; server vẽ lại ảnh và bỏ EXIF/GPS.
4. "Chỉ phòng tôi" hiện cho phòng người đăng và các phòng con, cùng luật với Tin nội bộ. Bài loại này không khen / gắn tên được người ở phòng khác.
5. Chuông chỉ gửi khi:
   - được gắn tên;
   - được khen;
   - có bình luận / lời chúc vào bài của mình;
   - CLB mình tham gia có sự kiện mới.

   Event `announcement`: chỉ chuông, không Teams.
6. Câu lạc bộ:
   - Nhân viên đề xuất, HR duyệt một lần. Khi chờ duyệt, người khác bấm "muốn tham gia".
   - Vào CLB tự do. Người phụ trách tạo sự kiện.
   - Bài CLB hiện cả ở Bảng tin chung.
   - Patch `p001_seed_clubs` tạo sẵn 3 CLB (Chạy bộ, Bóng đá, Cầu lông) khi bảng còn trống, chưa có người phụ trách. HR chọn người phụ trách ở tab CLB.
7. Giá trị lời khen (`constants.KUDOS_VALUES`) là **tạm thời**. Thay bằng bộ giá trị thật của công ty khi PO gửi.

## Không double thông tin

Bảng tin chỉ lấy dữ liệu từ module gốc qua `sources.py`. Mỗi loại dữ liệu chỉ có một bản:

| Hiện trên Bảng tin | Lấy từ |
|---|---|
| Tin HR | Thẻ nhúng từ `internal_posts.service.feed_cards`. Tim và bình luận là của chính bài Tin nội bộ. |
| Sinh nhật / bạn mới / kỷ niệm | `home_today.service.people_today`. Tim dùng chung khoá popup (`bd:/ann:/new:`). Lời chúc là bình luận trên bài `kind=moment`, tạo lúc người đầu tiên chúc. |
| Khảo sát | Khảo sát đang mở (`surveys` `respond_service.hub`) hiện ở "Cần bạn" và trong lọc "Sự kiện & khảo sát". |
| Góp ý | Mục "Đã làm" trên bảng chung (`feedback.service.board`). |
| eCentric Hall | Chỉ có link, không làm chat mới. |

Bình luận dùng chung bảng `EC Post Comment` và chung bộ luật `internal_posts/comments.py`:
- Phân biệt loại bài bằng cột mới `ref_doctype`; `post` đổi thành Dynamic Link. Patch `internal_posts.p003` điền giá trị cho dữ liệu cũ.
- Phần riêng của Bảng tin nằm ở `comments_subject.py`.

Chiều ngược lại, popup "Hôm nay ở eCentric" đọc từ Bảng tin qua `sources.popup_events` và `sources.wish_counts`:
- Ô "Sự kiện công ty · Sắp ra mắt" thay bằng sự kiện CLB trong 14 ngày tới.
- Mỗi người được chúc có link "lời chúc trên Bảng tin".

## Quyền

Mọi DocType (`EC Social Post`, `EC Club`, `EC Club Member`, `EC Event RSVP`, `EC Social Report`) chỉ System Manager có quyền, HR Manager được đọc. Không có `has_permission`; mọi đường đọc / ghi đi qua `service.py`, nơi `domain.can_see` quyết định ai thấy bài nào.

## Test

```
python -m unittest ecentric_workspace.social.tests.test_social
```
