import time
from pathlib import Path
import pytest
import psutil

from dareplane_utils.module_handling.module_connection import ModuleConnection
from dareplane_utils.module_handling.launcher import PythonLauncher
from dareplane_utils.module_handling.communication import (
    Communicator,
    SocketCommunicator,
)


class RecordingCommunicator(Communicator):
    """Communicator capturing what would go on the wire"""

    def __init__(self):
        self.sent: list[bytes] = []

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def send(self, data: bytes) -> None:
        self.sent.append(data)

    def receive(self, size: int) -> bytes:
        return b""


@pytest.mark.parametrize(
    "msg, expected",
    [
        (b"UP", b"UP;"),
        (b"GET_PCOMMS", b"GET_PCOMMS;"),
        (b"STARTTHREAD|param=1", b"STARTTHREAD|param=1;"),
        (b"UP;", b"UP;"),  # already terminated -> unchanged
        (b";", b";"),
    ],
)
def test_send_message_appends_delimiter(msg, expected):
    """The delimiter is required for the server side framing, see DefaultServer.process_connection"""
    communicator = RecordingCommunicator()
    conn = ModuleConnection(
        name="test_connection",
        launcher=PythonLauncher(cwd=Path("."), entry_point="tests.resources.test_server"),
        communicator=communicator,
    )

    conn.send_message(msg)

    assert communicator.sent == [expected]


def test_send_message_without_delimiter_is_handled_by_server():
    """End-to-end: an unterminated message must still reach the server intact"""
    connection = ModuleConnection(
        name="test_connection",
        launcher=PythonLauncher(cwd=Path("."), entry_point="tests.resources.test_server"),
        communicator=SocketCommunicator(name="test_communicator", ip="127.0.0.1", port=8080),
    )

    connection.start()
    time.sleep(2)

    # no trailing b";" -> send_message has to add it, otherwise the server
    # buffers the command and never responds
    connection.send_message(b"UP")
    assert connection.receive_message(size=2048).decode() == "1"

    connection.stop()


def test_module_connection():
    # Create a module connection with the test server as the target
    connection = ModuleConnection(
        name="test_connection",
        launcher=PythonLauncher(cwd=Path("."), entry_point="tests.resources.test_server"),
        communicator=SocketCommunicator(name="test_communicator", ip="127.0.0.1", port=8080),
    )

    connection.start()
    # Wait for the connection to be established
    time.sleep(2)

    # Check that the connection is alive
    pid = connection.launcher.process.pid
    assert pid is not None
    assert connection.launcher.process.poll() is None
    assert connection.communicator.socket_c is not None

    connection.send_message(b"UP")
    response = connection.receive_message(size=2048)
    assert response.decode() == "1"

    # Stop the connection and check that the process is terminated
    connection.stop()
    time.sleep(1)
    assert connection.launcher.process is None

    # Check that the pid is not running anymore
    with pytest.raises(psutil.NoSuchProcess):
        proc = psutil.Process(pid)

        # If the process is still alive, kill it to avoid leaving a dangling process
        proc.kill()

    
def test_module_connection_cleanup():
    # Create a module connection with the test server as the target
    connection = ModuleConnection(
        name="test_connection",
        launcher=PythonLauncher(cwd=Path("."), entry_point="tests.resources.test_server"),
        communicator=SocketCommunicator(name="test_communicator", ip="127.0.0.1", port=8080),
    )

    # Connect
    connection.start()
    time.sleep(2)

    pid = connection.launcher.process.pid
    assert pid is not None
    assert connection.launcher.process.poll() is None

    # Delete the connection object without explicitly stopping it, and check that the process is terminated
    del connection
    time.sleep(1)

    # Check that the pid is not running anymore
    with pytest.raises(psutil.NoSuchProcess):
        proc = psutil.Process(pid)

        # If the process is still alive, kill it to avoid leaving a dangling process
        proc.kill()


def test_python_connection_with_args_and_kwargs():
    port = 8089
    cmd_name = "CONFIGURABLESERVERTEST"

    # Create a module connection with the configurable server as the target, passing in args and kwargs to the launcher
    launcher = PythonLauncher(
        entry_point="tests.resources.configurable_server",
        cwd=Path(__file__).parent.parent,
        args=[str(port), "127.0.0.1"],
        kwargs={"command_name": cmd_name},
    )
    communicator = SocketCommunicator(name="test_communicator", ip="127.0.0.1", port=port)

    conn = ModuleConnection(
        name="test_connection",
        launcher=launcher,
        communicator=communicator,
    )
    conn.start()
    time.sleep(2)

    conn.send_message(b"GET_PCOMMS")
    pcomms = conn.receive_message(size=2048).decode()

    assert cmd_name in pcomms

    conn.stop()