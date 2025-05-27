# A plain event_loop which precisely adheres to timing by using the adjusted sleep_s
import inspect
import time
from dataclasses import dataclass
from threading import Event
from typing import Any, Callable, Optional

from dareplane_utils.general.time import sleep_s


@dataclass
class DelayedCallback:
    """
    Simple auxiliary struct to store a callback and a delay.

    This class is used to store a callback function along with a delay and a start timestamp.
    It is typically used in the context of an event loop to schedule callbacks to be executed
    after a specified delay.

    Attributes
    ----------
    cb : Callable
        The callback function to be executed.
    delay_s : float
        The delay in seconds before the callback is executed relative to `self.start_ts`.
    start_ts : float
        The timestamp when the delay starts. Defaults to the current time.
    """

    cb: Callable
    delay_s: float
    start_ts: float = time.perf_counter()


class EventLoop:
    """
    A class that implements a custom event loop with precise timing.

    The EventLoop uses dareplane_utils.general.time.sleep_s for more precise
    sleep timing at the expense of CPU usage.

    Callbacks are the means of interacting with the event loop. There are two types of callbacks:

    - Periodic callbacks: These are executed at regular intervals.

    - One-time callbacks: These are executed once and then removed from the list of callbacks.
      One-time callback can furthermore be scheduled to run at a specific time in the future.

    Callbacks can be any callable function, which usually gets one argument `ctx` -
    a context object, that can be of type any. This ensures that any type of input can
    be implemented. See the example section for more details.


    Attributes
    ----------
    dt_s : float
        The time interval in seconds between callback executions.
    stop_event : threading.Event
        An event that, when set, signals the event loop to stop.
    last_run_ts : float
        The timestamp of the last callback execution.
    callbacks : list[Callable]
        A list of periodic callback functions.
    callbacks_once : list[Callable]
        A list of one-time callback functions.
    delayed_callbacks_once : list[DelayedCallback]
        A list of delayed one-time callback functions.
    ctx : Any
        A context object that is passed to the callback functions.
    now : float
        The current timestamp as of time.perf_counter(). Used for time keeping internally.


    Examples
    --------
    >>> def no_arg_callback():
    ...     print("Running with no args")
    >>>
    >>> evloop = EventLoop(dt_s=0.1)  # process callbacks every 100ms
    >>> evloop.add_callback_once(lambda ctx: no_arg_callback())
    >>>
    >>> # just to stop the loop after 1s
    >>> evloop.add_delayed_callback_once(cb=lambda ctx: evloop.stop_event.set(), dt=1)
    >>>
    >>> evloop.run()
    Running with no args
    >>>
    >>> # NOTE: This example is left to explain how wrapping works. Creating a wrapper is no longer necessary
    >>> #       if no `ctx` is an arg / kwargs, the event_loop.validate_callback() will automatically create
    >>> #       a wrapper version for you.

    >>> def custom_arg_and_kwarg_callback(a, b=1, c=2):
    ...     print(f"Running with {a=}, {b=}, {c=}")
    >>>
    >>> def wrapped_custom_arg_and_kwargs(ctx: dict):
    ...     custom_arg_and_kwarg_callback(ctx["a"], b=ctx["b"], c=ctx["c"])
    >>>
    >>> evloop = EventLoop(dt_s=0.1, ctx={"a": 11, "b": 22, "c": 33})
    >>> evloop.add_callback_once(wrapped_custom_arg_and_kwargs)
    >>>
    >>> # just to stop the loop after 1s
    >>> evloop.add_delayed_callback_once(cb=lambda ctx: evloop.stop_event.set(), dt=1)
    >>>
    >>> evloop.run()
    Running with a=11, b=22, c=33

    """

    def __init__(
        self, dt_s: float, stop_event: Optional[Event] = None, ctx: Optional[Any] = None
    ):
        """
        Initialize the EventLoop with a specified time interval and optional context.

        Parameters
        ----------
        dt_s : float
            The time interval in seconds between callback executions.
        stop_event : Optional[Event], optional
            An event that, when set, signals the event loop to stop. If not provided, a new Event is created.
        ctx : Optional[Any], optional
            A context object that is passed to the callback functions. Defaults to None. The self.ctx will be
            passed to every callback regardless of value
        """

        self.dt_s = dt_s
        self.stop_event = stop_event if stop_event is not None else Event()
        self.last_run_ts = time.perf_counter()
        self.callbacks = []
        self.callbacks_once = []
        self.delayed_callbacks_once = []
        self.ctx: Any = ctx
        self.now: float = 0.0

    def add_callback(self, cb: Callable):
        """
        Add a periodic callback to the event loop.

        Parameters
        ----------
        cb : Callable
            The callback function to be added.
        """
        cb = self.validate_callback(cb)

        self.callbacks.append(cb)

    def add_callbacks(self, cbs: list[Callable]):
        """
        A convenience function to add multiple periodic callbacks to the event loop.

        Parameters
        ----------
        cbs : list[Callable]
            A list of callback functions to be added.
        """
        for cb in cbs:
            self.add_callback(cb)

    def add_delayed_callback_once(self, cb: Callable, dt: float = 0.0):
        """
        Add a one-time callback to the event loop that is evaluated after a delay.

        Parameters
        ----------
        cb : Callable
            The callback function to be added.
        dt : float, optional
            The delay in seconds before the callback is executed. Defaults to 0.0.
        """

        cb = self.validate_callback(cb)
        dcb = DelayedCallback(cb, dt, time.perf_counter())
        self.delayed_callbacks_once.append(dcb)

    def add_callback_once(self, cb: Callable):
        """
        Add a one-time callback to the event loop.

        Parameters
        ----------
        cb : Callable
            The callback function to be added.
        """

        cb = self.validate_callback(cb)
        self.callbacks_once.append(cb)

    def add_callbacks_once(self, cbs: list[Callable]):
        """
        Convenience function to add multiple one-time callbacks to the event loop.

        Parameters
        ----------
        cbs : list[Callable]
            A list of callback functions to be added.
        """

        for cb in cbs:
            self.add_callback_once(cb)

    def validate_callback(self, cb) -> Callable:
        """
        Check that every callback accepts at least a kwarg with 'ctx'.
        More kwargs are possible.
        """
        assert isinstance(cb, Callable), f"The provided {cb=} is not a Callable"
        spec = inspect.getfullargspec(cb)

        if "ctx" not in spec.args:  # make a context optional
            return lambda ctx: cb()

        return cb

    def run(self):
        """
        Run the event loop, evaluating the callback every `self.dt_s` seconds
        """
        while not self.stop_event.is_set():

            self.now = time.perf_counter()
            dt_last = self.now - self.last_run_ts > self.dt_s
            if dt_last:
                self.process_callbacks()

                # check how much still needed to sleep as the callback processing
                # might have taken significant amount of time
                dt_remaining = max(0, self.dt_s - (self.now - self.last_run_ts))
                self.last_run_ts = self.now

                sleep_s(dt_remaining)
            else:
                sleep_s(self.dt_s - dt_last)

    def process_callbacks(self):

        while self.callbacks_once != []:
            cb = self.callbacks_once.pop(0)
            cb(ctx=self.ctx)

        if self.delayed_callbacks_once != []:
            to_pop = []
            for i, dcb in enumerate(self.delayed_callbacks_once):
                if self.now - dcb.start_ts > dcb.delay_s:
                    dcb.cb(ctx=self.ctx)
                    to_pop.append(i)

            self.delayed_callbacks_once = [
                dcb
                for i, dcb in enumerate(self.delayed_callbacks_once)
                if i not in to_pop
            ]

        for cb in self.callbacks:
            cb(ctx=self.ctx)


if __name__ == "__main__":
    # examples for use of callbacks

    def no_arg_callback():
        print("Running with no args")

    evloop = EventLoop(dt_s=0.1)  # process callbacks every 100ms

    # for a callback with no args we use lambda to blank the callback arg
    evloop.add_callback_once(lambda ctx: no_arg_callback())

    # stop the evloop after 1s
    evloop.add_delayed_callback_once(cb=lambda ctx: evloop.stop_event.set(), dt=1)

    evloop.run()

    def custom_arg_and_kwarg_callback(a, b=1, c=2):
        print(f"Running with {a=}, {b=}, {c=}")

    # reset to showcase the args
    def wrapped_custom_arg_and_kwargs(ctx: dict):
        custom_arg_and_kwarg_callback(ctx["a"], b=ctx["b"], c=ctx["c"])

    evloop = EventLoop(dt_s=0.1, ctx={"a": 11, "b": 22, "c": 33})
    evloop.add_callback_once(wrapped_custom_arg_and_kwargs)
    # stop the evloop after 1s
    evloop.add_delayed_callback_once(cb=lambda ctx: evloop.stop_event.set(), dt=1)
    evloop.run()
