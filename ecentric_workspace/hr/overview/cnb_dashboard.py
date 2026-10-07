# Copyright (c) 2026, eCentric and contributors
"""File "Timesheet Thang N Dashboard" cua CnB - xuat thang tu ERP (ec-cnb-dashboard-v1).

07/10/2026 (Hoan): moi thang CnB tu ghep 4 sheet bang tay - xuat Monthly Attendance Sheet,
xuat SLA va Phan bo cong viec tu /tong-quan, tra phong ban tu file "Danh sach nhan su" ngoai,
roi dung dashboard loc theo phong. File nay dung lai DUNG mau do (ten sheet, cot, mau, cong
thuc, o chon phong ban) de CnB khong phai lam tay nua.

Khac file tay (co chu dich):
- Phong ban lay tu ho so nhan vien ERP (Hoan chot 07/10), khong link ra file ngoai.
- Cong thuc dashboard tro dung toi dong cuoi. File tay co o "TONG NGHI PHEP" chi cong 30 dong
  dau (AM2:AM31) nen thang 9 hien 21 thay vi 43 ngay phep; cot ty le chia cho tong co ca
  dong "Tong cong" nen ty le bi nho di mot nua. Ca hai sua o day.

Ham THUAN (chi openpyxl, khong frappe) de test bang python tran. Khong co truong luong nao.
"""
import io

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule, Rule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.styles.differential import DifferentialStyle
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation

ALL = "All Department"
NAVY = "FF1E293B"
LINE = "FFE2E8F0"
ZEBRA = "FFF8FAFC"
OK_GREEN = "FF00B050"
OK_FILL = "FFEBF1DE"   # mau Excel hien that cho dxf cua file tay (theme accent3, tint 0.8)
WO_FILL = "FFFFCCCC"

_thin = Side(style="thin", color=LINE)
BOX = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)
HEAD_FONT = Font(name="Calibri", size=11, bold=True, color="FFFFFFFF")
HEAD_FILL = PatternFill("solid", fgColor=NAVY)
HEAD_ALIGN = Alignment(horizontal="center", vertical="center", wrap_text=True)
BODY = Font(name="Arial", size=11)
BODY_B = Font(name="Arial", size=11, bold=True)

TS_FIXED = ["Phòng ban", "Mã NV", "Họ và Tên", "NV chốt công", "Lead chốt công", "Ca Làm Việc"]
TS_TOTALS = ["Công thực tế (P)", "Lễ (H)", "Phép (L)", "Nghỉ không lương (A)", "TỔNG CÔNG \n(TOTAL PAID DAYS)"]
SLA_HEAD = ["Phòng ban", "Mã NV", "Nhân viên", "Email", "% SLA", "Đúng hạn", "Đã chấm", "Trễ", "Bỏ lỡ",
            "Đang mở", "Đã nghỉ"]
BW_HEAD = ["Phòng ban", "Mã NV", "Nhân viên", "Mã NV", "Trạng thái", "Đang chờ"]
BW_STATUS = {"final": "Đã chốt", "wait_lead": "Chờ lead", "wait_head": "Chờ trưởng phòng",
             "returned": "Bị trả lại", "draft": "Chưa nộp", "none": "Chưa nộp"}
CODES = ("P", "H", "L", "A")


def tag(period):
    """'2026-09' -> 'T09.2026' (hau to ten sheet cua file tay)."""
    return "T%s.%s" % (period[5:7], period[:4])


def filename(period):
    return "Timesheet_Thang_%d_%s_Dashboard.xlsx" % (int(period[5:7]), period[:4])


# ------------------------------------------------------------------ du lieu
def timesheet_rows(result, dept_of):
    """result: (columns, data, ...) cua bao cao Monthly Attendance Sheet (da co 2 cot chot cong).
    dept_of: {employee: ten phong}. -> (nhan ngay ['1 Tue', ...], [dong])."""
    columns, data = (list(result[0] or []), list(result[1] or [])) if result else ([], [])
    days = [c for c in columns if isinstance(c, dict) and _is_day(c.get("fieldname"))]
    out = []
    for d in data:
        if not isinstance(d, dict) or not d.get("employee"):
            continue
        out.append({
            "department": dept_of.get(d["employee"]) or "", "employee": d["employee"],
            "name": d.get("employee_name") or "", "member": d.get("ec_nv_chot_cong") or "",
            "lead": d.get("ec_lead_chot_cong") or "", "shift": d.get("shift") or "",
            "codes": [d.get(c["fieldname"]) or None for c in days],
        })
    return [c.get("label") for c in days], out


def _is_day(f):
    p = str(f or "").split("-")
    return len(p) == 3 and all(x.isdigit() for x in p)


def sla_rows(sla, emp_of_user):
    """sla: ket qua team_summary.build_sla. -> (ten nhom, [dong]) xep theo phong roi ten."""
    groups = sla.get("groups") or []
    out = []
    for dep in sorted(sla.get("departments") or [], key=lambda x: x["label"]):
        for m in sorted(dep["members"], key=lambda x: x["name"] or ""):
            out.append([dep["label"], emp_of_user.get(m["user"]) or "", m["name"], m["user"], m["rate"],
                        m["ontime"], m["scored"], m["late"], m["missed"], m["open"], "x" if m["left"] else ""]
                       + [(m["groups"].get(g["key"]) or {}).get("rate") for g in groups])
    return ["%% %s" % g["label"] for g in groups], out


def brand_rows(bw):
    """bw: ket qua team_summary.build_brand. -> (ten brand, [dong])."""
    brands = bw.get("brands") or []
    out = []
    for dep in sorted(bw.get("departments") or [], key=lambda x: x["label"]):
        for m in sorted(dep["members"], key=lambda x: x["name"] or ""):
            w = m["weights"]
            out.append([dep["label"], m["employee"], m["name"], m["employee"], BW_STATUS.get(m["status"], m["status"]),
                        ", ".join(m["waiting_on"])] + [w.get(b["id"]) for b in brands]
                       + [round(sum(w.values()), 2) if w else None])
    return ["%s (%%)" % b["label"] for b in brands], out


# ------------------------------------------------------------------ ve
def _header(ws, labels, height=None):
    for i, t in enumerate(labels, 1):
        c = ws.cell(1, i, t)
        c.font, c.fill, c.alignment = HEAD_FONT, HEAD_FILL, HEAD_ALIGN
    if height:
        ws.row_dimensions[1].height = height


def _body(ws, rows, left_cols, bold_cols=()):
    for r, vals in enumerate(rows, 2):
        zebra = PatternFill("solid", fgColor=ZEBRA) if r % 2 == 1 else None
        for i, v in enumerate(vals, 1):
            c = ws.cell(r, i, v)
            c.font = BODY_B if i in bold_cols else BODY
            c.border = BOX
            c.alignment = Alignment(horizontal="left" if i in left_cols else "center", vertical="center")
            if zebra:
                c.fill = zebra


def _widths(ws, widths):
    for col, w in widths.items():
        ws.column_dimensions[col].width = w


def _close_rules(ws, last):
    """Hai cot D/E: o "Da chot" to xanh (giong file tay, ap ca cho SLA/% Brand)."""
    green = DifferentialStyle(font=Font(bold=True, color=OK_GREEN), fill=PatternFill(bgColor=OK_FILL))
    r1 = Rule(type="expression", dxf=green, formula=['OR(LEFT($D2, 7)="Đã chốt", $D2="Leader chốt thay")'])
    r2 = Rule(type="expression", dxf=green, formula=['LEFT($E2, 7)="Đã chốt"'])
    ws.conditional_formatting.add("D2:D%d" % last, r1)
    ws.conditional_formatting.add("E2:E%d" % last, r2)


def _wo_rule(ws, first_col, last_col, last):
    ws.conditional_formatting.add(
        "%s2:%s%d" % (first_col, last_col, last),
        FormulaRule(formula=['%s$2="WO"' % first_col], fill=PatternFill(bgColor=WO_FILL)))


def _dup_rule(ws):
    ws.conditional_formatting.add("B1:B1048576", Rule(
        type="duplicateValues", dxf=DifferentialStyle(font=Font(color="FF9C0006"), fill=PatternFill(bgColor="FFFFC7CE"))))


def _timesheet(wb, period, days, rows):
    ws = wb.create_sheet("Timesheet %s" % tag(period))
    ws.sheet_view.zoomScale = 70
    n = len(days)
    first, last_day = L(7), L(6 + n)
    cP, cH, cL, cA, cT = (L(7 + n + i) for i in range(5))
    _header(ws, TS_FIXED + days + TS_TOTALS, 31.5)
    body = []
    for i, x in enumerate(rows, 2):
        rng = "%s%d:%s%d" % (first, i, last_day, i)
        body.append([x["department"], x["employee"], x["name"], x["member"], x["lead"], x["shift"]] + x["codes"] + [
            '=COUNTIF(%s,"P")+COUNTIF(%s,"HD/P")*0.5' % (rng, rng),
            '=COUNTIF(%s,"H")' % rng,
            '=COUNTIF(%s,"L")+COUNTIF(%s,"HD/P")*0.5' % (rng, rng),
            '=COUNTIF(%s,"A")+COUNTIF(%s,"HD/A")*0.5' % (rng, rng),
            "=%s%d+%s%d" % (cP, i, cH, i)])
    _body(ws, body, left_cols={1, 2, 3, 6}, bold_cols={11 + n})
    last = max(len(rows) + 1, 2)
    _widths(ws, {"A": 23.38, "B": 16, "C": 25.88, "D": 22.88, "E": 25.62, "F": 16.5,
                 cP: 13.88, cH: 11.62, cL: 10.75, cA: 18.75, cT: 18.75})
    for k in range(7, 7 + n):
        ws.column_dimensions[L(k)].width = 6
    ws.auto_filter.ref = "A1:%s%d" % (cT, last)
    _close_rules(ws, last)
    _wo_rule(ws, first, cT, last)
    return ws.title, last, (cP, cH, cL, cA)


def _sla(wb, period, groups, rows):
    ws = wb.create_sheet("SLA %s" % tag(period))
    ws.sheet_view.zoomScale = 85
    ws.freeze_panes = "A2"
    head = SLA_HEAD + groups
    _header(ws, head)
    _body(ws, rows, left_cols={1, 2, 3}, bold_cols={5})
    last = max(len(rows) + 1, 2)
    _widths(ws, {"A": 23.38, "B": 16, "C": 25.88, "D": 24.75, "E": 10.88, "F": 10.88, "G": 10.88, "H": 10.88,
                 "I": 10.88, "J": 11.75, "K": 11.75})
    for k in range(12, len(head) + 1):
        ws.column_dimensions[L(k)].width = 18 if k == 12 else 14.5
    ws.auto_filter.ref = "A1:%s%d" % (L(len(head)), last)
    _dup_rule(ws)
    _close_rules(ws, last)
    ws.conditional_formatting.add("E2:E1048576", CellIsRule(
        operator="greaterThanOrEqual", formula=["90"], font=Font(bold=True, color=OK_GREEN),
        fill=PatternFill(bgColor=OK_FILL)))


def _brand(wb, period, brands, rows):
    ws = wb.create_sheet("% Brand")
    ws.sheet_view.zoomScale = 70
    head = BW_HEAD + brands + ["Tổng (%)"]
    _header(ws, head, 75)
    _body(ws, rows, left_cols={1, 2, 3, 6})
    last = max(len(rows) + 1, 2)
    _widths(ws, {"A": 23.38, "B": 16, "C": 25.88, "D": 22.88, "E": 25.62, "F": 27.38})
    for k in range(7, len(head)):
        ws.column_dimensions[L(k)].width = 6
    ws.column_dimensions[L(len(head))].width = 11.5
    ws.auto_filter.ref = "A1:%s%d" % (L(len(head)), last)
    _dup_rule(ws)
    _close_rules(ws, last)
    if len(head) >= 7:
        _wo_rule(ws, "G", L(len(head)), last)


def _overview(ws, period, sheet, last, cols, departments):
    cP, cH, cL, cA = cols
    ws.sheet_view.zoomScale = 160
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = 9   # A4, nhu file tay
    _widths(ws, {"A": 3, "B": 22, "C": 22, "D": 22, "E": 22, "F": 22, "G": 18, "H": 24, "I": 20})
    for r, h in {2: 14.25, 5: 15, 8: 26.25, 12: 15, 13: 15, 14: 15, 15: 15, 16: 15, 17: 15}.items():
        ws.row_dimensions[r].height = h
    mid = Alignment(horizontal="center", vertical="center")

    ws.merge_cells("B2:F3")
    c = ws["B2"]
    c.value = "BÁO CÁO TỔNG QUAN CHẤM CÔNG THÁNG %d/%s" % (int(period[5:7]), period[:4])
    c.font, c.fill, c.alignment = Font(name="Calibri", size=18, bold=True, color="FFFFFFFF"), HEAD_FILL, mid
    ws["C4"] = "eCentric HR Management | Cập nhật tự động & Lọc theo phòng ban"
    ws["C4"].font = Font(name="Calibri", size=10, italic=True, color="FF64748B")

    amber = Side(style="medium", color="FFF5A623")
    ws["B5"] = "🔍 CHỌN PHÒNG BAN:"
    ws["B5"].font = Font(name="Calibri", size=11, bold=True, color=NAVY)
    ws["B5"].alignment = Alignment(horizontal="right", vertical="center")
    ws["C5"] = ALL
    ws["C5"].font = Font(name="Calibri", size=11, bold=True, color=NAVY)
    ws["C5"].fill = PatternFill("solid", fgColor="FFFEF3C7")
    ws["C5"].alignment = mid
    ws["C5"].border = Border(left=amber, right=amber, top=amber, bottom=amber)
    ws.merge_cells("D5:F5")
    ws["D5"] = "👈 Bấm để lọc dữ liệu Dashboard theo Phòng Ban"
    ws["D5"].font = Font(name="Calibri", size=9, italic=True, color="FF64748B")
    ws["D5"].alignment = Alignment(horizontal="left")
    ws["D5"].border = Border(left=amber)

    opts = [ALL] + sorted({d for d in departments if d})
    joined = ",".join(o.replace(",", " ") for o in opts)
    if len(joined) <= 250:
        dv = DataValidation(type="list", formula1='"%s"' % joined, allow_blank=True)
    else:   # Excel gioi han 255 ky tu cho danh sach viet thang: ghi ra cot an K
        for i, o in enumerate(opts, 1):
            ws.cell(i, 11, o)
        ws.column_dimensions["K"].hidden = True
        dv = DataValidation(type="list", formula1="=$K$1:$K$%d" % len(opts), allow_blank=True)
    ws.add_data_validation(dv)
    dv.add("C5")

    rng = lambda col: "'%s'!%s2:%s%d" % (sheet, col, col, last)   # noqa: E731
    dep = rng("A")

    def total(col, sel="C5"):
        return '=IF(%s="%s", SUM(%s), SUMIF(%s, %s, %s))' % (sel, ALL, rng(col), dep, sel, rng(col))

    cards = [
        ("B", "TỔNG NHÂN SỰ", '=IF(C5="%s", COUNTA(%s), COUNTIF(%s, C5))' % (ALL, rng("B"), dep),
         "FFF1F5F9", NAVY),
        ("C", "TỔNG CÔNG THỰC TẾ (P)", total(cP), "FFECFDF5", "FF059669"),
        ("D", "TỔNG NGHỈ LỄ (H)", total(cH), "FFFEF2F2", "FFDC2626"),
        ("E", "TỔNG NGHỈ PHÉP (L)", total(cL), "FFFFFBEB", "FFD97706"),
        ("F", "TỔNG NGHỈ KHÔNG LƯƠNG (A)", total(cA), "FFF8FAFC", "FF475569"),
    ]
    for col, label, formula, bg, fg in cards:
        fill = PatternFill("solid", fgColor=bg)
        for r, v, font in ((7, label, Font(name="Calibri", size=9, bold=True, color="FF475569")),
                           (8, formula, Font(name="Calibri", size=20, bold=True, color=fg)),
                           (9, "Tự động nhảy số theo lọc", Font(name="Calibri", size=8, italic=True, color="FF94A3B8"))):
            c = ws["%s%d" % (col, r)]
            c.value, c.font, c.fill, c.alignment, c.border = v, font, fill, mid, BOX

    for col, t in zip("BCDE", ["Loại Công / Trạng Thái", "Mã Ký Hiệu", "Tổng Số Lượng", "Tỷ Lệ (%)"]):
        c = ws["%s12" % col]
        c.value, c.font, c.fill, c.alignment = t, HEAD_FONT, HEAD_FILL, Alignment(horizontal="center")
    lines = [("Công thực tế", "P_ Present", cP), ("Nghỉ Lễ", "H_ Holiday", cH),
             ("Nghỉ Phép", "L_ Leave", cL), ("Nghỉ không lương", "A _ Absent", cA)]
    for r, (label, code, col) in enumerate(lines, 13):
        _row(ws, r, label, code, total(col, "$C$5"))
    _row(ws, 17, "Tổng công", "Total", "=D13+D14+D15")
    for r in range(13, 18):
        # Ty le tren tong cac loai ngay (P+H+L+A). File tay chia cho ca dong Tong cong -> nho mot nua.
        ws["E%d" % r] = "=IF(SUM(D$13:D$16)=0,0,D%d/SUM(D$13:D$16))" % r
        ws["E%d" % r].number_format = "0.0%"
    for r in range(15, 23):
        for col in "GHI":
            ws["%s%d" % (col, r)].border = BOX


def _row(ws, r, label, code, formula):
    mid = Alignment(vertical="center")
    for col, v, h, f in (("B", label, "left", BODY), ("C", code, "center", BODY),
                         ("D", formula, "right", BODY_B), ("E", None, "right", BODY)):
        c = ws["%s%d" % (col, r)]
        if v is not None:
            c.value = v
        c.font, c.border = f, BOX
        c.alignment = Alignment(horizontal=h, vertical=mid.vertical)


def build(period, days, ts_rows, sla_groups, sla, bw_brands, bw):
    """-> bytes cua file .xlsx 4 sheet giong file tay cua CnB. Mo file la vao ngay sheet Tong Quan."""
    wb = Workbook()
    overview = wb.active
    overview.title = "Tổng Quan"
    sheet, last, cols = _timesheet(wb, period, days, ts_rows)
    _sla(wb, period, sla_groups, sla)
    _brand(wb, period, bw_brands, bw)
    _overview(overview, period, sheet, last, cols, [r["department"] for r in ts_rows])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
