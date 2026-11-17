# Copyright (c) 2026, eCentric and contributors
"""EC License Machine (+ bang con EC License Install): mot ban ghi cho moi may that, dung chung 3 app.
So lieu bao ve (last_seen, last_ip, last_checkin) ghi bang set_value khong doi modified / khong tao Version;
doi trang thai / ten / ghi chu luu bang doc.save() -> Track Changes giu vet."""
import json

from ecentric_workspace.ai_tools.features.ai_live import license_constants as L

_FIELDS = ["name", "label", "status", "guid_h", "disk_h", "mac_h", "host", "win_user", "os", "first_ip", "last_ip",
           "source_dist", "parent_machine", "reason", "block_message", "blocked_manual", "clone_warning", "clone_host",
           "note", "via_checkin", "approved_by", "approved_at", "first_seen", "last_seen", "notified_pending", "notified_clone",
           "creation"]
_LIST_FIELDS = ["name", "label", "status", "host", "win_user", "last_ip", "source_dist", "parent_machine", "reason",
                "clone_warning", "last_seen", "first_seen", "creation", "blocked_manual", "via_checkin"]
_INSTALL_FIELDS = ["name", "parent", "product", "hw", "pending_hw", "reissued_at", "machine_id", "build_id", "app_dir",
                   "license_issued_at", "license_hw", "last_checkin", "last_checkin_ip"]


def sys_dt(ts):
    """epoch -> datetime gio he thong (khong tz) cho truong Datetime."""
    from ecentric_workspace.ai_tools.features.ai_live.repositories.health_repository import local_dt
    return local_dt(ts)


def to_ts(dt):
    """Datetime (gio he thong) -> epoch giay; trong -> 0."""
    if not dt:
        return 0.0
    import frappe
    from zoneinfo import ZoneInfo
    d = frappe.utils.get_datetime(dt)
    return d.replace(tzinfo=ZoneInfo(frappe.utils.get_system_timezone())).timestamp()


def _macs(v):
    if isinstance(v, list):
        return v
    try:
        out = json.loads(v or "[]")
    except (TypeError, ValueError):
        return []
    return out if isinstance(out, list) else []


def _machine(row, installs):
    m = dict(row)
    m["fp"] = {"guid_h": row.get("guid_h") or "", "disk_h": row.get("disk_h") or "", "mac_h": _macs(row.get("mac_h"))}
    m["installs"] = installs
    m["hw"] = {i["product"]: i.get("hw") for i in installs if i.get("hw")}
    m["reissued_at"] = {i["product"]: to_ts(i.get("reissued_at")) for i in installs if i.get("reissued_at")}
    return m


class LicenseMachineRepository:
    # ------------------------------------------------------------ doc
    def _installs(self, names):
        import frappe
        if not names:
            return {}
        out = {n: [] for n in names}
        for r in frappe.get_all(L.INSTALL, filters={"parent": ["in", list(names)], "parenttype": L.MACHINE},
                                fields=_INSTALL_FIELDS, order_by="idx asc", limit_page_length=0):
            out.setdefault(r["parent"], []).append(r)
        return out

    def by_guid(self, guid_h):
        import frappe
        rows = frappe.get_all(L.MACHINE, filters={"guid_h": guid_h}, fields=_FIELDS, order_by="creation asc",
                              limit_page_length=50)
        inst = self._installs([r["name"] for r in rows])
        return [_machine(r, inst.get(r["name"], [])) for r in rows]

    def get(self, name):
        import frappe
        rows = frappe.get_all(L.MACHINE, filters={"name": name}, fields=_FIELDS, limit_page_length=1) if name else []
        if not rows:
            return None
        return _machine(rows[0], self._installs([name]).get(name, []))

    def create(self, vals, installs):
        import frappe
        doc = frappe.get_doc(dict(_db(vals), doctype=L.MACHINE))
        for i in installs:
            doc.append("installs", _db(i))
        doc.insert(ignore_permissions=True)
        return doc.name

    def save(self, name, vals):
        """Doi trang thai / ten / ghi chu: luu qua doc -> co Version (Track Changes)."""
        import frappe
        doc = frappe.get_doc(L.MACHINE, name)
        doc.update(_db(vals))
        doc.save(ignore_permissions=True)

    def touch(self, name, vals):
        """So lieu bao ve: khong doi modified, khong tao Version."""
        import frappe
        if vals:
            frappe.db.set_value(L.MACHINE, name, _db(vals), update_modified=False)

    def upsert_install(self, name, product, vals):
        import frappe
        row = frappe.db.get_value(L.INSTALL, {"parent": name, "parenttype": L.MACHINE, "product": product}, "name")
        if row:
            frappe.db.set_value(L.INSTALL, row, _db(vals), update_modified=False)
            return
        doc = frappe.get_doc(L.MACHINE, name)
        doc.append("installs", _db(dict(vals, product=product)))
        doc.save(ignore_permissions=True)

    def dist_owner(self, dist_id, exclude=None):
        """May DA DUYET dau tien cua goi (khac may hien tai) - chu goi tinh theo MAY, khong theo app."""
        import frappe
        flt = {"source_dist": dist_id, "status": L.Status.APPROVED, "via_checkin": 0}   # ban ghi tu khai khong lam chu goi
        if exclude:
            flt["name"] = ["!=", exclude]
        rows = frappe.get_all(L.MACHINE, filters=flt, fields=["name", "label", "host"],
                              order_by="approved_at asc, creation asc", limit_page_length=1)
        return rows[0] if rows else None

    def count_approved(self, dist_id):
        import frappe
        return frappe.db.count(L.MACHINE, {"source_dist": dist_id, "status": L.Status.APPROVED})

    def count_pending_by_dist(self):
        import frappe
        rows = frappe.db.sql("select ifnull(source_dist, ''), count(*) from `tabEC License Machine` "
                             "where status = %s group by source_dist", (L.Status.PENDING,))
        out = {}
        for did, n in rows:
            out[did or ""] = out.get(did or "", 0) + int(n)
        return out

    # ------------------------------------------------------------ trang duyet
    def counts(self, running_since):
        import frappe
        return {"pending": frappe.db.count(L.MACHINE, {"status": L.Status.PENDING}),
                "running": frappe.db.count(L.MACHINE, {"last_seen": [">=", running_since]}),
                "blocked": frappe.db.count(L.MACHINE, {"status": L.Status.BLOCKED}),
                "clone": frappe.db.count(L.MACHINE, {"clone_warning": 1})}

    def search(self, flt, q, order, page):
        """flt: dict filter Frappe da dung o service; q: chuoi tim (host / label / IP / ma may)."""
        import frappe
        or_f = None
        if q:
            like = "%" + q.replace("%", "").replace("_", "\\_") + "%"
            or_f = [[L.MACHINE, f, "like", like] for f in ("name", "host", "label", "last_ip", "win_user")]
        rows = frappe.get_all(L.MACHINE, filters=flt, or_filters=or_f, fields=_LIST_FIELDS, order_by=order,
                              limit_start=page * L.PAGE_SIZE, limit_page_length=L.PAGE_SIZE + 1)
        more = len(rows) > L.PAGE_SIZE
        rows = rows[:L.PAGE_SIZE]
        inst = self._installs([r["name"] for r in rows])
        for r in rows:
            r["installs"] = inst.get(r["name"], [])
        return rows, more

    def children(self, name):
        import frappe
        return frappe.get_all(L.MACHINE, filters={"parent_machine": name}, fields=_LIST_FIELDS,
                              order_by="creation asc", limit_page_length=200)

    def tree_rows(self, dist=None):
        import frappe
        flt = {"source_dist": dist} if dist else {}
        return frappe.get_all(L.MACHINE, filters=flt, fields=["name", "label", "host", "status", "source_dist",
                                                              "parent_machine", "clone_warning", "last_seen"],
                              order_by="creation asc", limit_page_length=2000)

    def labels(self, names):
        import frappe
        names = [n for n in set(names) if n]
        if not names:
            return {}
        return {r["name"]: r.get("label") or r.get("host") or r["name"]
                for r in frappe.get_all(L.MACHINE, filters={"name": ["in", names]}, fields=["name", "label", "host"],
                                        limit_page_length=0)}


def _db(vals):
    out = dict(vals)
    if "fp" in out:
        fp = out.pop("fp") or {}
        out.update(guid_h=fp.get("guid_h") or "", disk_h=fp.get("disk_h") or "",
                   mac_h=json.dumps(fp.get("mac_h") or []))
    for k, v in list(out.items()):
        if k.endswith(("_at", "_seen", "last_checkin")) and isinstance(v, (int, float)) and not isinstance(v, bool):
            out[k] = sys_dt(v) if v else None
    return out


def dt_str(ts):
    """epoch -> 'YYYY-MM-DD HH:MM:SS' gio he thong (cho bo loc / so sanh tren trang)."""
    return sys_dt(ts).strftime("%Y-%m-%d %H:%M:%S")
