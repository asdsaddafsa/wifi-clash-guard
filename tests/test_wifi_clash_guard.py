import unittest
import sys

from wifi_clash_guard import (
    decode_netsh_output,
    decode_ssid_bytes,
    is_configured_clash_running,
    is_dangerous,
    normalize_executable_path,
    normalized_ssids,
    should_show_startup_warning,
)


class WifiClashGuardTests(unittest.TestCase):
    def test_decode_utf8_ssid(self):
        raw = "    SSID                   : 网络中文\r\n".encode("utf-8")
        self.assertIn("网络中文", decode_netsh_output(raw))

    def test_decode_gb18030_ssid(self):
        raw = "    SSID                   : 家庭网络\r\n".encode("gb18030")
        self.assertIn("家庭网络", decode_netsh_output(raw))

    def test_decode_ssid_bytes_supports_utf8_and_gb18030(self):
        self.assertEqual(decode_ssid_bytes("网络中文".encode("utf-8")), "网络中文")
        self.assertEqual(decode_ssid_bytes("家庭网络".encode("gb18030")), "家庭网络")

    def test_normalized_ssids_removes_empty_and_case_duplicates(self):
        self.assertEqual(
            normalized_ssids([" Cafe ", "cafe", "", "家庭网络"]),
            ["Cafe", "家庭网络"],
        )

    def test_dangerous_matching_is_case_insensitive(self):
        self.assertTrue(is_dangerous("CoffeeShop", ["coffeeshop"]))
        self.assertFalse(is_dangerous("CoffeeShop", ["Home"]))

    def test_startup_warning_requires_dangerous_ssid_and_running_executable(self):
        clash_path = normalize_executable_path("Clash Verge.exe")
        self.assertTrue(
            should_show_startup_warning(
                "CoffeeShop", ["coffeeshop"], clash_path, [clash_path]
            )
        )

    def test_startup_warning_skips_safe_unknown_and_not_running_cases(self):
        clash_path = normalize_executable_path("Clash Verge.exe")
        self.assertFalse(
            should_show_startup_warning("Home", ["CoffeeShop"], clash_path, [clash_path])
        )
        self.assertFalse(
            should_show_startup_warning(None, ["CoffeeShop"], clash_path, [clash_path])
        )
        self.assertFalse(
            should_show_startup_warning("CoffeeShop", ["CoffeeShop"], clash_path, [])
        )

    def test_process_identity_uses_normalized_full_path(self):
        configured = normalize_executable_path("apps" + "/../apps/Clash Verge.exe")
        running = normalize_executable_path("apps/Clash Verge.exe")
        self.assertEqual(configured, running)
        self.assertTrue(is_configured_clash_running(configured, [running]))
        self.assertFalse(
            is_configured_clash_running(configured, [normalize_executable_path("other.exe")])
        )

    def test_normalized_path_accepts_windows_extended_prefix(self):
        ordinary = normalize_executable_path(sys.executable)
        extended = normalize_executable_path("\\\\?\\" + ordinary)
        self.assertEqual(extended, ordinary)


if __name__ == "__main__":
    unittest.main()
