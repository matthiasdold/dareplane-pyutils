# functions shard between test files
import contextlib
import socket
import subprocess
import sys
import threading
import time

from dareplane_utils.default_server.server import DefaultServer


@contextlib.contextmanager
def running_server(port: int, pcommand_map: dict | None = None):
    """Start a DefaultServer listening on `port`, shut it down on exit.

    Parameters
    ----------
    port : int
        Port to bind. Each test should pass its own to avoid collisions.
    pcommand_map : dict | None
        Command map to install; defaults to a single thread-spawning command.

    Yields
    ------
    DefaultServer
        The running server instance.
    """
    server = DefaultServer(port=port)
    stop_event = threading.Event()
    server.init_server(stop_event=stop_event)
    server.pcommand_map = pcommand_map or {"STARTTHREAD": get_test_thread}

    server_thread = threading.Thread(target=server.start_listening)
    server_thread.start()

    try:
        yield server
    finally:
        stop_event.set()
        server_thread.join()
        server.shutdown()


@contextlib.contextmanager
def connected_client(port: int):
    """Yield a TCP client connected to `port`, closed on exit."""
    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c.connect(("localhost", port))
    try:
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
