# Wi-Fi Clash Guard

Windows 托盘工具：在启动 Clash Verge 前检查当前 Wi-Fi SSID，并对手动设置的危险 SSID 进行提醒。

## 推荐：无需 Python 的 PowerShell 版本

Windows PowerShell 5.1 通常已随系统安装，可直接运行：

```powershell
cd C:\路径\wifi-clash-guard
powershell.exe -ExecutionPolicy Bypass -File .\WifiClashGuard.ps1
```

启动后，从右下角托盘图标进入“管理危险 SSID”，手动添加需要提醒的 Wi-Fi 名称，并选择 Clash Verge 的 exe 文件。

检查当前 SSID：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\WifiClashGuard.ps1 -Check
```

## 使用方法

1. 安装 Python 3.10+。
2. 在本目录执行：

   ```powershell
   pip install -r requirements.txt
   ```

3. 启动托盘程序：

   ```powershell
   python wifi_clash_guard.py
   ```

   如果 Windows 的 `python` 命令不可用，也可以直接双击 `start_guard.bat`；本机 Python 安装器路径下的 `pythonw.exe` 会被自动优先使用。

如果托盘菜单暂时没有弹出设置窗口，可以直接运行：

```powershell
python -X utf8 wifi_clash_guard.py --settings
```

该入口会直接打开设置窗口，其中包含危险 SSID 列表和 Clash Verge exe 路径选择框。

PowerShell 版本也支持直接打开设置：

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\WifiClashGuard.ps1 -Settings
```

或者双击 `open_settings.ps1`。

4. 从托盘图标进入“管理危险 SSID”，手动添加需要提醒的 Wi-Fi 名称，并选择 Clash Verge 的 exe 文件。
5. 保存后，可以使用“启动 Clash Verge”菜单启动；危险 SSID 下会先弹窗确认。

## 把它接到桌面快捷方式

将原 Clash Verge 快捷方式的目标改成下面的命令，并把“起始位置”设为本目录：

```text
pythonw.exe C:\路径\wifi-clash-guard\wifi_clash_guard.py --launch
```

首次运行托盘程序并保存设置后，`--launch` 会检查当前 SSID，再启动配置的 Clash Verge。

## 配置文件

配置保存在：

```text
%APPDATA%\WifiClashGuard\config.json
```

配置界面是推荐的修改方式；配置文件也可以手动备份或编辑。

## 打包 EXE

```powershell
pyinstaller --noconfirm --onefile --windowed --name WifiClashGuard wifi_clash_guard.py
```

打包后，可将 `dist\WifiClashGuard.exe --launch` 设置为 Clash Verge 的快捷方式目标。托盘程序则直接运行 `dist\WifiClashGuard.exe`。
