# Copyright (c) 2026, eCentric and contributors
"""Phan thuong sau khi nop khao sat.

VONG QUAY (ket qua ngay):
    Xac suat trung cua MOT luot = qua_con_lai / luot_con_lai_du_kien, kep vao [0, 1].
    luot_con_lai_du_kien = max(so_nguoi_du_kien - so_luot_da_quay, 1).
    Dung cong thuc nay (ke thua tu /khao-sat tra sua 07/2026) vi no giu hai tinh chat ma ca
    hai ben deu can:
      - cong bang theo thu tu: nguoi quay dau va nguoi quay cuoi co cung ky vong trung;
      - khong "het qua som" va khong "con qua thua": neu dung bang so nguoi du kien thi
        phat het DUNG so qua, nguoi cuoi cung con qua thi chac chan trung (p = 1).
    Trung thi chon hang qua theo trong so = so luong con lai cua hang do.

CON SO MAY MAN (quay cuoi dot):
    Nop xong nhan so thu tu (001, 002, ...). Nguoi tao bam quay: moi hang qua rut ngau nhien
    KHONG lap trong so nguoi chua trung.

Bo sinh ngau nhien duoc TRUYEN VAO (`rng.random()`, `rng.sample()`) - test dung so co dinh,
service dung `random.SystemRandom()` (nguon ngau nhien cua he dieu hanh, khong doan truoc
duoc). Sandbox Server Script truoc day phai lay micro-giay lam so ngau nhien; app code thi
khong can.
"""


def remaining(prizes):
    """[{id, label, quantity, awarded}] -> tong so qua con lai."""
    return sum(max(int(p.get("quantity") or 0) - int(p.get("awarded") or 0), 0) for p in prizes)


def win_probability(prizes, expected, spins_done):
    left = remaining(prizes)
    if left <= 0:
        return 0.0
    spins_left = max(int(expected or 0) - int(spins_done or 0), 1)
    return max(0.0, min(1.0, float(left) / spins_left))


def pick_prize(prizes, rng):
    """Chon hang qua theo trong so so luong con lai. None neu het qua."""
    pool = [(p, max(int(p.get("quantity") or 0) - int(p.get("awarded") or 0), 0)) for p in prizes]
    total = sum(w for _p, w in pool)
    if total <= 0:
        return None
    x = rng.random() * total
    for p, w in pool:
        if w <= 0:
            continue
        if x < w:
            return p
        x -= w
    return [p for p, w in pool if w > 0][-1]


def spin(prizes, expected, spins_done, rng):
    """(trung?, hang_qua | None, xac_suat)."""
    p = win_probability(prizes, expected, spins_done)
    if p <= 0:
        return False, None, p
    if rng.random() < p:
        prize = pick_prize(prizes, rng)
        return prize is not None, prize, p
    return False, None, p


def draw(prizes, candidates, rng):
    """Quay so: {prize_id: [user, ...]} cho moi hang qua con lai.

    candidates : danh sach user CHUA trung (da loc san), thu tu khong quan trong.
    Moi nguoi trung toi da MOT qua trong mot lan quay.
    """
    pool = sorted(set(candidates))
    out = {}
    for p in prizes:
        need = max(int(p.get("quantity") or 0) - int(p.get("awarded") or 0), 0)
        if need <= 0 or not pool:
            continue
        won = rng.sample(pool, min(need, len(pool)))
        out[p["id"]] = won
        pool = [u for u in pool if u not in won]
    return out


def format_number(n):
    return "%03d" % int(n)
