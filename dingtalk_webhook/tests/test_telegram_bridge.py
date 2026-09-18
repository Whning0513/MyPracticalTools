from __future__ import annotations

import unittest

from dingtalk_webhook.telegram_bridge import split_message


class TelegramMessageTests(unittest.TestCase):
    def test_newline_at_window_start_still_makes_progress(self) -> None:
        text = "\n" + ("a" * 3800) + "tail"

        chunks = split_message(text)

        self.assertGreater(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 3799)
        self.assertEqual(chunks[-1], "atail")
        self.assertTrue(all(0 < len(chunk) <= 3800 for chunk in chunks))

    def test_long_lines_are_split_when_no_newline_is_available(self) -> None:
        chunks = split_message("x" * 10, max_length=4)

        self.assertEqual(chunks, ["xxxx", "xxxx", "xx"])


if __name__ == "__main__":
    unittest.main()
