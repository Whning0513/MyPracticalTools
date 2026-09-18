from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from dingtalk_webhook.sender import get_dingtalk_credentials


class CredentialTests(unittest.TestCase):
    def test_credentials_are_required(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DINGTALK_ACCESS_TOKEN"):
                get_dingtalk_credentials()

    def test_credentials_are_read_from_environment(self) -> None:
        values = {
            "DINGTALK_ACCESS_TOKEN": "token-from-env",
            "DINGTALK_SECRET": "secret-from-env",
        }
        with patch.dict(os.environ, values, clear=True):
            self.assertEqual(get_dingtalk_credentials(), ("token-from-env", "secret-from-env"))


if __name__ == "__main__":
    unittest.main()
