$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$script:root = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:port = 8765
$script:base = "http://127.0.0.1:$($script:port)"
$script:proc = $null
$script:running = $true

# 单实例：用文件锁判断托盘是否已在运行（进程退出会自动释放）
$script:lockPath = Join-Path $script:root 'tray.lock'
$script:lock = $null
try {
    $script:lock = [System.IO.File]::Open(
        $script:lockPath,
        [System.IO.FileMode]::OpenOrCreate,
        [System.IO.FileAccess]::ReadWrite,
        [System.IO.FileShare]::None)
} catch {
    exit
}

function Test-Port {
    $c = New-Object Net.Sockets.TcpClient
    try {
        return $c.ConnectAsync('127.0.0.1', $script:port).Wait(300)
    } catch {
        return $false
    } finally {
        $c.Dispose()
    }
}

function Start-Server {
    if (Test-Port) { return $true }
    $bundled = 'C:\Users\zhehua\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe'
    if (Test-Path $bundled) {
        $py = $bundled
    } elseif (Get-Command pythonw.exe -ErrorAction SilentlyContinue) {
        $py = (Get-Command pythonw.exe).Source
    } elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
        $py = (Get-Command python.exe).Source
    } else {
        return $false
    }
    $script:proc = Start-Process -FilePath $py `
        -ArgumentList '-X', 'utf8', 'app.py', "$($script:port)" `
        -WorkingDirectory $script:root -WindowStyle Hidden -PassThru
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Milliseconds 250
        if (Test-Port) { return $true }
    }
    return (Test-Port)
}

function Ensure-Server {
    if (Test-Port) { return $true }
    return (Start-Server)
}

function Invoke-Api($path, $payload) {
    $json = '{}'
    if ($null -ne $payload) {
        $json = $payload | ConvertTo-Json -Compress
    }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    return Invoke-RestMethod -Uri "$($script:base)$path" -Method Post `
        -ContentType 'application/json; charset=utf-8' -Body $bytes -TimeoutSec 6
}

function Show-Msg($text, $isError = $false) {
    $icon = [System.Windows.Forms.ToolTipIcon]::Info
    if ($isError) { $icon = [System.Windows.Forms.ToolTipIcon]::Error }
    $script:ni.ShowBalloonTip(2500, 'AniMe Vision', $text, $icon)
}

$serverOk = Start-Server
if (-not $serverOk) {
    [System.Windows.Forms.MessageBox]::Show('后台服务启动失败，请检查 Python，或用 start.bat 启动。')
}

function Close-Tray {
    $script:running = $false
    try { $script:ni.Visible = $false; $script:ni.Dispose() } catch { }
    try { if ($script:lock) { $script:lock.Dispose() } } catch { }
    Remove-Item $script:lockPath -ErrorAction SilentlyContinue
}

# 托盘图标
$script:ni = New-Object System.Windows.Forms.NotifyIcon
$iconPath = Join-Path $script:root 'anime.ico'
if (Test-Path $iconPath) {
    $script:ni.Icon = New-Object System.Drawing.Icon -ArgumentList $iconPath
} else {
    $script:ni.Icon = [System.Drawing.SystemIcons]::Application
}
$script:ni.Text = 'AniMe Vision 控制台'
$script:ni.Visible = $true

$menu = New-Object System.Windows.Forms.ContextMenuStrip

$fx = $menu.Items.Add('灯效')
$fx.add_Click({
    try {
        if (-not (Ensure-Server)) { Show-Msg '后台服务未启动' $true; return }
        $r = Invoke-Api '/api/playlist/start' @{}
        if ($r.ok) { Show-Msg '已切换到灯效' } else { Show-Msg ("灯效： " + $r.error) $true }
    } catch {
        Show-Msg ('灯效失败：' + $_.Exception.Message) $true
    }
})

$sys = $menu.Items.Add('系统信息')
$sys.add_Click({
    try {
        if (-not (Ensure-Server)) { Show-Msg '后台服务未启动' $true; return }
        $r = Invoke-Api '/api/sysinfo' @{ use_saved = $true }
        if ($r.ok) { Show-Msg '已切换到系统信息' } else { Show-Msg ('系统信息： ' + $r.error) $true }
    } catch {
        Show-Msg ('系统信息失败：' + $_.Exception.Message) $true
    }
})

$music = $menu.Items.Add('音乐')
$music.add_Click({
    try {
        if (-not (Ensure-Server)) { Show-Msg '后台服务未启动' $true; return }
        $style = 'bars'
        $gain = 1.0
        $prefsPath = Join-Path $script:root 'prefs.json'
        if (Test-Path $prefsPath) {
            try {
                $p = Get-Content $prefsPath -Raw -Encoding UTF8 | ConvertFrom-Json
                if ($p.music_style) { $style = [string]$p.music_style }
                if ($p.gain) { $gain = [double]$p.gain }
            } catch { }
        }
        $r = Invoke-Api '/api/music' @{ on = $true; gain = $gain; style = $style }
        if ($r.ok) { Show-Msg '已切换到音乐' } else { Show-Msg ('音乐： ' + $r.error) $true }
    } catch {
        Show-Msg ('音乐失败：' + $_.Exception.Message) $true
    }
})

$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

$miOpen = $menu.Items.Add('打开控制台')
$miOpen.add_Click({
    if (Ensure-Server) {
        Start-Process $script:base
    } else {
        Show-Msg '后台服务未启动' $true
    }
})

$menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

$quit = $menu.Items.Add('退出')
$quit.add_Click({
    try {
        Invoke-WebRequest "$($script:base)/api/shutdown" -UseBasicParsing -TimeoutSec 5 | Out-Null
    } catch { }
    Start-Sleep -Milliseconds 1200
    # 兜底：不管服务有没有正常清屏，直接再写一帧全灭
    $pyw = 'C:\Users\zhehua\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\pythonw.exe'
    if (-not (Test-Path $pyw)) {
        $c = Get-Command pythonw.exe -ErrorAction SilentlyContinue
        if ($c) { $pyw = $c.Source } else { $pyw = $null }
    }
    if ($pyw) {
        try {
            $clr = Start-Process -FilePath $pyw `
                -ArgumentList '-X', 'utf8', 'clear_panel.py' `
                -WorkingDirectory $script:root -WindowStyle Hidden -PassThru
            if (-not $clr.WaitForExit(3000)) {
                try { Stop-Process -Id $clr.Id -Force } catch { }
            }
        } catch { }
    }
    if ($script:proc -and -not $script:proc.HasExited) {
        try { Stop-Process -Id $script:proc.Id -Force } catch { }
    }
    Close-Tray
})

# 网页里点「关闭程序」后服务会退出，托盘发现端口没了就一起收掉
$script:serverOk = $serverOk
$script:downTicks = 0
$script:lastCheck = Get-Date
$script:firstTick = $true

$script:ni.ContextMenuStrip = $menu
$script:ni.add_DoubleClick({
    if (Ensure-Server) { Start-Process $script:base }
})

while ($script:running) {
    [System.Windows.Forms.Application]::DoEvents()
    if ($script:firstTick) {
        $script:firstTick = $false
        try {
            # 某些 Windows 11 上需要重新挂一次才会出现在隐藏图标里
            $script:ni.Visible = $false
            Start-Sleep -Milliseconds 150
            $script:ni.Visible = $true
            $script:ni.ShowBalloonTip(3000, 'AniMe Vision',
                '托盘已启动，右键图标可快速切换灯效',
                [System.Windows.Forms.ToolTipIcon]::Info)
        } catch { }
    }
    Start-Sleep -Milliseconds 100
    if (((Get-Date) - $script:lastCheck).TotalSeconds -ge 1.5) {
        $script:lastCheck = Get-Date
        if (Test-Port) {
            $script:downTicks = 0
        } elseif ($script:proc -and -not $script:proc.HasExited) {
            # 服务进程还在，端口暂时探测失败不算退出
            $script:downTicks = 0
        } elseif (-not $script:serverOk) {
            # 启动失败时保留托盘，方便右键重试
            $script:downTicks = 0
        } else {
            $script:downTicks++
            if ($script:downTicks -ge 3) {
                Close-Tray
            }
        }
    }
}
