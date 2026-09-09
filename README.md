# Wi-Fi Clash Guard

[![Build and publish Windows release](https://github.com/asdsaddafsa/wifi-clash-guard/actions/workflows/release.yml/badge.svg)](https://github.com/asdsaddafsa/wifi-clash-guard/actions/workflows/release.yml)
[![Latest release](https://img.shields.io/github/v/release/asdsaddafsa/wifi-clash-guard?sort=semver)](https://github.com/asdsaddafsa/wifi-clash-guard/releases)

Windows 托盘工具：在启动 Clash Verge 前检查当前 Wi-Fi SSID，并对手动设置的危险网络进行提醒。

Wi-Fi Clash Guard is a small Windows tray utility for Clash Verge users. It keeps a manually maintained list of risky Wi-Fi names, checks the current SSID before launching Clash Verge, and warns when Clash Verge is already running on a listed network.

## 功能

- 手动添加、修改和删除危险 SSID，匹配不区分大小写。
- 使用 Windows WLAN API 读取当前 SSID，并对 UTF-8、GB18030 等常见中文编码做兼容处理。
- 通过 `--launch` 启动 Clash Verge：危险 SSID 或无法读取 SSID 时先弹窗确认。
- 托盘程序启动时，如果检测到已配置的 Clash Verge 正在危险网络上运行，立即显示一次提醒。
- 独立设置窗口，配置危险 SSID、Clash Verge 可执行文件路径和 Windows 开机启动。
- 配置保存在用户 AppData，不写入项目目录，也不会上传 SSID 或配置内容。
- 提供无需 Python 的 PowerShell 回退版本。

## 下载运行版

推荐直接下载最新 Windows x64 版本：

**[下载 Wi-Fi Clash Guard v0.1.5](https://github.com/asdsaddafsa/wifi-clash-guard/releases/tag/v0.1.5)**

下载 `WifiClashGuard-v0.1.5-windows-x64.exe` 后：

1. 双击运行，托盘区会出现 Wi-Fi Clash Guard 图标。
2. 右键托盘图标，打开“设置（SSID 与 Clash 路径）”。
3. 添加需要提醒的 SSID，并选择 Clash Verge 的 `.exe` 文件。
4. 使用“启动 Clash Verge”菜单，或把 `--launch` 接入原有快捷方式。

运行版不需要安装 Python。程序只支持 Windows；当前发布资产面向 Windows x64。

## 提醒逻辑

| 场景 | 行为 |
| --- | --- |
| 通过“启动 Clash Verge”菜单或 `--launch` 启动 | 先读取 SSID；危险网络或 SSID 无法读取时要求确认 |
| 托盘启动时 Clash Verge 已经在运行，且当前 SSID 在危险名单中 | 显示一次启动提醒 |
| 右键“检测当前 SSID” | 显示当前 SSID；未连接 Wi-Fi 时显示明确提示 |
| 仅打开设置窗口 | 不创建第二个托盘图标，也不会触发启动提醒 |

启动提醒不会自动断开 Wi-Fi、修改代理或杀掉 Clash Verge；是否继续由用户确认。

## 配置

配置文件位置：

```text
%APPDATA%\WifiClashGuard\config.json
```

推荐通过设置窗口修改配置。配置文件不应提交到 Git；项目的 `.gitignore` 已排除 `.env`、本地 JSON 配置、缓存、日志和构建输出。

## 从源码运行

需要 Python 3.10+，并且 Python 安装中包含可用的 Tcl/Tk：

```powershell
cd C:\路径\wifi-clash-guard
python -m pip install -r requirements.txt
python wifi_clash_guard.py
```

常用命令：

```powershell
# 仅打开设置窗口
python -X utf8 wifi_clash_guard.py --settings

# 检查网络后启动已配置的 Clash Verge
python -X utf8 wifi_clash_guard.py --launch
```

如果 `python` 命令不可用，可以双击 `start_guard.bat`；它会优先尝试本机 Python 安装器目录中的 `pythonw.exe`。

## 不安装 Python：PowerShell 版本

Windows PowerShell 5.1 通常已随系统安装：

```powershell
cd C:\路径\wifi-clash-guard
powershell.exe -ExecutionPolicy Bypass -File .\WifiClashGuard.ps1
```

PowerShell 版本提供相同的托盘、设置、SSID 检测和 Clash 启动入口：

```powershell
# 检查当前 SSID
powershell.exe -ExecutionPolicy Bypass -File .\WifiClashGuard.ps1 -Check

# 直接打开设置窗口
powershell.exe -ExecutionPolicy Bypass -File .\WifiClashGuard.ps1 -Settings

# 检查网络后启动 Clash Verge
powershell.exe -ExecutionPolicy Bypass -File .\WifiClashGuard.ps1 -Launch
```

也可以双击 `open_settings.ps1` 打开设置。

## 接入 Clash Verge 快捷方式

将原 Clash Verge 快捷方式的“目标”改为下面的命令，并把“起始位置”设为项目或 EXE 所在目录：

```text
"C:\路径\WifiClashGuard-v0.1.5-windows-x64.exe" --launch
```

先在设置窗口中保存 Clash Verge 的实际 `.exe` 路径。之后通过这个快捷方式启动时，Wi-Fi Clash Guard 会完成检查并在用户确认后启动 Clash Verge。

## 本地构建

```powershell
cd C:\路径\wifi-clash-guard
python -m pip install -r requirements.txt
.\build_exe.ps1 -Version v0.1.5
```

构建脚本会预先检查 Tcl/Tk。输出文件位于 `dist\`，其中带版本号的文件名为：

```text
dist\WifiClashGuard-v0.1.5-windows-x64.exe
```

如果本机 Python 的 Tcl/Tk 损坏，建议使用 GitHub Actions：推送 `v*` tag 后，工作流会在 Python 3.12 的 Windows x64 runner 上测试并构建 Release EXE。

## 已知限制

- 目前只支持 Windows；SSID 读取依赖 Windows WLAN API，并保留 `netsh` 回退路径。
- SSID 必须完全匹配危险名单（忽略大小写），不会自动判断开放网络、加密方式或钓鱼热点。
- 程序只检查配置的 Clash Verge 可执行文件路径，不会识别所有可能的 Clash 内核进程。
- 本地 Python GUI 需要完整的 Tcl/Tk；缺失时可使用 PowerShell 版本或 GitHub Release EXE。

## 参与贡献

欢迎提交 Issue 和 Pull Request，尤其是：

- 不同 Windows 版本或无线网卡上的 SSID 读取问题；
- 更多编码环境下的显示兼容性问题；
- 不改变默认安全行为的测试和文档改进。

提交问题时请勿上传 `%APPDATA%\WifiClashGuard\config.json`、日志、个人 SSID 列表或其他本地敏感文件。

## 许可证

本项目采用 [MIT License](LICENSE)。你可以自由使用、修改和分发代码，但请保留许可证与版权声明。
