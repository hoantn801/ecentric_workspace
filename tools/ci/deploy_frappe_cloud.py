# Copyright (c) 2026, eCentric and contributors
"""Bấm nút Deploy của Frappe Cloud từ dòng lệnh -- chỉ dùng thư viện chuẩn.

    python tools/ci/deploy_frappe_cloud.py --list-groups
    python tools/ci/deploy_frappe_cloud.py --group <bench group> --commit $(git rev-parse HEAD)
    python tools/ci/deploy_frappe_cloud.py --group <bench group> --wait

Biến môi trường bắt buộc:

    FC_API_KEY      API key của user trên Frappe Cloud
    FC_API_SECRET   API secret tương ứng
    FC_TEAM         team sở hữu bench group (bắt buộc khi user thuộc nhiều team)
    FC_BENCH_GROUP  tên bench group, thay cho --group
    FC_HOST         mặc định https://cloud.frappe.io

VỀ FC_TEAM. Một user Frappe Cloud có thể thuộc nhiều team. Không gửi header
`X-Press-Team` thì Press dùng team MẶC ĐỊNH của user (`get_current_team()` trong
`press/utils/__init__.py`) -- và nếu bench group nằm ở team khác thì mọi API trả về
danh sách RỖNG chứ không báo lỗi. Rỗng-mà-không-lỗi là kiểu hỏng khó đoán nhất, nên
`--list-groups` in luôn danh sách team khi không thấy group nào.

Ở máy, đặt chúng trong file `.env` ở gốc repo (`.gitignore` đã chặn file này) --
script tự đọc. Trên GitHub Actions thì không có `.env`; giá trị đến từ secret của repo.
Biến đã có sẵn trong môi trường luôn THẮNG file `.env`, để CI không bao giờ đọc nhầm
một file lọt vào runner.

NÓ GỌI GÌ. Đúng ba method mà nút "Update" trên dashboard Frappe Cloud gọi
(`press/api/bench.py` trong repo frappe/press):

    press.api.bench.fetch_latest_app_update   ép FC đọc lại GitHub ngay, không chờ webhook
    press.api.bench.deploy_information        app nào có bản mới, site nào thuộc bench group
    press.api.bench.deploy_and_update         build image mới rồi chuyển site sang bench mới

VÌ SAO KHÔNG DỰA HẲN VÀO AUTO DEPLOY CỦA FRAPPE CLOUD. Auto Deploy chạy ngay khi FC nhận
webhook của GitHub, tức là TRƯỚC khi CI kịp chạy -- commit gãy vẫn lên site. Tắt Auto
Deploy và để job này gọi sau khi các phép kiểm xanh thì thứ tự mới đúng. Đánh đổi: nếu
job không chạy (hỏng secret, GitHub Actions chết) thì không có gì tự deploy nữa.

ĐIỀU CHƯA KIỂM CHỨNG. Hình dạng tham số ở đây đọc từ mã nguồn `frappe/press` nhánh
master và từ chính dashboard Vue của Frappe Cloud, KHÔNG phải từ một lần chạy thật với
tài khoản của eCentric. Lần chạy đầu tiên nên làm bằng tay (`--dry-run` rồi bỏ cờ đó ra)
và đọc kỹ những gì nó in. Press là sản phẩm chạy liên tục; nếu FC đổi tên tham số thì chỗ
gãy sẽ là `deploy_and_update` và thông báo lỗi trả về nguyên văn.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_HOST = "https://cloud.frappe.io"

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

#: Trạng thái cuối của một Deploy Candidate. Ngoài hai giá trị này nghĩa là còn đang chạy.
TERMINAL_OK = {"Success"}
TERMINAL_FAIL = {"Failure"}


class PressError(Exception):
    pass


def load_env_file(path):
    """Đọc `.env` dạng `KHOÁ=giá trị` vào os.environ. Trả về các khoá đã nạp.

    Cố tình KHÔNG đè biến đã có sẵn: trên CI, secret đến từ môi trường và phải thắng
    bất cứ file nào tình cờ nằm trong runner.

    Đây là bản tối giản, không phải `python-dotenv`: không nội suy `${BIẾN}`, không
    chuỗi nhiều dòng. Nếu một ngày cần tới những thứ đó thì lúc đó hẵng thêm phụ thuộc.
    """
    if not os.path.isfile(path):
        return []

    loaded = []
    with open(path, "r", encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            key, sep, value = line.partition("=")
            if not sep:
                continue
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            if key and key not in os.environ:
                os.environ[key] = value
                loaded.append(key)
    return loaded


# -- gọi API --------------------------------------------------------------

def call(host, key, secret, method, params=None, team=None, attempts=3, timeout=60):
    """POST /api/method/<method> và trả về giá trị của khoá `message`.

    Frappe bọc kết quả whitelisted method trong `{"message": ...}`. Lỗi trả về HTTP 4xx/5xx
    kèm JSON có `exception`; in nguyên văn vì thông báo của Press thường đã đủ rõ (vd
    "Bench can only be deployed by the bench owner").
    """
    url = "%s/api/method/%s" % (host.rstrip("/"), method)
    body = json.dumps(params or {}).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Authorization", "token %s:%s" % (key, secret))
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    if team:
        request.add_header("X-Press-Team", team)

    last = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8") or "{}")
                return payload.get("message")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            try:
                parsed = json.loads(detail)
                detail = parsed.get("exception") or parsed.get("message") or detail
            except ValueError:
                pass
            if exc.code in (401, 403):
                raise PressError(
                    "%s -> HTTP %d. Kiểm tra FC_API_KEY/FC_API_SECRET và quyền của user "
                    "trên bench group này.\n%s" % (method, exc.code, detail)
                )
            if exc.code < 500:
                raise PressError("%s -> HTTP %d\n%s" % (method, exc.code, detail))
            last = PressError("%s -> HTTP %d\n%s" % (method, exc.code, detail))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last = PressError("%s -> %s" % (method, exc))

        if attempt < attempts:
            time.sleep(3 * attempt)
    raise last


# -- các bước -------------------------------------------------------------

def list_groups(api, team):
    groups = api("press.api.bench.all") or []
    if not groups:
        # Rỗng ở đây hầu như luôn là "sai team", không phải "không có bench group".
        # In thẳng danh sách team ra để bước tiếp theo là copy-paste, không phải đoán.
        account = api("press.api.account.get") or {}
        teams = account.get("teams") or []
        print("  Không thấy bench group nào ở team %s." % (team or "(mặc định của user)"))
        if len(teams) > 1 or (teams and not team):
            print("  User %s thuộc %d team. Thử lại với --team:" % (
                (account.get("user") or {}).get("name", "?"), len(teams)))
            for item in teams:
                print("      --team %-14s (%s, chủ: %s)" % (
                    item.get("name"), item.get("team_title"), item.get("user")))
        return
    print("")
    print("  %-28s %-24s %-10s %s" % ("NAME (dùng cho --group)", "TITLE", "VERSION", "SITES"))
    for group in groups:
        print("  %-28s %-24s %-10s %s" % (
            group.get("name"), group.get("title"), group.get("version"),
            group.get("number_of_sites"),
        ))
    print("")


def pick_release(app):
    """Bản release sẽ deploy cho app này, chọn đúng như dashboard Frappe Cloud chọn.

    `releases` chỉ chứa các bản MỚI HƠN bản đang chạy, xếp mới nhất trước
    (`ReleaseGroup.get_next_apps`). Bench đang chạy bản mới nhất => danh sách rỗng, và
    đó là trạng thái bình thường chứ không phải lỗi.
    """
    releases = app.get("releases") or []
    target = app.get("next_release")
    for release in releases:
        if release.get("name") == target and not release.get("is_yanked"):
            return release.get("name"), release.get("hash")

    # Bản mới nhất bị yank: lùi về bản dùng được gần nhất thay vì bỏ cuộc. `--commit`
    # vẫn chặn ở bước sau nếu bản đó không phải commit đang cần.
    for release in releases:
        if not release.get("is_yanked"):
            return release.get("name"), release.get("hash")

    return target, app.get("next_release_hash")


def find_app(info, app_name):
    for app in info.get("apps") or []:
        if app.get("app") == app_name or app.get("name") == app_name:
            return app
    known = ", ".join(sorted(a.get("app") or a.get("name") for a in info.get("apps") or []))
    raise PressError("Bench group không có app %r. App đang có: %s" % (app_name, known))


def wait_for_commit(api, group, app_name, commit, timeout, interval):
    """Chờ tới khi FC đã tạo App Release cho đúng commit này.

    Webhook GitHub -> App Release không tức thời. Deploy trước khi FC thấy commit mới thì
    build ra đúng cái đang chạy, và job vẫn xanh -- kiểu thất bại tệ nhất vì im lặng.

    Trả về thêm cờ `đã chạy rồi`: `deploy_information` chỉ liệt kê những release MỚI HƠN
    bản đang chạy, nên khi bench đã ở đúng commit cần thì danh sách rỗng. Không so với
    `current_hash` trước thì hàm này sẽ chờ hết giờ đúng lúc mọi thứ đang ổn.
    """
    deadline = time.time() + timeout
    while True:
        info = api("press.api.bench.deploy_information", {"name": group})
        app = find_app(info, app_name)
        release, app_hash = pick_release(app)
        current = (app.get("current_hash") or "").lower()

        if commit and current.startswith(commit.lower()[:10]):
            return info, app, release, app_hash, True

        if info.get("deploy_in_progress"):
            state = "bench group đang deploy dở"
        elif not commit:
            return info, app, release, app_hash, False
        elif app_hash and app_hash.lower().startswith(commit.lower()[:10]):
            return info, app, release, app_hash, False
        else:
            state = "bench đang chạy %s, FC chưa có release cho %s" % (
                current[:10] or "(không rõ)", commit[:10])

        if time.time() >= deadline:
            raise PressError(
                "Hết %ds chờ mà %s.\n"
                "Thường là do app trên FC trỏ nhánh khác, hoặc GitHub App của Frappe Cloud "
                "chưa được cấp quyền trên repo này." % (timeout, state)
            )
        print("  ... %s -- chờ %ds" % (state, interval))
        sys.stdout.flush()
        time.sleep(interval)


def wait_for_deploy(api, group, timeout, interval):
    """Chờ build xong, rồi báo trạng thái Deploy Candidate mới nhất.

    Đây là phần mong manh nhất của script: Press đang chuyển dần sang Release Pipeline và
    trạng thái build đã dời sang Deploy Candidate Build. Nên chỉ coi "Failure" là RỚT,
    còn trạng thái lạ thì in ra và để người đọc quyết định -- đoán mò ở đây sẽ tạo ra
    job đỏ giả hoặc xanh giả.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        info = api("press.api.bench.deploy_information", {"name": group})
        if not info.get("deploy_in_progress") and not info.get("has_running_release_pipeline"):
            break
        print("  ... đang build")
        sys.stdout.flush()
        time.sleep(interval)
    else:
        print("  Hết %ds chờ. Build vẫn đang chạy -- xem tiếp trên dashboard." % timeout)
        return 0

    candidates = list(api("press.api.bench.candidates", {
        "filters": {"group": group}, "order_by": "creation desc", "limit_page_length": 1,
    }) or [])
    if not candidates:
        print("  Không đọc được trạng thái build. Xem trên dashboard.")
        return 0

    latest = candidates[0]
    status = latest.get("status")
    print("  Deploy Candidate %s -> %s" % (latest.get("name"), status))
    if status in TERMINAL_FAIL:
        return 1
    if status not in TERMINAL_OK:
        print("  Trạng thái không nằm trong tập đã biết; coi như chưa kết luận được.")
    return 0


# -- main -----------------------------------------------------------------

def main():
    # Console Windows mặc định cp1252 và mọi chuỗi help ở đây là tiếng Việt, nên phải
    # sửa stream TRƯỚC `parse_args()` -- đặt sau thì `--help` gãy vì UnicodeEncodeError
    # trước khi kịp chạy tới dòng sửa.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="Trigger deploy trên Frappe Cloud")
    parser.add_argument("--group", help="tên bench group (Release Group.name); mặc định FC_BENCH_GROUP")
    parser.add_argument("--team", help="team sở hữu bench group; mặc định FC_TEAM")
    parser.add_argument("--app", default="ecentric_workspace",
                        help="tên app trên bench group (mặc định ecentric_workspace)")
    parser.add_argument("--commit", help="SHA phải có mặt trên FC trước khi deploy")
    parser.add_argument("--host", default=os.environ.get("FC_HOST", DEFAULT_HOST))
    parser.add_argument("--list-groups", action="store_true",
                        help="in các bench group của tài khoản rồi thoát")
    parser.add_argument("--wait", action="store_true", help="chờ build xong và báo kết quả")
    parser.add_argument("--skip-sites", action="store_true",
                        help="chỉ build bench mới, KHÔNG chuyển site sang")
    parser.add_argument("--dry-run", action="store_true",
                        help="in payload sẽ gửi rồi dừng, không deploy")
    parser.add_argument("--release-timeout", type=int, default=600,
                        help="giây chờ FC thấy commit (mặc định 600)")
    parser.add_argument("--build-timeout", type=int, default=2400,
                        help="giây chờ build khi có --wait (mặc định 2400)")
    parser.add_argument("--interval", type=int, default=20)
    parser.add_argument("--env-file", default=os.path.join(ROOT, ".env"),
                        help="file .env đọc thêm (mặc định .env ở gốc repo)")
    args = parser.parse_args()

    loaded = load_env_file(args.env_file)
    if loaded:
        print("  đọc %s: %s" % (os.path.basename(args.env_file), ", ".join(loaded)))

    # `--host` lấy default lúc parse, tức TRƯỚC khi .env được nạp. Bù lại ở đây, nhưng
    # chỉ khi người dùng không tự truyền --host.
    if "--host" not in sys.argv:
        args.host = os.environ.get("FC_HOST", DEFAULT_HOST)

    key = os.environ.get("FC_API_KEY")
    secret = os.environ.get("FC_API_SECRET")
    if not key or not secret:
        raise SystemExit(
            "Thiếu FC_API_KEY / FC_API_SECRET.\n"
            "Đã tìm trong biến môi trường và trong %s.\n"
            "File .env cần đúng dạng, mỗi dòng một khoá, không có khoảng trắng quanh dấu =:\n"
            "    FC_API_KEY=...\n    FC_API_SECRET=..." % args.env_file
        )

    team = args.team or os.environ.get("FC_TEAM") or None
    group = args.group or os.environ.get("FC_BENCH_GROUP") or None

    def api(method, params=None):
        return call(args.host, key, secret, method, params, team=team)

    if args.list_groups:
        list_groups(api, team)
        return 0

    if not group:
        raise SystemExit("Thiếu --group (hoặc FC_BENCH_GROUP). Chạy --list-groups để xem tên.")
    args.group = group

    print("")
    print("  Frappe Cloud · %s" % args.host)
    print("  team          %s" % (team or "(mặc định của user)"))
    print("  bench group   %s" % args.group)
    print("  app           %s" % args.app)
    print("  commit        %s" % (args.commit or "(không kiểm)"))
    print("")

    # Ép FC đọc GitHub ngay. Webhook có thể chậm hoặc trượt; gọi thêm ở đây là rẻ và
    # biến "chờ vô định" thành "chờ có giới hạn".
    try:
        api("press.api.bench.fetch_latest_app_update", {"name": args.group, "app": args.app})
    except PressError as exc:
        print("  Không ép được FC đọc lại GitHub (vẫn tiếp tục, chờ webhook):\n  %s" % exc)

    info, app, release, app_hash, already_deployed = wait_for_commit(
        api, args.group, args.app, args.commit, args.release_timeout, args.interval
    )

    if already_deployed:
        print("  Không có gì để deploy: bench đã chạy đúng %s." % args.commit[:10])
        return 0

    if not app.get("update_available"):
        print("  Không có gì để deploy: bench đang chạy đúng %s." % (app_hash or "bản này"))
        return 0

    if not release or not app_hash:
        raise PressError(
            "FC chưa có App Release dùng được cho %s. Mở dashboard xem mục Apps của bench "
            "group -- thường là repo chưa được GitHub App của Frappe Cloud cấp quyền."
            % args.app
        )

    apps = [{"app": args.app, "source": app.get("source"), "release": release, "hash": app_hash}]
    sites = [] if args.skip_sites else (info.get("sites") or [])

    print("  sẽ deploy     %s  (release %s)" % (app_hash[:10], release))
    print("  site cập nhật %s" % (", ".join(s.get("name") for s in sites) or "(không có)"))
    print("")

    if args.dry_run:
        print(json.dumps({"name": args.group, "apps": apps, "sites": sites},
                         ensure_ascii=False, indent=2))
        print("\n  --dry-run: dừng ở đây.")
        return 0

    result = api("press.api.bench.deploy_and_update",
                 {"name": args.group, "apps": apps, "sites": sites})
    print("  Đã bấm deploy. Press trả về: %s" % result)
    print("  Theo dõi: %s/dashboard/groups/%s/deploys"
          % (args.host.rstrip("/"), args.group))
    print("")

    if args.wait:
        return wait_for_deploy(api, args.group, args.build_timeout, args.interval)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PressError as error:
        print("\n  RỚT: %s\n" % error)
        sys.exit(1)
