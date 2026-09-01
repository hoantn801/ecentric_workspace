# Copyright (c) 2026, eCentric and contributors
"""BOT 9 / vong 3 - kiem tra DONG DEU (parity) cho MOI feature trong approval_center/features.

VI SAO CO FILE NAY. Payment Request da duoc soi ba vong; 26 form con lai thi chua, ma tat ca
dung CHUNG mot engine (shared/requests/*, shared/workflow/*). Loi thuong gap nhat o day khong
phai loi logic moi - la COPY THIEU: mot form duoc nhan ban tu form khac va bo sot mot manh.
Cach bat hieu qua nhat khong phai doc tung form, ma la SO CHEO: manh nao 26 form co ma 1 form
khong co.

QUY TAC CUA FILE NAY (rut ra tu bai hoc "form 27 lot danh sach go tay", 31/08):
  * KHONG BAO GIO liet ke ten feature bang tay. Danh sach feature LUON quet tu thu muc
    features/. Them feature moi -> tu dong bi kiem.
  * Moi phep do phai co CHOT SO LUONG (_assert_scanner_alive). Neu refactor lam regex mu
    (tra ve rong), test PHAI do chu khong phai xanh im lang.

BO CUC:
  Nhom A - BAT BIEN CUNG: dung cho MOI feature, hom nay xanh. Feature moi vi pham -> do.
  Nhom B - LO HONG DA CHOT (pinned gaps): tap hop feature dang VI PHAM duoc ghim cung.
    Tap PHINH TO  = co feature moi copy lai khuon sai  -> do (chan lan rong).
    Tap CO LAI    = ai do da sua that                  -> do, kem huong dan go ghim.
    Day khong phai "test khang dinh loi ton tai roi thoi": no la cong chan lan rong + cong
    nhac go ghim, ca hai chieu deu do.

Chay: python3 -m unittest ecentric_workspace.approval_center.tests.standalone.test_e2e3_feature_parity
(khong can bench / frappe that).
"""
import ast
import json
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
# tests/standalone -> tests -> approval_center
CENTER = os.path.dirname(os.path.dirname(_HERE))
FEATURES_DIR = os.path.join(CENTER, "features")
DOCTYPE_DIR = os.path.join(CENTER, "doctype")
MANIFEST = os.path.join(CENTER, "patches", "resync_manifest.json")

LAYER_FILES = (
    ("domain", "definition.py"),
    ("application", "service.py"),
    ("controllers", "api.py"),
    ("infrastructure", "setup.py"),
    ("infrastructure", "activation.py"),
    ("infrastructure", "page_sync.py"),
    ("ui", "main_section.html"),
)

# Toan bo repo hien co 27 form. Con so nay la CHOT: quet ra it hon nghia la phep do hong
# (duong dan sai / thu muc doi ten), khong phai "repo bot form".
MIN_FEATURES = 27

_SM_GATE = re.compile(r'["\']System Manager["\']\s+not\s+in\s+frappe\.get_roles')
_CALL = re.compile(r'call\(\s*["\']([A-Za-z_][A-Za-z0-9_]*)["\']')
_DATA_MODEL = re.compile(r'data-model\s*=\s*\\?["\']([a-z0-9_]+)\\?["\']')
_DATA_CHECKS = re.compile(r'data-checks\s*=\s*\\?["\']([a-z0-9_]+)\\?["\']')
_CAP = re.compile(r'cap\.(can_[a-z_]+)')
_ROUTE = re.compile(r'^ROUTE\s*=\s*["\']([^"\']+)["\']', re.M)


def _read(*parts):
    path = os.path.join(*parts)
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _features():
    names = sorted(
        name for name in os.listdir(FEATURES_DIR)
        if name != "__pycache__" and os.path.isdir(os.path.join(FEATURES_DIR, name)))
    return names


FEATURES = _features()


def _feature_file(feature, layer, filename):
    return os.path.join(FEATURES_DIR, feature, layer, filename)


# --------------------------------------------------------------------------- #
# Be mat API that su cua mot feature
# --------------------------------------------------------------------------- #
def _dict_literal_keys(source, marker):
    """Ten khoa cua dict duoc tra ve / update trong mot module adapter."""
    keys = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key in node.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.add(key.value)
    keys.discard(marker)
    return keys


_ADAPTER_SRC = _read(CENTER, "shared", "api_adapter.py")
_FULFIL_SRC = _read(CENTER, "shared", "fulfillment_api_adapter.py")
ADAPTER_NAMES = {name for name in _dict_literal_keys(_ADAPTER_SRC, None)
                 if not name.startswith("_") or name.startswith("_")}
FULFIL_NAMES = _dict_literal_keys(_FULFIL_SRC, None) | {"set_operation_fields"}


def _api_surface(feature):
    """Ten ma UI cua feature nay co the goi qua namespace api.<feature>.*"""
    source = _read(_feature_file(feature, "controllers", "api.py"))
    names = set()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    if "bind_fulfillment(" in source:
        names |= ADAPTER_NAMES | FULFIL_NAMES
    elif "bind(" in source and "api_adapter" in source:
        names |= ADAPTER_NAMES
    return names, source


# --------------------------------------------------------------------------- #
# ApprovalDefinition: doc bang AST, khong eval module (khong co frappe)
# --------------------------------------------------------------------------- #
def _make_param_map(func):
    """ApprovalDefinition kwarg -> vi tri tham so cua ham _make cuc bo."""
    params = [arg.arg for arg in func.args.args]
    for node in ast.walk(func):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "ApprovalDefinition":
            mapping = {}
            for keyword in node.keywords:
                if (keyword.arg and isinstance(keyword.value, ast.Name)
                        and keyword.value.id in params):
                    mapping[keyword.arg] = params.index(keyword.value.id)
            return mapping, params
    return {}, params


def _definition(feature):
    source = _read(_feature_file(feature, "domain", "definition.py"))
    tree = ast.parse(source)
    funcs = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        target = node.targets[0]
        if not (isinstance(target, ast.Name) and target.id.endswith("_DEFINITION")):
            continue
        call = node.value
        if not isinstance(call, ast.Call):
            continue
        name = getattr(call.func, "id", "")
        raw = {}
        if name == "ApprovalDefinition":
            for keyword in call.keywords:
                if keyword.arg:
                    raw[keyword.arg] = keyword.value
        elif name in funcs:
            mapping, params = _make_param_map(funcs[name])
            by_name = {}
            for index, arg in enumerate(call.args):
                if index < len(params):
                    by_name[params[index]] = arg
            for keyword in call.keywords:
                if keyword.arg:
                    by_name[keyword.arg] = keyword.value
            for def_kwarg, index in mapping.items():
                param = params[index]
                if param in by_name:
                    raw[def_kwarg] = by_name[param]
        out = {}
        for key, value in raw.items():
            try:
                out[key] = ast.literal_eval(value)
            except Exception:
                out[key] = None
        return out
    return {}


def _doctype_slug(doctype):
    return doctype.lower().replace(" ", "_").replace("/", "_")


def _doctype_json(doctype):
    slug = _doctype_slug(doctype)
    path = os.path.join(DOCTYPE_DIR, slug, slug + ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _doctype_controller(doctype):
    slug = _doctype_slug(doctype)
    return os.path.join(DOCTYPE_DIR, slug, slug + ".py")


# --------------------------------------------------------------------------- #
class _Base(unittest.TestCase):
    def _assert_scanner_alive(self, produced, minimum, what):
        """Phep do phai TU CHUNG MINH la con song.

        Bai hoc 31/08: mot bo test doc file ma im lang tra ve rong sau khi reorg thi xanh
        het - va che mat moi loi. Moi vong quet o day deu phai vuot mot nguong toi thieu."""
        self.assertGreaterEqual(
            produced, minimum,
            "phep quet '%s' chi thay %d muc (toi thieu %d): regex/duong dan da mu, "
            "KHONG phai repo sach." % (what, produced, minimum))


# =========================================================================== #
# NHOM A - BAT BIEN CUNG (dung cho moi feature, hom nay xanh)
# =========================================================================== #
class TestFeatureLayout(_Base):
    def test_scan_finds_every_feature(self):
        self._assert_scanner_alive(len(FEATURES), MIN_FEATURES, "features/")

    def test_every_feature_has_the_seven_canonical_files(self):
        missing = []
        for feature in FEATURES:
            for layer, filename in LAYER_FILES:
                if not os.path.exists(_feature_file(feature, layer, filename)):
                    missing.append("%s/%s/%s" % (feature, layer, filename))
        self.assertEqual([], missing, "thieu file khuon chuan: %s" % missing)


class TestSystemManagerGates(_Base):
    """Bai hoc outside_work: mot setup.py bo sot chot System Manager => bat ky nguoi dung
    dang nhap nao cung upsert duoc EC Approval Process (tu dat minh lam cap duyet)."""

    def _gate_scan(self, layer, filename):
        checked, ungated = 0, []
        for feature in FEATURES:
            path = _feature_file(feature, layer, filename)
            source = _read(path)
            # Chi xet phan MA, khong xet docstring/comment: mot dong "# chot System Manager"
            # tung du de qua mat phep grep chuoi.
            code = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
            code = re.sub(r'"""(?:.|\n)*?"""', "", code)
            checked += 1
            if not _SM_GATE.search(code):
                ungated.append(feature)
        return checked, ungated

    def test_every_setup_gates_on_system_manager(self):
        checked, ungated = self._gate_scan("infrastructure", "setup.py")
        self._assert_scanner_alive(checked, MIN_FEATURES, "setup.py")
        self.assertEqual([], ungated, "setup.py KHONG chot System Manager: %s" % ungated)

    def test_every_activation_gates_on_system_manager(self):
        checked, ungated = self._gate_scan("infrastructure", "activation.py")
        self._assert_scanner_alive(checked, MIN_FEATURES, "activation.py")
        self.assertEqual([], ungated, "activation.py KHONG chot System Manager: %s" % ungated)

    def test_every_page_sync_gates_on_system_manager(self):
        checked, ungated = self._gate_scan("infrastructure", "page_sync.py")
        self._assert_scanner_alive(checked, MIN_FEATURES, "page_sync.py")
        self.assertEqual([], ungated, "page_sync.py KHONG chot System Manager: %s" % ungated)


class TestUiWiring(_Base):
    """Moi call("x") trong HTML phai tro toi mot ham CO THAT trong be mat API cua feature.

    Day la phep bat "dut day": mot nut bam goi endpoint khong ton tai chi lo ra khi co nguoi
    bam dung no tren production."""

    def test_every_ui_call_resolves_to_a_real_api_name(self):
        total_calls, broken = 0, {}
        for feature in FEATURES:
            html = _read(_feature_file(feature, "ui", "main_section.html"))
            calls = set(_CALL.findall(html))
            # `call(method, args)` la ham bao noi bo, khong phai ten endpoint.
            calls -= {"call"}
            total_calls += len(calls)
            surface, _src = _api_surface(feature)
            missing = sorted(calls - surface)
            if missing:
                broken[feature] = missing
        self._assert_scanner_alive(total_calls, 250, "call() trong UI")
        self.assertEqual({}, broken, "UI goi endpoint khong ton tai: %s" % broken)

    def test_every_ui_namespace_points_at_an_existing_api_shim(self):
        checked, missing = 0, []
        for feature in FEATURES:
            html = _read(_feature_file(feature, "ui", "main_section.html"))
            for dotted in set(re.findall(
                    r'ecentric_workspace\.approval_center\.api\.([a-z_]+)\.', html)):
                checked += 1
                shim = os.path.join(CENTER, "api", dotted + ".py")
                if not os.path.exists(shim):
                    missing.append("%s -> api/%s.py" % (feature, dotted))
                    continue
                if "features.%s.controllers" % dotted not in _read(shim):
                    missing.append("%s -> api/%s.py khong re-export feature" % (feature, dotted))
        self._assert_scanner_alive(checked, MIN_FEATURES, "namespace API trong UI")
        self.assertEqual([], missing, "namespace UI tro vao khoang khong: %s" % missing)


class TestPageSyncContract(_Base):
    def test_every_feature_html_is_tracked_in_resync_manifest(self):
        with open(MANIFEST, encoding="utf-8") as handle:
            manifest = json.load(handle)
        missing = [f for f in FEATURES
                   if "approval_center/features/%s/ui/main_section.html" % f not in manifest]
        self._assert_scanner_alive(len(manifest), MIN_FEATURES, "resync_manifest.json")
        self.assertEqual([], missing,
                         "HTML khong nam trong resync_manifest -> sua HTML se khong ai biet "
                         "phai deploy lai: %s" % missing)

    def test_activation_route_matches_page_sync_route(self):
        checked, mismatched = 0, []
        for feature in FEATURES:
            act = _ROUTE.search(_read(_feature_file(feature, "infrastructure", "activation.py")))
            page = _ROUTE.search(_read(_feature_file(feature, "infrastructure", "page_sync.py")))
            if not (act and page):
                mismatched.append("%s: thieu hang ROUTE" % feature)
                continue
            checked += 1
            if act.group(1) != page.group(1):
                mismatched.append("%s: activation=%s page_sync=%s"
                                  % (feature, act.group(1), page.group(1)))
        self._assert_scanner_alive(checked, MIN_FEATURES, "ROUTE")
        self.assertEqual([], mismatched,
                         "the phe duyet se tro toi trang 404: %s" % mismatched)


class TestDoctypeContract(_Base):
    def test_every_definition_doctype_has_json_and_controller(self):
        checked, problems = 0, []
        for feature in FEATURES:
            definition = _definition(feature)
            doctype = definition.get("business_doctype")
            if not doctype:
                problems.append("%s: khong doc duoc business_doctype" % feature)
                continue
            checked += 1
            if _doctype_json(doctype) is None:
                problems.append("%s: thieu %s.json" % (feature, _doctype_slug(doctype)))
            if not os.path.exists(_doctype_controller(doctype)):
                problems.append("%s: thieu controller .py" % feature)
        self._assert_scanner_alive(checked, MIN_FEATURES, "business_doctype")
        self.assertEqual([], problems, "%s" % problems)

    def test_every_reqd_field_is_editable_and_bound_in_the_form(self):
        """reqd=1 tren DocType nhung khong nam trong editable_fields => save_draft khong bao
        gio ghi duoc no => phieu khong bao gio luu duoc. Va reqd=1 nhung form khong co o
        nhap => nguoi dung khong co cach nao dien."""
        total_reqd, problems = 0, []
        for feature in FEATURES:
            definition = _definition(feature)
            doctype = definition.get("business_doctype")
            schema = _doctype_json(doctype) if doctype else None
            if not schema:
                continue
            required = [f["fieldname"] for f in schema.get("fields", []) if f.get("reqd")]
            total_reqd += len(required)
            editable = set(definition.get("editable_fields") or ())
            html = _read(_feature_file(feature, "ui", "main_section.html"))
            bound = set(_DATA_MODEL.findall(html)) | set(_DATA_CHECKS.findall(html))
            for fieldname in required:
                if editable and fieldname not in editable:
                    problems.append("%s.%s: reqd=1 nhung khong o editable_fields"
                                    % (feature, fieldname))
                if fieldname not in bound:
                    problems.append("%s.%s: reqd=1 nhung form khong co o nhap"
                                    % (feature, fieldname))
        self._assert_scanner_alive(total_reqd, 120, "truong reqd=1")
        self.assertEqual([], problems, "%s" % problems)


class TestApprovalProcessSeed(_Base):
    def test_no_feature_seeds_a_zero_level_process(self):
        """0 cap duyet = gui la duyet xong. Khong form nao duoc phep nhu vay."""
        counts, zero = {}, []
        for feature in FEATURES:
            source = _read(_feature_file(feature, "infrastructure", "setup.py"))
            levels = len(re.findall(r'level_name["\']?\s*[:=]', source))
            counts[feature] = levels
            if levels == 0:
                zero.append(feature)
        self._assert_scanner_alive(sum(counts.values()), MIN_FEATURES, "level_name")
        self.assertEqual([], zero, "setup khong tao cap duyet nao: %s" % zero)

    def test_every_setup_creates_the_process_in_draft(self):
        """Setup KHONG duoc tu bat process Active - viec do thuoc activation.py (2 buoc,
        dry-run mac dinh). Mot setup tu Active hoa la mot form len song khong qua UAT."""
        offenders = [f for f in FEATURES
                     if re.search(r'\.status\s*=\s*["\']Active["\']',
                                  _read(_feature_file(f, "infrastructure", "setup.py")))]
        self.assertEqual([], offenders, "setup.py tu bat Active: %s" % offenders)


# =========================================================================== #
# NHOM B - LO HONG DA CHOT
# =========================================================================== #
def _dead_end_features():
    """Form co hien nut 'Yeu cau bo sung' cho cap duyet NHUNG khong co duong quay lai
    cho nguoi de nghi (khong nhanh cap.can_edit -> resubmit)."""
    offenders = []
    for feature in FEATURES:
        html = _read(_feature_file(feature, "ui", "main_section.html"))
        caps = set(_CAP.findall(html))
        if "can_request_information" in caps and "can_edit" not in caps:
            offenders.append(feature)
    return sorted(offenders)


def _no_cancel_features():
    offenders = []
    for feature in FEATURES:
        caps = set(_CAP.findall(_read(_feature_file(feature, "ui", "main_section.html"))))
        if "can_cancel" not in caps:
            offenders.append(feature)
    return sorted(offenders)


def _department_unlocked_features():
    """department nam trong editable_fields (nguoi de nghi ghi duoc qua save_draft, ke ca o
    trang thai 'Information Required') MA controller DocType khong khoa snapshot."""
    offenders = []
    for feature in FEATURES:
        definition = _definition(feature)
        doctype = definition.get("business_doctype")
        if not doctype:
            continue
        if "department" not in set(definition.get("editable_fields") or ()):
            continue
        controller = _doctype_controller(doctype)
        source = _read(controller) if os.path.exists(controller) else ""
        if "snapshot_lock" not in source:
            offenders.append(feature)
    return sorted(offenders)


def _no_drift_lock_features():
    offenders = []
    for feature in FEATURES:
        source = _read(_feature_file(feature, "infrastructure", "page_sync.py"))
        if "expect_sha" not in source:
            offenders.append(feature)
    return sorted(offenders)


def _fulfillment_features():
    out = []
    for feature in FEATURES:
        if "def claim_fulfillment" in _read(_feature_file(feature, "application", "service.py")):
            out.append(feature)
    return sorted(out)


def _narrow_fulfiller_gate_features():
    """Form co hang doi xu ly nhung cong claim KHONG chap nhan 'Fulfiller da cau hinh tren
    EC Approval Process' - chi chap nhan ToDo dang mo hoac System Manager."""
    offenders = []
    for feature in _fulfillment_features():
        source = _read(_feature_file(feature, "application", "service.py"))
        if "is_active_process_fulfiller" not in source:
            offenders.append(feature)
    return sorted(offenders)


def _no_submit_amount_guard_features():
    """Form co truong tien (Currency) MA duong submit cua no khong he kiem tra gia tri tien."""
    offenders = []
    for feature in FEATURES:
        definition = _definition(feature)
        doctype = definition.get("business_doctype")
        schema = _doctype_json(doctype) if doctype else None
        if not schema:
            continue
        money = [f["fieldname"] for f in schema.get("fields", [])
                 if f.get("fieldtype") in ("Currency", "Float")
                 and not f["fieldname"].startswith(("actual_", "approved_"))]
        if not money:
            continue
        service = _read(_feature_file(feature, "application", "service.py"))
        controller_path = _doctype_controller(doctype)
        controller = _read(controller_path) if os.path.exists(controller_path) else ""
        blob = service + "\n" + controller
        # Nhieu form so sanh qua bien cuc bo (`val = float(doc.get(f) or 0); if val < 0`)
        # hoac qua vong lap tren mot tuple ten truong, nen khong the bat dinh danh ke ben
        # dau so sanh. Tieu chi: co nhac truong tien VA co it nhat mot phep so voi 0.
        mentions_money = any(name in blob for name in money)
        # Phep so voi 0 phai DAN TOI mot loi tu choi, neu khong no chi la bien dem vong lap
        # (contract_review co `while left > 0:` va khong he chan gia tri hop dong).
        lines = blob.splitlines()
        rejects_on_zero = any(
            re.search(r'(<=|<|>=|>)\s*0\b', line) and "frappe.throw" in "\n".join(lines[i:i + 3])
            for i, line in enumerate(lines))
        if not (mentions_money and rejects_on_zero):
            offenders.append(feature)
    return sorted(offenders)


class TestPinnedGaps(_Base):
    """Moi tap duoi day duoc GHIM. Phinh to = lan rong khuon sai. Co lai = da sua that."""

    def _assert_pinned(self, actual, expected, story):
        actual, expected = sorted(actual), sorted(expected)
        added = sorted(set(actual) - set(expected))
        removed = sorted(set(expected) - set(actual))
        self.assertEqual(
            expected, actual,
            "%s\n  MOI VI PHAM (khuon sai vua lan sang): %s\n"
            "  DA SUA (go khoi ghim trong test nay): %s" % (story, added, removed))

    def test_pinned_sendback_dead_end_forms(self):
        self._assert_pinned(
            _dead_end_features(),
            ["employee_info_update", "livestream_supplies", "service_referral"],
            "NGO CUT TRA-LAI: cap duyet bam 'Yeu cau bo sung' duoc, nhung man hinh chi tiet "
            "cua nguoi de nghi khong co nhanh cap.can_edit -> khong co nut sua & gui lai. "
            "Backend CO endpoint resubmit (api_adapter.bind) - chi UI thieu nut.")

    def test_pinned_forms_without_cancel_button(self):
        self._assert_pinned(
            _no_cancel_features(),
            ["employee_info_update", "livestream_supplies", "service_referral"],
            "KHONG CO NUT HUY: nguoi de nghi (va ca System Manager) khong huy duoc yeu cau "
            "tu man hinh form; capabilities.derive VAN tra can_cancel.")

    def test_pinned_department_snapshot_unlocked_forms(self):
        self._assert_pinned(
            _department_unlocked_features(),
            ["affiliate_bonus", "asset_damage_loss", "asset_request", "budget_setting",
             "compensation_leave", "employee_referral", "hiring_request", "hr_activity",
             "late_early_out", "leave", "livestream_sample", "payment_request", "promotion",
             "purchase_request", "resignation", "special_bonus", "system_request"],
            "PHONG BAN DOI DUOC SAU KHI GUI: command_service.save_draft ghi moi truong trong "
            "editable_fields va CHO PHEP chay o trang thai 'Information Required'; 8 form khac "
            "chan bang _department_snapshot_lock trong controller DocType, 17 form nay thi khong. "
            "department la truong lai visibility (EC Viewer Permission) va dinh tuyen L1.")

    def test_pinned_page_sync_without_drift_lock(self):
        self._assert_pinned(
            _no_drift_lock_features(),
            ["contract_review"],
            "THIEU KHOA DRIFT: page_sync khong truyen expect_sha, nen mot lan goi sync se GHI DE "
            "ban live ke ca khi co nguoi da sua truc tiep tren site. 26 page_sync khac deu co.")

    def test_pinned_narrow_fulfiller_gate(self):
        self._assert_pinned(
            _narrow_fulfiller_gate_features(),
            ["ai_topup", "resignation"],
            "CONG CLAIM HEP HON ANH EM: 4/6 form co hang doi chap nhan "
            "engine.is_active_process_fulfiller(...) lam duong vao thu hai. Hai form nay chi "
            "chap nhan ToDo dang mo -> Fulfiller da cau hinh nhung mat ToDo se khong nhan viec "
            "duoc, yeu cau ket trong hang doi cho toi khi System Manager vao tay.")

    def test_pinned_money_forms_without_submit_amount_guard(self):
        self._assert_pinned(
            _no_submit_amount_guard_features(),
            ["ai_topup", "contract_review"],
            "FORM TIEN KHONG CHAN SO TIEN. ai_topup: requested_amount (Currency) khong co "
            "reqd=1 tren DocType, service.submit() khong kiem tra, controller cung khong -> "
            "gui duoc phieu voi so tien rong / am, va approved_amount duoc mac dinh bang no. "
            "contract_review: contract_value co reqd=1 nhung khong he kiem dau -> gia tri am "
            "di qua. 9 form tien con lai deu chan.")

    def test_fulfillment_scan_is_alive(self):
        self._assert_scanner_alive(len(_fulfillment_features()), 6, "claim_fulfillment")


if __name__ == "__main__":
    unittest.main()
