from __future__ import annotations

import unittest
from urllib.parse import parse_qs, urlsplit

from dingtalk_webhook.sender import DingTalkSender


class SenderUrlTests(unittest.TestCase):
    def test_base64_signature_is_url_encoded(self) -> None:
        sender = DingTalkSender("token+/=", "secret")
        sender._sign = lambda _timestamp: "a+b/c=="  # type: ignore[method-assign]

        query = parse_qs(urlsplit(sender._url()).query)

        self.assertEqual(query["access_token"], ["token+/="])
        self.assertEqual(query["sign"], ["a+b/c=="])


if __name__ == "__main__":
    unittest.main()
