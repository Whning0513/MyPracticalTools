"""
Shared CC invocation logic — used by both bridge.py and telegram_bridge.py.

Supports two modes (set via CC_MODE env var):
  print  — stateless: `claude -p` per message
  tmux   — stateful: persistent CC in tmux, context carries over
"""
import os
import re
import time
import asyncio
import subprocess

from .sender import DingTalkSender, get_dingtalk_credentials

# ── config ──────────────────────────────────────────────────────────
CC_MODE = os.environ.get("CC_MODE", "print")
CC_TIMEOUT = int(os.environ.get("CC_TIMEOUT", "180"))
CC_MAX_LEN = int(os.environ.get("CC_MAX_RESPONSE_LENGTH", "3500"))
TMUX_SESSION = os.environ.get("TMUX_CC_SESSION", "cc-bridge")
TMUX_CWD = os.environ.get("TMUX_CWD", "/data/whn")

_sender: DingTalkSender | None = None


def get_sender() -> DingTalkSender:
    """Lazily construct the DingTalk sender after configuration is present."""

    global _sender
    if _sender is None:
        _sender = DingTalkSender(*get_dingtalk_credentials())
    return _sender

_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_AT_RE = re.compile(r"@\S+\s*")
_BOX_RE = re.compile(r"[─-╿]+")


# ── helpers ─────────────────────────────────────────────────────────
def simplify_tables(text: str) -> str:
    """Collapse box-drawing sequences: >10 chars → newline, ≤10 → two spaces."""
    def _repl(m: re.Match) -> str:
        return "\n" if len(m.group()) > 10 else "  "
    return _BOX_RE.sub(_repl, text)


def strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def strip_at_mention(text: str) -> str:
    """Remove leading @botName mention from DingTalk/Telegram message."""
    return _AT_RE.sub("", text, count=1).strip()


# ── tmux session ────────────────────────────────────────────────────
class TmuxSession:
    """Persistent CC process inside a tmux session.

    Sends messages via send-keys, detects completion by polling
    capture-pane until the output stabilises."""

    def __init__(self, name: str = TMUX_SESSION, cwd: str = TMUX_CWD):
        self.name = name
        self.cwd = cwd
        self._lock = asyncio.Lock()
        self._ensure()

    def _ensure(self):
        """Create the tmux session if it doesn't already exist."""
        r = subprocess.run(
            ["tmux", "has-session", "-t", self.name], capture_output=True,
        )
        if r.returncode == 0:
            return  # already running

        subprocess.run(
            ["tmux", "new-session", "-d", "-s", self.name,
             "-c", self.cwd, "-x", "200", "-y", "50"],
            check=True,
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, "claude", "Enter"],
            check=True,
        )
        time.sleep(3)  # give CC time to boot

    def _capture(self) -> str:
        r = subprocess.run(
            ["tmux", "capture-pane", "-t", self.name, "-p", "-S", "-500"],
            capture_output=True, text=True,
        )
        return r.stdout

    def _send_keys(self, message: str):
        """Send literal text + Enter to the tmux session."""
        subprocess.run(
            ["tmux", "send-keys", "-l", "-t", self.name, message],
            check=True,
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, "Enter"],
            check=True,
        )

    @staticmethod
    def _diff(before: str, after: str) -> str:
        """Return new content in *after* not present in *before*.

        Walks backward from the end to find the common suffix, then returns
        the lines in 'after' that sit between the old prefix and that suffix.
        Handles send-keys -l modifying the prompt line in-place."""
        if not before:
            return after.strip()
        if before in after:
            idx = after.index(before)
            return after[idx + len(before):].strip()

        b_lines = before.splitlines()
        a_lines = after.splitlines()

        # Walk backward to find common suffix
        common = 0
        for i in range(1, min(len(b_lines), len(a_lines)) + 1):
            if b_lines[-i] == a_lines[-i]:
                common += 1
            else:
                break

        new_start = len(b_lines) - common
        new_end = len(a_lines) - common
        if new_end > new_start:
            return "\n".join(a_lines[new_start:new_end]).strip()
        return ""

    async def send(self, message: str, timeout: int = CC_TIMEOUT) -> str:
        """Send a message to the persistent CC and wait for the reply."""
        async with self._lock:
            before = strip_ansi(self._capture())
            self._send_keys(message)
            await asyncio.sleep(2)

            last = strip_ansi(self._capture())
            stable = 0
            deadline = time.time() + timeout

            while time.time() < deadline:
                await asyncio.sleep(2)
                current = strip_ansi(self._capture())
                if current == last:
                    stable += 1
                    if stable >= 3:
                        break
                else:
                    stable = 0
                    last = current

            after = strip_ansi(self._capture())
            result = self._diff(before, after)
            return result if result else "(CC 未产生新输出)"

    # ── session control ───────────────────────────────────────────
    def interrupt(self):
        """Send Ctrl+C to interrupt whatever CC is doing."""
        subprocess.run(
            ["tmux", "send-keys", "-t", self.name, "C-c"],
            check=True,
        )

    async def restart_cc(self, resume_id: str = ""):
        """Exit current CC, start a fresh (or resumed) one."""
        async with self._lock:
            self.interrupt()
            await asyncio.sleep(1.5)

            # Send /exit to CC
            subprocess.run(
                ["tmux", "send-keys", "-l", "-t", self.name, "/exit"],
                check=True,
            )
            subprocess.run(
                ["tmux", "send-keys", "-t", self.name, "Enter"],
                check=True,
            )
            await asyncio.sleep(4)  # wait for CC to fully exit

            # Start new CC
            if resume_id:
                cmd = f"claude --resume {resume_id}"
            else:
                cmd = "claude"
            subprocess.run(
                ["tmux", "send-keys", "-l", "-t", self.name, cmd],
                check=True,
            )
            subprocess.run(
                ["tmux", "send-keys", "-t", self.name, "Enter"],
                check=True,
            )
            await asyncio.sleep(3)  # wait for CC to boot

    async def resume_last(self):
        """Exit CC and resume the most recent session."""
        await self.restart_cc(resume_id="--last")

    async def resume_last_with_context(self) -> str:
        """Exit CC, resume last session, and return recent conversation context."""
        await self.restart_cc(resume_id="--last")
        return self.get_recent_output()

    async def exit_cc(self):
        """Exit CC (stay at shell prompt)."""
        async with self._lock:
            self.interrupt()
            await asyncio.sleep(1.5)
            subprocess.run(
                ["tmux", "send-keys", "-l", "-t", self.name, "/exit"],
                check=True,
            )
            subprocess.run(
                ["tmux", "send-keys", "-t", self.name, "Enter"],
                check=True,
            )

    def get_recent_output(self, max_chars: int = 2000) -> str:
        """Capture the pane and return the tail (~last N chars) of visible content."""
        raw = self._capture()
        clean = strip_ansi(raw).strip()
        if len(clean) > max_chars:
            clean = "...\n" + clean[-max_chars:]
        return clean


def _session_id_from_file(filename: str) -> str | None:
    """Given a session filename (PID), return the real sessionId (UUID)."""
    import json as _json
    sessions_dir = os.path.expanduser("~/.claude/sessions")
    path = os.path.join(sessions_dir, filename)
    if not os.path.isfile(path):
        return None
    try:
        with open(path) as fp:
            d = _json.load(fp)
        return d.get("sessionId")
    except Exception:
        return None


def _session_files(limit: int | None = None) -> list[str]:
    """Return session files in the same newest-first order shown to users."""

    sessions_dir = os.path.expanduser("~/.claude/sessions")
    if not os.path.isdir(sessions_dir):
        return []
    files = sorted(
        [f for f in os.listdir(sessions_dir) if f.endswith(".json")],
        key=lambda f: os.path.getmtime(os.path.join(sessions_dir, f)),
        reverse=True,
    )
    return files if limit is None else files[:limit]


def set_session_title(title: str) -> bool:
    """Rename the most recently modified CC session to *title*."""
    import json as _json
    sessions_dir = os.path.expanduser("~/.claude/sessions")
    if not os.path.isdir(sessions_dir):
        return False
    files = sorted(
        [f for f in os.listdir(sessions_dir) if f.endswith(".json")],
        key=lambda f: os.path.getmtime(os.path.join(sessions_dir, f)),
        reverse=True,
    )
    if not files:
        return False
    path = os.path.join(sessions_dir, files[0])
    try:
        with open(path) as fp:
            d = _json.load(fp)
        d["name"] = title
        with open(path, "w") as fp:
            _json.dump(d, fp, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def resolve_session_id(user_input: str) -> str | None:
    """Convert user input to a real CC sessionId (UUID).
    Accepts: numeric PID, short PID prefix, or full UUID."""
    import json as _json
    sessions_dir = os.path.expanduser("~/.claude/sessions")
    if not os.path.isdir(sessions_dir):
        return None

    # If it looks like a UUID (contains dashes), use as-is
    if "-" in user_input and len(user_input) > 20:
        return user_input

    files = _session_files()

    # Numeric input is the index shown by /sessions when it points to one.
    if user_input.isdigit():
        index = int(user_input)
        if 1 <= index <= len(files):
            session_id = _session_id_from_file(files[index - 1])
            if session_id:
                return session_id

    # Otherwise treat it as a PID/filename prefix and look up the UUID.
    for f in files:
        if not f.endswith(".json"):
            continue
        pid = f[:-5]
        if pid == user_input or pid.startswith(user_input):
            sid = _session_id_from_file(f)
            if sid:
                return sid

    # Try direct filename lookup
    filename = f"{user_input}.json"
    sid = _session_id_from_file(filename)
    if sid:
        return sid

    return None


def list_sessions() -> str:
    """Read ~/.claude/sessions/*.json and return a formatted session list."""
    import json as _json
    import time as _time

    sessions_dir = os.path.expanduser("~/.claude/sessions")
    if not os.path.isdir(sessions_dir):
        return "(无会话记录)"

    files = _session_files(limit=15)

    if not files:
        return "(无会话记录)"

    lines = ["最近 15 个会话 (回复 `/resume <编号>` 或 `/resume <PID>`):\n"]
    for i, f in enumerate(files, 1):
        path = os.path.join(sessions_dir, f)
        try:
            with open(path) as fp:
                d = _json.load(fp)
        except Exception:
            continue
        pid = f[:-5]
        mtime = os.path.getmtime(path)
        t = _time.strftime("%m-%d %H:%M", _time.localtime(mtime))
        name = d.get("name", "") or "(无标题)"
        if len(name) > 25:
            name = name[:25] + "..."
        status = d.get("status", "")
        lines.append(f"#{i}  `{pid}`  {t}  [{status}]  {name}")
    return "\n".join(lines)


# Singleton
_tmux: TmuxSession | None = None


def get_tmux() -> TmuxSession:
    global _tmux
    if _tmux is None:
        _tmux = TmuxSession()
    return _tmux


# ── CC invocation ───────────────────────────────────────────────────
async def run_claude_print(prompt: str) -> str:
    """Stateless: `claude -p` per message."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=CC_TIMEOUT,
        )
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            return f"CC 异常退出 (exit {proc.returncode})\n\n```\n{err[:1000]}\n```"
        return strip_ansi(stdout.decode("utf-8", errors="replace")).strip()
    except asyncio.TimeoutError:
        return f"CC 查询超时 ({CC_TIMEOUT}s)"
    except FileNotFoundError:
        return "未找到 claude 命令，请确认 CC 已安装并位于 PATH 中"


async def run_claude(prompt: str) -> str:
    raw = await get_tmux().send(prompt) if CC_MODE == "tmux" else await run_claude_print(prompt)
    return simplify_tables(raw)


# ── reply formatting ────────────────────────────────────────────────
def format_reply(prompt: str, response: str, sender_nick: str = "") -> str:
    """Format CC response as a plain-text reply (suitable for Telegram / DingTalk)."""
    quoted = prompt[:200].replace("\n", " ")
    mode_tag = "[tmux]" if CC_MODE == "tmux" else ""
    body = f"> 提问{mode_tag}: {quoted}\n\n{response}"
    if sender_nick:
        body += f"\n\n---\n回复 @{sender_nick}"
    if len(body) > CC_MAX_LEN:
        body = body[:CC_MAX_LEN - 30] + "\n\n... (消息过长，已截断)"
    return body
