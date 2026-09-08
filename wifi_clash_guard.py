"""Wi-Fi SSID safety guard for launching Clash Verge on Windows."""

from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
import queue
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Iterable

# Keep command-line text readable in Chinese Windows terminals. Tkinter GUI
# strings do not depend on this, but --help and diagnostics do.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover - handled with a user-facing message
    pystray = None
    Image = None
    ImageDraw = None


APP_NAME = "Wi-Fi Clash Guard"
CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "WifiClashGuard"
CONFIG_PATH = CONFIG_DIR / "config.json"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "WifiClashGuard"

DEFAULT_CONFIG: dict[str, Any] = {
    "dangerous_ssids": [],
    "clash_path": "",
    "block_by_default_when_ssid_unknown": True,
    "start_with_windows": False,
}


def load_config() -> dict[str, Any]:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        backup = CONFIG_PATH.with_suffix(".invalid.json")
        try:
            CONFIG_PATH.replace(backup)
        except OSError:
            pass
        save_config(DEFAULT_CONFIG.copy())
        return DEFAULT_CONFIG.copy()
    config = DEFAULT_CONFIG.copy()
    config.update(raw if isinstance(raw, dict) else {})
    config["dangerous_ssids"] = normalized_ssids(config.get("dangerous_ssids", []))
    config["clash_path"] = str(config.get("clash_path", ""))
    return config


def save_config(config: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def normalized_ssids(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item.casefold() not in {x.casefold() for x in result}:
            result.append(item)
    return result


def decode_ssid_bytes(raw: bytes) -> str:
    """Decode the raw SSID bytes returned by the Windows WLAN API."""
    if not raw:
        return ""

    candidates: list[str] = []
    for encoding in ("utf-8-sig", "gb18030", "big5", "mbcs", "oem", "latin-1"):
        try:
            decoded = raw.decode(encoding, errors="strict")
        except (LookupError, UnicodeDecodeError):
            continue
        if decoded and decoded not in candidates:
            candidates.append(decoded)

    # Prefer the first strict candidate. UTF-8 is checked first, while a
    # legacy Chinese SSID falls through to GB18030 before the machine's ANSI
    # code page. This keeps the result independent of the runner's locale.
    return candidates[0].strip() if candidates else raw.decode("latin-1", errors="replace").strip()


def _get_current_ssid_wlanapi() -> str | None:
    """Read the connected SSID through wlanapi.dll, avoiding console encoding."""
    if os.name != "nt":
        return None

    class Guid(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_ulong),
            ("Data2", ctypes.c_ushort),
            ("Data3", ctypes.c_ushort),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class Dot11Ssid(ctypes.Structure):
        _fields_ = [("uSSIDLength", ctypes.wintypes.DWORD), ("ucSSID", ctypes.c_ubyte * 32)]

    class WlanAssociationAttributes(ctypes.Structure):
        _fields_ = [
            ("Dot11Ssid", Dot11Ssid),
            ("Dot11BssType", ctypes.c_uint),
            ("Dot11Bssid", ctypes.c_ubyte * 6),
            ("dot11PhyType", ctypes.c_uint),
            ("uDot11PhyIndex", ctypes.wintypes.DWORD),
            ("wlanSignalQuality", ctypes.wintypes.DWORD),
            ("ulRxRate", ctypes.wintypes.DWORD),
            ("ulTxRate", ctypes.wintypes.DWORD),
        ]

    class WlanSecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("bSecurityEnabled", ctypes.wintypes.BOOL),
            ("dot11AuthAlgorithm", ctypes.c_uint),
            ("dot11CipherAlgorithm", ctypes.c_uint),
        ]

    class WlanConnectionAttributes(ctypes.Structure):
        _fields_ = [
            ("isState", ctypes.c_uint),
            ("wlanConnectionMode", ctypes.c_uint),
            ("strProfileName", ctypes.c_wchar * 256),
            ("wlanAssociationAttributes", WlanAssociationAttributes),
            ("wlanSecurityAttributes", WlanSecurityAttributes),
        ]

    class WlanInterfaceInfo(ctypes.Structure):
        _fields_ = [
            ("InterfaceGuid", Guid),
            ("strInterfaceDescription", ctypes.c_wchar * 256),
            ("isState", ctypes.c_uint),
        ]

    class WlanInterfaceInfoList(ctypes.Structure):
        _fields_ = [
            ("dwNumberOfItems", ctypes.wintypes.DWORD),
            ("dwIndex", ctypes.wintypes.DWORD),
            ("InterfaceInfo", WlanInterfaceInfo * 1),
        ]

    try:
        wlanapi = ctypes.WinDLL("wlanapi.dll")
        client_handle = ctypes.wintypes.HANDLE()
        negotiated_version = ctypes.wintypes.DWORD()
        result = wlanapi.WlanOpenHandle(
            2, None, ctypes.byref(negotiated_version), ctypes.byref(client_handle)
        )
        if result != 0:
            return None

        interface_list = ctypes.c_void_p()
        connection_data = ctypes.c_void_p()
        try:
            result = wlanapi.WlanEnumInterfaces(
                client_handle, None, ctypes.byref(interface_list)
            )
            if result != 0 or not interface_list.value:
                return None

            info_list = ctypes.cast(
                interface_list, ctypes.POINTER(WlanInterfaceInfoList)
            ).contents
            interface_array = (WlanInterfaceInfo * info_list.dwNumberOfItems).from_address(
                ctypes.addressof(info_list.InterfaceInfo)
            )
            for interface in interface_array:
                # wlan_interface_state_connected == 1
                if interface.isState != 1:
                    continue
                data_size = ctypes.wintypes.DWORD()
                opcode_type = ctypes.c_uint()
                result = wlanapi.WlanQueryInterface(
                    client_handle,
                    ctypes.byref(interface.InterfaceGuid),
                    7,  # wlan_intf_opcode_current_connection
                    None,
                    ctypes.byref(data_size),
                    ctypes.byref(connection_data),
                    ctypes.byref(opcode_type),
                )
                if result != 0 or not connection_data.value:
                    continue
                attributes = ctypes.cast(
                    connection_data, ctypes.POINTER(WlanConnectionAttributes)
                ).contents
                ssid = attributes.wlanAssociationAttributes.Dot11Ssid
                length = min(int(ssid.uSSIDLength), len(ssid.ucSSID))
                decoded = decode_ssid_bytes(bytes(ssid.ucSSID[:length]))
                if decoded:
                    return decoded
                wlanapi.WlanFreeMemory(connection_data)
                connection_data = ctypes.c_void_p()
            return None
        finally:
            if connection_data.value:
                wlanapi.WlanFreeMemory(connection_data)
            if interface_list.value:
                wlanapi.WlanFreeMemory(interface_list)
            wlanapi.WlanCloseHandle(client_handle, None)
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def get_current_ssid() -> str | None:
    """Return the first connected Wi-Fi SSID, or None if it cannot be read."""
    api_ssid = _get_current_ssid_wlanapi()
    if api_ssid:
        return api_ssid

    try:
        completed = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            timeout=5,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None

    output = decode_netsh_output(completed.stdout)

    # SSID is deliberately matched as a complete key, so BSSID is ignored.
    for line in output.splitlines():
        match = re.match(r"^\s*SSID\s*:\s*(.*)\s*$", line, re.IGNORECASE)
        if match and match.group(1).strip():
            return match.group(1).strip()
    return None


def decode_netsh_output(raw: bytes) -> str:
    """Decode netsh output without assuming the console code page."""
    if not isinstance(raw, bytes):
        return str(raw)

    encodings = ["utf-8-sig"]
    if os.name == "nt":
        encodings.extend(["mbcs", "oem"])
    encodings.extend(["gb18030", "latin-1"])

    candidates: list[str] = []
    for encoding in encodings:
        try:
            decoded = raw.decode(encoding, errors="replace")
        except (LookupError, UnicodeError):
            continue
        if decoded not in candidates:
            candidates.append(decoded)

    def score(value: str) -> tuple[int, int, int, int, int]:
        replacements = value.count("\ufffd")
        private_use = sum(0xE000 <= ord(char) <= 0xF8FF for char in value)
        cjk = sum(
            (0x3400 <= ord(char) <= 0x4DBF)
            or (0x4E00 <= ord(char) <= 0x9FFF)
            for char in value
        )
        controls = sum(ord(char) < 32 and char not in "\r\n\t" for char in value)
        printable = sum(char.isprintable() or char in "\r\n\t" for char in value)
        return (-replacements, -private_use, cjk, -controls, printable)

    return max(candidates, key=score, default="")


def is_dangerous(ssid: str | None, dangerous_ssids: list[str]) -> bool:
    if ssid is None:
        return False
    folded = ssid.casefold()
    return any(folded == item.casefold() for item in dangerous_ssids)


def normalize_executable_path(path: str | os.PathLike[str]) -> str:
    """Return a comparable absolute path for a configured executable."""
    raw_path = str(os.fspath(path)).strip().strip('"')
    if not raw_path:
        return ""
    if os.name == "nt":
        extended_unc_prefix = "\\\\?\\UNC"
        extended_prefix = "\\\\?\\"
        device_prefix = "\\\\.\\"
        if raw_path.casefold().startswith(extended_unc_prefix.casefold() + "\\"):
            raw_path = "\\\\" + raw_path[len(extended_unc_prefix) + 1 :]
        elif raw_path.startswith(extended_prefix) or raw_path.startswith(device_prefix):
            raw_path = raw_path[4:]
    candidate = Path(raw_path).expanduser()
    try:
        candidate = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        candidate = candidate.absolute()
    return os.path.normcase(os.path.normpath(str(candidate)))


def _running_process_paths() -> list[str]:
    """Return full executable paths for running Windows processes."""
    if os.name != "nt":
        return []

    class ProcessEntry32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    process_query_limited_information = 0x1000
    snapshot_flags = 0x00000002  # TH32CS_SNAPPROCESS
    invalid_handle_value = ctypes.c_void_p(-1).value
    kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32W),
    ]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry32W),
    ]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    try:
        snapshot = kernel32.CreateToolhelp32Snapshot(snapshot_flags, 0)
    except (AttributeError, OSError):
        return []
    if snapshot in (None, invalid_handle_value):
        return []

    paths: list[str] = []
    try:
        entry = ProcessEntry32W()
        entry.dwSize = ctypes.sizeof(ProcessEntry32W)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return paths
        while True:
            process = kernel32.OpenProcess(
                process_query_limited_information, False, entry.th32ProcessID
            )
            if process:
                try:
                    buffer = ctypes.create_unicode_buffer(32768)
                    size = wintypes.DWORD(len(buffer))
                    if kernel32.QueryFullProcessImageNameW(
                        process, 0, buffer, ctypes.byref(size)
                    ):
                        paths.append(buffer.value[: size.value])
                finally:
                    kernel32.CloseHandle(process)
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return paths


def is_configured_clash_running(
    clash_path: str, process_paths: Iterable[str] | None = None
) -> bool:
    """Check whether the configured executable path belongs to a running process."""
    normalized_configured = normalize_executable_path(clash_path)
    if not normalized_configured:
        return False
    try:
        paths = _running_process_paths() if process_paths is None else process_paths
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    return any(
        normalized_configured == normalize_executable_path(process_path)
        for process_path in paths
    )


def should_show_startup_warning(
    ssid: str | None,
    dangerous_ssids: list[str],
    clash_path: str,
    process_paths: Iterable[str] | None = None,
) -> bool:
    """Return whether the tray startup informational warning should be shown."""
    return is_dangerous(ssid, dangerous_ssids) and is_configured_clash_running(
        clash_path, process_paths
    )


def start_clash(clash_path: str) -> tuple[bool, str]:
    path = Path(clash_path).expanduser()
    if not path.is_file():
        return False, f"找不到 Clash Verge 程序：\n{path}\n\n请先在设置中选择正确的 exe 文件。"
    try:
        subprocess.Popen([str(path)], cwd=str(path.parent), close_fds=True)
    except OSError as exc:
        return False, f"启动 Clash Verge 失败：{exc}"
    return True, ""


def startup_command() -> str:
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    script = Path(__file__).resolve()
    if pythonw.exists() and script.suffix == ".py":
        return f'"{pythonw}" "{script}" --tray'
    return f'"{Path(sys.executable).resolve()}" --tray'


def set_startup(enabled: bool) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "开机自启只支持 Windows。"
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, startup_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
    except OSError as exc:
        return False, f"设置开机自启失败：{exc}"
    return True, ""


def tray_image():
    image = Image.new("RGBA", (64, 64), (32, 105, 180, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 56, 56), radius=10, fill=(245, 248, 252, 255))
    draw.arc((16, 16, 48, 48), 210, 330, fill=(32, 105, 180, 255), width=4)
    draw.arc((22, 22, 42, 42), 210, 330, fill=(32, 105, 180, 255), width=4)
    draw.ellipse((29, 36, 35, 42), fill=(32, 105, 180, 255))
    return image


def show_native_error(message: str) -> None:
    """Show an error even when Tk cannot initialize its Tcl/Tk runtime."""
    if os.name == "nt":
        try:
            ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x10)
            return
        except (AttributeError, OSError):
            pass
    print(message, file=sys.stderr)


def launch_settings_process() -> tuple[bool, str]:
    """Start a visible settings-only process from a tray callback."""
    if getattr(sys, "frozen", False):
        command = [str(Path(sys.executable).resolve()), "--settings"]
    else:
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        executable = pythonw if pythonw.exists() else Path(sys.executable)
        command = [str(executable), str(Path(__file__).resolve()), "--settings"]

    try:
        subprocess.Popen(
            command,
            cwd=str(Path(__file__).resolve().parent),
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        return False, f"无法打开设置窗口：{exc}"
    return True, ""


def show_settings_window() -> int:
    """Run the settings UI as a normal visible Tk application."""
    config = load_config()
    root = tk.Tk()
    root.title("Wi-Fi Clash Guard 设置")
    root.resizable(False, False)

    frame = ttk.Frame(root, padding=14)
    frame.grid(sticky="nsew")
    ttk.Label(frame, text="危险 SSID（匹配不区分大小写）").grid(
        row=0, column=0, columnspan=2, sticky="w"
    )
    ssid_list = tk.Listbox(frame, height=8, width=42, exportselection=False)
    ssid_list.grid(row=1, column=0, rowspan=4, padx=(0, 8), pady=(6, 10))
    for item in config["dangerous_ssids"]:
        ssid_list.insert(tk.END, item)

    def add_ssid() -> None:
        value = simpledialog.askstring("添加危险 SSID", "请输入完整 SSID：", parent=root)
        if value and value.strip():
            value = value.strip()
            current = [ssid_list.get(i) for i in range(ssid_list.size())]
            if value.casefold() not in {x.casefold() for x in current}:
                ssid_list.insert(tk.END, value)

    def edit_ssid() -> None:
        selection = ssid_list.curselection()
        if not selection:
            messagebox.showinfo(APP_NAME, "请先选择一个 SSID。", parent=root)
            return
        index = selection[0]
        value = simpledialog.askstring(
            "修改危险 SSID",
            "请输入完整 SSID：",
            initialvalue=ssid_list.get(index),
            parent=root,
        )
        if value and value.strip():
            ssid_list.delete(index)
            ssid_list.insert(index, value.strip())

    def delete_ssid() -> None:
        for index in reversed(ssid_list.curselection()):
            ssid_list.delete(index)

    ttk.Button(frame, text="添加", command=add_ssid).grid(row=1, column=1, sticky="ew")
    ttk.Button(frame, text="修改", command=edit_ssid).grid(
        row=2, column=1, sticky="ew", pady=4
    )
    ttk.Button(frame, text="删除", command=delete_ssid).grid(row=3, column=1, sticky="ew")

    ttk.Label(frame, text="Clash Verge 可执行文件").grid(
        row=5, column=0, columnspan=2, sticky="w", pady=(4, 0)
    )
    clash_path = tk.StringVar(value=config.get("clash_path", ""))
    path_entry = ttk.Entry(frame, textvariable=clash_path, width=43)
    path_entry.grid(row=6, column=0, padx=(0, 8), pady=(6, 10))

    def choose_clash() -> None:
        selected = filedialog.askopenfilename(
            parent=root,
            title="选择 Clash Verge exe",
            filetypes=[("程序文件", "*.exe"), ("所有文件", "*.*")],
        )
        if selected:
            clash_path.set(selected)
            path_entry.icursor(tk.END)

    ttk.Button(frame, text="选择…", command=choose_clash).grid(
        row=6, column=1, sticky="ew"
    )

    startup_var = tk.BooleanVar(value=bool(config.get("start_with_windows", False)))
    ttk.Checkbutton(
        frame,
        text="Windows 开机自动运行托盘程序",
        variable=startup_var,
    ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(0, 8))

    def close_window() -> None:
        root.destroy()

    def save_and_close() -> None:
        values = [ssid_list.get(i).strip() for i in range(ssid_list.size())]
        config["dangerous_ssids"] = normalized_ssids(values)
        config["clash_path"] = clash_path.get().strip()
        config["start_with_windows"] = startup_var.get()
        save_config(config)
        ok, error = set_startup(startup_var.get())
        if not ok:
            messagebox.showerror(APP_NAME, error, parent=root)
            return
        close_window()

    buttons = ttk.Frame(frame)
    buttons.grid(row=8, column=0, columnspan=2, sticky="e")
    ttk.Button(buttons, text="取消", command=close_window).pack(side=tk.RIGHT, padx=(8, 0))
    ttk.Button(buttons, text="保存", command=save_and_close).pack(side=tk.RIGHT)

    root.protocol("WM_DELETE_WINDOW", close_window)
    root.update_idletasks()
    width = root.winfo_width()
    height = root.winfo_height()
    x = max((root.winfo_screenwidth() - width) // 2, 0)
    y = max((root.winfo_screenheight() - height) // 2, 0)
    root.geometry(f"{width}x{height}+{x}+{y}")
    root.lift()
    root.focus_force()
    path_entry.focus_set()
    root.mainloop()
    return 0


class GuardApp:
    def __init__(self) -> None:
        self.config = load_config()
        self.root = tk.Tk()
        self.root.withdraw()
        self.icon = None
        self._ui_actions: queue.Queue = queue.Queue()
        self._startup_warning_shown = False

    def run(self) -> None:
        if pystray is None:
            messagebox.showerror(
                APP_NAME,
                "缺少运行依赖。请在项目目录执行：\npip install -r requirements.txt",
            )
            return
        self.icon = pystray.Icon(
            APP_NAME,
            tray_image(),
            APP_NAME,
            menu=pystray.Menu(
                pystray.MenuItem("启动 Clash Verge", self._tray_launch),
                pystray.MenuItem("设置（SSID 与 Clash 路径）", self._tray_settings),
                pystray.MenuItem("检测当前 SSID", self._tray_check),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", self._quit),
            ),
        )
        self.icon.run_detached()
        self.root.after(0, self._show_startup_warning)
        self.root.after(50, self._drain_ui_actions)
        self.root.mainloop()

    def _show_startup_warning(self) -> None:
        if self._startup_warning_shown:
            return
        self._startup_warning_shown = True
        clash_path = self.config.get("clash_path", "")
        if not is_configured_clash_running(clash_path):
            return
        ssid = get_current_ssid()
        if not is_dangerous(ssid, self.config["dangerous_ssids"]):
            return
        shown = ssid if ssid is not None else "无法读取"
        messagebox.showwarning(
            "网络安全提醒",
            f"当前 Wi‑Fi：{shown}\n\n"
            "检测到配置的 Clash Verge 已经在运行，且当前 SSID 位于危险名单中。",
            parent=self.root,
        )

    def _drain_ui_actions(self) -> None:
        """Run tray callbacks on Tk's main thread.

        pystray invokes menu handlers from its own Windows message thread.
        Calling Tkinter directly from that thread can make a menu item appear
        to do nothing (or raise ``RuntimeError: main thread is not in main
        loop``), especially for modal windows such as the SSID settings form.
        """
        while True:
            try:
                action = self._ui_actions.get_nowait()
            except queue.Empty:
                break
            try:
                action()
            finally:
                self._ui_actions.task_done()
        if self.root.winfo_exists():
            self.root.after(50, self._drain_ui_actions)

    def _call_on_ui(self, callback) -> None:
        self._ui_actions.put(callback)

    def _tray_launch(self, *_args) -> None:
        self._call_on_ui(self.launch_clash)

    def _tray_settings(self, *_args) -> None:
        ok, error = launch_settings_process()
        if not ok:
            show_native_error(error)

    def _tray_check(self, *_args) -> None:
        self._call_on_ui(self.show_current_ssid)

    def _quit(self, *_args) -> None:
        self._call_on_ui(self._shutdown)

    def _shutdown(self) -> None:
        if self.icon is not None:
            self.icon.stop()
        self.root.destroy()

    def launch_clash(self) -> None:
        ssid = get_current_ssid()
        dangerous = is_dangerous(ssid, self.config["dangerous_ssids"])
        unknown = ssid is None
        if dangerous or (unknown and self.config["block_by_default_when_ssid_unknown"]):
            shown = ssid if ssid is not None else "无法读取（可能未连接 Wi‑Fi 或使用网线）"
            answer = messagebox.askyesno(
                "网络安全提醒",
                f"当前 Wi‑Fi：{shown}\n\n"
                "这个网络在危险 SSID 名单中，请确认是否仍要启动 Clash Verge？\n\n"
                "选择“否”将取消启动。",
                icon="warning",
            )
            if not answer:
                return
        ok, error = start_clash(self.config.get("clash_path", ""))
        if not ok:
            messagebox.showerror(APP_NAME, error)

    def show_current_ssid(self) -> None:
        ssid = get_current_ssid()
        text = ssid or "无法读取（未连接 Wi‑Fi、使用网线或系统命令不可用）"
        messagebox.showinfo(APP_NAME, f"当前 SSID：{text}")

def launch_once() -> int:
    config = load_config()
    ssid = get_current_ssid()
    if is_dangerous(ssid, config["dangerous_ssids"]) or (
        ssid is None and config["block_by_default_when_ssid_unknown"]
    ):
        root = tk.Tk()
        root.withdraw()
        shown = ssid if ssid is not None else "无法读取"
        answer = messagebox.askyesno(
            "网络安全提醒",
            f"当前 Wi‑Fi：{shown}\n\n"
            "该网络在危险名单中，是否仍然启动 Clash Verge？",
            icon="warning",
        )
        root.destroy()
        if not answer:
            return 1
    ok, error = start_clash(config.get("clash_path", ""))
    if not ok:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(APP_NAME, error)
        root.destroy()
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--launch", action="store_true", help="检查网络后启动 Clash Verge")
    parser.add_argument("--tray", action="store_true", help="启动托盘程序")
    parser.add_argument("--settings", action="store_true", help="仅打开设置窗口")
    args = parser.parse_args()
    try:
        if args.launch:
            return launch_once()
        if args.settings:
            return show_settings_window()
        GuardApp().run()
        return 0
    except tk.TclError as exc:
        show_native_error(
            "图形界面组件 Tcl/Tk 初始化失败，无法打开设置窗口。\n\n"
            "请改用同目录的 WifiClashGuard.ps1 -Settings，或重新安装带 Tcl/Tk 的 Python。\n\n"
            f"详细信息：{exc}"
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
