import logging
import socket
import threading
from collections import deque

from dareplane_utils.default_server.server import (
    DefaultCallbackServer,
    process_callbacks,
)
from tests.resources.shared import connected_client, running_server, wait_until


def callback_server(port: int):
    return running_server(port, server_cls=DefaultCallbackServer)


def recv_all(client, expected: int) -> bytes:
    """Collect until `expected` bytes arrive - payloads can span several packets"""
    client.settimeout(2)
    buffer = b""
    while len(buffer) < expected:
        try:
            chunk = client.recv(4096)
        except TimeoutError:
            break
        if not chunk:
            break
        buffer += chunk
    return buffer


def test_queued_callbacks_are_sent_to_client():
    """Payloads appended to the stack reach the connected client, in order"""
    with (
        callback_server(8181) as server,
        connected_client(8181, drain_banner=True) as client,
    ):
        wait_until(lambda: server.current_conn is not None)
        for i in range(5):
            server.callback_stack.append(f"cb{i};")

        assert recv_all(client, len(b"cb0;cb1;cb2;cb3;cb4;")) == b"cb0;cb1;cb2;cb3;cb4;"
        assert wait_until(lambda: len(server.callback_stack) == 0)


def test_callback_stack_is_a_deque():
    """append/popleft must stay atomic - a list would race with the send thread"""
    with callback_server(8182) as server:
        assert isinstance(server.callback_stack, deque)


def test_each_connection_gets_its_own_tracked_thread():
    """A literal book keeping key would drop the previous thread on reconnect"""
    with callback_server(8183) as server:
        for _ in range(3):
            with connected_client(8183, drain_banner=True):
                wait_until(lambda: server.current_conn is not None)

        keys = [k for k in server.threads if "callbacks" in k]
        assert len(keys) == 3
        assert len(set(keys)) == 3


def test_callback_threads_are_daemons():
    """A stranded callback thread must never block interpreter shutdown.

    Spawned explicitly from a NON-daemon thread: threading.Thread inherits the
    daemon flag from its creator, so running the server on a daemon thread would
    make this pass regardless of the explicit daemon=True.
    """
    server = DefaultCallbackServer(port=8184)
    stop_event = threading.Event()
    server.init_server(stop_event=stop_event)
    server_thread = threading.Thread(target=server.start_listening, daemon=False)
    server_thread.start()
    try:
        with connected_client(8184, drain_banner=True):
            assert wait_until(lambda: len(server.threads) > 0)
            assert all(thread.daemon for thread, _ in server.threads.values())
    finally:
        stop_event.set()
        if server.current_conn:
            server.current_conn.close()
        server_thread.join(timeout=5)
        server.shutdown()


def test_shutdown_stops_callback_threads():
    """close_threads() must terminate every registered callback thread"""
    with callback_server(8185) as server:
        with connected_client(8185, drain_banner=True):
            assert wait_until(lambda: len(server.threads) > 0)
            threads = [thread for thread, _ in server.threads.values()]

        server.shutdown()
        assert wait_until(lambda: not any(t.is_alive() for t in threads))


def test_closed_connection_stops_thread_without_raising():
    """A send on a socket closed under the thread must end it cleanly, not by traceback.

    Driven without a listen loop: the callback thread is started directly against
    a socket that is then closed, which isolates the send failure from the
    accept()/recv() paths that have their own handling.
    """
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    server = DefaultCallbackServer(port=8186)
    server.logger.addHandler(Capture())
    left, right = socket.socketpair()
    server.current_conn = left

    stop_event = threading.Event()
    thread = threading.Thread(
        target=process_callbacks, args=(server, stop_event), daemon=True
    )
    thread.start()
    try:
        server.callback_stack.append("before;")
        assert wait_until(lambda: right.recv(64) == b"before;")

        # the connection dies under the thread while payloads are queued
        left.close()
        for i in range(20):
            server.callback_stack.append(f"y{i};")

        assert wait_until(lambda: not thread.is_alive())
        assert any("Callback connection lost" in m for m in records)
    finally:
        stop_event.set()
        right.close()
