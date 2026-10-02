# Copyright (c) 2026, eCentric and contributors
"""Phan thuong sau khi nop khao sat - tinh toan thuan, khong import frappe.

Ba kieu (PO Hoan chot 01/10/2026):

VONG QUAY CHIA DOT (ket qua ngay khi quay):
    K = tong so phan qua, E = so nguoi du kien. Chia luot quay 1..E thanh K dot lien tiep gan
    bang nhau; moi dot giau san DUNG MOT luot trung o vi tri ngau nhien (bot truoc luc phat
    hanh, khong gui trinh duyet). Nguoi quay thu 1 hay thu 100 deu co cung co hoi ~K/E, va ba
    nguoi dau KHONG THE an het qua (moi dot chi mot qua).
    It nguoi hon du kien -> qua cua dot chua toi KHONG trao (PO chot "B", 01/10 18:10).
    Doi qua giua chung (them / bot so luong) -> `plan` lai CHO PHAN CON LAI tu luot ke tiep.

CON SO MAY MAN (quay theo gio hen):
    Moi nguoi tu chon mot so trong dai 1..N (khong trung - kiem o service duoi khoa). Toi gio
    quay, rut KHONG LAP cac so trong CA DAI: so co nguoi giu thi nguoi do trung, so trong thi
    qua do de lai (PO chot "A", 01/10 18:01). Quay tu giai nho toi giai lon.

DUA VE DICH (quay theo gio hen):
    Ai nop phieu cung co xe. Thu tu ve dich = mot hoan vi ngau nhien cua nguoi tham gia, quyet
    o server; trinh duyet chi phat lai hieu ung dung thu tu do.

Bo sinh ngau nhien duoc TRUYEN VAO (`rng.random()`, `rng.randint()`, `rng.sample()`,
`rng.shuffle()`) - test dung so co dinh, service dung `random.SystemRandom()`.
"""


def remaining(prizes):
    """[{id, label, quantity, awarded}] -> tong so qua con lai."""
    return sum(max(int(p.get("quantity") or 0) - int(p.get("awarded") or 0), 0) for p in prizes)


def units(prizes, left_only=True):
    """Tach hang qua thanh tung PHAN, theo thu tu dong (dong dau = giai lon nhat).

    [{id, quantity, awarded}] -> [prize_id, prize_id, ...]
    """
    out = []
    for p in prizes:
        n = int(p.get("quantity") or 0)
        if left_only:
            n -= int(p.get("awarded") or 0)
        out.extend([p["id"]] * max(n, 0))
    return out


# --------------------------------------------------------------------- vong quay --

def windows(first, last, k):
    """Chia luot first..last thanh k dot lien tiep gan bang nhau -> [(tu, den), ...].
    Dot dau co the ngan hon mot luot; khong dot nao rong (k bi kep ve so luot)."""
    n = last - first + 1
    k = max(0, min(k, n))
    out = []
    for i in range(k):
        a = first + (i * n) // k
        b = first + ((i + 1) * n) // k - 1
        out.append((a, b))
    return out


def plan(prizes, expected, spins_done, rng):
    """Ke hoach giau qua cho cac luot TU spins_done + 1 toi expected.

    Tra [{"from", "to", "seq", "prize"}] - moi dot mot qua, `seq` la luot trung (bi mat).
    Qua nao vao dot nao cung ngau nhien (xao tron phan qua truoc khi gan).
    """
    left = units(prizes)
    first = int(spins_done or 0) + 1
    last = max(int(expected or 0), first + len(left) - 1)
    if not left:
        return []
    rng.shuffle(left)
    out = []
    for (a, b), pid in zip(windows(first, last, len(left)), left):
        out.append({"from": a, "to": b, "seq": rng.randint(a, b), "prize": pid})
    return out


def spin_result(slots, seq, prizes):
    """Luot thu `seq` trung qua nao? None neu khong trung / qua cua dot da het."""
    left = {p["id"]: int(p.get("quantity") or 0) - int(p.get("awarded") or 0) for p in prizes}
    for s in slots or []:
        if int(s.get("seq") or 0) == seq and left.get(s.get("prize"), 0) > 0:
            return s["prize"]
    return None


def wave_info(slots, seq, prizes, spun=False):
    """Thong tin CONG KHAI cho man vong quay: dot cua luot `seq`, dot do con qua khong.

    Khong lo vi tri luot trung. "Con qua" chi noi qua cua dot chua bi ai lay.
    spun : luot `seq` DA quay xong (tinh ca luot do vao "da qua").
    """
    cut = seq + 1 if spun else seq
    ordered = sorted(slots or [], key=lambda s: s["from"])
    names = {p["id"]: p.get("label") or "" for p in prizes}
    waves = []
    for i, s in enumerate(ordered):
        waves.append({"index": i + 1, "from": s["from"], "to": s["to"],
                      "state": "done" if cut > s["seq"] else ("open" if cut >= s["from"] else "later"),
                      "prize": names.get(s["prize"], "")})
    mine = next((w for w in waves if w["from"] <= seq <= w["to"]), None)
    return {"seq": seq, "waves": waves, "current": mine["index"] if mine else 0}


# ------------------------------------------------------------------- so may man --

def draw_order(prizes):
    """Thu tu quay so: tu giai NHO toi giai LON (dong cuoi -> dong dau), moi phan mot luot.
    Tra [(prize_id, rank)] voi rank = so thu tu dong (1 = giai lon nhat)."""
    out = []
    for rank, p in reversed(list(enumerate(prizes, start=1))):
        n = max(int(p.get("quantity") or 0) - int(p.get("awarded") or 0), 0)
        out.extend([(p["id"], rank)] * n)
    return out


def lucky_draw(prizes, holders, top, rng):
    """Rut so trong CA DAI 1..top, khong lap.

    holders : {so: user} - nguoi dang giu so (moi so mot nguoi, moi nguoi mot so).
    Tra [{"prize", "rank", "number", "user"}] theo thu tu quay; `user` None = so trong, qua de lai.
    """
    order = draw_order(prizes)
    nums = rng.sample(range(1, int(top) + 1), min(len(order), int(top)))
    return [{"prize": pid, "rank": rank, "number": n, "user": holders.get(n)}
            for (pid, rank), n in zip(order, nums)]


def free_number(top, taken, rng):
    """Mot so CON TRONG ngau nhien trong 1..top, hoac None neu het so."""
    free = [n for n in range(1, int(top) + 1) if n not in taken]
    return rng.choice(free) if free else None


def assign_missing(top, holders, users, rng):
    """May boc giup (PO Hoan 02/10): nguoi DA NOP ma toi gio quay chua chon so -> moi nguoi mot so
    con trong ngau nhien, khong trung. Het so trong thi nguoi con lai khong co so.
    Tra {so: user} chi gom cac so vua boc (khong dung toi `holders`)."""
    have = set(holders.values())
    todo = sorted(u for u in set(users) if u not in have)
    free = [n for n in range(1, int(top) + 1) if n not in holders]
    rng.shuffle(free)
    return dict(zip(free, todo))


# --------------------------------------------------------------------- dua ve dich --

def race(prizes, users, rng):
    """Thu tu ve dich + nguoi nhan qua.

    Tra {"order": [user, ...], "winners": [{"prize", "rank", "place", "user"}]}.
    Ve nhat nhan giai lon nhat (dong dau), lan luot xuong.
    """
    order = sorted(set(users))
    rng.shuffle(order)
    ranked = []
    for rank, p in enumerate(prizes, start=1):
        n = max(int(p.get("quantity") or 0) - int(p.get("awarded") or 0), 0)
        ranked.extend([(p["id"], rank)] * n)
    winners = [{"prize": pid, "rank": rank, "place": i + 1, "user": u}
               for i, ((pid, rank), u) in enumerate(zip(ranked, order))]
    return {"order": order, "winners": winners}


def format_number(n, top=100):
    """So hien thi du chu so theo dai: dai 100 -> 007, dai 1000 -> 0007."""
    width = max(3, len(str(int(top or 0))))
    return str(int(n)).zfill(width)
