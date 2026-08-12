import time

from dareplane_utils.logging.logger import get_logger
from tests.resources.shared import connected_client, get_test_thread, running_server

logger = get_logger("testlogger")


# for checking which process is running at a given port, we can use netstat with e.g.
# `netstat -anv -p tcp | grep 8080`

THREAD_PCOMMS = {"STARTTHREAD": get_test_thread}


def test_spawning_thread_from_client():
    with (
        running_server(8091, pcommand_map=THREAD_PCOMMS) as server,
        connected_client(8091) as client,
    ):
        # Send a message to the server to spawn a thread
        client.sendall(b"STARTTHREAD;")

        time.sleep(0.1)
        logger.debug(f"{server.threads=}")

        # the thread should be registerd for book keeping
        assert len(server.threads.keys()) == 1

        client.sendall(b"CLOSE;")


def test_stopping_processes():
    with (
        running_server(8092, pcommand_map=THREAD_PCOMMS) as server,
        connected_client(8092) as client,
    ):
        client.sendall(b"STARTTHREAD;")

        time.sleep(0.1)
        server.close_threads()

        assert len(server.threads.keys()) == 0
        client.sendall(b"CLOSE;")
