"""Immutable adapters used by declarative request definitions."""
from dataclasses import dataclass
from importlib import import_module


@dataclass(frozen=True, slots=True)
class ServiceMethod:
    module: str
    method: str

    def __call__(self, *args, **kwargs):
        return getattr(import_module(self.module), self.method)(*args, **kwargs)


@dataclass(frozen=True, slots=True)
class ExactAndDateFilters:
    fields: tuple = ()
    like_fields: tuple = ()

    def __call__(self, target, supplied):
        for fieldname in self.fields:
            if supplied.get(fieldname):
                target[fieldname] = supplied[fieldname]
        for fieldname in self.like_fields:
            if supplied.get(fieldname):
                target[fieldname] = ["like", "%%%s%%" % supplied[fieldname]]
        if supplied.get("from_date") and supplied.get("to_date"):
            target["creation"] = ["between", [supplied["from_date"], supplied["to_date"]]]


@dataclass(frozen=True, slots=True)
class BrandOptions:
    """Static options + the live Brand master list.

    Brand was a free-text box, so the same brand arrived spelled several ways and could not
    be filtered or grouped. Reads the standard `Brand` DocType (permission-checked by
    frappe.get_all) and exposes it as `brands`; falls back to the static entries alone if the
    DocType is unavailable, so a form never breaks over a lookup."""
    entries: tuple = ()

    def __call__(self):
        out = {key: list(values) for key, values in self.entries}
        try:
            import frappe
            rows = frappe.get_all("Brand", fields=["name", "ec_brand_name", "ec_status"],
                                  order_by="name asc", limit_page_length=0)
            active = [r for r in rows if (r.get("ec_status") or "Active") == "Active"] or rows
            # value = mã brand (khớp dữ liệu đang lưu); label = "MÃ — Tên" cho dễ chọn.
            out["brands"] = [{"value": r["name"],
                              "label": ("%s — %s" % (r["name"], r["ec_brand_name"]))
                                       if r.get("ec_brand_name") and r["ec_brand_name"] != r["name"]
                                       else r["name"]}
                             for r in active]
        except Exception:
            out.setdefault("brands", [])
        return out


@dataclass(frozen=True, slots=True)
class BrandAndDepartmentOptions:
    """Compose BrandOptions + DepartmentOptions cho form cần cả hai (Contract Review:
    brand để chọn legal entity, department để Sale admin tạo giúp phòng ban khác)."""
    entries: tuple = ()

    def __call__(self):
        out = BrandOptions(self.entries)()
        try:
            out.update(DepartmentOptions()())
        except Exception:
            out.setdefault("departments", [])
        return out


@dataclass(frozen=True, slots=True)
class StaticOptions:
    entries: tuple = ()

    def __call__(self):
        return {key: list(values) for key, values in self.entries}


def service_callbacks(feature, title=False):
    base = "ecentric_workspace.approval_center.features.%s.application.service" % feature
    return {
        "title_builder": ServiceMethod(base, "gen_title") if title else None,
        "submitter": ServiceMethod(base, "submit"),
        "resubmitter": ServiceMethod(base, "resubmit"),
    }


@dataclass(frozen=True, slots=True)
class DepartmentOptions:
    extra_entries: tuple = ()

    def __call__(self):
        import frappe
        filters = {}
        meta = frappe.get_meta("Department")
        if meta.has_field("disabled"):
            filters["disabled"] = 0
        if meta.has_field("is_group"):
            filters["is_group"] = 0
        rows = frappe.get_all(
            "Department", filters=filters, fields=["name", "department_name"],
            order_by="department_name asc", limit_page_length=0)
        result = {"departments": [
            {"value": row.name, "label": row.department_name or row.name} for row in rows]}
        result.update({key: list(values) for key, values in self.extra_entries})
        return result


@dataclass(frozen=True, slots=True)
class DepartmentRows:
    def __call__(self):
        import frappe
        return frappe.get_all(
            "Department", filters={"disabled": 0}, fields=["name", "department_name"],
            order_by="department_name asc", limit_page_length=0)


