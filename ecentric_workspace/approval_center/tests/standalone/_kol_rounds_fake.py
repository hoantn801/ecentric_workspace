"""Gia lap kho kol_rounds (EC KOL Acceptance, 24/11/2026) bang danh sach `acceptances` tren doc gia - de
cac test viet tu thoi bang con (truoc 24/11) van kiem duoc nghiep vu dot nghiem thu.

    from _kol_rounds_fake import install
    install(importlib.import_module(PKG + ".kol_rounds"))
Dong gia (Row / FakeDoc - dict co thuoc tinh) vua la ban xem vua la "Document" de ghi: test kiem
row.status sau khi goi la thay ngay."""


def install(mod, frappe_throw=None):
    parents = {}

    def rows(business):
        if not business or isinstance(business, str):
            return []
        out = list(business.get("acceptances") or [])
        for r in out:
            if r.get("round_no") is None:
                r["round_no"] = r.get("idx")
            if r.get("idx") is None:
                r["idx"] = r.get("round_no")
            r.setdefault("approval_status", "")
            parents[id(r)] = business
        return out

    def find(business, row_name):
        for r in rows(business):
            if row_name and row_name in (r.get("name"), r.get("legacy_row")):
                return r
        return None

    def get(business, row_name):
        r = find(business, row_name)
        if r is None:
            import frappe
            (frappe_throw or frappe.throw)("Không tìm thấy đợt nghiệm thu.")
        return r

    def create(doc, values, user):
        r = doc.append("acceptances", dict(values))
        r["round_no"] = r.get("idx")
        r["contract"] = doc.get("name")
        r["requested_by"] = user
        parents[id(r)] = doc
        return r

    def save(r):
        return r

    def delete(r):
        doc = parents.get(id(r))
        if doc is not None:
            doc["acceptances"] = [x for x in doc.get("acceptances") or [] if x is not r]

    def set_values(name, values):
        for doc in list(parents.values()):
            for r in doc.get("acceptances") or []:
                if r.get("name") == name:
                    r.update(values)

    mod.rows, mod.find, mod.get, mod.create, mod.save, mod.delete, mod.set_values = (
        rows, find, get, create, save, delete, set_values)
    mod.invalidate = lambda contract=None: None

    def lock(name):
        for doc in list(parents.values()):
            for r in doc.get("acceptances") or []:
                if r.get("name") == name:
                    return r.get("approval_request")
        return None
    mod.lock = lock
    return mod
