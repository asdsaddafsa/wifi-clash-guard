param(
    [switch]$Launch,
    [switch]$Check,
    [switch]$Tray,
    [switch]$Settings
)

$ErrorActionPreference = 'Stop'
$AppName = 'Wi-Fi Clash Guard'
$ConfigDirectory = Join-Path $env:APPDATA 'WifiClashGuard'
$ConfigPath = Join-Path $ConfigDirectory 'config.json'
$RunKeyPath = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$RunValueName = 'WifiClashGuard'

function Get-DefaultConfig {
    return [ordered]@{
        dangerous_ssids = @()
        clash_path = ''
        block_by_default_when_ssid_unknown = $true
        start_with_windows = $false
    }
}

function Save-GuardConfig([hashtable]$Config) {
    if (-not (Test-Path -LiteralPath $ConfigDirectory)) {
        New-Item -ItemType Directory -Path $ConfigDirectory -Force | Out-Null
    }
    $Config | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
}

function Normalize-SSIDs([object]$Values) {
    $result = [System.Collections.Generic.List[string]]::new()
    if ($null -eq $Values) { return @() }
    foreach ($value in @($Values)) {
        $item = [string]$value
        if (-not [string]::IsNullOrWhiteSpace($item) -and
            -not ($result | Where-Object { $_.Equals($item.Trim(), [System.StringComparison]::OrdinalIgnoreCase) })) {
            $result.Add($item.Trim())
        }
    }
    return @($result)
}

function Read-GuardConfig {
    $config = Get-DefaultConfig
    if (-not (Test-Path -LiteralPath $ConfigPath)) {
        Save-GuardConfig $config
        return $config
    }
    try {
        $raw = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($null -ne $raw.dangerous_ssids) { $config.dangerous_ssids = Normalize-SSIDs $raw.dangerous_ssids }
        if ($null -ne $raw.clash_path) { $config.clash_path = [string]$raw.clash_path }
        if ($null -ne $raw.block_by_default_when_ssid_unknown) { $config.block_by_default_when_ssid_unknown = [bool]$raw.block_by_default_when_ssid_unknown }
        if ($null -ne $raw.start_with_windows) { $config.start_with_windows = [bool]$raw.start_with_windows }
    }
    catch {
        $invalidPath = "$ConfigPath.invalid.json"
        try { Move-Item -LiteralPath $ConfigPath -Destination $invalidPath -Force } catch { }
        Save-GuardConfig $config
    }
    return $config
}

function Get-CurrentSSID {
    try {
        $output = netsh wlan show interfaces 2>$null | Out-String
        foreach ($line in ($output -split "`r?`n")) {
            if ($line -match '^\s*SSID\s*:\s*(.+?)\s*$') {
                return $Matches[1].Trim()
            }
        }
    }
    catch { }
    return $null
}

function Test-DangerousSSID([string]$SSID, [object]$DangerousSSIDs) {
    if ([string]::IsNullOrWhiteSpace($SSID)) { return $false }
    foreach ($item in @($DangerousSSIDs)) {
        if ($SSID.Equals([string]$item, [System.StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    return $false
}

function Set-Startup([bool]$Enabled) {
    if ($Enabled) {
        $command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Tray"
        New-ItemProperty -Path $RunKeyPath -Name $RunValueName -Value $command -PropertyType String -Force | Out-Null
    }
    else {
        Remove-ItemProperty -Path $RunKeyPath -Name $RunValueName -ErrorAction SilentlyContinue
    }
}

function Start-Clash([hashtable]$Config) {
    $path = [Environment]::ExpandEnvironmentVariables([string]$Config.clash_path)
    if ([string]::IsNullOrWhiteSpace($path) -or -not (Test-Path -LiteralPath $path -PathType Leaf)) {
        [System.Windows.Forms.MessageBox]::Show(
            "找不到 Clash Verge 程序。`n`n请在托盘菜单的设置中选择正确的 exe 文件。",
            $AppName,
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
        return $false
    }
    try {
        Start-Process -FilePath $path -WorkingDirectory (Split-Path -Parent $path) | Out-Null
        return $true
    }
    catch {
        [System.Windows.Forms.MessageBox]::Show(
            "启动 Clash Verge 失败：`n$($_.Exception.Message)", $AppName,
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
        return $false
    }
}

function Confirm-AndStartClash([hashtable]$Config) {
    $ssid = Get-CurrentSSID
    $dangerous = Test-DangerousSSID $ssid $Config.dangerous_ssids
    $unknown = [string]::IsNullOrWhiteSpace($ssid)
    if ($dangerous -or ($unknown -and $Config.block_by_default_when_ssid_unknown)) {
        $shown = if ($unknown) { '无法读取（可能未连接 Wi-Fi 或使用网线）' } else { $ssid }
        $message = "当前 Wi-Fi：$shown`n`n该网络在危险 SSID 名单中，是否仍然启动 Clash Verge？`n`n选择【否】将取消启动。"
        $answer = [System.Windows.Forms.MessageBox]::Show(
            $message, '网络安全提醒',
            [System.Windows.Forms.MessageBoxButtons]::YesNo,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        )
        if ($answer -ne [System.Windows.Forms.DialogResult]::Yes) { return }
    }
    [void](Start-Clash $Config)
}

function New-SettingsForm([hashtable]$Config) {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = 'Wi-Fi Clash Guard 设置'
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MaximizeBox = $false
    $form.MinimizeBox = $false
    $form.ClientSize = New-Object System.Drawing.Size(540, 410)

    $label = New-Object System.Windows.Forms.Label
    $label.Text = '危险 SSID（匹配不区分大小写）'
    $label.Location = New-Object System.Drawing.Point(16, 15)
    $label.AutoSize = $true
    $form.Controls.Add($label)

    $list = New-Object System.Windows.Forms.ListBox
    $list.Location = New-Object System.Drawing.Point(16, 40)
    $list.Size = New-Object System.Drawing.Size(370, 145)
    foreach ($item in @($Config.dangerous_ssids)) { [void]$list.Items.Add($item) }
    $form.Controls.Add($list)

    $add = New-Object System.Windows.Forms.Button
    $add.Text = '添加'
    $add.Location = New-Object System.Drawing.Point(400, 40)
    $add.Size = New-Object System.Drawing.Size(120, 30)
    $add.Add_Click({
        $value = [Microsoft.VisualBasic.Interaction]::InputBox('请输入完整 SSID：', '添加危险 SSID', '')
        if (-not [string]::IsNullOrWhiteSpace($value) -and
            -not (@($list.Items) | Where-Object { $_.ToString().Equals($value.Trim(), [System.StringComparison]::OrdinalIgnoreCase) })) {
            [void]$list.Items.Add($value.Trim())
        }
    })
    $form.Controls.Add($add)

    $edit = New-Object System.Windows.Forms.Button
    $edit.Text = '修改'
    $edit.Location = New-Object System.Drawing.Point(400, 78)
    $edit.Size = New-Object System.Drawing.Size(120, 30)
    $edit.Add_Click({
        if ($list.SelectedIndex -lt 0) {
            [System.Windows.Forms.MessageBox]::Show('请先选择一个 SSID。', $AppName) | Out-Null
            return
        }
        $index = $list.SelectedIndex
        $value = [Microsoft.VisualBasic.Interaction]::InputBox('请输入完整 SSID：', '修改危险 SSID', $list.SelectedItem.ToString())
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            $list.Items[$index] = $value.Trim()
        }
    })
    $form.Controls.Add($edit)

    $remove = New-Object System.Windows.Forms.Button
    $remove.Text = '删除'
    $remove.Location = New-Object System.Drawing.Point(400, 116)
    $remove.Size = New-Object System.Drawing.Size(120, 30)
    $remove.Add_Click({
        if ($list.SelectedIndex -ge 0) { $list.Items.RemoveAt($list.SelectedIndex) }
    })
    $form.Controls.Add($remove)

    $pathLabel = New-Object System.Windows.Forms.Label
    $pathLabel.Text = 'Clash Verge 可执行文件'
    $pathLabel.Location = New-Object System.Drawing.Point(16, 205)
    $pathLabel.AutoSize = $true
    $form.Controls.Add($pathLabel)

    $path = New-Object System.Windows.Forms.TextBox
    $path.Location = New-Object System.Drawing.Point(16, 230)
    $path.Size = New-Object System.Drawing.Size(370, 24)
    $path.Text = [string]$Config.clash_path
    $form.Controls.Add($path)

    $browse = New-Object System.Windows.Forms.Button
    $browse.Text = '选择…'
    $browse.Location = New-Object System.Drawing.Point(400, 228)
    $browse.Size = New-Object System.Drawing.Size(120, 28)
    $browse.Add_Click({
        $dialog = New-Object System.Windows.Forms.OpenFileDialog
        $dialog.Filter = '程序文件 (*.exe)|*.exe|所有文件 (*.*)|*.*'
        $dialog.Title = '选择 Clash Verge exe'
        if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { $path.Text = $dialog.FileName }
    })
    $form.Controls.Add($browse)

    $startup = New-Object System.Windows.Forms.CheckBox
    $startup.Text = 'Windows 开机自动运行托盘程序'
    $startup.Location = New-Object System.Drawing.Point(16, 275)
    $startup.AutoSize = $true
    $startup.Checked = [bool]$Config.start_with_windows
    $form.Controls.Add($startup)

    $save = New-Object System.Windows.Forms.Button
    $save.Text = '保存'
    $save.Location = New-Object System.Drawing.Point(330, 345)
    $save.Size = New-Object System.Drawing.Size(90, 30)
    $save.Add_Click({
        $Config.dangerous_ssids = Normalize-SSIDs @($list.Items)
        $Config.clash_path = $path.Text.Trim()
        $Config.start_with_windows = $startup.Checked
        Save-GuardConfig $Config
        Set-Startup $startup.Checked
        $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.Close()
    })
    $form.Controls.Add($save)

    $cancel = New-Object System.Windows.Forms.Button
    $cancel.Text = '取消'
    $cancel.Location = New-Object System.Drawing.Point(430, 345)
    $cancel.Size = New-Object System.Drawing.Size(90, 30)
    $cancel.Add_Click({ $form.Close() })
    $form.Controls.Add($cancel)
    return $form
}

function Show-SettingsOnly {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    Add-Type -AssemblyName Microsoft.VisualBasic

    $config = Read-GuardConfig
    $form = New-SettingsForm $config
    [void]$form.ShowDialog()
    $form.Dispose()
}

function Start-TrayApp {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing

    $config = Read-GuardConfig
    $context = New-Object System.Windows.Forms.ApplicationContext
    $notify = New-Object System.Windows.Forms.NotifyIcon
    $notify.Text = $AppName
    $notify.Icon = [System.Drawing.SystemIcons]::Shield
    $notify.Visible = $true

    $menu = New-Object System.Windows.Forms.ContextMenuStrip
    $launchItem = $menu.Items.Add('启动 Clash Verge')
    $settingsItem = $menu.Items.Add('设置（SSID 与 Clash 路径）')
    $checkItem = $menu.Items.Add('检测当前 SSID')
    [void]$menu.Items.Add('-')
    $exitItem = $menu.Items.Add('退出')
    $notify.ContextMenuStrip = $menu

    $launchItem.Add_Click({ Confirm-AndStartClash $config })
    $settingsItem.Add_Click({
        $form = New-SettingsForm $config
        [void]$form.ShowDialog()
        $form.Dispose()
    })
    $checkItem.Add_Click({
        $ssid = Get-CurrentSSID
        $shown = if ([string]::IsNullOrWhiteSpace($ssid)) { '无法读取当前 SSID' } else { $ssid }
        [System.Windows.Forms.MessageBox]::Show("当前 SSID：$shown", $AppName) | Out-Null
    })
    $exitItem.Add_Click({
        $notify.Visible = $false
        $notify.Dispose()
        $context.ExitThread()
    })
    $notify.Add_DoubleClick({ Confirm-AndStartClash $config })
    [System.Windows.Forms.Application]::Run($context)
}

if ($Check) {
    $ssid = Get-CurrentSSID
    if ([string]::IsNullOrWhiteSpace($ssid)) { Write-Output 'SSID: <unavailable>' } else { Write-Output "SSID: $ssid" }
    exit 0
}

if ($Launch) {
    Add-Type -AssemblyName System.Windows.Forms
    $config = Read-GuardConfig
    Confirm-AndStartClash $config
    exit 0
}

if ($Settings) {
    Show-SettingsOnly
    exit 0
}

Start-TrayApp
