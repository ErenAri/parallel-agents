"""QThread wrapper that runs an asyncio coroutine and emits progress signals.

UI code never touches asyncio directly. Use:

    job = AsyncJob(my_coroutine_factory)
    job.progress.connect(handler)
    job.finished_ok.connect(on_done)
    job.failed.connect(on_err)
    job.start()
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from parallel_agents.desktop._qt import QThread, Signal


class AsyncJob(QThread):
    progress = Signal(dict)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, coro_factory: Callable[[], Awaitable[Any]]) -> None:
        super().__init__()
        self._coro_factory = coro_factory

    def run(self) -> None:
        try:
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(self._coro_factory())
            finally:
                loop.close()
            self.finished_ok.emit(result)
        except Exception as exc:  # noqa: BLE001 - surface any failure to UI
            self.failed.emit(f"{type(exc).__name__}: {exc}")
