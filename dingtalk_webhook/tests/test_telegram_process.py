from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

from dingtalk_webhook import telegram_bridge


class TelegramProcessTests(unittest.TestCase):
    def test_error_after_snapshot_is_sent_to_user(self) -> None:
        async def fail_after_delay(_prompt: str) -> str:
            await asyncio.sleep(0.02)
            raise RuntimeError("claude failed")

        with (
            patch.object(telegram_bridge, "_CC_SNAPSHOT_DELAY", 0.001),
            patch.object(telegram_bridge, "run_claude", new=fail_after_delay),
            patch.object(telegram_bridge, "send_telegram_message", return_value=123) as send,
            patch.object(telegram_bridge, "_tg_post") as post,
        ):
            asyncio.run(telegram_bridge.process_message(1, "hello", "alice", 42))

        body = send.call_args.args[1]
        self.assertIn("CC 执行出错: claude failed", body)
        post.assert_called_once_with(
            "deleteMessage", {"chat_id": 1, "message_id": 42}
        )

    def test_missing_status_message_does_not_trigger_invalid_cleanup(self) -> None:
        async def succeed(_prompt: str) -> str:
            return "answer"

        with (
            patch.object(telegram_bridge, "run_claude", new=succeed),
            patch.object(telegram_bridge, "send_telegram_message", return_value=123),
            patch.object(telegram_bridge, "_tg_post") as post,
        ):
            asyncio.run(telegram_bridge.process_message(1, "hello", "alice", None))

        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
