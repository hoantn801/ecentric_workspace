<#
  Đồng bộ chấm công: máy khuôn mặt Hikvision  ->  ERP eCentric   (ec-face-checkin-v1)

  Chạy trên một máy Windows ĐANG Ở VĂN PHÒNG (cùng mạng với máy chấm công).
  Đọc toàn bộ lượt quét của một tháng trên máy rồi gửi lên ERP. Lượt nào ERP đã có
  (máy đã tự đẩy lên lúc quét) thì ERP bỏ qua, nên bấm bao nhiêu lần cũng không trùng.

  Bấm đúp "Dong bo cham cong.bat". Lần đầu sẽ hỏi IP máy, tài khoản máy và mã ERP;
  mật khẩu được mã hoá bằng tài khoản Windows đang dùng (chỉ người này giải được).

  Tuỳ chọn:
    -Thang 2026-09    đồng bộ tháng chỉ định (mặc định: hỏi, Enter = tháng này)
    -ChiXem           chỉ đọc máy và đếm theo loại sự kiện, KHÔNG gửi lên ERP
    -CaiDatLai        nhập lại IP / mật khẩu / mã ERP
#>
param(
    [string]$Thang = "",
    [switch]$ChiXem,
    [switch]$CaiDatLai,
    [switch]$KhongHoi,
    [string]$MatKhauMay = "",
    [string]$MaErp = ""
)

$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
} catch {}

$Here = $PSScriptRoot
$CfgPath = Join-Path $Here "cau-hinh.json"
$SecPath = Join-Path $Here "bi-mat.dat"
$LogPath = Join-Path $Here "nhat-ky.txt"
$ErpMethod = "/api/method/ecentric_workspace.hr.face_device.api.sync"

function Write-Log([string]$msg) {
    $line = "{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    try { Add-Content -Path $LogPath -Value $line -Encoding UTF8 } catch {}
}

function Ask([string]$label, [string]$default) {
    $v = Read-Host ("{0} [{1}]" -f $label, $default)
    if ([string]::IsNullOrWhiteSpace($v)) { return $default }
    return $v.Trim()
}

function Get-Config {
    $cfg = [ordered]@{ erp_url = "https://team.ecentric.vn"; device_host = ""; device_user = "admin";
                       device_name = "VP"; tz = "+07:00"; page_size = 30; batch = 500 }
    if (Test-Path $CfgPath) {
        $saved = Get-Content $CfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($p in $saved.PSObject.Properties) { $cfg[$p.Name] = $p.Value }
    }
    if ($KhongHoi) { return $cfg }
    if ($CaiDatLai -or -not $cfg.device_host) {
        Write-Host "--- Cài đặt lần đầu ---"
        $cfg.device_host = Ask "IP máy chấm công (xem trên máy: Cài đặt > Mạng)" $cfg.device_host
        $cfg.device_user = Ask "Tài khoản đăng nhập máy" $cfg.device_user
        $cfg.device_name = Ask "Tên máy (để phân biệt nếu có nhiều máy)" $cfg.device_name
        $cfg.erp_url = Ask "Địa chỉ ERP" $cfg.erp_url
        ($cfg | ConvertTo-Json) | Set-Content -Path $CfgPath -Encoding UTF8
    }
    return $cfg
}

function To-Plain($secure) {
    $b = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($b) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($b) }
}

function Get-Secrets {
    if ($MatKhauMay -and $MaErp) { return @{ device = $MatKhauMay; erp = $MaErp } }
    if ((Test-Path $SecPath) -and -not $CaiDatLai) {
        $s = Get-Content $SecPath -Raw | ConvertFrom-Json
        return @{ device = To-Plain (ConvertTo-SecureString $s.device);
                  erp = To-Plain (ConvertTo-SecureString $s.erp) }
    }
    if ($KhongHoi) { throw "Chưa có mật khẩu đã lưu. Chạy tay một lần để nhập." }
    $d = Read-Host "Mật khẩu tài khoản máy chấm công" -AsSecureString
    $e = Read-Host "Mã đồng bộ ERP (ec_face_sync_token, hỏi Hoàn)" -AsSecureString
    @{ device = (ConvertFrom-SecureString $d); erp = (ConvertFrom-SecureString $e) } |
        ConvertTo-Json | Set-Content -Path $SecPath -Encoding UTF8
    return @{ device = To-Plain $d; erp = To-Plain $e }
}

function Invoke-Device($cfg, [string]$pass, [string]$path, $body) {
    # Máy Hikvision dùng Digest auth; HttpWebRequest tự trả lời thử thách 401.
    $base = "http://{0}" -f $cfg.device_host
    $cc = New-Object System.Net.CredentialCache
    $cc.Add([Uri]$base, "Digest", (New-Object System.Net.NetworkCredential($cfg.device_user, $pass)))
    $req = [System.Net.HttpWebRequest]::Create($base + $path)
    $req.Method = "POST"
    $req.Credentials = $cc
    $req.ContentType = "application/json"
    $req.Timeout = 30000
    $bytes = [Text.Encoding]::UTF8.GetBytes(($body | ConvertTo-Json -Depth 5 -Compress))
    $req.ContentLength = $bytes.Length
    $st = $req.GetRequestStream(); $st.Write($bytes, 0, $bytes.Length); $st.Close()
    $resp = $req.GetResponse()
    try {
        $rd = New-Object IO.StreamReader($resp.GetResponseStream(), [Text.Encoding]::UTF8)
        return ($rd.ReadToEnd() | ConvertFrom-Json)
    } finally { $resp.Close() }
}

function Get-DeviceEvents($cfg, [string]$pass, [string]$start, [string]$end) {
    $all = New-Object System.Collections.ArrayList
    $sid = [guid]::NewGuid().ToString("N")
    $pos = 0
    for ($page = 0; $page -lt 20000; $page++) {
        $cond = [ordered]@{ searchID = $sid; searchResultPosition = $pos; maxResults = [int]$cfg.page_size;
                            major = 5; minor = 0; startTime = $start; endTime = $end }
        $r = (Invoke-Device $cfg $pass "/ISAPI/AccessControl/AcsEvent?format=json" @{ AcsEventCond = $cond }).AcsEvent
        $n = [int]$r.numOfMatches
        foreach ($it in @($r.InfoList)) {
            if ($null -eq $it) { continue }
            [void]$all.Add([ordered]@{ major = $it.major; minor = $it.minor; time = $it.time;
                                       employeeNoString = $it.employeeNoString; serialNo = $it.serialNo })
        }
        $pos += $n
        if ($page % 10 -eq 9) { Write-Host ("  ... đã đọc {0} sự kiện" -f $all.Count) }
        if ($r.responseStatusStrg -ne "MORE" -or $n -le 0) { break }
    }
    return ,$all
}

function Send-Erp($cfg, [string]$token, $events) {
    $sum = [ordered]@{ created = 0; present = 0; duplicate = 0; closed = 0; errors = 0; bad_time = 0 }
    $unknown = New-Object System.Collections.ArrayList
    $url = $cfg.erp_url.TrimEnd("/") + $ErpMethod
    $size = [int]$cfg.batch
    for ($i = 0; $i -lt [Math]::Max($events.Count, 1); $i += $size) {
        $chunk = @()
        if ($events.Count -gt 0) { $chunk = @($events[$i..([Math]::Min($i + $size, $events.Count) - 1)]) }
        $json = @{ device = $cfg.device_name; events = $chunk } | ConvertTo-Json -Depth 5 -Compress
        $r = Invoke-RestMethod -Method Post -Uri $url -Headers @{ "X-EC-Face-Token" = $token } `
                -ContentType "application/json; charset=utf-8" -Body ([Text.Encoding]::UTF8.GetBytes($json)) -TimeoutSec 120
        $m = $r.message
        if (-not $m.ok) { throw "ERP từ chối (sai mã đồng bộ hoặc chưa bật)." }
        if ($m.disabled) { throw "Đồng bộ chấm công đang tắt trên ERP (ec_face_checkin_disabled)." }
        foreach ($k in @($sum.Keys)) { $sum[$k] += [int]$m.$k }
        foreach ($u in @($m.unknown)) { if ($u -and -not $unknown.Contains($u)) { [void]$unknown.Add($u) } }
    }
    $sum["unknown"] = $unknown
    return $sum
}

function Get-Range([string]$ym, [string]$tz) {
    $first = [datetime]::ParseExact($ym + "-01", "yyyy-MM-dd", $null)
    $last = $first.AddMonths(1).AddSeconds(-1)
    if ($last -gt (Get-Date)) { $last = Get-Date }
    return @(($first.ToString("yyyy-MM-ddTHH:mm:ss") + $tz), ($last.ToString("yyyy-MM-ddTHH:mm:ss") + $tz))
}

# ------------------------------------------------------------------ chạy
try {
    Write-Host "=== Đồng bộ chấm công máy khuôn mặt -> ERP ==="
    $cfg = Get-Config
    $sec = Get-Secrets
    if (-not $Thang) {
        $Thang = (Get-Date).ToString("yyyy-MM")
        if (-not $KhongHoi) { $Thang = Ask "Đồng bộ tháng nào (yyyy-MM)" $Thang }
    }
    if ($Thang -notmatch '^\d{4}-\d{2}$') { throw "Tháng phải có dạng 2026-09." }
    $range = Get-Range $Thang $cfg.tz
    Write-Host ("Đọc máy {0}: {1} -> {2}" -f $cfg.device_host, $range[0], $range[1])
    $events = Get-DeviceEvents $cfg $sec.device $range[0] $range[1]
    Write-Host ("Máy trả về {0} sự kiện." -f $events.Count)

    if ($ChiXem) {
        $events | Group-Object { "major {0} / minor {1}" -f $_.major, $_.minor } | Sort-Object Count -Descending |
            ForEach-Object { Write-Host ("  {0,-24} {1,6} lần" -f $_.Name, $_.Count) }
        Write-Host "(Chế độ chỉ xem: không gửi gì lên ERP.)"
        Write-Log ("ChiXem {0}: {1} su kien" -f $Thang, $events.Count)
        return
    }

    $s = Send-Erp $cfg $sec.erp $events
    Write-Host ""
    Write-Host ("Thêm mới lên ERP:        {0} lượt chấm" -f $s.created)
    Write-Host ("  trong đó tạo ngày công: {0}" -f $s.present)
    Write-Host ("ERP đã có sẵn (bỏ qua):  {0}" -f $s.duplicate)
    if ($s.closed) { Write-Host ("Tháng đã chốt công (không ghi): {0}" -f $s.closed) -ForegroundColor Yellow }
    if ($s.unknown.Count) {
        Write-Host ("Mã trên máy CHƯA gắn nhân viên: {0}" -f ($s.unknown -join ", ")) -ForegroundColor Yellow
        Write-Host "  -> Nhân sự điền mã này vào 'Attendance Device ID' của nhân viên rồi bấm đồng bộ lại."
    }
    if ($s.errors -or $s.bad_time) { Write-Host ("Lỗi: {0} (xem Error Log trên ERP)" -f ($s.errors + $s.bad_time)) -ForegroundColor Red }
    Write-Host "Xong."
    Write-Log ("{0}: may={1} moi={2} cong={3} trung={4} chot={5} chua_gan={6} loi={7}" -f $Thang, $events.Count,
        $s.created, $s.present, $s.duplicate, $s.closed, ($s.unknown -join "|"), $s.errors)
} catch {
    $msg = $_.Exception.Message
    if ($msg -match "401") { $msg = "Sai tài khoản / mật khẩu máy chấm công. Chạy lại với -CaiDatLai." }
    elseif ($msg -match "403") { $msg = "ERP từ chối: sai mã đồng bộ hoặc ERP chưa cấu hình ec_face_sync_token. Chạy lại với -CaiDatLai." }
    elseif ($msg -match "Unable to connect|actively refused|timed out|No such host|Name or service") {
        $msg = "Không kết nối được máy chấm công. Laptop phải đang dùng mạng văn phòng. (" + $msg + ")"
    }
    Write-Host ("LỖI: " + $msg) -ForegroundColor Red
    Write-Log ("LOI " + $msg)
    exit 1
}
