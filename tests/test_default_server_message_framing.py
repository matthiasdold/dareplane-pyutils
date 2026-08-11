import logging
import socket
import threading
import time

import pytest

from dareplane_utils.default_server.server import DefaultServer
from tests.resources.shared import get_test_thread

PORT = 8082


@pytest.fixture
def server_with_thread_spawning():
    server = DefaultServer(port=PORT)
    stop_event = threading.Event()
    server.init_server(stop_event=stop_event)
    server.pcommand_map = {"STARTTHREAD": get_test_thread}

    stop_event.clear()
    server_thread = threading.Thread(target=server.start_listening)
    server_thread.start()

    yield server

    stop_event.set()
    server_thread.join()
    server.shutdown()


@pytest.fixture
def client():
    c = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    c.connect(("localhost", PORT))
    yield c
    c.close()


def test_command_split_across_packets(server_with_thread_spawning, client):
    """A command fragmented over multiple TCP segments must be reassembled"""
    for fragment in (b"START", b"THR", b"EAD;"):
        client.sendall(fragment)
        time.sleep(0.05)

    time.sleep(0.1)
    assert len(server_with_thread_spawning.threads) == 1


def test_multiple_commands_in_single_packet(server_with_thread_spawning, client):
    """Concatenated commands in one recv must each be handled"""
    client.sendall(b"STARTTHREAD;STARTTHREAD;STARTTHREAD;")

    time.sleep(0.2)
    assert len(server_with_thread_spawning.threads) == 3


def test_incomplete_trailing_command_is_buffered(server_with_thread_spawning, client):
    """A complete command followed by a fragment: only the complete one runs"""
    client.sendall(b"STARTTHREAD;START")
    time.sleep(0.1)
    assert len(server_with_thread_spawning.threads) == 1

    # completing the fragment triggers the second command
    client.sendall(b"THREAD;")
    time.sleep(0.1)
    assert len(server_with_thread_spawning.threads) == 2


def test_empty_commands_are_ignored(server_with_thread_spawning, client):
    """Repeated delimiters and whitespace must not produce warnings/handling"""
    client.sendall(b";;  ;\r\n;STARTTHREAD;")

    time.sleep(0.15)
    assert len(server_with_thread_spawning.threads) == 1


@pytest.fixture
def log_records(server_with_thread_spawning):
    """Capture records directly - the dareplane logger does not propagate to root"""
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = server_with_thread_spawning.logger
    handler = Capture()
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    yield records

    logger.removeHandler(handler)
    logger.setLevel(prev_level)


@pytest.mark.parametrize("up_msg", [b"UP;", b"UP\r\n;", b"UP|;"])
def test_up_is_not_logged(server_with_thread_spawning, client, log_records, up_msg):
    """UP is a periodic health check and must not show up in the logs"""
    client.sendall(up_msg)
    time.sleep(0.15)

    assert not [r for r in log_records if "Received:" in r.getMessage()]


def test_other_pcomms_are_still_logged(server_with_thread_spawning, client, log_records):
    """Only UP is silenced - regular PCOMMS are still logged at INFO"""
    client.sendall(b"STARTTHREAD;")
    time.sleep(0.15)

    received = [r for r in log_records if "Received:" in r.getMessage()]
    assert len(received) == 1
    assert received[0].levelname == "INFO"
