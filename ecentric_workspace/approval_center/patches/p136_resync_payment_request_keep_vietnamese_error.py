# Copyright (c) 2026, eCentric and contributors
"""`mapErr` nuot MOI cau tieng Viet co chu "quyen" va thay bang mot cau chung vo nghia.

03/09 chi Hien bam "Gui yeu cau". May chu tra ve dung cau can biet:

    PermissionError: "Bạn chưa được cấp quyền ký số (UAT allowlist)."

Man hinh hien: "Bạn không còn quyền thực hiện hành động này." - chi vi luat nay:

    if(/access|permission|allowed|quyền/i.test(m)) return "Bạn không còn quyền ...";

Hai cau dan toi hai hanh dong khac han. Cau that: "nho quan tri them ban vao danh sach ky
so" - lam duoc ngay. Cau hien ra: "ban vua mat quyen" - khong lam gi duoc, va sai su that.

Mat 20 phut truy nguoc moi ra, va phai lay traceback tu phien cua chinh chi Hien. Nguoi dung
binh thuong thi khong truy duoc gi ca - ho chi thay he thong tu choi ma khong noi ly do.

Luat do sinh ra de che thong diep KY THUAT tieng Anh ("access denied", "not permitted") -
thu nguoi dung khong doc duoc. Nhung no khong phan biet duoc voi cau TIENG VIET ma chinh
minh viet cho nguoi dung doc. Gio chi che khi thong diep khong co dau tieng Viet.

CON LAI, CHUA SUA: 24 form khac deu co y nguyen luat nay (cung mot doan chep di chep lai).
Gom thanh mot dot rieng - moi trang la mot patch resync, va sua 25 trang cung luc luc cuoi
mot dot dai la cach tao loi moi. Loi goc la 25 ban sao cua cung mot ham xu ly loi; huong
dung la mot helper chung trong public/js.

Patch moi vi p133 da chay - patch chay MOT LAN.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
