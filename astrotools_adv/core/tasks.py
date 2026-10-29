"""Run blocking work (network, big computations) off the GUI thread.

Compute in the worker, build/plot Qt and matplotlib objects in the callbacks:
callbacks always run on the GUI thread, ``fn`` never does.
"""
from __future__ import annotations

import traceback
from typing import Any, Callable, List, Optional

from PyQt5.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

_synchronous = False
_alive: List["_Task"] = []  # keeps running tasks (and their signals) referenced


def set_synchronous(flag: bool) -> None:
    """Run tasks inline on the calling thread (used by the test-suite)."""
    global _synchronous
    _synchronous = bool(flag)


class _Signals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(object, str)  # exception, formatted traceback
    finished = pyqtSignal()


class _Task(QRunnable):
    def __init__(self, fn: Callable[..., Any], args: tuple, kwargs: dict) -> None:
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _Signals()

    def run(self) -> None:  # executed in a pool thread
        try:
            value = self.fn(*self.args, **self.kwargs)
        except BaseException as exc:  # noqa: BLE001 - report everything to the GUI
            self.signals.error.emit(exc, traceback.format_exc())
        else:
            self.signals.result.emit(value)
        finally:
            self.signals.finished.emit()


def submit(
    fn: Callable[..., Any],
    *args: Any,
    on_result: Optional[Callable[[Any], None]] = None,
    on_error: Optional[Callable[[BaseException, str], None]] = None,
    on_finished: Optional[Callable[[], None]] = None,
    **kwargs: Any,
) -> None:
    """Run ``fn(*args, **kwargs)`` in the global thread pool.

    Exactly one of ``on_result`` / ``on_error`` fires, then ``on_finished``.
    """
    task = _Task(fn, args, kwargs)
    if on_result:
        task.signals.result.connect(on_result)
    if on_error:
        task.signals.error.connect(on_error)

    def _done() -> None:
        if task in _alive:
            _alive.remove(task)
        if on_finished:
            on_finished()

    task.signals.finished.connect(_done)
    _alive.append(task)
    if _synchronous:
        task.run()
    else:
        QThreadPool.globalInstance().start(task)


def wait_all(timeout_ms: int = 30000) -> bool:
    """Block until every task finished (tests/shutdown)."""
    return QThreadPool.globalInstance().waitForDone(timeout_ms)
