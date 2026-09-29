# home_today — popup "Hôm nay ở eCentric" + trang trí ngày sinh nhật

PO Hoàn chốt 29/09/2026. Brief: `ERP Website/NHIEU_LOP/brief_popup_su_kien.md`.
Đặc tả giao diện (PO duyệt): `C:\dev\home-popup-su-kien\v3_ban_chot\popup_hom_nay_mockup_v3_chot.html`.

## Popup (trang chủ, `public/js/ec_home_popup.js`)
Slider "ảnh phủ kín": trái tối đa 6 ô, phải khung ảnh lớn + nội dung. Ô rỗng thì ẩn.

| Ô | Nguồn |
|---|---|
| Thông báo | DocType **`EC Home Announcement`** (Thông báo trang chủ). "Chỉ ảnh (hiện full)" → mỗi thông báo một ô riêng, ảnh phủ kín |
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

## Thêm thông báo lên popup (tính năng mới, chính sách, sự kiện, poster)
ERP → gõ **EC Home Announcement** vào ô tìm (hoặc mở `/app/ec-home-announcement/new`). Quyền: System Manager, HR Manager, HR User.

- **Tiêu đề**, **Loại** (Tính năng mới / Module mới / Chính sách / Sự kiện / Thông báo), **Hiện từ ngày / đến ngày** (trống = 7 ngày), tích **Đăng lên popup**.
- **Cách hiện = Ảnh + nội dung:** gộp vào ô "Thông báo"; ảnh (nếu có) làm ảnh bìa; Tóm tắt hiện ngay, Nội dung chi tiết mở bằng "Xem chi tiết"; Đường dẫn + Chữ trên nút (vd `/ec-hr/attendance` · "Dùng thử ngay").
- **Cách hiện = Chỉ ảnh (hiện full):** chỉ cần Tiêu đề + Ảnh. Thông báo thành một ô riêng, ảnh phủ kín khung phải (nền là chính ảnh làm mờ), bấm ảnh mở ảnh gốc. Ảnh ngang ~1600×900 đẹp nhất.
- Ảnh tải lên ở form này luôn là tệp công khai. Lưu/xoá → popup cập nhật ngay (xoá cache).
