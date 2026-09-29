# home_today — popup "Hôm nay ở eCentric" + trang trí ngày sinh nhật

PO Hoàn chốt 29/09/2026. Brief: `ERP Website/NHIEU_LOP/brief_popup_su_kien.md`.
Đặc tả giao diện (PO duyệt): `C:\dev\home-popup-su-kien\v3_ban_chot\popup_hom_nay_mockup_v3_chot.html`.

## Popup (trang chủ, `public/js/ec_home_popup.js`)
Slider "ảnh phủ kín": trái tối đa 6 ô, phải khung ảnh lớn + nội dung. Ô rỗng thì ẩn.

| Ô | Nguồn |
|---|---|
| Thông báo | News Post tích **Đưa lên popup trang chủ** (`ec_show_in_popup`, hạn `ec_popup_until`, trống = 7 ngày) + Company Policy mới có hiệu lực ≤ 7 ngày (tự lên) |
| Sinh nhật | Employee Active: hôm nay + 7 ngày tới, **chỉ ngày/tháng** |
| Bạn mới | `welcome_today()` của chat HR (từ 08:30, kill switch `ec_onboard_welcome_disabled`) |
| Sự kiện công ty | "Sắp ra mắt" (chưa có dữ liệu) |
| Nghỉ lễ sắp tới | Holiday List của người xem (Employee → Company default), bỏ ngày nghỉ tuần |
| Kỷ niệm gắn bó | Employee.date_of_joining tròn năm hôm nay |

Hiện mỗi lần mở trang chủ khi có nội dung; "Không hiện lại hôm nay" nhớ trong trình duyệt,
có mục mới trong ngày thì hiện lại. Thả cảm xúc ❤️🌸🎂🎉 lưu ở DocType `EC Home Reaction`.

## Trang trí trang chủ (Jinja `home_today_celebration`, vẽ sẵn trong markup)
Ngày có sinh nhật: cả công ty **Nhẹ** (dây cờ + nhãn) · cùng phòng ban **Vừa** (+ bóng bay, lấp lánh)
· chính người sinh nhật **Rực rỡ** (+ dải navy lễ hội, pháo giấy, ruy băng). Tất cả là lớp nổi.

## Cấu trúc
`domain.py` (tính toán thuần, test không cần bench) → `repository.py` (mọi truy vấn DB) →
`service.py` (ghép theo người dùng phiên, repo tiêm được) → `api.py` (whitelist, không nhận `user`) /
`jinja.py` (hàm trang chủ, không bao giờ ném lỗi).

## Thêm thông báo lên popup
Vào Desk → News Post → tạo tin, **Published**, tích **Đưa lên popup trang chủ**, (tuỳ) chọn ngày hết.
Loại `MODULE MỚI` hiện nhãn xanh, `CHÍNH SÁCH` nhãn navy, còn lại "Thông báo". Ảnh bìa: trường Image
(file công khai `/files/...`). Chính sách: tạo Company Policy với ngày hiệu lực, không cần tích.
Dữ liệu dùng chung cache 10 phút.
