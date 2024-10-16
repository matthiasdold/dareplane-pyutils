import pytest
import time
import socket
import psutil
import threading

from tests.resources.shared import get_test_subprocess

from dareplane_utils.default_server.server import DefaultServer
from dareplane_utils.logging.logger import get_logger

logger = get_logger("testlogger")

# for checking which process is running at a given port, we can use netstat with e.g.
# `netstat -anv -p tcp | grep 8080`


@pytest.fixture
def get_default_server_with_process_spawning():
    # Init the server
    server = DefaultServer(port=8080)
    stop_event = threading.Event()
    server.init_server(stop_event=stop_event)

    # Add process creation capabilities
    pcommand_map = {"STARTPROCESS": get_test_subprocess}
    server.pcommand_map = pcommand_map

    # Run the servers processing in a separate thread
    stop_event.clear()  # in case it was set before
    server_thread = threading.Thread(target=server.start_listening)
    server_thread.start()

    yield server_thread, stop_event, server

    # Teardown
    stop_event.set()
    server_thread.join()
    server.shutdown()


def test_spawning_processes_from_client(
    get_default_server_with_process_spawning,
):
    server_thread, stop_event, server = get_default_server_with_process_spawning

    # Send a message to the server to spawn a process
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("localhost", 8080))
    client.sendall(b"STARTPROCESS")

    time.sleep(0.1)
    logger.debug(f"{server.processes=}")

    # the process should be registerd for book keeping
    assert len(server.processes.keys()) == 1

    client.sendall(b"CLOSE")
    client.close()


def test_stopping_processes(get_default_server_with_process_spawning):
    server_thread, stop_event, server = get_default_server_with_process_spawning

    # Send a message to the server to spawn a process
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(("localhost", 8080))
    client.sendall(b"STARTPROCESS")

    # the process should be registerd for book keeping
    time.sleep(0.1)  # allow for thread to process command and spawn
    subp = list(server.processes.values())[0]
    # print(f"{subp=}")
    # print(f"{psutil.Process(subp).children()=}")

    server.close_processes()

    assert len(server.processes.keys()) == 0

    # Validate that the process was killed by checking the children
    parent_ps = psutil.Process(subp.pid)
    assert parent_ps.children() == []
    client.sendall(b"CLOSE")
    client.close()
