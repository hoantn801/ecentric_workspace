# Copyright (c) 2026, eCentric and contributors
"""Host QC: dien lai mac dinh Host QC Settings.

p001 (24/11) goi set_defaults so voi frappe.get_single(); Single chua luu dong nao thi get_single tra mac dinh
DocType trong bo nho nen khong luu gi -> tren site diem tru / nguong / bang chung deu = 0 (moi phien GREEN,
khong tru diem). Patch nay ghi moi o dang trong/0 bang mac dinh trong DocType JSON (+ SETTINGS_DEFAULTS cua
p001), roi doi rules_version de may tai lai luat. Bo qua Check va Password; khong dong vao o da co gia tri."""
import frappe

from ecentric_workspace.host_qc.constants import doctypes as DT
from ecentric_workspace.host_qc.patches.p001_setup import SETTINGS_DEFAULTS
from ecentric_workspace.host_qc.repositories.settings_repository import SettingsRepository
from ecentric_workspace.host_qc.services.bump_rules_version_service import BumpRulesVersionService

NUMERIC = ("Int", "Float", "Percent", "Currency")
SKIP = ("Check", "Password", "Table", "Table MultiSelect", "Section Break", "Column Break", "Tab Break", "HTML")


def execute():
    filled = SettingsRepository().set_defaults(meta_defaults() | SETTINGS_DEFAULTS)
    BumpRulesVersionService().execute()
    if filled:
        print("host_qc p002: dien %d o Settings: %s" % (len(filled), ", ".join(filled)))


def meta_defaults():
    out = {}
    for f in frappe.get_meta(DT.SETTINGS).fields:
        if f.fieldtype in SKIP or f.default in (None, "") or f.read_only:
            continue
        out[f.fieldname] = (float(f.default) if f.fieldtype != "Int" else int(f.default)) if f.fieldtype in NUMERIC \
            else f.default
    return out
