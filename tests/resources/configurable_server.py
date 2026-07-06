# A server implementation for testing purposes only

import threading
import argparse

from dareplane_utils.default_server.server import DefaultServer
from dareplane_utils.logging.logger import get_logger
from fire import Fire

logger = get_logger("testlogger")
logger.setLevel(10)

def run_server(
    port: int = 8080,
    ip: str = "127.0.0.1",
    loglevel: int = 10,
    command_name: str = "TEST",
    stop_event: threading.Event = threading.Event(),
):
    logger.setLevel(loglevel)

    pcommand_map = {
        "GET_PCOMMS": "START|INIT|STOP|RUN_BLOCK",
        command_name: lambda: print(f"{command_name} received."),
    }

    server = DefaultServer(port=port, ip=ip, pcommand_map=pcommand_map, name="control_room")

    # initialize to start the socket
    server.init_server(stop_event=stop_event)
    # start processing of the server
    logger.info("Server will start listening")
    server.start_listening()

    return 0

if __name__ == "__main__":
    Fire(run_server)