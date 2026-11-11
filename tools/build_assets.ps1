# 用 Blender 重新產生 assets\ 底下的模型（每條賽道的 GLB＋中心線 JSON、卡丁車 GLB）。
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File tools\build_assets.ps1 [-Track hills,beach] [-V2] [-NoKart] [-Blender <blender.exe 路徑>]
# 不給 -Track 就全部重產（tools\blender\*_layout.json 每個一條；只挑跟產生器同一版格式的 layout）
# -V2：改用 build_track2.py（賽道格式 v2，見 tools\blender\TRACK_V2.md），多產出 <id>_col.json
param(
    [string]$Blender = 'D:\Tool\Blender\blender-4.2.23-windows-x64\blender.exe',
    [string[]]$Track,
    [switch]$V2,
    [switch]$NoKart
)
# 不設 ErrorActionPreference=Stop：PS 5.1 會把 Blender 寫到 stderr 的雜訊當成錯誤中斷
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path $Blender)) { throw "找不到 Blender：$Blender（用 -Blender 指定，需要 4.2 以上）" }
$script = if ($V2) { 'tools\blender\build_track2.py' } else { 'tools\blender\build_track.py' }
# -File 呼叫時逗號清單會變成一個字串，自己拆
$Track = @($Track | ForEach-Object { $_ -split ',' } | Where-Object { $_ })
if (-not $Track) {
    # v2 layout 的 points 是物件（{ "p": [...] }），v1 是 [x, z, y] 陣列
    $Track = Get-ChildItem (Join-Path $root 'tools\blender') -Filter '*_layout.json' | Where-Object {
        $p = (Get-Content $_.FullName -Raw -Encoding UTF8 | ConvertFrom-Json).points
        ($p.Count -gt 0 -and $p[0] -is [System.Management.Automation.PSCustomObject]) -eq [bool]$V2
    } | ForEach-Object { $_.Name -replace '_layout\.json$', '' }
}
Push-Location $root
try {
    foreach ($t in $Track) {
        & $Blender -b --factory-startup -P $script -- . $t 2>&1 | Where-Object { $_ -match '\[track2?\]|Error|Traceback|line \d+' }
    }
    if (-not $NoKart) {
        & $Blender -b --factory-startup -P tools\blender\build_kart.py -- . 2>&1 | Where-Object { $_ -match '\[kart\]|Error|Traceback' }
    }
} finally { Pop-Location }
