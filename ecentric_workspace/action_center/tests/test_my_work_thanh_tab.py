"""/viec-cua-toi: resync phai GIU thanh tab duoi (07/10/2026 - p213/p264/p267 tung xoa mat no).

    python -m pytest ecentric_workspace/action_center/tests/test_my_work_thanh_tab.py
"""
import importlib.util
import pathlib
import sys
import types

APP = pathlib.Path(__file__).resolve().parents[2]


def load(boom=False):
    W = types.SimpleNamespace(written=None, logs=[], calls=[])
    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr.log_error = lambda **k: W.logs.append(k)
    fr.get_traceback = lambda: "tb"
    fr.whitelist = lambda **k: (lambda f: f)
    fr.db = types.SimpleNamespace(exists=lambda *a: False)
    util = types.ModuleType("ecentric_workspace.approval_center.page_sync_util")

    def upsert(route, name, title, html, publish=1):
        W.written = html
        return {"name": None, "action": "updated"}
    util.upsert_web_page = upsert
    tb = types.ModuleType("ecentric_workspace.hr.pages.tab_bar")
    tb.INSERT_TARGETS = {"viec-cua-toi": "#ec-mywork-root"}

    def insert_transform(ms, route, sel):
        W.calls.append((route, sel))
        if boom:
            raise ValueError("source page missing")
        return ms + "<!--ec-tabbar-shared-v1-->"
    tb.insert_transform = insert_transform
    ac = types.ModuleType("ecentric_workspace.approval_center")
    ac.page_sync_util = util
    for n in ("ecentric_workspace", "ecentric_workspace.hr", "ecentric_workspace.hr.pages"):
        sys.modules[n] = types.ModuleType(n)
    sys.modules["ecentric_workspace.hr.pages"].tab_bar = tb
    sys.modules.update({"frappe": fr, "ecentric_workspace.approval_center": ac,
                        util.__name__: util, tb.__name__: tb})
    spec = importlib.util.spec_from_file_location("mw_ps", APP / "action_center/pages/my_work/page_sync.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m, W


def test_sync_gan_thanh_tab_vao_nguon_truoc_khi_ghi():
    m, W = load()
    m.sync()
    assert W.calls == [("viec-cua-toi", "#ec-mywork-root")]
    assert W.written.endswith("<!--ec-tabbar-shared-v1-->") and "data-ec-cho-duyet" in W.written


def test_khong_lay_duoc_thanh_tab_van_sync_va_ghi_log():
    m, W = load(boom=True)
    m.sync()
    assert "data-ec-cho-duyet" in W.written and "ec-tabbar" not in W.written and W.logs
