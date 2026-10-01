"""p244: them Fulfiller vao 2 process Daily Target dang CUNG Active ma KHONG goi save()
(save bi validate chan - ly do p242 hong tren production 01/10/2026). Idempotent.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_p244_daily_target_fulfiller.py
"""
import importlib.util
import pathlib
import sys
import types

APP = pathlib.Path(__file__).resolve().parents[3]


class Obj(dict):
    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v


def load():
    st = types.SimpleNamespace(roles=set(), rows={"DAILY_TARGET_PROJECT-V1": [Obj(participant_purpose="Approver", role=None, idx=1)],
                                                  "DAILY_TARGET_CONSOLIDATED-V1": []},
                               saved=0, logs=[])
    fr = types.ModuleType("frappe")

    class Doc(Obj):
        def insert(self, ignore_permissions=False):
            st.roles.add(self["role_name"])

        def db_insert(self):
            st.rows[self["parent"]].append(Obj(self))

        def save(self, *a, **k):
            st.saved += 1
            raise AssertionError("khong duoc save process")
    fr.new_doc = lambda dt: Doc(doctype=dt)
    fr.get_doc = lambda d: Doc(d)
    fr.get_all = lambda dt, filters=None, fields=None: list(st.rows[filters["parent"]])

    def exists(dt, name):
        return name in st.roles if dt == "Role" else name in st.rows
    fr.db = types.SimpleNamespace(exists=exists, commit=lambda: None, rollback=lambda: None,
                                  set_value=lambda *a, **k: None)
    fr.utils = types.SimpleNamespace(now=lambda: "2026-10-01 16:00:00")
    fr.get_traceback = lambda: "tb"
    fr.log_error = lambda title=None, message=None: st.logs.append(message)
    sys.modules["frappe"] = fr
    spec = importlib.util.spec_from_file_location(
        "p244", APP / "approval_center/patches/p244_daily_target_fulfiller_khong_qua_save.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m, st


def test_them_fulfiller_ca_hai_process_khong_save_va_idempotent():
    m, st = load()
    m.execute()
    assert st.roles == {"EC Data Team"} and st.saved == 0
    for code, rows in st.rows.items():
        ful = [r for r in rows if r.participant_purpose == "Fulfiller"]
        assert len(ful) == 1 and ful[0].role == "EC Data Team" and ful[0].source_type == "Role", code
        assert ful[0].parentfield == "participants"
    assert st.rows["DAILY_TARGET_PROJECT-V1"][-1].idx == 2
    m.execute()
    assert sum(r.participant_purpose == "Fulfiller" for rs in st.rows.values() for r in rs) == 2
    assert "LOI" not in st.logs[-1]
