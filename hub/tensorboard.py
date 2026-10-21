"""Authenticated per-run TensorBoard processes over a private loopback proxy."""

import socket
import subprocess
import sys
import threading
import time


class TensorBoards:
    def __init__(self, cfg):
        self.cfg = cfg
        self.entries = {}
        self.lock = threading.Lock()

    def url(self, key):
        with self.lock:
            for old, (process, port, seen) in list(self.entries.items()):
                if process.poll() is not None or time.monotonic() - seen > 900:
                    if process.poll() is None:
                        process.terminate()
                    process.wait(timeout=10)
                    del self.entries[old]
            if key in self.entries:
                process, port, _ = self.entries[key]
                self.entries[key] = (process, port, time.monotonic())
                return f"http://127.0.0.1:{port}"
            if len(self.entries) >= 6:
                raise RuntimeError(
                    "Close an unused TensorBoard tab and try again in a few minutes"
                )
            folder = self.cfg.data / "tensorboard" / key
            if not folder.exists() or not list(folder.glob("events.out.tfevents*")):
                raise ValueError(
                    "Training metrics have not arrived yet. Try again after the first iterations."
                )
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            log = (folder / "server.log").open("ab")
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "tensorboard.main",
                    "--logdir",
                    str(folder),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--path_prefix",
                    f"/api/runs/{key}/tensorboard",
                    "--load_fast",
                    "false",
                    "--reload_interval",
                    "5",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            log.close()
            self.entries[key] = (process, port, time.monotonic())
            return f"http://127.0.0.1:{port}"

    def close(self):
        for process, _, _ in self.entries.values():
            if process.poll() is None:
                process.terminate()
        for process, _, _ in self.entries.values():
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
