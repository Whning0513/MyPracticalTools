"""
Telegram Bot bridge for Claude Code.

Uses manual HTTP polling (urllib) with multi-proxy failover.
No ngrok, no public URL needed.

Usage:
  export TELEGRAM_BOT_TOKEN="your-token"
  export TELEGRAM_PROXY="http://127.0.0.1:7890,http://127.0.0.1:3383"
  python -m dingtalk_webhook.telegram_bridge
"""
import os
import re
import json
import time
import asyncio
import subprocess
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .cc_runner import (
    run_claude,
    format_reply,
    simplify_tables,
    CC_MODE,
    get_tmux,
    list_sessions,
    resolve_session_id,
    set_session_title,
)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_PROXY = [
    p.strip() for p in os.environ.get("TELEGRAM_PROXY", "").split(",") if p.strip()
]
TELEGRAM_POLL_INTERVAL = int(os.environ.get("TELEGRAM_POLL_INTERVAL", "3"))
TELEGRAM_MAX_LEN = 3800
TELEGRAM_DOWN_THRESHOLD = 5  # consecutive failures before marking as down
TELEGRAM_OFFSET_FILE = Path(
    os.environ.get(
        "TELEGRAM_OFFSET_FILE",
        "~/.cache/dingtalk-webhook/telegram-offset",
    )
).expanduser()

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

if not TELEGRAM_PROXY:
    TELEGRAM_PROXY = [""]  # direct connection fallback

_executor = ThreadPoolExecutor(max_workers=4)

# ── network state ───────────────────────────────────────────────────
_net = {
    "failures": 0,
    "was_down": False,
    "last_chat_id": None,
}


def load_polling_offset(path: str | Path = TELEGRAM_OFFSET_FILE) -> int:
    """Load the last acknowledged Telegram update offset."""
    try:
        value = int(Path(path).expanduser().read_text(encoding="utf-8").strip(), 10)
    except (OSError, TypeError, ValueError):
        return 0
    return max(0, value)


def save_polling_offset(offset: int, path: str | Path = TELEGRAM_OFFSET_FILE) -> None:
    """Persist an offset atomically so a restart does not replay old updates."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    temporary.write_text(str(max(0, offset)), encoding="utf-8")
    temporary.replace(target)


def split_message(text: str, max_length: int = TELEGRAM_MAX_LEN) -> list[str]:
    """Split a Telegram message without producing an empty, non-progressing chunk."""

    if max_length <= 0:
        raise ValueError("max_length must be positive")
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_length:
        split_at = remaining.rfind("\n", 0, max_length)
        # A newline at position zero would leave the input unchanged after
        # stripping. Force a hard split so every iteration makes progress.
        if split_at <= 0:
            split_at = max_length
        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def _is_network_error(err: str) -> bool:
    """Check if an error string looks like a network-level failure."""
    keywords = [
        "SSL:", "EOF", "timeout", "refused", "unreachable",
        "reset", "Connection", "NetworkError", "urlopen error",
        "Tunnel", "ProxyError", "ConnectError",
    ]
    return any(k.lower() in err.lower() for k in keywords)


# ── HTTP helpers (multi-proxy) ──────────────────────────────────────
def _tg_get(path: str) -> dict:
    """GET request to Telegram API, trying all proxies."""
    last_err = ""
    for proxy_url in TELEGRAM_PROXY:
        for attempt in range(2):
            try:
                handler = urllib.request.ProxyHandler({"https": proxy_url}) if proxy_url else urllib.request.ProxyHandler({})
                opener = urllib.request.build_opener(handler)
                with opener.open(f"{BASE_URL}/{path}", timeout=20) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                last_err = str(e)
                if attempt < 1:
                    time.sleep(0.5)
    return {"ok": False, "error": last_err, "_network": True}


def _tg_post(path: str, body: dict) -> dict:
    """POST request to Telegram API, trying all proxies."""
    data = json.dumps(body).encode("utf-8")
    last_err = ""
    for proxy_url in TELEGRAM_PROXY:
        for attempt in range(2):
            try:
                handler = urllib.request.ProxyHandler({"https": proxy_url}) if proxy_url else urllib.request.ProxyHandler({})
                opener = urllib.request.build_opener(handler)
                req = urllib.request.Request(
                    f"{BASE_URL}/{path}",
                    data=data,
                    headers={
                        "Content-Type": "application/json",
                        "Connection": "close",
                    },
                )
                with opener.open(req, timeout=20) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                last_err = str(e)
                if attempt < 1:
                    time.sleep(0.5)
    return {"ok": False, "error": last_err, "_network": True}


# ── message sending ─────────────────────────────────────────────────
def send_telegram_message(chat_id: int, text: str) -> int | None:
    """Send a text message via Telegram. Returns message_id or None."""
    text = simplify_tables(text)
    chunks = split_message(text)

    last_id = None
    for chunk in chunks:
        result = _tg_post("sendMessage", {"chat_id": chat_id, "text": chunk})
        if result.get("ok"):
            last_id = result["result"]["message_id"]
        else:
            print(f"[tg] send error: {result.get('error', result)}")
        time.sleep(0.3)
    return last_id


# ── command handling ────────────────────────────────────────────────
async def handle_command(chat_id: int, text: str, loop) -> bool:
    """Handle tmux control commands. Returns True if a command was handled."""

    def reply(msg: str):
        send_telegram_message(chat_id, msg)

    if CC_MODE != "tmux":
        await loop.run_in_executor(_executor, reply,
            f"当前是 print 模式，不支持会话控制命令。\n设置 CC_MODE=tmux 后可用。")
        return True

    tmux = get_tmux()

    if text == "/new":
        print(f"[tg] /new — restarting CC session")
        await loop.run_in_executor(_executor, reply, "新开对话...")
        await tmux.restart_cc()
        await loop.run_in_executor(_executor, reply, "新对话已开始（第一条消息将作为标题）")

    elif text.startswith("/new "):
        title = text.split(" ", 1)[1].strip()
        print(f"[tg] /new '{title}'")
        await loop.run_in_executor(_executor, reply, f"新开对话「{title}」...")
        await tmux.restart_cc()
        await asyncio.sleep(3)
        set_session_title(title)
        await loop.run_in_executor(_executor, reply, f"新对话「{title}」已创建（发送第一条消息后可用 /title 重新锁定标题）")

    elif text.startswith("/title "):
        title = text.split(" ", 1)[1].strip()
        print(f"[tg] /title '{title}'")
        if set_session_title(title):
            await loop.run_in_executor(_executor, reply, f"会话已改名为「{title}」")
        else:
            await loop.run_in_executor(_executor, reply, "改名失败，找不到会话文件")

    elif text == "/exit":
        print(f"[tg] /exit — exiting CC")
        await loop.run_in_executor(_executor, reply, "退出 CC...")
        await tmux.exit_cc()
        await loop.run_in_executor(_executor, reply, "CC 已退出。发送 /new 重新开始。")

    elif text == "/resume" or text == "/r":
        print(f"[tg] /resume — resuming last CC session")
        await loop.run_in_executor(_executor, reply, "恢复最近对话...")
        await tmux.resume_last()
        # Capture the tail of resumed session for context
        await asyncio.sleep(2)
        ctx = tmux.get_recent_output(2000)
        await loop.run_in_executor(_executor, reply,
            f"对话已恢复，最近内容:\n\n{ctx}" if ctx else "对话已恢复")

    elif text.startswith("/resume "):
        user_input = text.split(" ", 1)[1].strip()
        # Handle "/resume 3" (index from /sessions list)
        if user_input.isdigit():
            # Look up by index or PID
            real_id = resolve_session_id(user_input)
            if not real_id:
                await loop.run_in_executor(_executor, reply, f"找不到会话 {user_input}，发送 /sessions 查看可用列表")
                return True
        else:
            real_id = user_input  # assume it's already a UUID

        print(f"[tg] /resume {user_input} -> {real_id}")
        await loop.run_in_executor(_executor, reply, f"恢复对话 {user_input}...")
        await tmux.restart_cc(resume_id=real_id)
        await asyncio.sleep(2)
        ctx = tmux.get_recent_output(2000)
        await loop.run_in_executor(_executor, reply,
            f"对话 {user_input} 已恢复，最近内容:\n\n{ctx}" if ctx else f"对话 {user_input} 已恢复")

    elif text == "/stop":
        print(f"[tg] /stop — interrupting CC")
        await loop.run_in_executor(_executor, reply, "中断...")
        tmux.interrupt()
        await loop.run_in_executor(_executor, reply, "已中断当前操作")

    elif text == "/sessions":
        print(f"[tg] /sessions — listing sessions")
        result = list_sessions()
        await loop.run_in_executor(_executor, reply, result)

    elif text == "/status":
        print(f"[tg] /status")
        status = f"CC 模式: {CC_MODE}\n网络状态: {'🟢 正常' if _net['failures'] < TELEGRAM_DOWN_THRESHOLD else '🔴 异常 (' + str(_net['failures']) + '次连续失败)'}\n代理: {TELEGRAM_PROXY}"
        await loop.run_in_executor(_executor, reply, status)

    elif text.startswith("/sh ") or text.startswith("/sh\n"):
        cmd = text.split("\n", 1)[0] if "\n" in text else text
        cmd = cmd[4:]  # strip "/sh " or "/sh\n"
        # Support multi-line: /sh\ncommand here
        if "\n" in text:
            cmd = text.split("\n", 1)[1]
        cmd = cmd.strip()
        if not cmd:
            await loop.run_in_executor(_executor, reply, "用法: /sh <命令>")
            return True
        print(f"[tg] /sh {cmd[:80]}")
        try:
            proc = subprocess.run(
                ["bash", "-lc", cmd],
                capture_output=True, text=True,
                timeout=120, cwd="/data/whn",
                env={**os.environ, "TERM": "dumb", "CLAUDE_CODE_OFFLINE": ""},
            )
            out = (proc.stdout + proc.stderr).strip()
            if not out:
                out = f"(exit {proc.returncode})"
            if len(out) > 3500:
                out = out[:3500] + "\n\n... (输出过长，已截断)"
            await loop.run_in_executor(_executor, reply, f"```\n{out}\n```")
        except subprocess.TimeoutExpired:
            await loop.run_in_executor(_executor, reply, "命令超时 (120s)")
        except Exception as e:
            await loop.run_in_executor(_executor, reply, f"执行出错: {e}")

    else:
        return False

    return True


# ── message processing ──────────────────────────────────────────────
_CC_SNAPSHOT_DELAY = int(os.environ.get("TELEGRAM_SNAPSHOT_DELAY", "15"))


async def process_message(chat_id: int, prompt: str, sender: str, status_msg_id: int):
    """Run CC and send result back. Sends an interim snapshot if CC takes >15s."""
    loop = asyncio.get_running_loop()
    cc_task = asyncio.create_task(run_claude(prompt))
    snapshot_msg_id = None

    try:
        response = await asyncio.wait_for(asyncio.shield(cc_task), timeout=_CC_SNAPSHOT_DELAY)
    except asyncio.TimeoutError:
        if CC_MODE == "tmux":
            snapshot = get_tmux().get_recent_output(1500)
            snapshot_msg_id = await loop.run_in_executor(
                _executor, send_telegram_message, chat_id,
                f"⏳ 思考中 ({_CC_SNAPSHOT_DELAY}s 快照):\n\n{snapshot}",
            )
        try:
            response = await cc_task
        except Exception as e:
            response = f"CC 执行出错: {e}"
    except Exception as e:
        response = f"CC 执行出错: {e}"

    if not response:
        response = "CC 返回了空内容"

    body = format_reply(prompt, response, sender)
    result_id = await loop.run_in_executor(_executor, send_telegram_message, chat_id, body)

    if result_id is None:
        if status_msg_id is not None:
            await loop.run_in_executor(
                _executor, _tg_post, "editMessageText",
                {"chat_id": chat_id, "message_id": status_msg_id,
                 "text": f"CC 已回复，但发送失败（网络异常）\n\n{body[:1000]}"},
            )
    else:
        if status_msg_id is not None:
            await loop.run_in_executor(
                _executor, _tg_post, "deleteMessage",
                {"chat_id": chat_id, "message_id": status_msg_id},
            )
        if snapshot_msg_id is not None:
            await loop.run_in_executor(
                _executor, _tg_post, "deleteMessage",
                {"chat_id": chat_id, "message_id": snapshot_msg_id},
            )


# ── polling loop ────────────────────────────────────────────────────
async def polling_loop():
    """Poll Telegram API with multi-proxy failover and network status tracking."""
    loop = asyncio.get_running_loop()
    offset = load_polling_offset(TELEGRAM_OFFSET_FILE)

    print(f"[tg] 大狗bot polling started (CC_MODE={CC_MODE}, proxies={TELEGRAM_PROXY})")

    while True:
        try:
            result = await loop.run_in_executor(
                _executor,
                lambda: _tg_get(f"getUpdates?offset={offset}&timeout=2"),
            )
        except Exception as e:
            _net["failures"] += 1
            print(f"[tg] polling exception ({_net['failures']}): {e}")
            if _net["failures"] == TELEGRAM_DOWN_THRESHOLD:
                print("[tg] ⚠️ NETWORK DOWN — will retry silently")
                _net["was_down"] = True
            await asyncio.sleep(TELEGRAM_POLL_INTERVAL)
            continue

        if not result.get("ok"):
            err = result.get("error", "unknown")
            if result.get("_network") or _is_network_error(err):
                _net["failures"] += 1
                if _net["failures"] == TELEGRAM_DOWN_THRESHOLD:
                    print(f"[tg] ⚠️ NETWORK DOWN (consecutive failures: {_net['failures']})")
                    _net["was_down"] = True
            else:
                print(f"[tg] API error: {err}")
            await asyncio.sleep(TELEGRAM_POLL_INTERVAL)
            continue

        # Network OK
        if _net["was_down"] or _net["failures"] >= TELEGRAM_DOWN_THRESHOLD:
            print(f"[tg] 🟢 NETWORK RECOVERED after {_net['failures']} failures")
            if _net["last_chat_id"]:
                await loop.run_in_executor(
                    _executor, send_telegram_message,
                    _net["last_chat_id"],
                    f"🟢 网络已恢复（中断了 {_net['failures']} 次请求）",
                )
        _net["failures"] = 0
        _net["was_down"] = False

        for upd in result.get("result", []):
            update_id = upd.get("update_id")
            if not isinstance(update_id, int) or isinstance(update_id, bool):
                continue
            offset = max(offset, update_id + 1)
            msg = upd.get("message", {})
            text = (msg.get("text") or "").strip()
            chat_id = msg.get("chat", {}).get("id")
            from_user = msg.get("from", {})
            sender = from_user.get("first_name") or from_user.get("username") or str(chat_id)

            _net["last_chat_id"] = chat_id

            if not text or not chat_id:
                continue

            if text == "/start":
                await loop.run_in_executor(
                    _executor, send_telegram_message,
                    chat_id,
                    f"大狗bot 已就绪 🐕\nCC 模式: {CC_MODE}\n代理: {TELEGRAM_PROXY}\n直接发消息交互。",
                )
                continue

            if text.startswith("/"):
                cmd_handled = await handle_command(chat_id, text, loop)
                if cmd_handled:
                    continue

            print(f"[tg] {sender}: {text[:80]}")

            status_result = await loop.run_in_executor(
                _executor, send_telegram_message, chat_id, "思考中...",
            )
            asyncio.create_task(process_message(chat_id, text, sender, status_result))

        if result.get("result"):
            try:
                save_polling_offset(offset, TELEGRAM_OFFSET_FILE)
            except OSError as error:
                # A read-only home directory should not stop message polling.
                print(f"[tg] cannot persist update offset: {error}")

        await asyncio.sleep(TELEGRAM_POLL_INTERVAL)


def main():
    if not TELEGRAM_BOT_TOKEN:
        print("错误: 请设置 TELEGRAM_BOT_TOKEN 环境变量")
        return 1

    print(f"[tg] 大狗bot 启动中 (CC_MODE={CC_MODE})...")

    # Eagerly init tmux if needed
    if CC_MODE == "tmux":
        print("[tg] 预热 tmux session...")
        get_tmux()
        print("[tg] tmux session ready")

    asyncio.run(polling_loop())


if __name__ == "__main__":
    exit(main() or 0)
