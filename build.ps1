<#
.SYNOPSIS
    一键打包 PDFer 为免安装的绿色版（dist\PDFer\PDFer.exe）。

.NOTES
    本文件必须保存为「UTF-8 with BOM」。Windows PowerShell 5.1 读取无 BOM 的 .ps1
    时会按系统 ANSI 代码页解码，中文会变成乱码并导致脚本无法解析。
    若用编辑器改过本文件，请确认 BOM 没被去掉。

.PARAMETER Python
    用于打包的 Python 解释器路径。留空时依次尝试 .venv、venv 和 PATH 中的 python。

.PARAMETER OneDir
    生成目录版 dist\PDFer\PDFer.exe。默认生成单文件 dist\PDFer.exe。

.EXAMPLE
    .\build.ps1
    .\build.ps1 -OneDir
    .\build.ps1 -Python "C:\Python313\python.exe"
#>
param(
    [string]$Python = "",
    [switch]$OneDir
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

if (-not $Python) {
    $candidates = @(
        (Join-Path $PSScriptRoot ".venv\Scripts\python.exe"),
        (Join-Path $PSScriptRoot "venv\Scripts\python.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            $Python = $candidate
            break
        }
    }
    if (-not $Python) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCommand) {
            $Python = $pythonCommand.Source
        }
    }
}

if (-not $Python -or -not (Test-Path -LiteralPath $Python)) {
    throw "找不到可用的 Python。请先创建 .venv，或用 -Python 参数指定解释器路径。"
}

$spec = if ($OneDir) { "pdfer.spec" } else { "pdfer-onefile.spec" }
$modeName = if ($OneDir) { "目录版" } else { "单 EXE" }

Write-Host "==> 1/3  生成图标" -ForegroundColor Cyan
& $Python -c "import sys; sys.path.insert(0, 'src'); from pdfer.icon import ensure_ico; print('    ', ensure_ico('assets/pdfer.ico'))"
if ($LASTEXITCODE -ne 0) { throw "图标生成失败（退出码 $LASTEXITCODE）" }

Write-Host ("==> 2/3  打包 {0}（首次约 1-3 分钟，请稍候）" -f $modeName) -ForegroundColor Cyan
& $Python -m PyInstaller --noconfirm --clean --log-level WARN $spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败（退出码 $LASTEXITCODE）" }

Write-Host "==> 3/3  产物信息" -ForegroundColor Cyan
$exe = if ($OneDir) {
    Join-Path $PSScriptRoot "dist\PDFer\PDFer.exe"
} else {
    Join-Path $PSScriptRoot "dist\PDFer.exe"
}
if (-not (Test-Path -LiteralPath $exe)) { throw "打包流程结束，但没有生成 $exe" }

if ($OneDir) {
    $bytes = (Get-ChildItem -LiteralPath (Join-Path $PSScriptRoot "dist\PDFer") -Recurse -File |
              Measure-Object -Property Length -Sum).Sum
} else {
    $bytes = (Get-Item -LiteralPath $exe).Length
    $hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    $hashFile = Join-Path $PSScriptRoot "dist\PDFer.exe.sha256.txt"
    "$hash  PDFer.exe" | Set-Content -LiteralPath $hashFile -Encoding ASCII
}

Write-Host ""
Write-Host ("  模式   : {0}" -f $modeName)
Write-Host ("  程序   : {0}" -f $exe)
Write-Host ("  体积   : {0:N1} MB" -f ($bytes / 1MB))
Write-Host ("  版本   : {0}" -f (& $Python -c "import sys; sys.path.insert(0, 'src'); from pdfer.version import __version__; print(__version__)"))
if ($OneDir) {
    Write-Host "  提示   : 整个 dist\PDFer 目录一起拷走；适合调试和更快冷启动。"
} else {
    Write-Host ("  校验   : {0}" -f $hashFile)
    Write-Host "  提示   : PDFer.exe 可单独复制到其它 Windows 电脑运行。"
}
