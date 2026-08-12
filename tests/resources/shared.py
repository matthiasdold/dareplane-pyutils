# functions shard between test files
import contextlib
import os
import socket
import subprocess
import sys
import threading
import time

from dareplane_utils.default_server.server import DefaultServer

# Teardown grace period. CI runners are slower than a dev machine, so allow an
# override via the environment instead of hardcoding a single value.
SHUTDOWN_TIMEOUT_S = float(os.environ.get("DP_TEST_SHUTDOWN_TIMEOUT_S", "5"))

# Upper bound for wait_until. Only reached when an expectation genuinely fails,
# so it can be generous without slowing down the passing case.
CONDITION_TIMEOUT_S = float(os.environ.get("DP_TEST_CONDITION_TIMEOUT_S", "5"))


def wait_until(predicate, timeout_s: float | None = None, interval_s: float = 0.01):
    """Poll `predicate` until it is truthy, or `timeout_s` elapses.

    Preferred over a fixed ``time.sleep`` before an assertion: it returns as soon
    as the condition holds, so the passing case stays fast, while still tolerating
    a slow CI runner. Returns the predicate's last value, so a caller can assert on
    it directly.

    Parameters
    ----------
    predicate : Callable[[], Any]
        Called repeatedly; polling stops as soon as it returns a truthy value.
    timeout_s : float | None
        Maximum time to wait. Defaults to CONDITION_TIMEOUT_S, settable via
        ``DP_TEST_CONDITION_TIMEOUT_S``.
    interval_s : float
        Delay between polls.
    """
    deadline = time.time() + (
        timeout_s if timeout_s is not None else CONDITION_TIMEOUT_S
    )
    value = predicate()
    while not value and time.time() < deadline:
        time.sleep(interval_s)
        value = predicate()
    return value


@contextlib.contextmanager
def running_server(
    port: int,
    pcommand_map: dict | None = None,
    shutdown_timeout_s: float | None = None,
):
    """Start a DefaultServer listening on `port`, shut it down on exit.

    Parameters
    ----------
    port : int
        Port to bind. Each test should pass its own to avoid collisions.
    pcommand_map : dict | None
        Command map to install; defaults to a single thread-spawning command.
    shutdown_timeout_s : float | None
        Seconds to wait for the server thread to stop. Defaults to
        SHUTDOWN_TIMEOUT_S, settable via ``DP_TEST_SHUTDOWN_TIMEOUT_S``.

    Yields
    ------
    DefaultServer
        The running server instance.
    """
    timeout_s = shutdown_timeout_s if shutdown_timeout_s is not None else SHUTDOWN_TIMEOUT_S
    server = DefaultServer(port=port)
    stop_event = threading.Event()
    server.init_server(stop_event=stop_event)
    server.pcommand_map = pcommand_map or {"STARTTHREAD": get_test_thread}

    # daemon: if teardown ever fails to stop this thread, it must not keep the
    # interpreter alive - CPython joins non-daemon threads without a timeout at
    # exit, which turns a test failure into a hung process
    server_thread = threading.Thread(target=server.start_listening, daemon=True)
    server_thread.start()

    try:
        yield server
    finally:
        # The stop event is sufficient on its own: accept() uses a finite timeout
        # so the listen loop re-checks the flag at least every accept_timeout_s.
        # Closing current_conn additionally unblocks a recv() that is waiting on a
        # still-connected client, which just makes teardown return sooner.
        stop_event.set()
        if server.current_conn:
            server.current_conn.close()
        server_thread.join(timeout=timeout_s)
        alive = server_thread.is_alive()
        server.shutdown()
        if alive:
            raise RuntimeError(
                f"server thread on port {port} did not stop within {timeout_s}s"
            )


@contextlib.contextmanager
def connected_client(port: int, drain_banner: bool = False):
    """Yield a TCP client connected to `port`, closed on exit.

    Parameters
    ----------
    port : int
        Port to connect to.
    drain_banner : bool
        If True, consume the ``Connected to <name>`` greeting the server sends on
        accept. Required before asserting on a command response, otherwise the
        first recv() returns the banner instead of the reply.
    """
    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c.connect(("localhost", port))
    try:
        if drain_banner:
            c.settimeout(2)
            c.recv(1024)
        yield c
    finally:
        c.close()


def get_default_server(port: int = 8080) -> DefaultServer:
    server = DefaultServer(port=port)
    server.init_server()
    return server


def get_test_subprocess() -> subprocess.Popen:
    p = subprocess.Popen([sys.executable, "-m", "tests.resources.infinite_sleep"])
    return p


def get_test_thread() -> subprocess.Popen:
    stop_event = threading.Event()
    # daemon for the same reason as the server thread: a spawned test thread that
    # outlives its stop_event must not block interpreter shutdown
    thread = threading.Thread(
        target=thread_event_interupted_sleep,
        kwargs={"stop_event": stop_event},
        daemon=True,
    )

    return thread, stop_event


def thread_event_interupted_sleep(stop_event: threading.Event):
    while not stop_event.is_set():
        time.sleep(1)
