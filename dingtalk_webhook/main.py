import os
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .sender import DingTalkSender

ACCESS_TOKEN = os.environ.get(
    "DINGTALK_ACCESS_TOKEN",
    "9f2bd3f1fcff3c673de165149be67895980b69001db1096f6eb0da329070cb2c",
)
SECRET = os.environ.get(
    "DINGTALK_SECRET",
    "SEC534c62399a9f81870bde8558d8c9a74592c1020c93c9ac13054e49bd4e62943b",
)

sender = DingTalkSender(ACCESS_TOKEN, SECRET)
app = FastAPI(title="DingTalk Webhook")


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
    result = sender.send_text(msg.content, msg.at_mobiles, msg.at_all)
    if result.get("errcode") != 0:
        raise HTTPException(status_code=502, detail=result)
    return result


@app.post("/send/markdown")
def send_markdown(msg: MarkdownMessage):
    result = sender.send_markdown(msg.title, msg.text, msg.at_mobiles, msg.at_all)
    if result.get("errcode") != 0:
        raise HTTPException(status_code=502, detail=result)
    return result


@app.post("/send/link")
def send_link(msg: LinkMessage):
    result = sender.send_link(msg.title, msg.text, msg.message_url, msg.pic_url)
    if result.get("errcode") != 0:
        raise HTTPException(status_code=502, detail=result)
    return result


@app.post("/notify")
def notify(msg: NotifyMessage):
    now = datetime.now().strftime("%H:%M:%S")
    formatted = f"发送者: {msg.sender}\n时间: {now}\n内容: {msg.content}"
    result = sender.send_text(formatted)
    if result.get("errcode") != 0:
        raise HTTPException(status_code=502, detail=result)
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("dingtalk_webhook.main:app", host="0.0.0.0", port=8000, reload=True)
