# Copyright (c) 2026, eCentric and contributors
"""Bang tinh tung buoc cho Ke toan soat (PO 12/11): moi dong = (khoan, cach tinh, so tien).

Chi DIEN GIAI so da luu tren phieu (gross_amount, pit_amount, vat_amount, payable_amount,
advance_amount) - khong tinh lai bang cong thuc khac, de bang luon khop so in tren hop dong.
Cong thuc chu viet theo dung thu tu cua kol.compute_amounts / kol_values.round_money.
"""
from ecentric_workspace.approval_center.features.contract_review.domain import kol
from ecentric_workspace.approval_center.features.contract_review.domain import kol_texts as T


def _n(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _m(v):
    return "{:,.0f}".format(T.round_half_up(_n(v))).replace(",", ".")


def _pct(v):
    x = _n(v)
    return ("%g" % x).replace(".", ",") + "%"


def _row(label, how, amount, strong=False):
    return {"label": label, "how": how, "amount": T.round_half_up(_n(amount)), "strong": bool(strong)}


def contract_steps(doc):
    """Bang tinh cua ca hop dong. [] khi phieu chua co so tien."""
    get = doc.get
    at, ct = get("amount_type"), get("creator_type")
    g, p, v, pay = _n(get("gross_amount")), _n(get("pit_amount")), _n(get("vat_amount")), _n(get("payable_amount"))
    if not (at and pay):
        return []
    pr, vr = get("pit_rate"), get("vat_rate")
    rows = []
    if at == kol.NET_AFTER_PIT:
        rows += [_row("Thực nhận (số nhập)", "", pay),
                 _row("Giá trị trước thuế (gross)", "%s ÷ (1 − %s)" % (_m(pay), _pct(pr)), g, True),
                 _row("Thuế TNCN %s (eCentric khấu trừ, nộp thay)" % _pct(pr), "%s − %s" % (_m(g), _m(pay)), p)]
    elif at == kol.GROSS_BEFORE_PIT:
        rows += [_row("Giá trị trước thuế (gross, số nhập)", "", g, True),
                 _row("Thuế TNCN %s (eCentric khấu trừ, nộp thay)" % _pct(pr), "%s × %s" % (_m(g), _pct(pr)), p),
                 _row("Thực nhận", "%s − %s" % (_m(g), _m(p)), pay)]
    elif at == kol.BEFORE_VAT:
        rows += [_row("Giá trước VAT (số nhập)", "", g, True),
                 _row("VAT %s" % _pct(vr), "%s × %s" % (_m(g), _pct(vr)), v),
                 _row("Tổng thanh toán (hóa đơn)", "%s + %s" % (_m(g), _m(v)), pay)]
    elif at == kol.WITH_VAT:
        rows += [_row("Tổng thanh toán (hóa đơn, số nhập)", "", pay),
                 _row("Giá trước VAT", "%s ÷ (1 + %s)" % (_m(pay), _pct(vr)), g, True),
                 _row("VAT %s" % _pct(vr), "%s − %s" % (_m(pay), _m(g)), v)]
    else:
        rows += [_row("Tổng thanh toán (hộ kinh doanh tự kê khai thuế)", "", pay, True)]
    adv = _n(get("advance_amount"))
    if adv:
        base, what = (g, "giá trước VAT") if ct == "Công ty" else (pay, "thực nhận")
        rows += [_row("Cọc %s trên %s" % (_pct(get("advance_percent")), what),
                      "%s × %s" % (_m(base), _pct(get("advance_percent"))), adv),
                 _row("Còn lại trả sau nghiệm thu" + (" (gồm toàn bộ VAT)" if ct == "Công ty" else ""),
                      "%s − %s" % (_m(pay), _m(adv)), pay - adv)]
    rows.append(_row("Chi phí eCentric (giá trị hợp đồng)",
                     "%s + %s" % (_m(g), _m(v)) if v else "= giá trị trước thuế", g + v, True))
    return rows


def round_steps(creator_type, amount, pit_rate, vat_rate, doc):
    """Bang tinh cua MOT dot nghiem thu (so tra creator cua dot -> so in tren BBNT)."""
    from ecentric_workspace.approval_center.features.contract_review.domain import kol_values as V
    m = V.round_money(creator_type, amount, pit_rate, vat_rate, doc)
    pay = m["total"] if creator_type in ("Công ty", "Hộ kinh doanh") else m["net"]
    if creator_type == "Cá nhân":
        pr = 10 if pit_rate in (None, "") else pit_rate
        return [_row("Thực nhận đợt này", "", m["net"]),
                _row("Giá trị trước thuế (gross)", "%s ÷ (1 − %s)" % (_m(m["net"]), _pct(pr)), m["gross"], True),
                _row("Thuế TNCN %s" % _pct(pr), "%s − %s" % (_m(m["gross"]), _m(m["net"])), m["gross"] - m["net"])]
    if creator_type == "Công ty":
        if _n(doc.get("advance_amount")):
            rest_pre = _n(doc.get("gross_amount")) - _n(doc.get("advance_amount"))
            rest = _n(doc.get("payable_amount")) - _n(doc.get("advance_amount"))
            how = "%s (trước VAT còn lại) × %s ÷ %s (còn lại)" % (_m(rest_pre), _m(pay), _m(rest))
        else:
            how = "%s ÷ (1 + %s)" % (_m(pay), _pct(8 if vat_rate in (None, "") else vat_rate))
        return [_row("Tổng thanh toán đợt này", "", pay),
                _row("Giá trước VAT", how, m["pre_vat"], True),
                _row("VAT", "%s − %s" % (_m(pay), _m(m["pre_vat"])), m["vat"])]
    return [_row("Tổng thanh toán đợt này (hộ kinh doanh)", "", pay, True)]
