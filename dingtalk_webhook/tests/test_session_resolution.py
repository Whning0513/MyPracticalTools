from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dingtalk_webhook.cc_runner import list_sessions, resolve_session_id


class SessionResolutionTests(unittest.TestCase):
    def test_resume_index_uses_the_order_shown_by_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            sessions = home / ".claude" / "sessions"
            sessions.mkdir(parents=True)
            self._write_session(sessions / "older.json", "older", 100)
            self._write_session(sessions / "newer.json", "newer", 200)

            with patch(
                "dingtalk_webhook.cc_runner.os.path.expanduser",
                return_value=str(sessions),
            ):
                self.assertEqual(resolve_session_id("1"), "newer")
                self.assertEqual(resolve_session_id("2"), "older")
                self.assertIn("#1  `newer`", list_sessions())

    @staticmethod
    def _write_session(path: Path, session_id: str, mtime: int) -> None:
        path.write_text(json.dumps({"sessionId": session_id}), encoding="utf-8")
        os.utime(path, (mtime, mtime))


if __name__ == "__main__":
    unittest.main()
