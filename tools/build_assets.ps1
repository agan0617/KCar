# 用 Blender 重新產生 assets\ 底下的模型（賽道 GLB＋中心線 JSON、卡丁車 GLB）。
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_assets.ps1 [-Blender <blender.exe 路徑>]
param(
    [string]$Blender = 'D:\Tool\Blender\blender-4.2.23-windows-x64\blender.exe',
    [string]$Track = 'track1'
)
# 不設 ErrorActionPreference=Stop：PS 5.1 會把 Blender 寫到 stderr 的雜訊當成錯誤中斷
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $Blender)) { throw "找不到 Blender：$Blender（用 -Blender 指定，需要 4.2 以上）" }
Push-Location $root
try {
    & $Blender -b --factory-startup -P tools\blender\build_track.py -- . $Track 2>&1 | Where-Object { $_ -match '\[track\]|Error|Traceback' }
    & $Blender -b --factory-startup -P tools\blender\build_kart.py -- . 2>&1 | Where-Object { $_ -match '\[kart\]|Error|Traceback' }
} finally { Pop-Location }
