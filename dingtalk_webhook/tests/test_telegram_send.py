from __future__ import annotations

import unittest
from unittest.mock import patch

from dingtalk_webhook import telegram_bridge


class TelegramSendTests(unittest.TestCase):
    def test_partial_chunk_failure_is_reported_as_failure(self) -> None:
        responses = [
            {"ok": True, "result": {"message_id": 10}},
            {"ok": False, "error": "temporary failure"},
        ]
        with (
            patch.object(telegram_bridge, "_tg_post", side_effect=responses) as post,
            patch.object(telegram_bridge.time, "sleep"),
        ):
            result = telegram_bridge.send_telegram_message(
                123, "x" * (telegram_bridge.TELEGRAM_MAX_LEN + 1)
            )

        self.assertIsNone(result)
        self.assertEqual(post.call_count, 2)

    def test_all_chunks_return_the_last_message_id(self) -> None:
        responses = [
            {"ok": True, "result": {"message_id": 10}},
            {"ok": True, "result": {"message_id": 11}},
        ]
        with (
            patch.object(telegram_bridge, "_tg_post", side_effect=responses) as post,
            patch.object(telegram_bridge.time, "sleep"),
        ):
            result = telegram_bridge.send_telegram_message(
                123, "x" * (telegram_bridge.TELEGRAM_MAX_LEN + 1)
            )

        self.assertEqual(result, 11)
        self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
