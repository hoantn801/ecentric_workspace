# Copyright (c) 2026, eCentric and contributors
"""Doc so tien thanh chu tieng Viet cho hop dong ("Ba mươi triệu đồng chẵn").

Thuan Python, khong goi frappe. Quy tac doc theo cach van ban hanh chinh thuong viet:
  - "lẻ" khi hang chuc = 0 va hang don vi != 0 (105 -> một trăm lẻ năm)
  - "mốt" cho don vi 1 khi hang chuc >= 2 (21 -> hai mươi mốt), "mười một" giu nguyen
  - "lăm" cho don vi 5 khi hang chuc >= 1 (15 -> mười lăm, 25 -> hai mươi lăm)
  - nhom 3 chu so dung giua (1.005.000) doc du "không trăm"
"""
_DIGITS = ("không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín")


def _three(n, full):
    """Doc mot nhom 0..999. `full` = nhom nay khong dung dau so (can doc 'không trăm')."""
    hundred, rest = divmod(n, 100)
    ten, one = divmod(rest, 10)
    words = []
    if hundred or full:
        words += [_DIGITS[hundred], "trăm"]
    if ten > 1:
        words += [_DIGITS[ten], "mươi"]
        if one == 1:
            words.append("mốt")
        elif one == 5:
            words.append("lăm")
        elif one:
            words.append(_DIGITS[one])
    elif ten == 1:
        words.append("mười")
        if one == 5:
            words.append("lăm")
        elif one:
            words.append(_DIGITS[one])
    elif one:
        if hundred or full:
            words.append("lẻ")
        words.append(_DIGITS[one])
    return words


def _below_billion(n, full_first):
    """Doc 0 < n < 1e9. Nhom dung sau mot nhom lon hon thi doc du ('không trăm', 'lẻ')."""
    words, first = [], True
    for unit, size in (("triệu", 10 ** 6), ("nghìn", 10 ** 3), ("", 1)):
        g, n = divmod(n, size)
        if not g:
            continue
        words += _three(g, full=(full_first or not first))
        if unit:
            words.append(unit)
        first = False
    return words


def number_to_words(n):
    """Doc so nguyen thanh chu (khong viet hoa, khong 'đồng')."""
    n = int(round(float(n or 0)))
    if n < 0:
        return "âm " + number_to_words(-n)
    if n == 0:
        return "không"
    if n < 10 ** 9:
        return " ".join(_below_billion(n, False))
    hi, lo = divmod(n, 10 ** 9)
    text = number_to_words(hi) + " tỷ"
    if lo:
        text += " " + " ".join(_below_billion(lo, True))
    return text


def amount_in_words(n):
    """'Ba mươi triệu đồng chẵn' / 'Một triệu hai trăm năm mươi nghìn đồng'."""
    n = int(round(float(n or 0)))
    text = number_to_words(n) + " đồng"
    if n and n % 1000 == 0:
        text += " chẵn"
    return text[:1].upper() + text[1:]
