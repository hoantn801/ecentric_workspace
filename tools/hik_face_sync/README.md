# Máy chấm công khuôn mặt Hikvision → ERP

Áp dụng cho DS-K1T341CMFW, và các máy MinMoe khác hỗ trợ ISAPI. Mã phiên bản: `ec-face-checkin-v1`.

Mỗi lượt quét mặt thành công sẽ thành một **Employee Checkin** trên ERP. Quy tắc giống hệt chấm công trên web:

- Lượt quét đầu tiên trong ngày là `IN`, các lượt sau là `OUT`.
- Lượt đầu tiên trước hoặc đúng 10:00 thì được tạo ngày công `Present`. Không tạo nếu ngày đó là ngày nghỉ, có phép đã duyệt, hoặc đã có ngày công.

Dữ liệu từ máy lên ERP đi theo hai đường, có thể dùng song song:

| Đường | Khi nào chạy | Cần gì |
|---|---|---|
| **Máy tự đẩy** (HTTP Listening) | Ngay lúc quét | Máy ra được internet |
| **Nút đồng bộ** (thư mục này) | CnB bấm, ví dụ cuối tháng trước khi chốt công | Một laptop Windows đang dùng mạng văn phòng |

Một lượt quét đã có trên ERP thì ERP bỏ qua, nên chạy cả hai đường hay bấm đồng bộ nhiều lần cũng không bị trùng. Tháng đã chốt công thì ERP không ghi thêm gì.

## 1. ERP: thêm cấu hình site

Thêm vào Frappe Cloud → Site → **Site Config**. Mỗi token là một chuỗi ngẫu nhiên dài. Tạo bằng lệnh PowerShell sau:
`-join ((48..57)+(97..122) | Get-Random -Count 40 | % {[char]$_})`

| Khoá | Ý nghĩa |
|---|---|
| `ec_face_push_token` | Mã để máy tự đẩy lên. Mã này nằm trên URL (bước 2). |
| `ec_face_sync_token` | Mã cho nút đồng bộ. CnB nhập một lần trên laptop. |
| `ec_face_checkin_disabled` | (tuỳ chọn) Đặt `1` để tạm ngừng ghi. Máy vẫn nhận phản hồi 200 nên không gửi dồn lại. |
| `ec_face_pass_minors` | (tuỳ chọn) Danh sách mã sự kiện được tính là chấm công. Mặc định `[1, 38, 75]` (thẻ, vân tay, khuôn mặt). |

Chưa đặt token nào thì đường tương ứng bị khoá và ERP trả lỗi 403.

## 2. Máy chấm công: cài đặt một lần

1. **Mạng:** đặt IP tĩnh trong mạng LAN văn phòng.
2. **Giờ:** chọn múi giờ GMT+07:00 và bật NTP. Giờ máy sai thì giờ công sai theo.
3. **Mã nhân viên:** khi đăng ký mặt, nhập ô *Employee No.* bằng **phần số của mã nhân viên**. Ví dụ HR-EMP-00070 thì nhập `70` hoặc `00070`, ERP tự khớp.
   - Nếu dùng mã khác, Nhân sự điền mã đó vào ô *Attendance Device ID* trong hồ sơ nhân viên trên ERP.
4. **Máy tự đẩy:** vào web của máy, tìm mục *HTTP Listening* (thường nằm trong Cấu hình → Mạng → Cài đặt nâng cao) và điền:
   - Địa chỉ / tên miền: `team.ecentric.vn`
   - URL: `/api/method/ecentric_workspace.hr.face_device.api.push?k=<ec_face_push_token>&d=VP`
   - Cổng: `443`
   - Giao thức: `HTTPS`

   Thử quét một lần, rồi xem mục Employee Checkin trên ERP để chắc lượt quét đã lên.

## 3. Nút đồng bộ cho CnB

1. Chép cả thư mục này về laptop CnB.
2. Mở bằng cách bấm đúp **`Dong bo cham cong.bat`** khi laptop đang dùng Wi-Fi văn phòng.
3. Lần đầu chạy, máy hỏi:
   - IP máy chấm công
   - tài khoản máy chấm công
   - mã `ec_face_sync_token`

   Mật khẩu được mã hoá bằng tài khoản Windows đang dùng và lưu trong `bi-mat.dat`.
4. Khi được hỏi tháng, Enter là chọn tháng hiện tại, hoặc gõ ví dụ `2026-09`.
5. Kết quả hiện số lượt được thêm mới, số lượt ERP đã có sẵn, và các mã trên máy chưa gắn nhân viên.

Các tuỳ chọn thêm:

- `-ChiXem`: chỉ đọc máy và đếm theo loại sự kiện. Nên dùng một lần khi mới lắp máy, để kiểm tra mã khuôn mặt có đúng là `major 5 / minor 75` không.
- `-CaiDatLai`: nhập lại IP, mật khẩu hoặc mã ERP.

Nhật ký chạy được ghi ở `nhat-ky.txt`.

## Lưu ý

- **Nên bấm đồng bộ trước khi chốt công.** Tháng đã chốt thì lượt bổ sung sẽ bị bỏ qua.
- **Nút đồng bộ chỉ để vá chỗ thiếu.** Nếu máy không tự đẩy lên được, nhân viên vẫn bị nhắc "chưa chấm công" trong tháng, và điểm SLA chấm công của những ngày đó không tự sửa lại khi đồng bộ bù. Phần máy tự đẩy phải chạy ổn hằng ngày.
