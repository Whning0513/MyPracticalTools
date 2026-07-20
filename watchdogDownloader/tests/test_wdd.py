from __future__ import annotations

import hashlib
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


WDD = Path(__file__).resolve().parents[1] / "wdd"
PAYLOAD = bytes(range(256)) * 2048
UNKNOWN_PAYLOAD = b"unknown-size-response\n" * 1024


class DownloadHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    resume_requests = 0
    range_headers: list[str] = []

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/unknown.bin":
            self.send_response(200)
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(UNKNOWN_PAYLOAD)
            self.close_connection = True
            return
        if self.path != "/resume.bin":
            self.send_error(404)
            return

        type(self).resume_requests += 1
        range_header = self.headers.get("Range")
        if range_header:
            type(self).range_headers.append(range_header)
            offset = int(range_header.removeprefix("bytes=").removesuffix("-"))
            body = PAYLOAD[offset:]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {offset}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True
            return

        self.send_response(200)
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.send_header("Connection", "close")
        self.end_headers()
        cutoff = len(PAYLOAD) // 4
        self.wfile.write(PAYLOAD[:cutoff])
        self.wfile.flush()
        self.connection.shutdown(socket.SHUT_RDWR)
        self.connection.close()
        self.close_connection = True


class WddIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        DownloadHandler.resume_requests = 0
        DownloadHandler.range_headers = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DownloadHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.project = self.root / "project"
        self.output = self.root / "output"
        self.manifest = self.root / "manifest.tsv"
        port = self.server.server_address[1]
        sha = hashlib.sha256(PAYLOAD).hexdigest()
        self.manifest.write_text(
            f"http://127.0.0.1:{port}/resume.bin\tresume.bin\t{len(PAYLOAD)}\t{sha}\n"
            f"http://127.0.0.1:{port}/unknown.bin\tunknown.bin\t0\t\n",
            encoding="utf-8",
        )
        self.run_wdd("init", self.project, self.output, self.manifest)
        with (self.project / ".wdd/config").open("a", encoding="utf-8") as handle:
            handle.write(
                "LOW_SPEED_LIMIT=1\nLOW_SPEED_TIME=5\nMAX_DOWNLOAD_TIME=15\n"
                "CONNECT_TIMEOUT=2\nBACKOFF_SECONDS=0\nCHECK_INTERVAL=1\nSTALL_LIMIT=5\n"
            )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_wdd(self, *args: object, check: bool = True) -> subprocess.CompletedProcess[str]:
        command = [str(WDD), *(str(value) for value in args)]
        try:
            return subprocess.run(
                command, check=check, text=True, capture_output=True, timeout=30,
                env={
                    **os.environ, "TERM": "xterm", "NO_COLOR": "1",
                    "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
                },
            )
        except subprocess.TimeoutExpired as error:
            states = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (self.project / ".wdd/files").glob("*.state")
            )
            self.fail(
                f"command timed out: {command}\nstdout:\n{error.stdout}\n"
                f"stderr:\n{error.stderr}\nstates:\n{states}"
            )

    def state_for(self, file: str) -> dict[str, str]:
        key = hashlib.sha256(file.encode()).hexdigest()
        state = self.project / ".wdd/files" / f"{key}.state"
        return dict(line.split("\t", 1) for line in state.read_text(encoding="utf-8").splitlines())

    def test_interrupted_transfer_resumes_and_unknown_size_requires_success_marker(self) -> None:
        completed = self.run_wdd("run", self.project)
        self.assertIn("complete", completed.stdout)
        self.assertEqual((self.output / "resume.bin").read_bytes(), PAYLOAD)
        self.assertEqual((self.output / "unknown.bin").read_bytes(), UNKNOWN_PAYLOAD)
        resumed = self.state_for("resume.bin")
        unknown = self.state_for("unknown.bin")
        self.assertEqual(resumed["status"], "complete")
        self.assertGreaterEqual(int(resumed["attempts"]), 2)
        self.assertGreater(int(resumed["resume_from"]), 0)
        self.assertEqual(unknown["status"], "complete")
        self.assertTrue(DownloadHandler.range_headers)
        self.assertRegex(DownloadHandler.range_headers[-1], r"^bytes=[1-9][0-9]*-$")
        self.run_wdd("verify", self.project)

        tui = self.run_wdd("tui", self.project, "--once")
        self.assertIn("WATCHDOG DOWNLOADER", tui.stdout)
        self.assertIn("COMPLETE", tui.stdout)
        self.assertIn("resume.bin", tui.stdout)
        self.assertNotIn("\x1b[", tui.stdout)
        self.assertEqual(tui.stderr, "")

    def test_reset_file_quarantines_data_and_can_download_again(self) -> None:
        self.run_wdd("run", self.project)
        self.run_wdd("reset-file", self.project, "resume.bin")
        self.assertFalse((self.output / "resume.bin").exists())
        quarantined = list((self.project / ".wdd/quarantine").glob("*/resume.bin"))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0].read_bytes(), PAYLOAD)
        self.run_wdd("run", self.project)
        self.assertEqual((self.output / "resume.bin").read_bytes(), PAYLOAD)

    def test_pause_is_visible_and_resume_starts_background_services(self) -> None:
        self.run_wdd("pause", self.project)
        paused = self.run_wdd("tui", self.project, "--once")
        self.assertIn("PAUSED", paused.stdout)

        self.run_wdd("resume", self.project)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            verified = self.run_wdd("verify", self.project, check=False)
            if verified.returncode == 0:
                break
            time.sleep(0.1)
        else:
            self.fail("background resume did not complete within 10 seconds")
        self.assertEqual((self.output / "resume.bin").read_bytes(), PAYLOAD)
        self.assertEqual((self.output / "unknown.bin").read_bytes(), UNKNOWN_PAYLOAD)
        self.run_wdd("stop", self.project, check=False)

    def test_manifest_cannot_escape_output_directory(self) -> None:
        bad_manifest = self.root / "bad.tsv"
        bad_manifest.write_text("https://example.invalid/x\t../escape.bin\t10\t\n", encoding="utf-8")
        bad_project = self.root / "bad-project"
        self.run_wdd("init", bad_project, self.output, bad_manifest)
        completed = self.run_wdd("run", bad_project, check=False)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("must stay below OUT_DIR", completed.stderr)

    def test_terminal_checksum_failure_is_visible(self) -> None:
        lines = self.manifest.read_text(encoding="utf-8").splitlines()
        fields = lines[0].split("\t")
        fields[3] = "0" * 64
        lines[0] = "\t".join(fields)
        self.manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")

        completed = self.run_wdd("run", self.project, check=False)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(self.state_for("resume.bin")["status"], "failed")
        tui = self.run_wdd("tui", self.project, "--once")
        self.assertIn("FAILED", tui.stdout)
        self.assertIn("reset-file", tui.stdout)

    def test_unknown_size_only_project_is_complete_for_watchdog(self) -> None:
        port = self.server.server_address[1]
        manifest = self.root / "unknown-only.tsv"
        manifest.write_text(
            f"http://127.0.0.1:{port}/unknown.bin\tunknown.bin\t0\t\n",
            encoding="utf-8",
        )
        project = self.root / "unknown-project"
        output = self.root / "unknown-output"
        self.run_wdd("init", project, output, manifest)
        self.run_wdd("run", project)
        watchdog = self.run_wdd("watchdog", project)
        self.assertIn("complete", watchdog.stdout)


if __name__ == "__main__":
    unittest.main()
