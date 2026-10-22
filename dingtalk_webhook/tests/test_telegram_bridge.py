from __future__ import annotations

import asyncio
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from dingtalk_webhook import telegram_bridge
from dingtalk_webhook.telegram_bridge import split_message


class TelegramMessageTests(unittest.TestCase):
    def test_proxy_summary_does_not_expose_proxy_urls_or_credentials(self) -> None:
        proxy_urls = [
            "http://alice:secret-one@proxy.example:7890",
            "http://bob:secret-two@backup.example:7890",
        ]
        with patch.object(telegram_bridge, "TELEGRAM_PROXY", proxy_urls):
            self.assertEqual(telegram_bridge.proxy_summary(), "2 configured proxies")

        with patch.object(telegram_bridge, "TELEGRAM_PROXY", [""]):
            self.assertEqual(telegram_bridge.proxy_summary(), "direct")

    def test_status_does_not_send_proxy_credentials(self) -> None:
        async def run_status() -> None:
            loop = asyncio.get_running_loop()
            with (
                patch.object(telegram_bridge, "CC_MODE", "tmux"),
                patch.object(telegram_bridge, "TELEGRAM_PROXY", ["http://alice:secret@proxy.example:7890"]),
                patch.object(telegram_bridge, "get_tmux"),
                patch.object(telegram_bridge, "send_telegram_message") as send,
            ):
                self.assertTrue(await telegram_bridge.handle_command(1, "/status", loop))
                message = send.call_args.args[1]
                self.assertIn("1 configured proxy", message)
                self.assertNotIn("alice", message)
                self.assertNotIn("secret", message)
                self.assertNotIn("proxy.example", message)

        asyncio.run(run_status())

    def test_allowed_user_ids_are_validated(self) -> None:
        self.assertEqual(
            telegram_bridge.parse_allowed_user_ids("123, 456,123"),
            frozenset({123, 456}),
        )
        with self.assertRaisesRegex(ValueError, "positive user IDs"):
            telegram_bridge.parse_allowed_user_ids("0")
        with self.assertRaisesRegex(ValueError, "comma-separated integers"):
            telegram_bridge.parse_allowed_user_ids("not-an-id")

    def test_unlisted_user_cannot_run_bot_commands(self) -> None:
        class StopPolling(Exception):
            pass

        async def stop_after_first_poll(_delay: float) -> None:
            raise StopPolling

        result = {
            "ok": True,
            "result": [
                {
                    "update_id": 10,
                    "message": {
                        "text": "/sh echo should-not-run",
                        "chat": {"id": 1234, "type": "private"},
                        "from": {"id": 999, "first_name": "stranger"},
                    },
                },
                {
                    "update_id": 11,
                    "message": {
                        "text": "run an unauthorized prompt",
                        "chat": {"id": 1234, "type": "private"},
                        "from": {"id": 999, "first_name": "stranger"},
                    },
                },
            ],
        }
        handle_command = AsyncMock(return_value=True)
        process_message = AsyncMock()
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(telegram_bridge, "TELEGRAM_ALLOWED_USER_IDS", frozenset({123})),
                patch.object(telegram_bridge, "TELEGRAM_OFFSET_FILE", f"{directory}/offset"),
                patch.object(telegram_bridge, "_tg_get", return_value=result),
                patch.object(telegram_bridge, "handle_command", handle_command),
                patch.object(telegram_bridge, "send_telegram_message", return_value=1),
                patch.object(telegram_bridge, "process_message", process_message),
                patch.object(telegram_bridge.asyncio, "sleep", new=stop_after_first_poll),
            ):
                with self.assertRaises(StopPolling):
                    asyncio.run(telegram_bridge.polling_loop())

        handle_command.assert_not_awaited()
        process_message.assert_not_called()

    def test_whoami_reports_id_without_authorizing_commands(self) -> None:
        class StopPolling(Exception):
            pass

        async def stop_after_first_poll(_delay: float) -> None:
            raise StopPolling

        result = {
            "ok": True,
            "result": [{
                "update_id": 11,
                "message": {
                    "text": "/whoami",
                    "chat": {"id": 1234, "type": "private"},
                    "from": {"id": 999, "first_name": "owner"},
                },
            }],
        }
        handle_command = AsyncMock()
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(telegram_bridge, "TELEGRAM_ALLOWED_USER_IDS", frozenset()),
                patch.object(telegram_bridge, "TELEGRAM_OFFSET_FILE", f"{directory}/offset"),
                patch.object(telegram_bridge, "_tg_get", return_value=result),
                patch.object(telegram_bridge, "send_telegram_message") as send,
                patch.object(telegram_bridge, "handle_command", handle_command),
                patch.object(telegram_bridge.asyncio, "sleep", new=stop_after_first_poll),
            ):
                with self.assertRaises(StopPolling):
                    asyncio.run(telegram_bridge.polling_loop())

        self.assertIn("999", send.call_args.args[1])
        handle_command.assert_not_awaited()

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
