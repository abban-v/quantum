"""Runtime helpers for calling deep-stack libraries from Streamlit.

Streamlit executes scripts in a worker thread with a small stack. Qiskit's
circuit construction can overflow it (segfault, not an exception). Running the
quantum solve in a dedicated thread with a larger stack avoids that.
"""

from __future__ import annotations

import threading
from typing import Any, Callable, TypeVar

T = TypeVar("T")

DEFAULT_STACK_BYTES = 32 * 1024 * 1024


def run_with_large_stack(
    func: Callable[..., T],
    *args: Any,
    stack_bytes: int = DEFAULT_STACK_BYTES,
    **kwargs: Any,
) -> T:
    """Run ``func`` in a thread with a larger stack and re-raise its error."""
    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def target() -> None:
        try:
            result["value"] = func(*args, **kwargs)
        except BaseException as exc:  # propagate to the caller
            error["value"] = exc

    previous = threading.stack_size()
    threading.stack_size(stack_bytes)
    try:
        thread = threading.Thread(target=target, name="qevr-quantum")
        thread.start()
        thread.join()
    finally:
        threading.stack_size(previous)

    if "value" in error:
        raise error["value"]
    if "value" not in result:
        raise RuntimeError("Threaded call returned no result")
    return result["value"]
