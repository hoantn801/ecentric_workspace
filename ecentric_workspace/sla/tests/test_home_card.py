# Copyright (c) 2026, eCentric and contributors
"""Bo nap widget SLA tren trang chu - chay bang python3 tran.

    python3 -m unittest ecentric_workspace.sla.tests.test_home_card -v

VI SAO MOT BO NAP BON DONG LAI CAN TEST. Trang chu la trang DUY NHAT khong co
ban HTML trong repo: moi lan patch ghi vao no la mot lan khong hoan tac duoc
bang git. Va kieu hong o day hoan toan im lang - go sai duong dan tai san thi
the <script> van duoc cam vao trang, trinh duyet tai ve 404, khong co loi nao
o phia may chu, va o "KPI QUY 0%" cu nam do nhu chua co gi xay ra.

Test nay doc tep patch bang AST chu khong import no: import se keo `frappe`
vao, va ca bo test cua module SLA deu chay duoc khong can bench.
"""
import ast
import io
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))          # .../ecentric_workspace
PATCH = os.path.join(APP, "sla", "patches", "p006_home_sla_card.py")


def _consts(path):
    """Hang so cap module cua mot tep, doc bang AST (khong import, khong frappe)."""
    with io.open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=path)
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        try:
            value = ast.literal_eval(node.value)
        except Exception:
            continue
        for t in node.targets:
            if isinstance(t, ast.Name):
                out[t.id] = value
    return out


class TestLoaderContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = _consts(PATCH)

    def test_asset_file_actually_exists(self):
        """Duong dan trong the <script> phai tro toi mot tep co that.

        Day la phep kiem dat gia nhat cua tep nay. Frappe phuc vu
        /assets/ecentric_workspace/... thang tu public/, khong qua bundle, nen
        khong co buoc build nao bao loi khi ten tep sai.
        """
        loader = self.c["LOADER"]
        prefix = 'src="/assets/ecentric_workspace/'
        i = loader.find(prefix)
        self.assertGreater(i, -1, "bo nap phai tro toi tai san cua chinh app nay")
        tail = loader[i + len(prefix):].split('"')[0]
        self.assertTrue(os.path.isfile(os.path.join(APP, "public", *tail.split("/"))),
                        "khong co tep public/%s" % tail)

    def test_marker_is_a_prefix_of_the_loader(self):
        # Kiem tra chay-lai-duoc dua vao `MARKER in val`. Neu moc khong phai la
        # mot phan cua chuoi duoc cam vao thi lan chay thu hai se cam them mot
        # ban nua - va trang chu se tai widget hai lan, mai mai.
        self.assertTrue(self.c["LOADER"].startswith(self.c["MARKER"]))

    def test_loader_carries_no_jinja(self):
        # Trang chu giu `dynamic_template=1`: chuoi cam vao DI QUA bo render
        # Jinja. Mot dau `{{` lac vao day se lam hong ca trang chu, khong phai
        # chi mot o.
        for token in ("{{", "}}", "{%", "%}"):
            self.assertNotIn(token, self.c["LOADER"])

    def test_writes_both_fields(self):
        self.assertEqual(tuple(self.c["TARGET_FIELDS"]),
                         ("main_section", "main_section_html"))


class TestPatchIsFailSafe(unittest.TestCase):
    """`execute()` khong duoc nem gi ra ngoai: mot patch nem loi chan ca ban deploy."""

    def test_execute_wraps_everything(self):
        with io.open(PATCH, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=PATCH)
        fn = [n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "execute"]
        self.assertEqual(len(fn), 1)
        body = fn[0].body
        self.assertEqual(len(body), 1, "than ham execute() phai la DUY NHAT mot try")
        self.assertIsInstance(body[0], ast.Try)
        handlers = body[0].handlers
        self.assertEqual(len(handlers), 1)
        # `except Exception` chu khong phai mot loai hep: cai ta muon chan la
        # "bat ky thu gi", vi cai gia cua mot loi lot ra la ca ban deploy.
        self.assertIsInstance(handlers[0].type, ast.Name)
        self.assertEqual(handlers[0].type.id, "Exception")
        self.assertFalse(any(isinstance(n, ast.Raise)
                             for n in ast.walk(handlers[0])),
                         "nhanh xu ly loi khong duoc nem lai")


class TestWidgetSource(unittest.TestCase):
    """Vai rang buoc cua tep JS ma khong co bo kiem nao khac bat duoc."""

    @classmethod
    def setUpClass(cls):
        with io.open(os.path.join(APP, "public", "js", "sla_home_card.js"),
                     encoding="utf-8") as fh:
            cls.src = fh.read()
        # Bo cac dong CHU THICH truoc khi soi cu phap. Chu thich duoc phep chua
        # dau `...` de trich ten bien - cai bi cam la template literal trong
        # MA NGUON. Khong tach hai thu nay ra thi phep kiem se cam ca viec viet
        # chu thich cho tu te, va nguoi sau se xoa no thay vi sua.
        cls.code = "\n".join(l for l in cls.src.split("\n")
                             if not l.lstrip().startswith("//"))

    def test_no_template_literals(self):
        # Quy uoc cua cac widget trang chu: ES5, noi chuoi. Trang chu chay qua
        # Jinja va tung phuc vu ca trinh duyet cu.
        self.assertNotIn("`", self.code)
        self.assertNotIn("${", self.code)

    def test_no_es6_syntax(self):
        # Vai dau hieu ES6 de lot qua review nhat.
        for token in ("=>", "let ", "const ", "..."):
            self.assertNotIn(token, self.code, "khong dung ES6: %r" % token)

    def test_no_jinja_tokens(self):
        for token in ("{{", "{%"):
            self.assertNotIn(token, self.src)

    def test_reads_the_same_endpoint_as_the_sla_page(self):
        # Mot nguon so duy nhat. Neu o day tu goi endpoint khac (hoac tu cong
        # tru) thi trang chu va /sla se noi hai con so khac nhau ve cung mot
        # nguoi, va ca hai deu mat gia tri.
        self.assertIn("ecentric_workspace.sla.controllers.api.my_board", self.src)

    def test_restores_the_card_on_failure(self):
        self.assertIn("card.innerHTML = original", self.src)

    def test_has_an_install_guard_and_a_retry_ceiling(self):
        self.assertIn("_ecSlaCardInstalled", self.src)
        self.assertIn("clearInterval", self.src)


if __name__ == "__main__":
    unittest.main()
