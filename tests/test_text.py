"""Testy formatowania liczb w polskiej konwencji."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.text import NBSP, num, upper_first  # noqa: E402


class TestNum(unittest.TestCase):
    def test_decimal_comma(self):
        self.assertEqual(num(8.4567, 2), "8,46")
        self.assertEqual(num(3.0, 1), "3,0")

    def test_thousands_use_non_breaking_space(self):
        self.assertEqual(num(370590, 0), f"370{NBSP}590")
        self.assertNotIn(",", num(1_234_567, 0))

    def test_no_decimals(self):
        self.assertEqual(num(47.6, 0), "48")


class TestUpperFirst(unittest.TestCase):
    def test_only_first_letter_changes(self):
        self.assertEqual(upper_first("nawet mały teleskop pokaże pierścienie"),
                         "Nawet mały teleskop pokaże pierścienie")

    def test_keeps_inner_capitals(self):
        # capitalize() zepsulo by nazwe wlasna - dlatego mamy wlasna funkcje
        self.assertEqual(upper_first("przez lornetkę widać księżyce Jowisza"),
                         "Przez lornetkę widać księżyce Jowisza")

    def test_empty_string(self):
        self.assertEqual(upper_first(""), "")


if __name__ == "__main__":
    unittest.main()
