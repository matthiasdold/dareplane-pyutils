import time
from pathlib import Path
import subprocess
import pytest
import psutil
import os

from dareplane_utils.module_handling.module_connection import ModuleConnection
from dareplane_utils.module_handling.launcher import PythonLauncher
from dareplane_utils.module_handling.communication import SocketCommunicator


def test_module_connection():
    # Create a module connection with the test server as the target
    connection = ModuleConnection(
        name="test_connection",
        launcher=PythonLauncher(cwd=Path("."), entry_point="tests.resources.tserver"),
        communicator=SocketCommunicator(name="test_communicator", ip="127.0.0.1", port=8080),
    )

    connection.start()
    # Wait for the connection to be established
    time.sleep(2)

    # Check that the connection is alive
    pid = connection.process.pid
    assert pid is not None
    assert connection.process.poll() is None
    assert connection.communicator.socket_c is not None

    connection.send_message(b"UP")
    response = connection.receive_message(size=2048)
    assert response.decode() == "1"

    # Stop the connection and check that the process is terminated
    connection.stop()
    time.sleep(1)
    assert connection.process is None

    # Check that the pid is not running anymore
    with pytest.raises(psutil.NoSuchProcess):
        proc = psutil.Process(pid)

        # If the process is still alive, kill it to avoid leaving a dangling process
        proc.kill()

    
def test_module_connection_cleanup():
    # Create a module connection with the test server as the target
    connection = ModuleConnection(
        name="test_connection",
        launcher=PythonLauncher(cwd=Path("."), entry_point="tests.resources.tserver"),
        communicator=SocketCommunicator(name="test_communicator", ip="127.0.0.1", port=8080),
    )

    # Connect
    connection.start()
    time.sleep(2)

    pid = connection.process.pid
    assert pid is not None
    assert connection.process.poll() is None

    # Delete the connection object without explicitly stopping it, and check that the process is terminated
    del connection
    time.sleep(1)

    # Check that the pid is not running anymore
    with pytest.raises(psutil.NoSuchProcess):
        proc = psutil.Process(pid)

        # If the process is still alive, kill it to avoid leaving a dangling process
        proc.kill()