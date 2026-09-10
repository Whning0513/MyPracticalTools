"""
DingTalk webhook bridge (HTTP callback mode).

Receives @bot messages from DingTalk outgoing webhook,
runs CC, and posts results back to the group.

For the newer Stream or Telegram bridges, see stream_bridge.py / telegram_bridge.py.
"""
import os

from contextlib import asynccontextmanager
from fastapi import FastAPI, BackgroundTasks

from .cc_runner import (
    sender,
    run_claude,
    format_reply,
    strip_at_mention,
    CC_MODE,
    get_tmux,
)

BRIDGE_PORT = int(os.environ.get("BRIDGE_PORT", "8001"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    if CC_MODE == "tmux":
        get_tmux()
    yield


app = FastAPI(title="CC-DingTalk Bridge", lifespan=lifespan)


async def run_claude_and_reply(prompt: str, sender_nick: str = ""):
    """Background task: run CC, then send result to DingTalk."""
    response = await run_claude(prompt)
    if not response:
        response = "CC 返回了空内容"
    body = format_reply(prompt, response, sender_nick)
    try:
        sender.send_markdown(title=f"CC: {prompt[:50].replace(chr(10), ' ')}", text=body)
    except Exception as e:
        print(f"[bridge] send_markdown failed: {e}")


@app.get("/health")
def health():
    return {"status": "ok", "mode": CC_MODE}


@app.post("/callback")
async def callback(payload: dict, background_tasks: BackgroundTasks):
    # DingTalk outgoing-webhook challenge verification
    if "challenge" in payload:
        return {"challenge": payload["challenge"]}

    # Extract message content
    text = payload.get("text", {})
    if isinstance(text, str):
        raw = text
    elif isinstance(text, dict):
        raw = text.get("content", "")
    else:
        raw = ""

    if not raw.strip():
        return {"errcode": 0, "errmsg": "empty"}

    prompt = strip_at_mention(raw)
    if not prompt:
        return {"errcode": 0, "errmsg": "empty after strip"}

    sender_nick = payload.get("senderNick", "")

    # Fire-and-forget — must return within ~3s of DingTalk's timeout
    background_tasks.add_task(run_claude_and_reply, prompt, sender_nick)

    return {"errcode": 0, "errmsg": f"processing: {prompt[:50]}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "dingtalk_webhook.bridge:app",
        host="0.0.0.0",
        port=BRIDGE_PORT,
        reload=True,
    )
