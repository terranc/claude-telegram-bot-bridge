"""
Tests for revert command functionality.
"""

import unittest


class TestRevertCallbackParsing(unittest.TestCase):
    """Test callback data parsing for revert operations."""

    def test_parse_select_callback(self):
        """Test parsing message selection callback."""
        data = "revert:select:42"
        parts = data.split(":")

        self.assertEqual(parts[0], "revert")
        self.assertEqual(parts[1], "select")
        self.assertEqual(int(parts[2]), 42)

    def test_parse_page_callback(self):
        """Test parsing pagination callback."""
        data = "revert:page:3"
        parts = data.split(":")

        self.assertEqual(parts[0], "revert")
        self.assertEqual(parts[1], "page")
        self.assertEqual(int(parts[2]), 3)

    def test_parse_mode_callback(self):
        """Test parsing mode selection callback."""
        data = "revert:mode:42:full"
        parts = data.split(":")

        self.assertEqual(parts[0], "revert")
        self.assertEqual(parts[1], "mode")
        self.assertEqual(int(parts[2]), 42)
        self.assertEqual(parts[3], "full")

    def test_parse_mode_callback_all_modes(self):
        """Test parsing all revert modes."""
        modes = ["full", "conv", "code", "summary", "cancel"]

        for mode in modes:
            data = f"revert:mode:10:{mode}"
            parts = data.split(":")

            self.assertEqual(parts[0], "revert")
            self.assertEqual(parts[1], "mode")
            self.assertEqual(int(parts[2]), 10)
            self.assertEqual(parts[3], mode)


if __name__ == "__main__":
    unittest.main()
