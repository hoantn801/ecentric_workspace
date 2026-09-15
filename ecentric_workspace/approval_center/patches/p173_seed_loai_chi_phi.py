# Copyright (c) 2026, eCentric and contributors
"""Gieo 27 dong danh muc `EC Loai Chi Phi` (09/09/2026, Hoan).

Schema cua DocType di theo `hooks.fixtures`; RIENG cac dong danh muc thi khong de o fixtures,
vi fixtures dong bo DB TU FILE moi lan migrate - Finance sua ten hay them muc tren site se bi
ghi de. Patch nay CHI TAO DONG CON THIEU (khoa theo `ma`) va khong bao gio dung vao dong da co.

Vi the mot bench moi van co du danh muc de form de nghi thanh toan hoat dong (`ec_loai_chi_phi`
la truong bat buoc), con production thi giu nguyen moi chinh sua cua Finance.

Nhom quyet dinh cach PnL doc khoan chi:
  Truc tiep khach hang / Van hanh cong ty  -> cong vao chi phi
  Luong & nhan su                          -> "da co trong khoi luong" thi KHONG cong lai
  Khong tinh vao chi phi                   -> tam ung, chi ho brand, ky quy, tra no goc
"""
import frappe

_ROWS = (
    ("TT_KOL", "Booking KOL / KOC", "Trực tiếp khách hàng", 1, 1, 10,
     "Trả phí cho KOL/KOC booking cho brand khách hàng."),
    ("TT_LIVE", "Chi phí livestream (host, studio, đạo cụ)", "Trực tiếp khách hàng", 1, 1, 20,
     "Thuê host, thuê studio, đạo cụ, setup phiên live."),
    ("TT_SAMPLE", "Hàng mẫu, quà tặng, hàng livestream", "Trực tiếp khách hàng", 1, 1, 30,
     "Mua hàng mẫu, quà tặng, hàng dùng cho phiên live."),
    ("TT_ADS", "Ngân sách quảng cáo chạy cho brand", "Trực tiếp khách hàng", 1, 1, 40,
     "Tiền ads eCentric ứng chạy cho brand. Nếu sau đó thu lại của brand thì chọn 'Chi hộ brand rồi thu lại'."),
    ("TT_AFF", "Hoa hồng affiliate / cộng tác viên bán hàng", "Trực tiếp khách hàng", 1, 1, 50,
     "Hoa hồng trả cho affiliate, cộng tác viên bán hàng."),
    ("TT_CONTENT", "Sản xuất nội dung (photo, video, model, thiết bị)", "Trực tiếp khách hàng", 1, 1, 60,
     "Chụp ảnh, quay video, thuê model, thuê thiết bị sản xuất."),
    ("TT_OUTSOURCE", "Thuê ngoài / freelancer theo dự án", "Trực tiếp khách hàng", 1, 1, 70,
     "Thuê đơn vị ngoài hoặc freelancer làm cho một dự án của khách."),
    ("TT_LOGISTICS", "Vận chuyển, đóng gói, giao nhận", "Trực tiếp khách hàng", 1, 1, 80,
     "Cước vận chuyển, vật tư đóng gói, phí giao nhận."),
    ("VH_OFFICE", "Thuê văn phòng, điện nước, phí quản lý", "Vận hành công ty", 1, 0, 110,
     "Tiền thuê mặt bằng, điện, nước, phí quản lý toà nhà."),
    ("VH_SOFTWARE", "Phần mềm, công cụ, AI, bản quyền", "Vận hành công ty", 1, 0, 120,
     "SaaS, licence, tài khoản AI (AI Topup cũng thuộc mục này)."),
    ("VH_ASSET", "Mua sắm thiết bị & tài sản", "Vận hành công ty", 1, 0, 130,
     "Laptop, màn hình, máy quay, nội thất. Khấu hao sẽ đấu nối sau."),
    ("VH_TELECOM", "Internet, điện thoại, cước", "Vận hành công ty", 1, 0, 140,
     "Cước internet, điện thoại, data."),
    ("VH_SUPPLIES", "Văn phòng phẩm, ăn uống, tiếp khách", "Vận hành công ty", 1, 0, 150,
     "Văn phòng phẩm, nước uống, ăn trưa chung, tiếp khách."),
    ("VH_TRAVEL", "Đi lại, công tác", "Vận hành công ty", 1, 0, 160,
     "Vé, khách sạn, taxi, phụ cấp công tác."),
    ("VH_MARKETING", "Marketing & thương hiệu eCentric", "Vận hành công ty", 1, 0, 170,
     "Marketing cho chính eCentric, không phải cho brand khách."),
    ("VH_PROFESSIONAL", "Pháp lý, kế toán, kiểm toán, tư vấn", "Vận hành công ty", 1, 0, 180,
     "Phí luật sư, kế toán ngoài, kiểm toán, tư vấn."),
    ("VH_HR", "Tuyển dụng & đào tạo", "Vận hành công ty", 1, 0, 190,
     "Đăng tin tuyển dụng, phí headhunt, khoá đào tạo."),
    ("VH_BANK", "Phí ngân hàng, lãi vay", "Vận hành công ty", 1, 0, 200,
     "Phí chuyển tiền, phí tài khoản, lãi vay (không gồm nợ gốc)."),
    ("VH_TAX", "Thuế, phí, lệ phí", "Vận hành công ty", 1, 0, 210,
     "Thuế môn bài, lệ phí nhà nước. KHÔNG gồm thuế TNCN của nhân viên."),
    ("VH_EVENT", "Sự kiện nội bộ, phúc lợi tập thể", "Vận hành công ty", 1, 0, 220,
     "Team building, sinh nhật công ty, tiệc nội bộ."),
    ("VH_OTHER", "Chi phí vận hành khác", "Vận hành công ty", 1, 0, 290,
     "Dùng khi không có mục nào đúng — nên hạn chế."),
    ("LG_TRONG_KHOI", "Lương / thưởng đã có trong khối lương", "Lương & nhân sự", 0, 0, 310,
     "Chọn mục này khi phiếu chi là lương, thưởng, phụ cấp đã nằm trong bảng lương. PnL KHÔNG cộng lại để không đếm trùng."),
    ("LG_NGOAI_KHOI", "Chi phí nhân sự khác (ngoài bảng lương)", "Lương & nhân sự", 1, 0, 320,
     "Trợ cấp thôi việc, phúc lợi trả tiền mặt ngoài bảng lương — khoản này PnL có cộng."),
    ("KT_TAMUNG", "Tạm ứng / hoàn ứng", "Không tính vào chi phí", 0, 0, 410,
     "Tiền ứng trước rồi hoàn lại — không phải chi phí của kỳ."),
    ("KT_CHIHO", "Chi hộ brand rồi thu lại", "Không tính vào chi phí", 0, 1, 420,
     "eCentric chi hộ và sẽ thu lại của brand — tiền ra nhưng không phải chi phí của mình."),
    ("KT_KYQUY", "Ký quỹ, đặt cọc", "Không tính vào chi phí", 0, 0, 430,
     "Tiền cọc thuê nhà, ký quỹ hợp đồng — sẽ lấy lại."),
    ("KT_TRANO", "Trả nợ gốc vay", "Không tính vào chi phí", 0, 0, 440,
     "Trả gốc khoản vay. Lãi vay thì chọn 'Phí ngân hàng, lãi vay'."),
)


def execute():
    if not frappe.db.exists("DocType", "EC Loai Chi Phi"):
        frappe.log_error("p173: chua co DocType EC Loai Chi Phi - bo qua", "p173 seed")
        return
    created = 0
    for row in _ROWS:
        ma = row[0]
        if frappe.db.exists("EC Loai Chi Phi", ma):
            continue
        try:
            doc = frappe.get_doc({"doctype": "EC Loai Chi Phi", "ma": ma, "ten": row[1],
                                  "nhom": row[2], "tinh_vao_chi_phi": row[3],
                                  "can_brand": row[4], "thu_tu": row[5], "goi_y": row[6]})
            doc.insert(ignore_permissions=True)
            created = created + 1
        except Exception:
            # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
            frappe.log_error(frappe.get_traceback(), "p173 seed %s" % ma)
    if created:
        frappe.db.commit()
    frappe.log_error("p173: tao moi %d / %d dong danh muc" % (created, len(_ROWS)), "p173 seed")
