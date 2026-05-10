from __future__ import annotations

import os
import sys
import threading
from typing import Any


class Spinner:
    FRAMES = [
        "⠋",
        "⠙",
        "⠚",
        "⠞",
        "⠖",
        "⠦",
        "⠴",
        "⠲",
        "⠳",
        "⠓",
    ]
    INTERVAL_SECONDS = 0.1
    START_DELAY_SECONDS = 0.15
    SPINNER_COLOR = "\033[38;2;71;136;208m"
    DONE_COLOR = "\033[38;2;71;136;208m"
    FAIL_COLOR = "\033[31m"
    RESET = "\033[0m"

    def __init__(
        self,
        message: str,
        stream: Any | None = None,
        enabled: bool | None = None,
        no_color: bool | None = None,
    ) -> None:
        self.message = message
        self.stream = stream or sys.stderr
        self.enabled = bool(enabled if enabled is not None else hasattr(self.stream, "isatty") and self.stream.isatty())
        self.no_color = bool(no_color) if no_color is not None else bool(os.getenv("NO_COLOR") or os.getenv("NO_COLOUR"))
        self._done = threading.Event()
        self._thread: threading.Thread | None = None
        self._index = 0
        self._rendered = False
        self._lock = threading.Lock()

    def _write(self, text: str) -> None:
        with self._lock:
            self.stream.write(text)
            self.stream.flush()

    def _clear(self) -> None:
        self._write("\r\033[2K")

    def _colorize(self, text: str, color: str) -> str:
        if self.no_color or not self.enabled:
            return text
        return f"{color}{text}{self.RESET}"

    def _frame(self) -> str:
        frame = self.FRAMES[self._index]
        self._index = (self._index + 1) % len(self.FRAMES)
        return self._colorize(frame, self.SPINNER_COLOR)

    def _render(self) -> None:
        self._rendered = True
        self._write(f"\r\033[2K{self._frame()} {self.message}")

    def _run(self) -> None:
        if self._done.wait(self.START_DELAY_SECONDS):
            return
        self._clear()
        self._render()
        while not self._done.wait(self.INTERVAL_SECONDS):
            self._render()

    def __enter__(self) -> "Spinner":
        if not self.enabled:
            return self
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if not self.enabled:
            return
        self._done.set()
        if self._thread is not None:
            self._thread.join(timeout=0.2)
        if self._rendered:
            status = "done" if exc is None else "failed"
            color = self.DONE_COLOR if exc is None else self.FAIL_COLOR
            self._write(f"\r\033[2K{self._colorize(status, color)} {self.message}\n")
