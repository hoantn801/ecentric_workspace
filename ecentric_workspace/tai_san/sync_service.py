# Copyright (c) 2026, eCentric and contributors
"""Dong bo so tai san theo file kiem ke (Excel IT) + nhap ban quyen Microsoft theo danh sach email.

Hoan duyet 27/11/2026 (file "Danh sach su dung thiet bi IT" + 4 danh sach license M365):
- Doi ma toan bo EC2024xxxx -> EC2026xxxx (giu so duoi, chu hoa).
- Nguoi giu / kho theo Excel: moi thay doi di qua service.transition (dung vong doi, co EC Asset Event,
  ghi chu nguon) - KHONG set_value thang trang thai.
- Ma cu khong co trong Excel thi giu nguyen (chi doi ma). Thiet bi moi (chua co tren ERP) chua them:
  thieu nguyen gia / ngay mua (Hoan: tinh sau).
- Ban quyen M365: moi goi mot ban quyen thue bao, so cho = so tai khoan; cap cho nhan vien theo email
  (KHONG gui thong bao tung nguoi); tai khoan dung chung chi tinh cho + ghi chu. Han / gia: bo sung sau.
Idempotent: chay lai khong lam gi them (so sanh trang thai hien tai voi dich).
"""
import json
import os
import re

from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import license_repository as LR
from ecentric_workspace.tai_san import license_service as LS
from ecentric_workspace.tai_san import product_service as PS
from ecentric_workspace.tai_san import repository as R
from ecentric_workspace.tai_san import service as S

_OLD = re.compile(r"^EC2024", re.I)


def new_tag(tag, old_prefix="EC2024", new_prefix="EC2026"):
    """EC202400072 -> EC202600072; ec202400046 -> EC202600046; ma khac -> None (khong doi)."""
    t = (tag or "").strip()
    if not re.match("^" + old_prefix, t, re.I):
        return None
    return (new_prefix + t[len(old_prefix):]).upper()


def _by_tag(assets):
    return {(a.get(C.TAG_FIELD) or "").strip().upper(): a for a in assets if a.get(C.TAG_FIELD)}


def _steps(status, holder, target):
    """Chuoi thao tac dua thiet bi ve dich. target = ma nhan vien, hoac None = ve kho (Sẵn sàng)."""
    if target is None:
        return {C.ST_IN_USE: [C.A_RETURN, C.A_CHECK_PASS], C.ST_RESERVED: [C.A_RETURN, C.A_CHECK_PASS],
                C.ST_PENDING_CHECK: [C.A_CHECK_PASS], C.ST_LOST: [C.A_FOUND, C.A_CHECK_PASS]}.get(status, [])
    if status == C.ST_IN_USE:
        return [] if holder == target else [C.A_TRANSFER]
    return {C.ST_AVAILABLE: [C.A_ASSIGN], C.ST_RESERVED: [C.A_ASSIGN],
            C.ST_PENDING_CHECK: [C.A_CHECK_PASS, C.A_ASSIGN],
            C.ST_LOST: [C.A_FOUND, C.A_CHECK_PASS, C.A_ASSIGN]}.get(status)


def sync_devices(ctx, rows, note, fixes=None):
    """rows: [{old_tag, email|None}] (email None = ve kho). fixes: [{old_tag, item_contains}] doi mau.
    Tra ve bao cao [(muc, ket qua)]. Loi tung dong khong chan dong khac."""
    out = []
    for r in rows:
        tag = r["old_tag"].upper()
        try:
            idx = _by_tag(R.assets())
            a = idx.get(tag) or idx.get(new_tag(tag) or "")
            if not a:
                out.append((tag, "bỏ qua: chưa có trên ERP"))
                continue
            target = None
            if r.get("email"):
                emp = R.employee_of_user(r["email"])
                if not emp or emp.status != "Active":
                    out.append((tag, "bỏ qua: không thấy nhân viên đang làm cho %s" % r["email"]))
                    continue
                target = emp.name
            steps = _steps(a.get(C.OPS_STATUS_FIELD), a.get("custodian"), target)
            if steps is None:
                out.append((tag, "bỏ qua: trạng thái %s không tự xử lý" % a.get(C.OPS_STATUS_FIELD)))
                continue
            for act in steps:
                S.transition(ctx, a.name, act, employee=target if act in (C.A_ASSIGN, C.A_TRANSFER) else None,
                             note=note, notify=False)
            out.append((tag, " → ".join(steps) if steps else "đã đúng"))
        except Exception as e:  # noqa: BLE001 - bao cao tung dong, khong dung ca dot
            out.append((tag, "lỗi: %s" % e))
    for f in fixes or []:
        try:
            idx = _by_tag(R.assets())
            a = idx.get(f["old_tag"].upper()) or idx.get(new_tag(f["old_tag"]) or "")
            items = [i for i in R.fixed_asset_items() if f["item_contains"].upper() in (i.item_name or "").upper()]
            if not a or not items:
                out.append((f["old_tag"], "bỏ qua sửa mẫu: thiếu thiết bị hoặc mẫu"))
                continue
            if a.get("item_code") != items[0].name:
                S.update_info(ctx, a.name, {"item_code": items[0].name, "asset_name": items[0].item_name})
                out.append((f["old_tag"], "mẫu = %s" % items[0].item_name))
            else:
                out.append((f["old_tag"], "mẫu đã đúng"))
            continue
        except Exception as e:  # noqa: BLE001
            out.append((f["old_tag"], "lỗi sửa mẫu: %s" % e))
    return out


def rename_tags(ctx, old_prefix="EC2024", new_prefix="EC2026"):
    """Doi ma moi thiet bi co ma bat dau old_prefix. Ma moi da co thiet bi khac giu -> bo qua, bao lai."""
    out = []
    assets = R.assets()
    taken = {(a.get(C.TAG_FIELD) or "").strip().upper() for a in assets}
    for a in assets:
        nt = new_tag(a.get(C.TAG_FIELD), old_prefix, new_prefix)
        if not nt:
            continue
        if nt in taken:
            out.append((a.get(C.TAG_FIELD), "bỏ qua: mã %s đã có thiết bị khác" % nt))
            continue
        S.update_info(ctx, a.name, {C.TAG_FIELD: nt})
        taken.add(nt)
        out.append((a.get(C.TAG_FIELD), nt))
    return out


def import_licenses(ctx, groups, marker):
    """groups: [{product_name, vendor, category, emails[], shared[]}]. Tao / dung lai phan mem + mot ban
    quyen moi goi, cap cho theo email. Da co ban quyen danh dau `marker`, hoac dung MOT ban quyen dang
    dung cua phan mem do (nhap tay truoc) -> dung lai, nang so cho neu thieu; khong tao trung."""
    out = []
    for g in groups:
        p = PS.create_product(ctx, {"product_name": g["product_name"], "vendor": g.get("vendor"),
                                    "category": g.get("category") or "Văn phòng",
                                    "license_type": C.LT_SUBSCRIPTION, "billing_cycle": C.CY_YEARLY}, force=True)
        pid = p.get("product") or (p.get("exact") or {}).get("name")
        seats = len(g["emails"]) + len(g.get("shared") or [])
        live = [x for x in LR.licenses() if x.product == pid and x.status != C.LS_CANCELLED]
        mine = [x for x in live if marker in (x.note or "")] or (live if len(live) == 1 else [])
        if mine:
            lic = mine[0].name
            if int(mine[0].seats or 0) < seats:
                LR.set_license(lic, {"seats": seats})
                LR.add_log(lic, "Số chỗ: %s → %d (theo danh sách Microsoft 365, %s)."
                           % (mine[0].seats, seats, marker), ctx.user)
        else:
            note = ("%s\nNhập từ danh sách Microsoft 365 admin. Hạn, kỳ thanh toán, giá: bổ sung sau."
                    % marker)
            if g.get("shared"):
                note += "\nTài khoản dùng chung (chỉ tính chỗ, không gắn người): " + ", ".join(g["shared"])
            lic = LR.insert_license({"product": pid, "license_name": g["product_name"], "vendor": g.get("vendor"),
                                     "category": g.get("category") or "Văn phòng",
                                     "license_type": C.LT_SUBSCRIPTION, "billing_cycle": C.CY_YEARLY,
                                     "status": C.LS_ACTIVE, "seats": seats, "account": "Microsoft 365 admin",
                                     "currency": C.BASE_CURRENCY, "note": note[:1000]})
            LR.add_log(lic, "Nhập %d chỗ từ danh sách Microsoft 365 (%s)." % (seats, marker), ctx.user)
        have = {s.employee for s in LR.active_seats() if s.license == lic}
        done, skipped = 0, []
        for email in g["emails"]:
            emp = R.employee_of_user(email)
            if not emp or emp.status != "Active":
                skipped.append(email)
                continue
            if emp.name in have:
                continue
            LS.assign(ctx, lic, emp.name, note=marker, notify=False)
            have.add(emp.name)
            done += 1
        out.append((g["product_name"], "%s · cấp thêm %d · không khớp nhân viên: %s"
                    % (lic, done, ", ".join(skipped) or "—")))
    return out


DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def load(file_name):
    with open(os.path.join(DATA_DIR, file_name), encoding="utf-8") as f:
        return json.load(f)


def run(ctx, devices_file, licenses_file):
    """Mot dot kiem ke: doi ma -> nguoi giu / kho -> sua mau -> ban quyen. Tra ve bao cao (list dong)."""
    dev, lic = load(devices_file), load(licenses_file)
    report = [("doi ma", r) for r in rename_tags(ctx)]
    report += [("thiet bi", r) for r in sync_devices(ctx, dev["rows"], dev["note"], dev.get("fixes"))]
    report += [("ban quyen", r) for r in import_licenses(ctx, lic["groups"], lic["marker"])]
    return report
