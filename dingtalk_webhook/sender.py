import hashlib
import hmac
import base64
import time
import json
import urllib.request
import urllib.error
from urllib.parse import urlencode
import os
from typing import Optional


def get_dingtalk_credentials() -> tuple[str, str]:
    """Read the DingTalk credentials from the environment.

    Credentials are deliberately not optional: a public package must never
    ship a fallback token or secret.
    """

    token = os.environ.get("DINGTALK_ACCESS_TOKEN", "").strip()
    secret = os.environ.get("DINGTALK_SECRET", "").strip()
    missing = []
    if not token:
        missing.append("DINGTALK_ACCESS_TOKEN")
    if not secret:
        missing.append("DINGTALK_SECRET")
    if missing:
        names = ", ".join(missing)
        raise RuntimeError(f"Missing DingTalk credential environment variable(s): {names}")
    return token, secret


class DingTalkSender:
    def __init__(self, access_token: str, secret: str):
        self.access_token = access_token
        self.secret = secret

    def _sign(self, timestamp: int) -> str:
        secret_enc = self.secret.encode("utf-8")
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            secret_enc, string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
        ).digest()
        return base64.b64encode(hmac_code).decode("utf-8")

    def _url(self) -> str:
        timestamp = str(round(time.time() * 1000))
        sign = self._sign(timestamp)
        query = urlencode(
            {
                "access_token": self.access_token,
                "timestamp": timestamp,
                "sign": sign,
            }
        )
        return f"https://oapi.dingtalk.com/robot/send?{query}"

    def _post(self, payload: dict) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._url(),
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            return {"errcode": e.code, "errmsg": e.read().decode("utf-8")}
        except Exception as e:
            return {"errcode": -1, "errmsg": str(e)}

    def send_text(self, content: str, at_mobiles: Optional[list[str]] = None, at_all: bool = False) -> dict:
        payload = {
            "msgtype": "text",
            "text": {"content": content},
        }
        if at_mobiles or at_all:
            payload["at"] = {}
            if at_mobiles:
                payload["at"]["atMobiles"] = at_mobiles
            if at_all:
                payload["at"]["isAtAll"] = True
        return self._post(payload)

    def send_markdown(self, title: str, text: str, at_mobiles: Optional[list[str]] = None, at_all: bool = False) -> dict:
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text},
        }
        if at_mobiles or at_all:
            payload["at"] = {}
            if at_mobiles:
                payload["at"]["atMobiles"] = at_mobiles
            if at_all:
                payload["at"]["isAtAll"] = True
        return self._post(payload)

    def send_link(self, title: str, text: str, message_url: str, pic_url: str = "") -> dict:
        payload = {
            "msgtype": "link",
            "link": {
                "title": title,
                "text": text,
                "messageUrl": message_url,
                "picUrl": pic_url,
            },
        }
        return self._post(payload)
