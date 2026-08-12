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

    server_thread = threading.Thread(target=server.start_listening)
    server_thread.start()

    try:
        yield server
    finally:
        # Setting the stop event alone is not enough: the loop is parked in a
        # blocking accept()/recv() and only re-checks the flag once those return.
        # Closing the sockets is what actually breaks out of them, so it has to
        # happen before the join rather than in shutdown() afterwards. Both are
        # needed - server_socket unblocks accept(), current_conn unblocks recv()
        # for a client that is still connected.
        stop_event.set()
        if server.current_conn:
            server.current_conn.close()
        if server.server_socket:
            server.server_socket.close()
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
    thread = threading.Thread(
        target=thread_event_interupted_sleep, kwargs={"stop_event": stop_event}
    )

    return thread, stop_event


def thread_event_interupted_sleep(stop_event: threading.Event):
    while not stop_event.is_set():
        time.sleep(1)
