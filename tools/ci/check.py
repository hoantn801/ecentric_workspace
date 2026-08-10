# Copyright (c) 2026, eCentric and contributors
"""Kiểm tra trước khi deploy -- chạy trên máy hoặc trong GitHub Actions, KHÔNG cần bench.

    python tools/ci/check.py            # chạy hết
    python tools/ci/check.py --only pagesync
    python tools/ci/check.py --skip pagesync

VÌ SAO CÓ FILE NÀY. `bench run-tests` cần MariaDB + Redis + một site đã cài app, tức là
không chạy được trong một job CI nhẹ. Những lỗi dưới đây thì KHÔNG cần bench vẫn bắt được,
và đều là loại lỗi mà Frappe Cloud chỉ báo sau khi đã build xong container -- hoặc tệ hơn,
không báo gì cả:

    syntax    Python gãy cú pháp -> app không import được, site 500 sau khi deploy
    json      DocType/fixture JSON hỏng -> `bench migrate` gãy giữa chừng
    jinja     template gãy cú pháp -> trang trắng, chỉ lộ khi có người mở đúng trang đó
    hooks     đường dẫn trong hooks.py trỏ vào hàm không tồn tại -> scheduler chết im lặng
    bundles   web_include_js/css trỏ vào bundle không có trong public/ -> asset 404
    git       *.pyc / __pycache__ bị commit -> bytecode cũ đè lên code mới trong image
    pagesync  BASELINE_SHA256 lệch với HTML mà commit này ship -> sync bị REFUSED

`pagesync` là phép kiểm đáng giá nhất của repo NÀY. Xem docstring của `check_pagesync`.

CÁI NÀY KHÔNG KIỂM ĐƯỢC: phân quyền thật của Frappe (Role Permission / User Permission),
hook vòng đời document, workflow, background job, `/api/method/...`, email, migrate.
Xanh ở đây nghĩa là "không gãy vì những lý do ngớ ngẩn", không phải "chạy đúng".
"""
import argparse
import ast
import json
import os
import subprocess
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

#: Tên app = tên package = tên module gốc. Ba thứ này trùng nhau trong một app Frappe;
#: đổi tên app thì phải đổi ở đây, ở pyproject.toml và ở hooks.py cùng lúc.
APP = "ecentric_workspace"
APP_DIR = os.path.join(ROOT, APP)
STUBS = os.path.join(HERE, "stubs")

#: Key trong hooks.py có giá trị là đường dẫn Python dạng chuỗi. Frappe không kiểm
#: những chuỗi này lúc cài -- sai tên hàm thì tới lúc scheduler chạy mới lộ.
HOOK_KEYS_WITH_DOTTED_PATHS = (
    "scheduler_events",
    "doc_events",
    "override_whitelisted_methods",
    "override_doctype_class",
    "permission_query_conditions",
    "has_permission",
    "on_session_creation",
    "on_logout",
    "before_request",
    "after_request",
    "before_job",
    "after_job",
    "jinja",
    "website_route_rules",
    "boot_session",
    "notification_config",
)

#: Key trong hooks.py trỏ tới asset. Giá trị có hai dạng: tên bundle
#: (`ec_shell.bundle.js` -> `public/js/ec_shell.bundle.js`) hoặc đường dẫn tuyệt đối
#: `/assets/<app>/...` -> `public/...`.
HOOK_KEYS_WITH_ASSETS = {
    "app_include_js": "js",
    "app_include_css": "css",
    "web_include_js": "js",
    "web_include_css": "css",
}

#: Thư mục bỏ qua khi đi tìm file.
SKIP_DIRS = ("__pycache__", ".git", "node_modules", "vendor", "dist", "build")


# -- tiện ích -------------------------------------------------------------

def walk_files(base, suffix, skip_dirs=SKIP_DIRS):
    for dirpath, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for filename in sorted(files):
            if filename.endswith(suffix):
                yield os.path.join(dirpath, filename)


def rel(path):
    return os.path.relpath(path, ROOT).replace(os.sep, "/")


def read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _indent(text):
    return "\n".join("        " + line for line in text.rstrip().splitlines())


# -- các phép kiểm ---------------------------------------------------------

def check_syntax():
    """Mọi file .py phải parse được bằng chính phiên bản Python đang chạy."""
    problems, count = [], 0
    for base in (APP_DIR, os.path.join(ROOT, "tools")):
        if not os.path.isdir(base):
            continue
        for path in walk_files(base, ".py"):
            count += 1
            try:
                ast.parse(read(path), filename=path)
            except SyntaxError as exc:
                problems.append("%s:%s  %s" % (rel(path), exc.lineno, exc.msg))
            except UnicodeDecodeError as exc:
                problems.append("%s  không đọc được bằng UTF-8: %s" % (rel(path), exc))
    return problems, "%d file .py" % count


def check_json():
    """DocType schema và fixture phải là JSON hợp lệ.

    `bench migrate` đọc những file này rất sớm; hỏng một dấu phẩy là site nằm giữa
    trạng thái nửa migrate.
    """
    problems, count = [], 0
    for path in walk_files(APP_DIR, ".json"):
        count += 1
        try:
            json.loads(read(path))
        except (ValueError, UnicodeDecodeError) as exc:
            problems.append("%s  %s" % (rel(path), exc))
    return problems, "%d file .json" % count


def check_jinja():
    """Mọi template Jinja phải parse được.

    Chỉ quét `templates/` và `www/` -- đó là hai nơi DUY NHẤT Frappe render bằng Jinja.
    Các file `*/frontend/*.html` KHÔNG nằm trong vùng này: chúng là HTML thô được
    `page_sync.py` nạp vào `main_section_html` của Web Page, không đi qua Jinja, và có
    chứa cú pháp JS mà Jinja sẽ hiểu sai.

    Hôm nay hai thư mục đó rỗng, nên phép kiểm này là 0 file. Giữ lại để ngày có người
    thêm template thật thì nó đã sẵn ở đó.
    """
    try:
        import jinja2
    except ImportError:
        return ["thiếu jinja2 -- cài bằng: python -m pip install \"jinja2>=3.1\""], "bỏ qua"

    env = jinja2.Environment()
    problems, count = [], 0
    for base in (os.path.join(APP_DIR, "templates"), os.path.join(APP_DIR, "www")):
        if not os.path.isdir(base):
            continue
        for path in walk_files(base, ".html"):
            count += 1
            try:
                env.parse(read(path), filename=rel(path))
            except jinja2.TemplateSyntaxError as exc:
                problems.append("%s:%s  %s" % (rel(path), exc.lineno, exc.message))
    return problems, "%d template" % count


def _hook_literals(tree, keys):
    """Giá trị của các assignment top-level có tên nằm trong `keys`, dạng literal."""
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in keys:
                try:
                    out[target.id] = ast.literal_eval(node.value)
                except ValueError:
                    # Giá trị tính bằng biểu thức -- không kiểm tĩnh được, bỏ qua có
                    # chủ ý thay vì đoán.
                    pass
    return out


def _hook_mutations(tree, keys):
    """Chuỗi thêm vào SAU khi gán, dạng `scheduler_events["hourly"].append("...")`.

    hooks.py của app này gắn các job esign bằng `.append()` và
    `.setdefault(...).append()` ở cuối file. `_hook_literals` chỉ đọc phép gán nên sẽ
    bỏ sót đúng những dòng đó -- tức là những dòng MỚI nhất, dễ sai tên nhất.
    """
    out = {}
    for node in tree.body:
        if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
            continue
        root, cursor = None, node.value.func
        while True:
            if isinstance(cursor, ast.Attribute):
                cursor = cursor.value
            elif isinstance(cursor, ast.Subscript):
                cursor = cursor.value
            elif isinstance(cursor, ast.Call):
                cursor = cursor.func
            elif isinstance(cursor, ast.Name):
                root = cursor.id
                break
            else:
                break
        if root not in keys:
            continue
        strings = [n.value for n in ast.walk(node.value)
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        out.setdefault(root, []).extend(strings)
    return out


def _collect_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _collect_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _collect_strings(item)


def _dotted_path_exists(dotted):
    """`ecentric_workspace.pm.api.tasks.pm_task_transition_guard` -> có thật không.

    Kiểm bằng AST chứ không import: import kéo theo `frappe` thật, thứ không có ở đây.
    """
    parts = dotted.split(".")
    for split in range(len(parts) - 1, 0, -1):
        module_parts, attr = parts[:split], parts[split]
        candidates = (
            os.path.join(ROOT, *module_parts) + ".py",
            os.path.join(ROOT, *module_parts, "__init__.py"),
        )
        for path in candidates:
            if not os.path.isfile(path):
                continue
            tree = ast.parse(read(path), filename=path)
            names = set()
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(node.name)
                elif isinstance(node, ast.Assign):
                    names.update(t.id for t in node.targets if isinstance(t, ast.Name))
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    names.update(a.asname or a.name.split(".")[0] for a in node.names)
            if attr in names:
                return True, None
            return False, "%s không có `%s`" % (rel(path), attr)
    return False, "không tìm thấy module cho đường dẫn này"


def check_hooks():
    """Đường dẫn Python khai trong hooks.py phải trỏ vào hàm có thật."""
    hooks_path = os.path.join(APP_DIR, "hooks.py")
    tree = ast.parse(read(hooks_path), filename=hooks_path)
    problems, count = [], 0

    values = _hook_literals(tree, HOOK_KEYS_WITH_DOTTED_PATHS)
    for key, strings in _hook_mutations(tree, HOOK_KEYS_WITH_DOTTED_PATHS).items():
        values.setdefault(key, [])
        values[key] = list(_collect_strings(values[key])) + strings

    prefix = APP + "."
    for key, value in sorted(values.items()):
        for dotted in _collect_strings(value):
            if not dotted.startswith(prefix):
                continue
            count += 1
            ok, detail = _dotted_path_exists(dotted)
            if not ok:
                problems.append("hooks.py %s -> %s  (%s)" % (key, dotted, detail))

    return problems, "%d đường dẫn" % count


def check_bundles():
    """`web_include_js` / `web_include_css` phải trỏ vào file có thật trong public/.

    Frappe nhận hai dạng giá trị và cả hai đều gãy im lặng khi sai: tên bundle
    (`ec_shell.bundle.js` -> `public/js/ec_shell.bundle.js`, được build thành asset có
    hash) và đường dẫn `/assets/<app>/...`. Sai tên thì trang vẫn render, chỉ là thiếu
    hẳn một mảng JS/CSS -- không có lỗi nào trên server để mà nhìn.
    """
    hooks_path = os.path.join(APP_DIR, "hooks.py")
    tree = ast.parse(read(hooks_path), filename=hooks_path)
    public = os.path.join(APP_DIR, "public")
    problems, count = [], 0

    values = _hook_literals(tree, tuple(HOOK_KEYS_WITH_ASSETS))
    asset_prefix = "/assets/%s/" % APP
    for key, value in sorted(values.items()):
        subdir = HOOK_KEYS_WITH_ASSETS[key]
        for asset in _collect_strings(value):
            count += 1
            if asset.startswith(asset_prefix):
                tail = asset[len(asset_prefix):].split("/")
            elif asset.startswith("/assets/"):
                continue          # asset của app khác -- không thuộc thẩm quyền ở đây
            elif asset.startswith(("http://", "https://", "//")):
                continue          # CDN ngoài
            else:
                tail = [subdir, asset]
            if not os.path.isfile(os.path.join(public, *tail)):
                problems.append("hooks.py %s -> %s  (không có %s)"
                                % (key, asset, rel(os.path.join(public, *tail))))

    return problems, "%d asset" % count


def check_git():
    """Không được commit bytecode.

    File .pyc cũ nằm trong image sẽ được Python dùng lại khi timestamp lệch, và bug đó
    trông y hệt "deploy không ăn".
    """
    try:
        out = subprocess.run(
            ["git", "ls-files", "*.pyc", "*.pyo", "__pycache__/*", "*/__pycache__/*"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        return ["không chạy được git ls-files: %s" % exc], "bỏ qua"

    tracked = [line for line in out.splitlines() if line.strip()]
    problems = ["đang được git theo dõi: %s" % path for path in tracked]
    return problems, "%d file bytecode bị theo dõi" % len(tracked)


def _pagesync_modules():
    """Module có gán `BASELINE_SHA256` ở cấp module -> (đường dẫn file, tên module)."""
    found = []
    for path in walk_files(APP_DIR, ".py"):
        if os.sep + "tests" + os.sep in path:
            continue
        source = read(path)
        if "BASELINE_SHA256" not in source:
            continue          # lọc thô trước khi parse: nhanh hơn nhiều lần
        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError:
            continue          # check `syntax` đã báo rồi, không báo hai lần
        declared = any(
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "BASELINE_SHA256"
                    for t in node.targets)
            for node in tree.body
        )
        if not declared:
            continue
        module = rel(path)[: -len(".py")].replace("/", ".")
        found.append((path, module))
    return found


def check_pagesync():
    """`BASELINE_SHA256` phải bằng sha256 của HTML mà chính commit này ship.

    ĐÂY LÀ PHÉP KIỂM QUAN TRỌNG NHẤT CỦA REPO NÀY. `page_sync_util.upsert_web_page`
    dùng `BASELINE_SHA256` làm khoá lạc quan: nó chỉ ghi khi HTML đang sống trên site
    băm ra đúng một trong các giá trị được chấp nhận. Quy trình sửa một trang là "sửa
    file HTML, bump BASELINE_SHA256, đẩy giá trị cũ sang SUPERSEDES_SHA256" -- cả ba
    trong CÙNG một commit.

    Quên bump thì KHÔNG có gì đỏ: sync trả về `{"action": "refused"}` và trang trên
    site giữ nguyên bản cũ. Deploy xanh, job xanh, trang không đổi. Phép kiểm này biến
    kiểu hỏng im lặng đó thành một dòng đỏ trước khi deploy.

    Cách làm: import thật module bằng stub `frappe` (tools/ci/stubs) rồi gọi `_html()`,
    băm bằng CHÍNH `page_sync_util.content_sha256` -- không chép lại công thức băm, để
    không bao giờ có chuyện phép kiểm băm một kiểu còn lúc chạy thật băm kiểu khác.

    `BASELINE_SHA256 = None` (legacy_pages/home) là cố ý: module đó tự khoá mình thành
    no-op cho tới khi có baseline được duyệt. Bỏ qua, không báo lỗi.
    """
    import importlib

    # Stub đứng SAU gốc repo: `ecentric_workspace` thật phải thắng, chỉ `frappe` mới
    # lấy từ stub.
    for entry in (STUBS, ROOT):
        if entry in sys.path:
            sys.path.remove(entry)
    sys.path.insert(0, STUBS)
    sys.path.insert(0, ROOT)

    from ecentric_workspace.approval_center.page_sync_util import content_sha256

    problems, checked, skipped = [], 0, 0
    for path, module_name in _pagesync_modules():
        try:
            module = importlib.import_module(module_name)
        except Exception:
            problems.append("%s  không import được:\n%s"
                            % (rel(path), _indent(traceback.format_exc())))
            continue

        baseline = getattr(module, "BASELINE_SHA256", None)
        if baseline is None:
            skipped += 1
            continue

        html_fn = getattr(module, "_html", None)
        if not callable(html_fn):
            problems.append("%s  có BASELINE_SHA256 nhưng không có _html()" % rel(path))
            continue

        try:
            actual = content_sha256(html_fn())
        except Exception:
            problems.append("%s  _html() gãy:\n%s"
                            % (rel(path), _indent(traceback.format_exc())))
            continue

        checked += 1
        if actual == baseline:
            continue
        if actual in tuple(getattr(module, "SUPERSEDES_SHA256", ()) or ()):
            problems.append(
                "%s  BASELINE_SHA256 và SUPERSEDES_SHA256 bị đảo: HTML đang ship băm ra "
                "%s, giá trị đó nằm trong SUPERSEDES chứ không phải BASELINE."
                % (rel(path), actual[:12]))
            continue
        problems.append(
            "%s  HTML đã đổi mà BASELINE_SHA256 chưa bump.\n"
            "        BASELINE_SHA256 = \"%s\"  (đang khai)\n"
            "        HTML đang ship   = \"%s\"\n"
            "        Sửa: đặt BASELINE_SHA256 = \"%s\" và đẩy giá trị cũ vào "
            "SUPERSEDES_SHA256 = (\"%s\",)"
            % (rel(path), baseline, actual, actual, baseline))

    # `checked` là số trang ĐÃ BĂM được, không phải số trang khớp -- gọi nó là "khớp"
    # thì dòng tóm tắt sẽ nói "35 trang khớp sha" ngay bên cạnh 3 trang đang RỚT.
    summary = "%d trang kiểm sha" % checked
    if skipped:
        summary += ", %d bỏ qua (BASELINE_SHA256 = None)" % skipped
    return problems, summary


CHECKS = (
    ("syntax", check_syntax),
    ("json", check_json),
    ("jinja", check_jinja),
    ("hooks", check_hooks),
    ("bundles", check_bundles),
    ("git", check_git),
    # `pagesync` phải chạy CUỐI: nó cắm stub `frappe` vào sys.path và không gỡ ra được.
    ("pagesync", check_pagesync),
)


def _force_utf8_streams():
    """Console Windows mặc định cp1252: một câu tiếng Việt đủ để ném UnicodeEncodeError.

    Phải gọi TRƯỚC `parse_args()`: chính chuỗi --help cũng là tiếng Việt, nên đặt sau thì
    `check.py --help` gãy trước khi kịp sửa stream.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main():
    _force_utf8_streams()

    parser = argparse.ArgumentParser(
        description="Kiểm tra %s trước khi deploy (không cần bench)" % APP
    )
    parser.add_argument("--only", action="append", metavar="TÊN",
                        help="chỉ chạy phép kiểm này (lặp lại được): "
                             + ", ".join(name for name, _fn in CHECKS))
    parser.add_argument("--skip", action="append", metavar="TÊN", default=[],
                        help="bỏ qua phép kiểm này (lặp lại được)")
    args = parser.parse_args()

    names = [name for name, _fn in CHECKS]
    for name in (args.only or []) + args.skip:
        if name not in names:
            raise SystemExit("Không có phép kiểm tên %r. Có: %s" % (name, ", ".join(names)))

    selected = [(n, f) for n, f in CHECKS
                if (not args.only or n in args.only) and n not in args.skip]

    print("")
    print("  %s · kiểm tra trước deploy" % APP)
    print("  %s" % ROOT)
    print("")

    failed = []
    for name, fn in selected:
        try:
            problems, summary = fn()
        except Exception:
            problems, summary = ["phép kiểm tự nó gãy:\n%s" % _indent(traceback.format_exc())], "gãy"
        mark = "OK  " if not problems else "RỚT "
        print("  [%s] %-8s %s" % (mark, name, summary))
        for problem in problems:
            print("        %s" % problem.replace("\n", "\n  "))
        if problems:
            failed.append(name)
        sys.stdout.flush()

    print("")
    if failed:
        print("  RỚT: %s" % ", ".join(failed))
        print("")
        return 1
    print("  Tất cả %d phép kiểm đều xanh." % len(selected))
    print("")
    return 0


if __name__ == "__main__":
    sys.exit(main())
