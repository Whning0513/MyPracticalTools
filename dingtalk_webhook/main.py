from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .sender import DingTalkSender, get_dingtalk_credentials
app = FastAPI(title="DingTalk Webhook")


def get_sender() -> DingTalkSender:
    """Build a sender only when an endpoint actually needs credentials."""

    return DingTalkSender(*get_dingtalk_credentials())


class TextMessage(BaseModel):
    content: str
    at_mobiles: list[str] = []
    at_all: bool = False


class MarkdownMessage(BaseModel):
    title: str
    text: str
    at_mobiles: list[str] = []
    at_all: bool = False


class LinkMessage(BaseModel):
    title: str
    text: str
    message_url: str
    pic_url: str = ""


class NotifyMessage(BaseModel):
    sender: str
    content: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/send/text")
def send_text(msg: TextMessage):
    result = get_sender().send_text(msg.content, msg.at_mobiles, msg.at_all)
    if result.get("errcode") != 0:
        raise HTTPException(status_code=502, detail=result)
    return result


@app.post("/send/markdown")
def send_markdown(msg: MarkdownMessage):
    result = get_sender().send_markdown(msg.title, msg.text, msg.at_mobiles, msg.at_all)
    if result.get("errcode") != 0:
        raise HTTPException(status_code=502, detail=result)
    return result


@app.post("/send/link")
def send_link(msg: LinkMessage):
    result = get_sender().send_link(msg.title, msg.text, msg.message_url, msg.pic_url)
    if result.get("errcode") != 0:
        raise HTTPException(status_code=502, detail=result)
    return result


@app.post("/notify")
def notify(msg: NotifyMessage):
    now = datetime.now().strftime("%H:%M:%S")
    formatted = f"发送者: {msg.sender}\n时间: {now}\n内容: {msg.content}"
    result = get_sender().send_text(formatted)
    if result.get("errcode") != 0:
        raise HTTPException(status_code=502, detail=result)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dingtalk_webhook.main:app", host="0.0.0.0", port=8000, reload=True)
