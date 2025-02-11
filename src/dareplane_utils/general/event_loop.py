# A plain event_loop which precisely adheres to timing by using the adjusted sleep_s
import inspect
import time
from threading import Event
from typing import Any, Callable

from dareplane_utils.general.time import sleep_s


class EventLoop:
    def __init__(self, dt_s: float, stop_event: Event = Event(), ctx: Any = None):
        self.dt_s = dt_s
        self.stop_event = stop_event
        self.last_run_ts = time.perf_counter()
        self.callbacks = []
        self.callbacks_once = []
        self.ctx: Any = ctx

    def add_callback(self, cb: Callable):
        self.validate_callback(cb)
        self.callbacks.append(cb)

    def add_callbacks(self, cbs: list[Callable]):
        for cb in cbs:
            self.add_callback(cb)

    def add_callback_once(self, cb: Callable):
        self.validate_callback(cb)
        self.callbacks_once.append(cb)

    def add_callbacks_once(self, cbs: list[Callable]):
        for cb in cbs:
            self.add_callback_once(cb)

    def validate_callback(self, cb):
        """Check that every callback accepts at least a kwarg with 'ctx'"""
        assert isinstance(cb, Callable), f"The provided {cb=} is not a Callable"
        spec = inspect.getfullargspec(cb)
        assert "ctx" in spec.args, f"Callback {cb=} requires at least one `ctx` kwarg"

    def run(self):
        while not self.stop_event.is_set():
            self.process_callbacks()
            now = time.perf_counter()
            dt_remaining = min(0, self.dt_s - (now - self.last_run_ts))
            sleep_s(dt_remaining)
            self.last_run_ts = now

    def process_callbacks(self):

        while self.callbacks_once != []:
            cb = self.callbacks_once.pop(0)
            cb(ctx=self.ctx)

        for cb in self.callbacks:
            cb(ctx=self.ctx)
