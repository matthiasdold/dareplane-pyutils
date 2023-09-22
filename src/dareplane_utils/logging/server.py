import logging
import select
import socketserver
import struct
from pathlib import Path

import ujson
from fire import Fire

from dareplane_utils.logging.logger import default_dareplane_config

# NOTE: For a usuall dareplane setup, we will not have more than one
# instance of a LogRecordSocketReceiver, which is usually managed via the
# control room module. It is still included here next to the logger and the
# ujson_socket_handler, as it is required for unit testing and would allow
# an easier testing of multiple modules (still logging to a single file)
# if the control room would not be used.


# Basically taken from here: https://docs.python.org/2/howto/logging-cookbook.html#sending-and-receiving-logging-events-across-a-network
class LogRecordStreamHandler(socketserver.StreamRequestHandler):
    """Handler for a streaming logging request.

    This basically logs the record using whatever logging policy is
    configured locally.
    """

    def handle(self):
        """
        Handle multiple requests - each expected to be a 4-byte length,
        followed by the LogRecord in pickle format. Logs the record
        according to whatever policy is configured locally.
        """
        while True:
            chunk = self.connection.recv(4)
            if len(chunk) < 4:
                break

            slen = struct.unpack(">L", chunk)[0]
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk = chunk + self.connection.recv(slen - len(chunk))

            obj = self.load_ujson(chunk)

            record = logging.makeLogRecord(obj)

            self.handle_log_record(record)

    def load_ujson(self, data):
        return ujson.loads(data)

    def handle_log_record(self, record):
        # if a name is specified, we use the named logger rather than the one
        # implied by the record.
        if self.server.logname is not None:
            name = self.server.logname
        else:
            name = record.name

        logger = logging.getLogger(name)

        # N.B. EVERY record gets logged. This is because Logger.handle
        # is normally called AFTER logger-level filtering. If you want
        # to do filtering, do it at the client end to save wasting
        # cycles and network bandwidth!
        logger.handle(record)


class LogRecordSocketReceiver(socketserver.ThreadingTCPServer):
    """
    Simple TCP socket-based logging receiver suitable for testing.
    """

    allow_reuse_address = 1

    def __init__(
        self,
        host="localhost",
        port=logging.handlers.DEFAULT_TCP_LOGGING_PORT,  # 9020
        handler=LogRecordStreamHandler,
        logfile: Path = Path("default_socket.log"),
    ):
        socketserver.ThreadingTCPServer.__init__(self, (host, port), handler)
        self.abort = 0
        self.timeout = 1
        self.logname = None
        self.logfile = logfile

        # All derived loggers within this process will log to a file
        modify_root_logger(self.logfile)

    def serve_until_stopped(self):
        print("LogRecordSocketReceiver is up and listening")
        abort = 0

        while not abort:
            rd, wr, ex = select.select(
                [self.socket.fileno()], [], [], self.timeout
            )
            if rd:
                self.handle_request()
            abort = self.abort


def modify_root_logger(logfile: Path):
    cfg = default_dareplane_config.copy()
    # Set the target log file
    cfg["handlers"]["file"] = {
        "class": "logging.FileHandler",
        "filename": str(logfile.resolve()),
        "formatter": "dareplane_standard",
    }

    # Filtering should be done at client level - server will log all
    cfg["root"]["level"] = logging.DEBUG
    cfg["root"]["handlers"] = ["console", "file"]

    logging.config.dictConfig(cfg)


def main(logfile: str = "default_socket.log"):
    rcv = LogRecordSocketReceiver(logfile=Path(logfile))
    rcv.serve_until_stopped()


if __name__ == "__main__":
    Fire(main)
