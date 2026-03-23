import sys
import time
from threading import Event

import numpy as np
import pytest

from dareplane_utils.general.event_loop import EventLoop
from dareplane_utils.logging.logger import get_logger

logger = get_logger(
    "dareplane_utils_test", add_console_handler=True, no_socket_handler=True
)
logger.setLevel("DEBUG")

# Windows Python 3.10 has poor timer resolution (~15ms)
# Python 3.11+ significantly improved this
IS_WINDOWS_PY310 = sys.platform == "win32" and sys.version_info[:2] == (3, 10)


def test_adding_non_callable_for_callback():
    ev = EventLoop(dt_s=0.01)
    with pytest.raises(AssertionError):
        ev.add_callback(1)

    with pytest.raises(AssertionError):
        ev.add_callback([1])

    with pytest.raises(AssertionError):
        ev.add_callback({"a": 2})


def test_missing_ctx_kwarg_in_callback():
    ev = EventLoop(dt_s=0.01)

    def test_foo():
        pass

    # should not lead to an error anymore, as we automatically wrap for convenience
    ev.add_callback(test_foo)

    def test_foo_ok(ctx={}):
        pass

    ev.add_callback(test_foo)


@pytest.mark.parametrize("dt_s", [0.001, 0.01, 0.1])
def test_accuracy_of_event_loop_for_different_dt(dt_s):

    buffer = np.zeros(max(100, int(1 / dt_s)))
    stop_event = Event()

    def cb(ctx: dict = {}, stop_event: Event = stop_event):
        buffer[ctx["idx"]] = time.perf_counter()
        ctx["idx"] = ctx["idx"] + 1
        if ctx["idx"] == len(buffer):
            stop_event.set()

    ev = EventLoop(dt_s=dt_s, stop_event=stop_event, ctx={"idx": 0})
    ev.add_callback(cb)

    ev.run()

    dt = np.diff(buffer)
    logger.debug(f"{dt.mean()=}, {dt.std()=}, {np.quantile(dt, [0.01, 0.99])=}")
    accuracy_decimals = 3

    # Windows Python 3.10 has poor timer resolution (~15.6ms minimum)
    # Skip precise timing assertions for this configuration
    if IS_WINDOWS_PY310:
        accuracy_decimals = 2
        if dt_s < 0.01:
            logger.warning(
                f"Skipping precise timing assertion for Windows Python 3.10 with dt_s={dt_s}. "
                f"Got mean={dt.mean():.6f}s instead of {dt_s}s due to poor timer resolution."
            )
            pytest.skip(
                "Windows Python 3.10 has insufficient timer resolution for sub-10ms intervals"
            )

    assert np.round(dt.mean() - dt_s, decimals=accuracy_decimals) == 0
    assert abs(dt.mean() + 3 * dt.std() - dt_s) < dt_s


# TODO: add a test for the delayed callbacks
