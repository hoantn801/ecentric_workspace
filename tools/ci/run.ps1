# Copyright (c) 2026, eCentric and contributors
# Chạy đúng bộ kiểm tra mà GitHub Actions chạy, nhưng ở máy này.
#
#     .\tools\ci\run.ps1
#     .\tools\ci\run.ps1 -Only pagesync
#     .\tools\ci\run.ps1 -Skip pagesync
#
# Chạy được từ bất kỳ thư mục nào -- script tự tìm gốc repo theo vị trí của chính nó.
[CmdletBinding()]
param(
    [string[]]$Only,
    [string[]]$Skip
)

$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$check = Join-Path $here "check.py"

$python = (Get-Command python -ErrorAction SilentlyContinue)
if ($null -eq $python) {
    Write-Error "Không tìm thấy python trong PATH. Cài Python 3.10+ rồi chạy lại."
}

# jinja2 là phụ thuộc DUY NHẤT của bộ kiểm. Kiểm trước để lỗi hiện ra dưới dạng một câu
# hướng dẫn, không phải ImportError giữa lúc kiểm.
& python -c "import jinja2" 2>$null
if (-not $?) {
    Write-Host "Thiếu jinja2. Đang cài..." -ForegroundColor Yellow
    & python -m pip install --quiet "jinja2>=3.1"
    if (-not $?) { Write-Error "Cài jinja2 thất bại." }
}

$arguments = @($check)
foreach ($name in $Only) { $arguments += @("--only", $name) }
foreach ($name in $Skip) { $arguments += @("--skip", $name) }

& python @arguments
exit $LASTEXITCODE
