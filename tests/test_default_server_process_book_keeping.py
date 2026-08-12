import sys
import time

import psutil

from dareplane_utils.logging.logger import get_logger
from tests.resources.shared import connected_client, get_test_subprocess, running_server

logger = get_logger("testlogger")
logger.setLevel("DEBUG")

# Platform-specific timeout for process operations
IS_WINDOWS = sys.platform == "win32"
PROCESS_TIMEOUT = 2.0 if IS_WINDOWS else 1.0

# for checking which process is running at a given port, we can use netstat with e.g.
# `netstat -anv -p tcp | grep 8080`

PROCESS_PCOMMS = {"STARTPROCESS": get_test_subprocess}


def test_spawning_processes_from_client():
    with (
        running_server(8093, pcommand_map=PROCESS_PCOMMS) as server,
        connected_client(8093) as client,
    ):
        time.sleep(0.2 if IS_WINDOWS else 0.1)

        logger.debug("Sending STARTPROCESS")
        client.sendall(b"STARTPROCESS;")
        time.sleep(0.2 if IS_WINDOWS else 0.1)

        logger.debug(f"{server.processes=}")

        # the process should be registerd for book keeping
        assert len(server.processes.keys()) == 1

        client.sendall(b"CLOSE;")


def test_stopping_processes():
    with (
        running_server(8094, pcommand_map=PROCESS_PCOMMS) as server,
        connected_client(8094) as client,
    ):
        client.sendall(b"STARTPROCESS;")

        # the process should be registerd for book keeping
        time.sleep(0.2 if IS_WINDOWS else 0.1)  # allow for thread to spawn
        subp = next(iter(server.processes.values()))

        server.close_processes()

        # Give Windows more time to terminate processes
        time.sleep(PROCESS_TIMEOUT)

        assert len(server.processes.keys()) == 0

        # Validate that the process was killed by checking the children
        try:
            parent_ps = psutil.Process(subp.pid)
            assert parent_ps.children() == []
        except psutil.NoSuchProcess:
            # Process already terminated - this is fine
            pass

        client.sendall(b"CLOSE;")
