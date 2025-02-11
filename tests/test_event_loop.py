import time
from threading import Event

import numpy as np
import pytest

from dareplane_utils.general.event_loop import EventLoop
from dareplane_utils.logging import get_logger


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

    with pytest.raises(AssertionError):
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

    assert np.allclose(dt.mean() + 3 * dt.std(), dt_s, atol=dt_s)
