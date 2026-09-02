# Copyright (c) 2026, eCentric and contributors
"""Dong dau lai ma bam cho cac goi dang ky, sau khi khoa ho so doi tu `modified` sang khoa
CAU TRUC (package.profile_structure_key).

VI SAO. Ma bam goi tron `modified` cua ho so ky so. Bat ky lan luu ho so nao - p127 (seed
buoc), p128 (seed canh Ky chinh), sua ghi chu - deu lam MOI goi dang ky lech bam, nguoi duyet
ke tiep bi chan "Goi tai lieu da thay doi so voi phien ban da khoa". 03/09 00:26 p128 len,
anh Lam bam Ky chinh tren goi 00030 (khoa 23:06) -> chan. Lien/Phuong qua duoc chi vi p127 len
truoc 23:05. Mot co che, mot lan may mot lan khong.

Khoa moi chi doc nhung truong quyet dinh HINH DANG goi (cap nao ky, may o moi tep, chinh
sach). Doi khoa = moi goi da khoa co ma bam cu -> phai dong dau lai MOT LAN, o day.

PHAM VI. Chi goi Locked/Active (dang ky). Goi Draft chua co dau; goi da xong/huy giu nguyen
dau cu lam lich su. Chan ky CHUA KET THUC cua goi do cung mang ban sao ma bam (binding so
DSR.package_hash voi goi) -> dong dau lai cung luc, cung gia tri. Chan da ket thuc giu dau cu.

RUI RO NOI THANG. Dong dau lai la tin rang tep + o ky cua goi KHONG bi sua giua luc khoa va
bay gio - dau cu khong so duoc voi dau moi nen khong chung minh duoc bang ma bam. Bu lai:
tep co sha256 rieng (van doi chieu luc tai PDF ve), o ky chi sua duoc qua API co quyen, va
moi lan dong dau ghi su kien PackageHashRestamped kem truoc/sau. Lam mot lan, ghi ro.
"""
import frappe

PKG = "EC Digital Signature Package"
DSR = "EC Digital Signature Request"


def execute():
    from ecentric_workspace.platform.esign import events
    from ecentric_workspace.platform.esign import package as pkgsvc
    from ecentric_workspace.platform.esign.state import DSR_TERMINAL

    rows = frappe.get_all(PKG, filters={"status": ["in", ("Locked", "Active")]},
                          fields=["name", "package_hash"], limit_page_length=0)
    doi = giu = 0
    for r in rows:
        moi = pkgsvc.compute_hash(r.name)
        if moi == r.package_hash:
            giu += 1
            continue
        frappe.db.set_value(PKG, r.name, "package_hash", moi)
        chan = frappe.get_all(DSR, filters={"package": r.name,
                                            "status": ["not in", DSR_TERMINAL],
                                            "package_hash": r.package_hash},
                              pluck="name", limit_page_length=0)
        for d in chan:
            frappe.db.set_value(DSR, d, "package_hash", moi)
        events.emit("PackageHashRestamped", package=r.name,
                    request_meta={"truoc": r.package_hash, "sau": moi, "chan_ky": chan,
                                  "ly_do": "khoa ho so doi tu modified sang cau truc (p129)"})
        doi += 1
        print("[OK] %s: dong dau lai (%d chan ky)" % (r.name, len(chan)))
    print("[OK] goi doi dau: %d, giu nguyen: %d" % (doi, giu))

    # VERIFY - doc lai tu DB: moi goi dang ky phai khop dau.
    lech = []
    for r in frappe.get_all(PKG, filters={"status": ["in", ("Locked", "Active")]},
                            fields=["name", "package_hash"], limit_page_length=0):
        if pkgsvc.compute_hash(r.name) != r.package_hash:
            lech.append(r.name)
    print("[OK]  moi goi dang ky khop dau" if not lech else "[ERR] con lech: %s" % lech)
    if lech:
        frappe.throw("p129: %d goi van lech dau sau khi dong lai" % len(lech))
