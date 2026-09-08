"""Wi-Fi SSID safety guard for launching Clash Verge on Windows."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import queue
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

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


def get_current_ssid() -> str | None:
    """Return the first connected Wi-Fi SSID, or None if it cannot be read."""
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
        return f'"{pythonw}" "{script}"'
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


class GuardApp:
    def __init__(self) -> None:
        self.config = load_config()
        self.root = tk.Tk()
        self.root.withdraw()
        self.icon = None
        self._ui_actions: queue.Queue = queue.Queue()
        self.settings_window: tk.Toplevel | None = None

    def run(self, open_settings: bool = False) -> None:
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
                pystray.MenuItem("管理危险 SSID", self._tray_settings),
                pystray.MenuItem("检测当前 SSID", self._tray_check),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("退出", self._quit),
            ),
        )
        self.icon.run_detached()
        self.root.after(50, self._drain_ui_actions)
        if open_settings:
            self.root.after(150, self.open_settings)
        self.root.mainloop()

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
        self._call_on_ui(self.open_settings)

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

    def open_settings(self) -> None:
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            self.settings_window.focus_force()
            return

        window = tk.Toplevel(self.root)
        self.settings_window = window
        window.title("Wi-Fi Clash Guard 设置")
        window.resizable(False, False)
        window.transient(self.root)

        frame = ttk.Frame(window, padding=14)
        frame.grid(sticky="nsew")
        ttk.Label(frame, text="危险 SSID（匹配不区分大小写）").grid(
            row=0, column=0, columnspan=2, sticky="w"
        )
        ssid_list = tk.Listbox(frame, height=8, width=42, exportselection=False)
        ssid_list.grid(row=1, column=0, rowspan=4, padx=(0, 8), pady=(6, 10))
        for item in self.config["dangerous_ssids"]:
            ssid_list.insert(tk.END, item)

        def add_ssid() -> None:
            value = simpledialog.askstring("添加危险 SSID", "请输入完整 SSID：", parent=window)
            if value and value.strip():
                value = value.strip()
                current = [ssid_list.get(i) for i in range(ssid_list.size())]
                if value.casefold() not in {x.casefold() for x in current}:
                    ssid_list.insert(tk.END, value)

        def edit_ssid() -> None:
            selection = ssid_list.curselection()
            if not selection:
                messagebox.showinfo(APP_NAME, "请先选择一个 SSID。", parent=window)
                return
            index = selection[0]
            value = simpledialog.askstring(
                "修改危险 SSID", "请输入完整 SSID：", initialvalue=ssid_list.get(index), parent=window
            )
            if value and value.strip():
                ssid_list.delete(index)
                ssid_list.insert(index, value.strip())

        def delete_ssid() -> None:
            for index in reversed(ssid_list.curselection()):
                ssid_list.delete(index)

        ttk.Button(frame, text="添加", command=add_ssid).grid(row=1, column=1, sticky="ew")
        ttk.Button(frame, text="修改", command=edit_ssid).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text="删除", command=delete_ssid).grid(row=3, column=1, sticky="ew")

        ttk.Label(frame, text="Clash Verge 可执行文件").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        clash_path = tk.StringVar(value=self.config.get("clash_path", ""))
        path_entry = ttk.Entry(frame, textvariable=clash_path, width=43)
        path_entry.grid(row=6, column=0, padx=(0, 8), pady=(6, 10))

        def choose_clash() -> None:
            selected = filedialog.askopenfilename(
                parent=window,
                title="选择 Clash Verge exe",
                filetypes=[("程序文件", "*.exe"), ("所有文件", "*.*")],
            )
            if selected:
                clash_path.set(selected)

        ttk.Button(frame, text="选择…", command=choose_clash).grid(row=6, column=1, sticky="ew")

        startup_var = tk.BooleanVar(value=bool(self.config.get("start_with_windows", False)))
        ttk.Checkbutton(frame, text="Windows 开机自动运行托盘程序", variable=startup_var).grid(
            row=7, column=0, columnspan=2, sticky="w", pady=(0, 8)
        )

        def close_window() -> None:
            try:
                window.grab_release()
            except tk.TclError:
                pass
            self.settings_window = None
            window.destroy()

        def save_and_close() -> None:
            values = [ssid_list.get(i).strip() for i in range(ssid_list.size())]
            values = normalized_ssids(values)
            self.config["dangerous_ssids"] = values
            self.config["clash_path"] = clash_path.get().strip()
            self.config["start_with_windows"] = startup_var.get()
            save_config(self.config)
            ok, error = set_startup(startup_var.get())
            if not ok:
                messagebox.showerror(APP_NAME, error, parent=window)
                return
            close_window()

        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="取消", command=close_window).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(buttons, text="保存", command=save_and_close).pack(side=tk.RIGHT)

        # A Toplevel transient to a withdrawn root can otherwise appear behind
        # the desktop on some Windows configurations.
        window.protocol("WM_DELETE_WINDOW", close_window)
        window.update_idletasks()
        window.deiconify()
        window.lift()
        window.focus_force()
        window.grab_set()


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
    parser.add_argument("--settings", action="store_true", help="启动托盘程序并直接打开设置")
    args = parser.parse_args()
    try:
        if args.launch:
            return launch_once()
        GuardApp().run(open_settings=args.settings)
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
