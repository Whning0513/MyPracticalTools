from __future__ import annotations

import asyncio
import tempfile
import unittest
from unittest.mock import patch

from dingtalk_webhook import telegram_bridge
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

    def test_polling_offset_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            offset_file = f"{directory}/telegram-offset"

            self.assertEqual(telegram_bridge.load_polling_offset(offset_file), 0)
            telegram_bridge.save_polling_offset(42, offset_file)

            self.assertEqual(telegram_bridge.load_polling_offset(offset_file), 42)

    def test_polling_starts_from_persisted_offset(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            offset_file = f"{directory}/telegram-offset"
            telegram_bridge.save_polling_offset(42, offset_file)
            requests: list[str] = []

            class StopPolling(Exception):
                pass

            def fake_get(path: str) -> dict:
                requests.append(path)
                return {"ok": True, "result": []}

            async def stop_after_first_poll(_delay: float) -> None:
                raise StopPolling

            with (
                patch.object(telegram_bridge, "TELEGRAM_OFFSET_FILE", offset_file),
                patch.object(telegram_bridge, "_tg_get", side_effect=fake_get),
                patch.object(telegram_bridge.asyncio, "sleep", new=stop_after_first_poll),
            ):
                with self.assertRaises(StopPolling):
                    asyncio.run(telegram_bridge.polling_loop())

            self.assertEqual(requests, ["getUpdates?offset=42&timeout=2"])


if __name__ == "__main__":
    unittest.main()
