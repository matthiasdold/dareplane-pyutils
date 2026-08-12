import contextlib
import logging
import time

import pytest

from tests.resources.shared import connected_client, running_server


@contextlib.contextmanager
def capture_logs(server):
    """Capture records directly - the dareplane logger does not propagate to root"""
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    logger = server.logger
    handler = Capture()
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)


def test_command_split_across_packets():
    """A command fragmented over multiple TCP segments must be reassembled"""
    with running_server(8083) as server, connected_client(8083) as client:
        for fragment in (b"START", b"THR", b"EAD;"):
            client.sendall(fragment)
            time.sleep(0.05)

        time.sleep(0.1)
        assert len(server.threads) == 1


def test_multiple_commands_in_single_packet():
    """Concatenated commands in one recv must each be handled"""
    with running_server(8084) as server, connected_client(8084) as client:
        client.sendall(b"STARTTHREAD;STARTTHREAD;STARTTHREAD;")

        time.sleep(0.2)
        assert len(server.threads) == 3


def test_incomplete_trailing_command_is_buffered():
    """A complete command followed by a fragment: only the complete one runs"""
    with running_server(8085) as server, connected_client(8085) as client:
        client.sendall(b"STARTTHREAD;START")
        time.sleep(0.1)
        assert len(server.threads) == 1

        # completing the fragment triggers the second command
        client.sendall(b"THREAD;")
        time.sleep(0.1)
        assert len(server.threads) == 2


def test_empty_commands_are_ignored():
    """Repeated delimiters and whitespace must not produce warnings/handling"""
    with running_server(8086) as server, connected_client(8086) as client:
        client.sendall(b";;  ;\r\n;STARTTHREAD;")

        time.sleep(0.15)
        assert len(server.threads) == 1


@pytest.mark.parametrize(
    "up_msg, port", [(b"UP;", 8087), (b"UP\r\n;", 8088), (b"UP|;", 8089)]
)
def test_up_is_not_logged(up_msg, port):
    """UP is a periodic health check and must not show up in the logs"""
    with running_server(port) as server, connected_client(port) as client:
        with capture_logs(server) as log_records:
            client.sendall(up_msg)
            time.sleep(0.15)

            assert not [r for r in log_records if "Received:" in r.getMessage()]


def test_other_pcomms_are_still_logged():
    """Only UP is silenced - regular PCOMMS are still logged at INFO"""
    with running_server(8090) as server, connected_client(8090) as client:
        with capture_logs(server) as log_records:
            client.sendall(b"STARTTHREAD;")
            time.sleep(0.15)

            received = [r for r in log_records if "Received:" in r.getMessage()]
            assert len(received) == 1
            assert received[0].levelname == "INFO"
