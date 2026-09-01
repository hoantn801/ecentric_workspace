# Copyright (c) 2026, eCentric and contributors
"""Vòng 3 — BOT 8: nhắc việc (ToDo) + thông báo quanh Payment Request / esign.

Cổng QC cũ (`action_center/tests/test_no_desk_urls.py`) giữ đúng MỘT nửa đường: con
đường ToDo → Action Center. Nửa còn lại — con đường Notification Log → chuông — chưa
ai canh, và nó có bộ dựng URL RIÊNG (`notification_center/resolvers._action_url`).
Hai bộ dựng cùng nhìn một `(document_type, document_name)` mà trả hai đích khác nhau:
Action Center trả `/pm#task/X`, chuông trả `/app/task/X`. Cùng một công việc, một nơi
mở được, một nơi 403.

Bộ test này giữ 7 điều:

  1. chuông KHÔNG BAO GIỜ trả link `/app/` — cùng luật với cổng QC ToDo;
  2. chuông và Action Center phải TRẢ CÙNG MỘT ĐÍCH cho cùng một chứng từ;
  3. `action_url` cổng phát thông báo đã tính đúng thì phải được LƯU (`link`), vì
     hộp thư đọc lại từ DB chứ không đọc từ lúc phát;
  4. máy quét ToDo producer phải đọc được HẰNG SỐ, không chỉ chuỗi trần — hiện nó
     mù hoàn toàn với hai producer của esign;
  5. mọi transition ĐÓNG phiếu phải có người được báo — `complete_approval` đang câm;
  6. `resubmit` phải khoá máy trạng thái như approve/reject/cancel/request_information;
  7. chân ký hỏng / nợ chữ ký phải chạm được tới MỘT NGƯỜI, không chỉ nằm trên trang ops.

Chạy KHÔNG cần bench:
    python3 -m unittest ecentric_workspace.approval_center.tests.standalone.test_e2e3_todo_notify

GHI CHÚ TRUNG THỰC: phần lớn test ở đây ĐANG ĐỎ. Chúng mô tả hợp đồng ĐÚNG, không
mô tả hành vi hiện tại. Xem V3_BOT8_NOTIFY_TODO.md để biết lỗ nào ứng với test nào.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))


def _root():
    """Gốc gói `ecentric_workspace` (thư mục chứa platform/esign)."""
    root = _HERE
    for _i in range(8):
        if os.path.isdir(os.path.join(root, "platform", "esign")):
            return root
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    raise AssertionError("khong tim thay goc ecentric_workspace")


_ROOT = _root()
_REPO = os.path.dirname(_ROOT)          # thư mục chứa gói -> đủ để import


def _read(*parts):
    p = os.path.join(_ROOT, *parts)
    with io.open(p, encoding="utf-8") as fh:
        return fh.read()


# --------------------------------------------------------------------------- #
# frappe giả — dùng chung cho các test hành vi
# --------------------------------------------------------------------------- #
class _D(dict):
    """Giống `frappe._dict`: đọc được bằng cả `r["x"]` lẫn `r.x`.

    Bản giả trả `dict` trần thì `r.name` ném AttributeError và test đỏ ở chỗ mã
    nguồn hoàn toàn đúng — một bản giả lệch với thật thì nó đỏ ở chỗ nó nên xanh.
    """

    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)


def _install_frappe_stub():
    """Cài `frappe` tối thiểu vào sys.modules (đủ cho hai module resolvers)."""
    fk = types.ModuleType("frappe")
    fk.__path__ = []
    fk.local = types.SimpleNamespace()
    fk.db = types.SimpleNamespace(get_value=lambda *a, **kw: None)
    fk.log_error = lambda *a, **kw: None
    fk.cache = lambda: types.SimpleNamespace(
        get_value=lambda k: None, set_value=lambda k, v, expires_in_sec=None: None)

    class _F(dict):
        @property
        def fieldtype(self):
            return self.get("fieldtype")

        @property
        def options(self):
            return self.get("options")

    class _Meta(object):
        """Form do Approval Engine quản: khai Link `approval_request` -> EC Approval
        Request. Đúng metadata mà has_engine_approval_link đọc ngoài production."""

        def __init__(self, dt):
            self.dt = dt

        def get_field(self, fn):
            if fn == "approval_request" and self.dt.startswith("EC "):
                return _F({"fieldtype": "Link", "options": "EC Approval Request"})
            return None

        def get_title_field(self):
            return "name"

        def has_field(self, fn):
            return self.get_field(fn) is not None

    fk.get_meta = lambda dt: _Meta(dt)

    # Nhường quyền cài `frappe` giả cho cổng QC có sẵn NẾU nó chưa chạy.
    # Lý do: `action_center/tests/test_no_desk_urls.py` dùng
    # `sys.modules.setdefault("frappe", _fk)` rồi ở `TestUnmappedReporting` nó gán
    # `_fk.log_error = ...` để đếm. Nếu module này cài bản giả trước thì `_fk` của
    # nó thành mồ côi, phép gán không tới được thứ đang chạy, và test CỦA NÓ đỏ
    # trong khi mã nguồn không đổi gì — đúng kiểu "test đỏ vì bản giả, không vì
    # mã nguồn". Nạp nó trước làm kết quả độc lập với thứ tự chạy.
    if "frappe" not in sys.modules:
        try:
            __import__("ecentric_workspace.action_center.tests.test_no_desk_urls")
        except Exception:
            pass

    live = sys.modules.get("frappe")
    if live is None:
        sys.modules["frappe"] = fk
        return fk
    if getattr(live, "__file__", None):
        return live                       # frappe THAT (chay duoi bench) -> khong dung vao
    # Mot module test khac da cai ban gia frappe cua rieng no vao process nay
    # (vd action_center/tests/test_no_desk_urls.py). Ban gia do hep hon: `_Meta`
    # cua no chi coi "EC ... Request" la form co Link approval_request, nen
    # "EC Digital Signature Package" bi coi nhu DocType la va test o day do vi
    # BAN GIA chu khong vi ma nguon. Ghi de get_meta bang ban rong hon -- van dung
    # cho moi khang dinh cua module kia (sieu tap), va lam ket qua doc lap voi
    # THU TU CHAY.
    live.get_meta = fk.get_meta
    for attr in ("db", "cache", "log_error", "local"):
        if not hasattr(live, attr):
            setattr(live, attr, getattr(fk, attr))
    return live


_FK = _install_frappe_stub()
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from ecentric_workspace.action_center import resolvers as AC          # noqa: E402
from ecentric_workspace.notification_center import resolvers as NC    # noqa: E402


def _todo(ref_type, ref_name, desc="", name="td-1"):
    return {"name": name, "reference_type": ref_type, "reference_name": ref_name,
            "description": desc, "priority": "Medium", "modified": "", "date": ""}


def _log(document_type, document_name, link=""):
    """Một dòng Notification Log ĐÚNG NHƯ publish_notification_event ghi ra.

    Chú ý `link`: mặc định RỖNG. Đó không phải giả định của test — hàm phát
    thông báo không hề map trường này (xem TestActionUrlIsPersisted)."""
    return {"name": "nl-1", "subject": "s", "email_content": "m",
            "document_type": document_type, "document_name": document_name,
            "from_user": "a@x.vn", "read": 0, "type": "Alert",
            "creation": "2026-09-01 10:00:00", "link": link}


# --------------------------------------------------------------------------- #
# tiện ích AST — đọc CÂY, không grep chữ
# --------------------------------------------------------------------------- #
def _fn_node(src, name, cls=None):
    """Node hàm `name` (tuỳ chọn: bên trong class `cls`). Ném nếu không có."""
    tree = ast.parse(src)
    scopes = [tree]
    if cls:
        scopes = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls]
    for scope in scopes:
        for node in ast.walk(scope):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
    raise AssertionError("khong tim thay ham %s" % name)


def _called_names(node):
    """Mọi tên hàm được GỌI trong `node` (cả `a.b.c(...)` -> {'c','b.c','a.b.c'})."""
    out = set()
    for n in ast.walk(node):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        parts = []
        while isinstance(f, ast.Attribute):
            parts.insert(0, f.attr)
            f = f.value
        if isinstance(f, ast.Name):
            parts.insert(0, f.id)
        if not parts:
            continue
        for i in range(len(parts)):
            out.add(".".join(parts[i:]))
    return out


def _uses_kwarg(node, kwarg):
    """`node` có lời gọi nào truyền keyword `kwarg` không (đọc cây, không grep chữ)."""
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and any(k.arg == kwarg for k in n.keywords):
            return True
    return False


def _module_consts(tree):
    """{ten: chuoi} cho mọi gán hằng chuỗi ở cấp module (kể cả gán nhiều tên)."""
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            continue
        for t in node.targets:
            if isinstance(t, ast.Name):
                out[t.id] = node.value.value
    return out


def _dict_literal(node, consts):
    """dict literal -> {khoa_chuoi: gia_tri_chuoi}, giải hằng số qua `consts`.

    Đây là điểm khác cốt lõi so với máy quét regex của cổng QC hiện có: giá trị
    viết bằng TÊN HẰNG (`"reference_type": DSR`) vẫn đọc ra được."""
    out = {}
    if not isinstance(node, ast.Dict):
        return out
    for k, v in zip(node.keys, node.values):
        if not (isinstance(k, ast.Constant) and isinstance(k.value, str)):
            continue
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            out[k.value] = v.value
        elif isinstance(v, ast.Name) and v.id in consts:
            out[k.value] = consts[v.id]
    return out


def _scan_todo_producers_ast():
    """Mọi DocType mà repo này TẠO ToDo tới, đọc bằng AST.

    Bắt ba hình dạng:
      * `frappe.get_doc({"doctype": "ToDo", "reference_type": <chuoi hoac HANG>})`
      * `assign_to.add({"doctype": <DocType dich>, "assign_to": [...]})` — Frappe
        tự đặt reference_type = doctype đó; máy quét cũ chỉ tình cờ bắt được
        `EC Order Retry` nhờ một bộ lọc dedupe nằm ngay bên trên, không phải nhờ
        nhận ra hình dạng này;
      * hằng `BUSINESS_DT`/`SETUP_REF_DOCTYPE`/`CASE_REF_DOCTYPE` (giữ tương thích
        với máy quét cũ, để test này là SIÊU TẬP chứ không phải tập khác).

    Trả về {doctype: "duong/dan/file.py"} để báo lỗi chỉ được đúng chỗ.
    """
    found = {}
    for root, dirs, files in os.walk(_ROOT):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "tests", "node_modules")]
        for f in files:
            if not f.endswith(".py"):
                continue
            p = os.path.join(root, f)
            try:
                src = io.open(p, encoding="utf-8").read()
            except Exception:
                continue
            if "ToDo" not in src and "assign_to" not in src:
                continue
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            consts = _module_consts(tree)
            rel = os.path.relpath(p, _ROOT)
            for nm in ("BUSINESS_DT", "SETUP_REF_DOCTYPE", "CASE_REF_DOCTYPE"):
                if nm in consts:
                    found.setdefault(consts[nm], rel)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Dict):
                    continue
                d = _dict_literal(node, consts)
                if d.get("doctype") == "ToDo":
                    rt = d.get("reference_type")
                    if rt:
                        found.setdefault(rt, rel)
                elif d.get("doctype") and "assign_to" in {
                        k.value for k in node.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)}:
                    # `assign_to` la LIST nen khong nam trong `d` (chi giu chuoi) --
                    # phai doc khoa tho.
                    found.setdefault(d["doctype"], rel)
    found.pop("ToDo", None)
    found.pop("Brand Approver", None)
    return found


# --------------------------------------------------------------------------- #
# 1. Chuông không được trỏ Desk  (mở rộng cổng QC ra ngoài action_center)
# --------------------------------------------------------------------------- #
class TestBellNeverLinksToDesk(unittest.TestCase):
    """`test_no_desk_urls.py` chỉ soi `action_center.resolvers.resolve_item`.

    Nhưng thông báo tới người dùng đi qua MỘT bộ dựng URL khác hẳn —
    `notification_center.resolvers._action_url` — và bộ đó không có nhánh
    `has_engine_approval_link`, không có `PORTAL_FALLBACK`, và cho Task thì gọi
    thẳng `build_task_url` (Desk) thay vì `build_pm_task_url` (portal).
    """

    def _bell(self, dt, dn="X-1", link=""):
        return NC.resolve_notification(_log(dt, dn, link)).get("action_url") or ""

    def test_pm_task_notification_is_not_a_desk_link(self):
        url = self._bell("Task", "TASK-0001")
        self.assertFalse(url.startswith("/app/"),
                         "chuong PM tra link Desk %s - 44%% tai khoan la Website User, "
                         "khong mo duoc /app" % url)

    def test_engine_governed_request_is_not_a_desk_link(self):
        for dt in ("EC Payment Request", "EC Purchase Request", "EC Contract Review Request"):
            url = self._bell(dt, "PAY-0001")
            self.assertFalse(url.startswith("/app/"),
                             "%s -> %s (Desk) tren chuong" % (dt, url))

    def test_portal_fallback_types_are_not_desk_links_on_the_bell(self):
        """Cùng danh sách mà cổng QC ToDo đã bắt buộc — chuông phải theo."""
        for dt in sorted(AC.PORTAL_FALLBACK):
            url = self._bell(dt, "X-1")
            self.assertFalse(url.startswith("/app/"),
                             "%s da co PORTAL_FALLBACK '%s' nhung chuong van tra %s"
                             % (dt, AC.PORTAL_FALLBACK[dt], url))

    def test_bell_and_action_center_agree_on_the_same_document(self):
        """Một chứng từ, một đích. Hai bộ dựng URL không được cãi nhau.

        Đây là bất biến mạnh nhất trong file: nó không cần biết đích ĐÚNG là gì,
        chỉ đòi hai con đường dẫn tới cùng một chỗ. Bất kỳ nhánh nào thêm vào một
        bên mà quên bên kia đều bị bắt.
        """
        mismatched = []
        for dt, dn in (("Task", "TASK-0001"),
                       ("Weekly Team Update", "WTU-0001"),
                       ("EC Payment Request", "PAY-0001"),
                       ("EC Alert", "ALERT-1"),
                       ("Leave Application", "HR-LAP-1"),
                       ("Attendance Request", "HR-ARQ-1"),
                       ("MSO Request", "MSO-1")):
            bell = self._bell(dt, dn)
            feed = AC.resolve_item(_todo(dt, dn)).get("action_url") or ""
            if bell != feed:
                mismatched.append("%s: chuong=%s  feed=%s" % (dt, bell, feed))
        self.assertEqual(mismatched, [],
                         "hai bo dung URL tra dich khac nhau cho cung mot chung tu:\n  "
                         + "\n  ".join(mismatched))

    def test_the_gate_has_teeth(self):
        """Chứng minh phép đo biết phân biệt: một type đã map phải XANH."""
        self.assertFalse(self._bell("Weekly Team Update", "WTU-1").startswith("/app/"))
        # ...và link tường minh vẫn thắng (nhánh PRECEDENCE 2026-08-10 còn sống)
        self.assertEqual(self._bell("MSO Request", "MSO-1", link="/approval?id=MSO-1&type=mso"),
                         "/approval?id=MSO-1&type=mso")


# --------------------------------------------------------------------------- #
# 2. action_url tính đúng lúc phát phải được LƯU
# --------------------------------------------------------------------------- #
def _notification_log_insert_keys(src):
    """Khoá của dict `{"doctype": "Notification Log", ...}` trong publish_notification_event."""
    node = _fn_node(src, "publish_notification_event")
    consts = _module_consts(ast.parse(src))
    for n in ast.walk(node):
        if isinstance(n, ast.Dict):
            d = _dict_literal(n, consts)
            if d.get("doctype") == "Notification Log":
                return {k.value for k in n.keys
                        if isinstance(k, ast.Constant) and isinstance(k.value, str)}
    raise AssertionError("khong tim thay lenh tao Notification Log")


class TestActionUrlIsPersisted(unittest.TestCase):
    """`notify()` của Approval Engine tính ra một link portal ĐÚNG
    (`_approval_link` -> `/approvals/<route>?id=<name>`), truyền vào
    `publish_notification_event`... rồi hàm đó chỉ dùng nó cho Teams + realtime.

    Dòng Notification Log được ghi KHÔNG có `link`. Hộp thư (`api.get_notifications`)
    đọc lại từ DB và tính lại URL từ `(document_type, document_name)` — tức là ném
    đi cái link đúng và dựng lại một cái sai.
    """

    SRC = _read("notification_center", "events.py")

    def test_notification_log_stores_the_action_url(self):
        keys = _notification_log_insert_keys(self.SRC)
        self.assertIn("link", keys,
                      "publish_notification_event tinh action_url roi vut di: dong "
                      "Notification Log khong co truong `link`, nen hop thu phai tu "
                      "dung lai URL (va dung sai). Khoa dang ghi: %s" % sorted(keys))

    def test_the_reader_would_use_it(self):
        """Nửa còn lại của hợp đồng: người đọc PHẢI ưu tiên `link`.

        Nếu chỉ sửa bên ghi mà bên đọc bỏ qua thì vẫn hỏng — nên khẳng định cả hai.
        """
        api_src = _read("notification_center", "api.py")
        self.assertIn('"link"', api_src, "api.get_notifications khong doc truong link")
        self.assertEqual(
            NC.resolve_notification(_log("Task", "T-1", link="/pm#task/T-1"))["action_url"],
            "/pm#task/T-1")

    def test_the_check_has_teeth(self):
        """Đột biến: thêm `"link": action_url` vào lệnh tạo -> phép đo phải XANH.

        Không có bước này thì `assertIn` ở trên có thể đang đo nhầm dict khác và
        đỏ vĩnh viễn bất kể mã nguồn thế nào.
        """
        mutated = self.SRC.replace(
            '"doctype": "Notification Log", "for_user": recipient,',
            '"doctype": "Notification Log", "link": action_url, "for_user": recipient,',
            1)
        self.assertNotEqual(mutated, self.SRC, "dot bien khong ap dung duoc - test da mu")
        self.assertIn("link", _notification_log_insert_keys(mutated))


# --------------------------------------------------------------------------- #
# 3. Máy quét ToDo producer không được mù với hằng số
# --------------------------------------------------------------------------- #
class TestTodoProducerScanIsNotBlind(unittest.TestCase):
    """Cổng QC hiện có quét bằng regex `"reference_type"\\s*:\\s*"([^"]+)"`.

    esign viết `"reference_type": DSR` — giá trị là TÊN HẰNG, không phải chuỗi
    trần. Regex không khớp, nên hai producer của esign chưa từng đi qua cổng.
    Đây đúng là kiểu hỏng "test grep source mù sau refactor" đã ghi trong memory.
    """

    PRODUCERS = _scan_todo_producers_ast()
    ESIGN_OPS_ROUTE = "/ec-esign/ops"

    def test_scan_finds_the_esign_producers(self):
        for dt in ("EC Digital Signature Request", "EC Digital Signature Package"):
            self.assertIn(dt, self.PRODUCERS,
                          "may quet khong thay producer %s (esign/tasks.py "
                          "_dead_letter_todo, esign/signed_files.py _dead_letter_review)"
                          % dt)

    def test_ast_scan_is_a_superset_of_the_regex_scan(self):
        """Không được đánh đổi: mọi thứ regex tìm được thì AST cũng phải tìm được."""
        for dt in ("Brand", "EC Order Retry", "Task", "EC Asset Request",
                   "EC System Request", "EC Data Request", "EC Document Request",
                   "EC AI Topup Request", "EC Resignation Request"):
            self.assertIn(dt, self.PRODUCERS, dt)

    def test_every_producer_resolves_to_a_portal_route(self):
        offenders = []
        for dt, where in sorted(self.PRODUCERS.items()):
            url = AC.resolve_item(_todo(dt, "X-1")).get("action_url") or ""
            if url.startswith("/app/"):
                offenders.append("%s (%s) -> %s" % (dt, where, url))
        self.assertEqual(offenders, [], "producer con tro Desk:\n  " + "\n  ".join(offenders))

    def test_esign_dead_letter_lands_on_the_ops_page_not_the_approval_hub(self):
        """Chỗ SỬA một chân ký hỏng là trang "Chân ký cần can thiệp", không phải hub.

        Cả hai DocType esign đều khai Link `approval_request`, nên nhánh
        `has_engine_approval_link` nuốt chúng và trả `/approvals`. Người trực vận
        hành mở ra thấy danh sách phê duyệt của chính mình — không có nút nào cứu
        được chân ký đang hỏng. Nhắc việc mở được mà vẫn là ngõ cụt.
        """
        for dt in ("EC Digital Signature Request", "EC Digital Signature Package"):
            url = AC.resolve_item(_todo(dt, "DSR-1")).get("action_url") or ""
            self.assertEqual(url, self.ESIGN_OPS_ROUTE,
                             "%s -> %s (khong phai trang ops)" % (dt, url))

    def test_the_scan_actually_scanned(self):
        self.assertGreaterEqual(len(self.PRODUCERS), 9,
                                "may quet tim duoc qua it: %s" % sorted(self.PRODUCERS))


# --------------------------------------------------------------------------- #
# 4. Mọi transition đóng phiếu phải chạm tới một người
# --------------------------------------------------------------------------- #
class TestEveryTerminalTransitionNotifiesSomeone(unittest.TestCase):
    """`reject`, `cancel`, `request_information` đều báo cho người đề nghị.
    `complete_approval` — kết thúc CÓ HẬU, cái duy nhất người ta chờ — thì không.

    Với 6 loại có fulfillment thì handler `on_final_approval` báo hộ. Với ~21 loại
    còn lại (Payment Request nằm trong đó) thì tuyệt đối không ai được báo: ToDo bị
    đóng hết, phiếu rời khỏi Action Center, và người đề nghị chỉ biết bằng cách tự
    mở lại trang.
    """

    SRC = _read("approval_center", "shared", "workflow", "transitions.py")

    def _calls(self, fn):
        return _called_names(_fn_node(self.SRC, fn))

    def test_control_transitions_do_notify(self):
        """Phép đo có răng: ba transition ĐÃ báo phải nhận diện được là có báo."""
        for fn in ("reject", "cancel", "request_information"):
            self.assertIn("notify", self._calls(fn), fn)

    def test_control_transitions_do_close_todos(self):
        for fn in ("reject", "cancel", "request_information", "complete_approval"):
            self.assertIn("close_todos", self._calls(fn), fn)

    def test_final_approval_notifies_the_requester(self):
        self.assertIn("notify", self._calls("complete_approval"),
                      "complete_approval dong het ToDo va khong bao ai. Voi mot loai "
                      "khong co _FULFILLMENT_HANDLERS (vd EC Payment Request) thi "
                      "'da duyet xong' la mot su kien HOAN TOAN im lang.")

    def test_fulfillment_handlers_do_not_cover_payment_request(self):
        """Ghi lại vì sao lỗ trên là thật chứ không phải do handler gánh."""
        node = None
        for n in ast.parse(self.SRC).body:
            if isinstance(n, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "_FULFILLMENT_HANDLERS"
                    for t in n.targets):
                node = n.value
        self.assertIsNotNone(node, "khong tim thay _FULFILLMENT_HANDLERS")
        covered = {k.value for k in node.keys
                   if isinstance(k, ast.Constant) and isinstance(k.value, str)}
        self.assertNotIn("EC Payment Request", covered)   # tiền đề của test trên


# --------------------------------------------------------------------------- #
# 5. resubmit phải khoá máy trạng thái
# --------------------------------------------------------------------------- #
class TestResubmitGuardsTheStateMachine(unittest.TestCase):
    """Vòng 2 đã vá `approve` / `reject` / `cancel` / `request_information`: đọc lại
    trạng thái SAU khoá hàng, `_guard_open` hai lần. `resubmit` bị bỏ sót hoàn toàn
    — không khoá hàng, không `_guard_open`.

    Cửa duy nhất còn lại là `restart`: `if status != "Information Required" and not
    restart: throw`. Nghĩa là hễ caller truyền `restart=True` thì một phiếu đã
    Rejected / Cancelled / Approved vẫn reset được toàn bộ cấp về Pending và
    `_activate_level` lại — sinh ToDo mới và thông báo "Cần duyệt" trên một phiếu
    mọi người tưởng đã đóng.

    Hậu quả riêng cho BOT này: `_activate_level` gọi `close_todos` KHÔNG phạm vi,
    nên nếu phiếu đã Approved và đang fulfillment thì việc của người xử lý bị huỷ
    trong khi `fulfillment_status` vẫn 'In Progress' — công việc mồ côi, không còn
    ToDo nào để feed nhìn thấy (xem `feed._open_fulfillment_todo`).
    """

    SRC = _read("approval_center", "shared", "workflow", "transitions.py")

    def _calls(self, fn):
        return _called_names(_fn_node(self.SRC, fn))

    def test_control_transitions_are_guarded(self):
        for fn in ("approve", "reject", "cancel", "request_information"):
            self.assertIn("_guard_open", self._calls(fn), fn)

    def test_resubmit_is_guarded_too(self):
        self.assertIn("_guard_open", self._calls("resubmit"),
                      "resubmit khong _guard_open: restart=True hoi sinh duoc mot "
                      "phieu terminal, sinh ToDo + thong bao 'Can duyet' tren phieu da dong")

    def test_resubmit_takes_a_row_lock_like_its_siblings(self):
        self.assertTrue(_uses_kwarg(_fn_node(self.SRC, "resubmit"), "for_update"),
                        "resubmit doc trang thai truoc khoa - tin don, khong phai su that "
                        "(approve/reject/cancel deu da khoa hang tu vong 2)")

    def test_the_row_lock_detector_has_teeth(self):
        for fn in ("approve", "reject", "cancel"):
            self.assertTrue(_uses_kwarg(_fn_node(self.SRC, fn), "for_update"), fn)

    def test_the_facade_gates_resubmit_like_it_gates_cancel(self):
        """`command_service.cancel` kiểm `can_cancel`; `command_service.resubmit` thì không.

        Nên endpoint `resubmit` được whitelist mà không hề kiểm người gọi có phải
        người đề nghị hay không — `can_resubmit` trong capabilities.py chỉ là gợi ý
        cho giao diện.
        """
        cs = _read("approval_center", "shared", "requests", "command_service.py")
        calls = _called_names(_fn_node(cs, "resubmit"))
        self.assertTrue({"derive", "capabilities.derive"} & calls,
                        "command_service.resubmit khong goi capabilities.derive - "
                        "khong kiem can_resubmit, khong kiem trang thai")


# --------------------------------------------------------------------------- #
# 6. Chân ký hỏng / nợ chữ ký phải chạm tới một người
# --------------------------------------------------------------------------- #
class TestEsignFailuresReachAHuman(unittest.TestCase):
    """Ba ngõ im lặng của esign:

      * `guard._record_signature_debt` — ghi cờ + một dòng lịch sử nói "chỉ chính
        người duyệt này ký bù được", nhưng KHÔNG báo cho chính người đó;
      * `requester.reconcile_and_complete_requester` — chân ký của NGƯỜI ĐỀ NGHỊ
        chết hẳn (Permanent Failure) thì chỉ set một trường + emit event; người
        đề nghị không được báo, và vì Level 1 chưa kích hoạt nên phiếu KHÔNG có
        ToDo nào cả, cho bất kỳ ai;
      * `tasks._dead_letter_todo` — giao việc cho MỘT System Manager bất kỳ tìm
        thấy đầu tiên, không thông báo, không nói cho người đang chờ ký.
    """

    GUARD = _read("platform", "esign", "guard.py")
    REQUESTER = _read("platform", "esign", "requester.py")
    TASKS = _read("platform", "esign", "tasks.py")

    _NOTIFY = {"notify", "engine.notify", "publish_notification_event",
               "ncev.publish_notification_event", "notify_approval_required",
               "events.publish_notification_event"}

    def _notifies(self, src, fn):
        return bool(self._NOTIFY & _called_names(_fn_node(src, fn)))

    def test_signature_debt_notifies_the_approver_who_owes_it(self):
        self.assertTrue(self._notifies(self.GUARD, "_record_signature_debt"),
                        "no chu ky chi nam tren /ec-esign/ops; nguoi duy nhat ky bu "
                        "duoc khong he biet minh dang no")

    def test_requester_signature_failure_notifies_the_requester(self):
        self.assertTrue(self._notifies(self.REQUESTER, "reconcile_and_complete_requester"),
                        "Submit & Sign that bai -> requester_signature_status='Failed', "
                        "Level 1 khong kich hoat, KHONG ToDo cho ai, KHONG bao ai. "
                        "Phieu nam Pending trong get_my_requests_summary nhu binh thuong.")

    def test_manual_review_dead_letter_notifies_and_not_just_files_a_todo(self):
        self.assertTrue(self._notifies(self.TASKS, "_dead_letter_todo"),
                        "Manual Review chi tao ToDo cho mot System Manager ngau nhien")

    def test_the_notify_detector_has_teeth(self):
        """Chứng minh bộ dò nhận ra một hàm CÓ báo — nếu không thì cả lớp này vô nghĩa."""
        eng = _read("approval_center", "shared", "workflow", "transitions.py")
        self.assertTrue(self._notifies(eng, "reject"))
        self.assertTrue(self._notifies(eng, "cancel_fulfillment"))

    def test_dead_letter_owner_selection_is_not_arbitrary(self):
        """"System Manager đầu tiên tìm thấy" không phải một người chịu trách nhiệm.

        `frappe.get_all("Has Role", ... limit_page_length=20)` không order_by, nên
        chủ sở hữu việc phụ thuộc thứ tự trả về của DB. Cùng một sự cố, hai lần
        chạy có thể rơi vào hai người.
        """
        self.assertTrue(_uses_kwarg(_fn_node(self.TASKS, "_dead_letter_todo"), "order_by"),
                        "nguoi nhan viec Manual Review duoc chon khong xac dinh: "
                        "get_all('Has Role', ... limit_page_length=20) khong order_by")


# --------------------------------------------------------------------------- #
# 7. Không báo cho người không xem được
# --------------------------------------------------------------------------- #
class TestNoNotificationWithoutPermission(unittest.TestCase):
    """Contract Review: khi hợp đồng chỉ là điều chỉnh, cấp CEO bị LOẠI khỏi snapshot
    (`skip_level_nos`) rồi CEO được gửi một thông báo `[CC]` kèm deep link.

    Nhưng cấp bị loại thì không có dòng `EC Approval Request Approver` nào —
    `permissions.can_view_request` xét đúng bốn tư cách (System Manager / người đề
    nghị / approver có dòng / fulfiller). CEO không thuộc tư cách nào, nên bấm vào
    link là 403. Thông báo có, quyền không.
    """

    SRC = _read("approval_center", "features", "contract_review", "application", "service.py")

    def test_cc_recipient_is_granted_read_on_the_document(self):
        calls = _called_names(_fn_node(self.SRC, "_notify_ceo_cc"))
        granting = {"_engine_grant_read", "engine._engine_grant_read", "assign",
                    "engine.assign", "add_docshare", "share.add"}
        self.assertTrue(granting & calls,
                        "gui link cho CEO ma khong cap quyen doc: CEO bi loai khoi "
                        "snapshot nen can_view_request() = False -> bam vao la 403")

    def test_can_view_request_really_requires_an_approver_row(self):
        """Tiền đề của test trên, đọc thẳng từ hàm quyền — không phải suy đoán."""
        perm = _read("approval_center", "shared", "workflow", "permissions.py")
        node = _fn_node(perm, "can_view_request")
        lits = {n.value for n in ast.walk(node)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        self.assertIn("EC Approval Request Approver", lits)
        # tu cach "participant cua Approval Process" KHONG duoc tinh la xem duoc
        self.assertNotIn("EC Approval Process", lits)


# --------------------------------------------------------------------------- #
# 8. Hành vi: close_todos huỷ cả việc fulfillment  (test XANH — ghi lại cơ chế)
# --------------------------------------------------------------------------- #
def _load_close_todos():
    """Chạy `close_todos` + `_engine_maintain_assign` THẬT trên một frappe giả."""
    src = _read("approval_center", "shared", "workflow", "transitions.py")
    tree = ast.parse(src)
    wanted = ("close_todos", "close_fulfillment_todos", "_engine_maintain_assign")
    segs = [ast.get_source_segment(src, n) for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name in wanted]
    assert len(segs) == len(wanted), "thieu ham can nap: %s" % len(segs)

    store = {}

    class _db(object):
        @staticmethod
        def get_value(dt, name, field, **kw):
            return "[]"

        @staticmethod
        def set_value(dt, name, field, value=None, update_modified=True):
            # frappe.db.set_value nhan CA hai dang: (dt, name, {patch}) va
            # (dt, name, field, value). Ban gia phai nhan ca hai, neu khong test
            # do vi ban gia lech chu khong vi ma nguon sai.
            patch = dict(field) if isinstance(field, dict) else {field: value}
            store.setdefault(name, {}).update(patch)

    fk = types.SimpleNamespace()
    fk.db = _db
    fk.flags = types.SimpleNamespace(mute_messages=False)
    fk.parse_json = lambda s: []
    fk.as_json = lambda o: "[]"
    fk.get_all = lambda dt, filters=None, fields=None, **kw: _ROWS["value"]

    ns = {"frappe": fk, "FULFILLMENT_MARKER": "ec_fulfillment",
          "_D": _D, "store": store}
    exec(compile("\n\n".join(segs), "transitions_subset.py", "exec"), ns)
    return ns, store


_ROWS = {"value": []}


class TestCloseTodosScope(unittest.TestCase):
    """`_activate_level` gọi `close_todos(doctype, name)` — KHÔNG phạm vi.

    Test này XANH: nó không tố cáo gì, nó ghi lại cơ chế để lỗ ở lớp 5 đọc được.
    `close_todos` huỷ MỌI ToDo Open trên chứng từ, kể cả việc fulfillment đang
    sống; `close_fulfillment_todos` thì ngược lại, chỉ đụng việc có dấu.
    """

    def setUp(self):
        self.ns, self.store = _load_close_todos()

    def test_close_todos_cancels_a_live_fulfillment_task(self):
        _ROWS["value"] = [_D({"name": "td-ful", "allocated_to": "op@x.vn",
                              "ec_fulfillment": 1})]
        self.ns["close_todos"]("EC Asset Request", "AR-1")
        self.assertEqual(self.store["td-ful"]["status"], "Cancelled")

    def test_close_fulfillment_todos_keeps_the_named_user(self):
        _ROWS["value"] = [_D({"name": "td-a", "allocated_to": "a@x.vn", "ec_fulfillment": 1}),
                          _D({"name": "td-b", "allocated_to": "b@x.vn", "ec_fulfillment": 1})]
        self.ns["close_fulfillment_todos"]("EC Asset Request", "AR-1", keep_user="a@x.vn")
        self.assertNotIn("td-a", self.store)
        self.assertEqual(self.store["td-b"]["status"], "Cancelled")

    def test_the_harness_has_teeth(self):
        """Không có dòng nào thì phải KHÔNG ghi gì — bản giả không tự trả lời chính nó."""
        _ROWS["value"] = []
        self.ns["close_todos"]("EC Asset Request", "AR-1")
        self.assertEqual(self.store, {})


# --------------------------------------------------------------------------- #
# 9. Đột biến — chứng minh 15 khẳng định ĐỎ ở trên có thể XANH
# --------------------------------------------------------------------------- #
class TestMutationsProveTheGatesCanBeSatisfied(unittest.TestCase):
    """Một test đỏ vĩnh viễn — đỏ bất kể mã nguồn thế nào — thì vô dụng hệt như một
    test xanh vĩnh viễn. Lớp này áp bản vá TỐI THIỂU vào BẢN SAO trong bộ nhớ của
    từng file rồi chạy lại đúng phép đo đã đỏ, và đòi nó chuyển xanh.

    Không file nào trên đĩa bị đụng tới.
    """

    ENG = _read("approval_center", "shared", "workflow", "transitions.py")

    def _assert_mutated(self, src, old, new, check):
        mutated = src.replace(old, new, 1)
        self.assertNotEqual(mutated, src, "dot bien khong ap dung duoc - phep do da mu")
        self.assertTrue(check(mutated), "vá roi ma phep do van do -> phep do do sai cho")

    def test_bell_desk_url_is_fixable(self):
        """Sửa `_action_url` để uỷ quyền cho Action Center -> chuông hết link Desk."""
        src = _read("notification_center", "resolvers.py")
        mutated = src.replace(
            "    return ac.build_desk_fallback_url(dt, dn)",
            "    return ac.resolve_item({'reference_type': dt, 'reference_name': dn,\n"
            "                            'name': 'x', 'description': ''})['action_url']", 1)
        mutated = mutated.replace("        return ac.build_task_url(dn)",
                                  "        return ac.build_pm_task_url(dn)", 1)
        self.assertNotEqual(mutated, src)
        ns = {"frappe": _FK, "ac": AC}
        exec(compile(mutated, "nc_resolvers_mutated.py", "exec"), ns)
        for dt in ("Task", "EC Payment Request", "Attendance Request",
                   "Leave Application", "EC Alert"):
            url = ns["resolve_notification"](_log(dt, "X-1"))["action_url"]
            self.assertFalse(url.startswith("/app/"), "%s -> %s" % (dt, url))

    def test_complete_approval_notify_is_fixable(self):
        self._assert_mutated(
            self.ENG,
            "    close_todos(req.reference_doctype, req.reference_name)\n"
            "    handler = _FULFILLMENT_HANDLERS.get(req.reference_doctype)",
            "    close_todos(req.reference_doctype, req.reference_name)\n"
            "    notify([req.requested_by], 'x', req.reference_doctype, req.reference_name)\n"
            "    handler = _FULFILLMENT_HANDLERS.get(req.reference_doctype)",
            lambda s: "notify" in _called_names(_fn_node(s, "complete_approval")))

    def test_resubmit_guard_is_fixable(self):
        self._assert_mutated(
            self.ENG,
            '    req = frappe.get_doc("EC Approval Request", request_name)\n'
            '    if req.approval_status not in ("Information Required",) and not restart:',
            '    req = frappe.get_doc("EC Approval Request", request_name)\n'
            '    _guard_open(req)\n'
            '    frappe.db.get_value("EC Approval Request", request_name, "name", for_update=True)\n'
            '    if req.approval_status not in ("Information Required",) and not restart:',
            lambda s: ("_guard_open" in _called_names(_fn_node(s, "resubmit"))
                       and _uses_kwarg(_fn_node(s, "resubmit"), "for_update")))

    def test_esign_debt_notify_is_fixable(self):
        guard_src = _read("platform", "esign", "guard.py")
        self._assert_mutated(
            guard_src,
            '        events.emit("SignatureDeferred", request_meta={',
            '        engine.notify([actor], "no chu ky", req.reference_doctype,\n'
            '                      req.reference_name)\n'
            '        events.emit("SignatureDeferred", request_meta={',
            lambda s: "engine.notify" in _called_names(_fn_node(s, "_record_signature_debt")))

    def test_contract_review_cc_grant_is_fixable(self):
        cr = _read("approval_center", "features", "contract_review", "application", "service.py")
        self._assert_mutated(
            cr,
            "            engine.notify(ceo, _(\"[CC] ",
            "            for u in ceo:\n"
            "                engine._engine_grant_read(BUSINESS_DT, doc.name, u)\n"
            "            engine.notify(ceo, _(\"[CC] ",
            lambda s: "engine._engine_grant_read" in _called_names(_fn_node(s, "_notify_ceo_cc")))

    def test_esign_ops_route_needs_a_branch_before_the_engine_link_arm(self):
        """Cảnh báo cho người sửa: thêm vào `PORTAL_FALLBACK` là KHÔNG đủ.

        `resolve_item` xét `has_engine_approval_link(rt)` TRƯỚC `PORTAL_FALLBACK`,
        mà cả hai DocType esign đều khai Link `approval_request` — nên nhánh hub
        vẫn nuốt trước. Test này giữ cho lời cảnh báo đó đúng: nếu thứ tự nhánh
        đổi, nó đỏ và người ta biết cách sửa đã khác.
        """
        node = _fn_node(_read("action_center", "resolvers.py"), "resolve_item")
        order = []
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
                if n.func.id == "has_engine_approval_link":
                    order.append("engine")
            if isinstance(n, ast.Compare) and any(
                    isinstance(c, ast.Name) and c.id == "PORTAL_FALLBACK"
                    for c in n.comparators):
                order.append("portal")
        self.assertEqual(order[:2], ["engine", "portal"],
                         "thu tu nhanh da doi -> cach sua trang ops cung phai doi")


if __name__ == "__main__":
    unittest.main()
