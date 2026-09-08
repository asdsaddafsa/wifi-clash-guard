import unittest

from wifi_clash_guard import (
    decode_netsh_output,
    decode_ssid_bytes,
    is_dangerous,
    normalized_ssids,
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


if __name__ == "__main__":
    unittest.main()
