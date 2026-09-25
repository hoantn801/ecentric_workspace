# Copyright (c) 2026, eCentric and contributors
"""Ba dau hieu ngoai le cho tab "Tao hang loat" cua Payment Request.

VI SAO CAN. Mot lo 8 phieu la 8 quyet dinh, va mat nguoi doc den phieu thu sau thi khong
con doc nua. Ba dau hieu duoi day re de tra va dat neu bo sot; chung KHONG chan viec gui,
chi bat den len dong do.

BA DAU HIEU, VA VI SAO LA BA CAI NAY:

  1. `new_account` - so tai khoan chua tung xuat hien tren mot phieu DA GUI nao.
     Khoa theo SO TAI KHOAN chu khong theo TEN nguoi nhan, vi hai le:
       - so tai khoan moi la thu chuyen tien di, va la thu AI doc sai (nham mot chu so);
         mot cai ten viet hoi khac ("Nguyen Van A" / "NGUYEN VAN A") van la dung nguoi.
       - ro ri it hon han: muon do "so tai khoan nay tung nhan tien chua" thi phai BIET
         truoc so tai khoan. Go mot cai ten vao de xem nguoi do co quan he voi eCentric
         khong thi ai cung lam duoc - do la mot oracle that su.
     Tra toan cong ty, va CHI tra ve dung/sai. Khong tra so lan, khong tra ten ai tao,
     khong tra so tien. Dieu do la co y: gia tri canh bao nam o chu "moi", khong nam o
     chi tiet.

  2. `dup_in_batch` - hai dong trong CUNG mot lo trung so tai khoan.
     Khong tra database mot lan nao. Day la phep kiem dang gia nhat cua man hinh, va no
     chi TON TAI DUOC vi co khai niem "lo": mot phieu doc lap khong bao gio biet no la
     ban sao cua phieu ben canh. Hai nguyen nhan deu dat: AI doc mot tep thanh hai, hoac
     mot khoan sap bi tra hai lan.

  3. `amount_off` - so tien lech xa lich su cua CHINH nguoi dang tao cho so tai khoan do.
     Cai nay BUOC phai doc so tien cu, nen no khong duoc mo ra toan cong ty - `owner` la
     nguoi dang dang nhap, khong hon. Khong co lich su thi IM LANG, khong bao gi: mot
     canh bao sai o phieu thu sau con te hon khong co canh bao nao, vi no day nguoi ta
     vao thoi quen bo qua ca ba dau hieu.

KHONG BAO GIO NEM. Ba dau hieu la thu tang them; mot loi SQL o day ma lam hong ca man hinh
tao phieu thi cai gia lon hon nhieu lan ich loi. Loi -> khong co co, va het.
"""
import frappe

DOCTYPE = "EC Payment Request"

#: Bao nhieu phieu cu thi du de noi "binh thuong anh tra khoang nay". Duoi nguong nay thi
#: mot lan tra tien le cung keo trung vi di, va canh bao thanh ra ngau nhien.
MIN_HISTORY = 3
#: Lech BAO NHIEU LAN thi dang goi la lech. 3 lan chu khong phai 2: doi voi KOL/KOC thi
#: 2 lan la chuyen thuong ngay, bao o day la bao suot ngay.
FACTOR = 3.0
#: Doc toi da bao nhieu phieu cu cho MOI so tai khoan. Lo toi da 10 dong -> 10 truy van.
HISTORY_LIMIT = 30


def _digits(value):
    """So tai khoan nguoi ta go co dau cach, dau cham, dau gach. "0123 456" va "0123456"
    la MOT so tai khoan - so sanh nguyen chuoi thi ca hai dau hieu deu truot."""
    return "".join(c for c in str(value or "") if c.isdigit())


def _median(numbers):
    xs = sorted(numbers)
    n = len(xs)
    if not n:
        return 0.0
    mid = n // 2
    return float(xs[mid]) if n % 2 else (float(xs[mid - 1]) + float(xs[mid])) / 2.0


#: So tai khoan nguoi ta go vao co the co dau cach / dau cham / dau gach. So sanh phai lam
#: tren chuoi DA CHUAN HOA o CA HAI dau - neu chi chuan hoa phia Python thi "0123 456 789"
#: trong DB khong bao gio khop voi "0123456789" vua go, va ca hai dau hieu deu truot am tham.
#: Loc bang LIKE tren 6 so cuoi cung KHONG lam duoc: 6 so cuoi co the bi mot dau cach cat doi.
_CHUAN = "REPLACE(REPLACE(REPLACE(IFNULL(bank_account_number,''),' ',''),'.',''),'-','')"


def _account_is_new(account):
    """True khi so tai khoan nay chua tung nam tren mot phieu DA GUI.

    `submitted_at` rong = ban nhap. Mot ban nhap khong chung minh duoc gi: chinh nguoi
    dung vua tao no bang lo nay cung co the la ban nhap.
    """
    row = frappe.db.sql(
        "SELECT name FROM `tab%s` WHERE %s = %%s AND IFNULL(submitted_at,'') != '' LIMIT 1"
        % (DOCTYPE, _CHUAN), (account,))
    return not row


def _amount_is_off(account, amount, user):
    """True khi so tien lech >= FACTOR lan so voi trung vi lich su CUA CHINH nguoi nay."""
    if not amount or amount <= 0:
        return False
    rows = frappe.db.sql(
        "SELECT payment_amount FROM `tab%s` WHERE %s = %%s AND owner = %%s "
        "AND IFNULL(submitted_at,'') != '' AND IFNULL(payment_amount,0) > 0 "
        "ORDER BY creation DESC LIMIT %%s" % (DOCTYPE, _CHUAN),
        (account, user, HISTORY_LIMIT))
    past = [float(r[0]) for r in rows]
    if len(past) < MIN_HISTORY:
        return False
    mid = _median(past)
    if mid <= 0:
        return False
    return amount >= mid * FACTOR or amount <= mid / FACTOR


def flag_rows(rows, user=None):
    """rows: [{"key": <id dong>, "bank_account_number": str, "payment_amount": number}]

    Tra ve {key: {"new_account": bool, "dup_in_batch": bool, "amount_off": bool}}.
    """
    user = user or frappe.session.user
    out = {}
    accounts = {}
    for row in (rows or []):
        key = str((row or {}).get("key") or "")
        if not key:
            continue
        acc = _digits((row or {}).get("bank_account_number"))
        out[key] = {"new_account": False, "dup_in_batch": False, "amount_off": False}
        if acc:
            accounts.setdefault(acc, []).append(key)

    for acc, keys in accounts.items():
        trung = len(keys) > 1
        try:
            moi = _account_is_new(acc)
        except Exception:
            moi = False
        for key in keys:
            out[key]["dup_in_batch"] = trung
            out[key]["new_account"] = moi

    by_key = {str((r or {}).get("key") or ""): r for r in (rows or [])}
    for acc, keys in accounts.items():
        for key in keys:
            try:
                amount = float(by_key[key].get("payment_amount") or 0)
            except (TypeError, ValueError):
                continue
            try:
                out[key]["amount_off"] = _amount_is_off(acc, amount, user)
            except Exception:
                pass
    return out
