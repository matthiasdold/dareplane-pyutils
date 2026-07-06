import subprocess
import sys
import threading
import time
from typing import Iterator

import pytest
import socket

from dareplane_utils.logging.logger import get_logger
from dareplane_utils.module_handling.communication import SocketCommunicator

logger = get_logger("testlogger", add_console_handler=True, no_socket_handler=True)
logger.setLevel(10)

def wait_for_port(host: str = "127.0.0.1", port: int = 9020, timeout: float = 5.0):
    """Wait until a port is open on the given host, or timeout."""
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with socket.socket() as s:
                s.settimeout(0.5)
                s.connect((host, port))
                s.close()
                return True
        except OSError as e:
            last_err = e
            time.sleep(0.5)
    raise TimeoutError(f"Port {host}:{port} not ready: {last_err}")

@pytest.fixture
def server_process() -> Iterator[subprocess.Popen]:
    proc = subprocess.Popen(
        [sys.executable, "-m", "tests.resources.test_server"],
    )
    # Wait for the server to be ready
    try:
        wait_for_port(port=8080)
    except TimeoutError as e:
        proc.terminate()
        raise RuntimeError("Server failed to start") from e
    
    yield proc

    # Teardown
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

def test_connection_to_server(server_process):
    proc = server_process
    # Connect to the server and send a command
    sc = SocketCommunicator(ip = "127.0.0.1", port = 8080, name="test")
    sc.connect()

    assert sc.socket_c is not None

    sc.socket_c.settimeout(2)  # Set a timeout for receiving data

    sc.send(b"UP")
    response = sc.receive(2048).decode()

    assert response == "1", f"Expected response '1' but got {response}"
      

@pytest.fixture
def slow_server_process() -> Iterator[subprocess.Popen]:
    proc = subprocess.Popen(
        [sys.executable, "-m", "tests.resources.slow_test_server"],
    )
    
    yield proc

    # Teardown
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_retry_connection_after_s_for_slow_startup(slow_server_process):
    proc = slow_server_process

    # Quick connection should fail
    with pytest.raises(OSError):
        sc = SocketCommunicator(ip="127.0.0.1", port=8081, name="test_slow", max_connect_retries=0)
        sc.connect()

    # slow start-up takes 5 seconds -> 3 seconds for retry with 3 retries should be enough
    sc = SocketCommunicator(ip="127.0.0.1", port=8081, name="test_slow", max_connect_retries=3, retry_after_s=3)


    sc.connect()
    assert sc.socket_c is not None

    time.sleep(0.5)  # wait a bit to ensure response arrived

    sc.send(b"GET_PCOMMS")
    pcoms = sc.receive(2048).decode("utf-8")
    assert pcoms is not None, "Did not receive any response from the server"
    assert "SLOWSERVERTEST" in pcoms, (
        f"Did not get the expected pcomms from the server - {pcoms=}"
    )
