import logging
import struct

import ujson


# By default logging will send the message as pickle - overwrite the method to send json
class UJsonSocketHandler(logging.handlers.SocketHandler):
    """
    A custom logging handler that sends log records as JSON over a socket.

    This handler extends the `SocketHandler` class to serialize log records using the `ujson` library
    instead of the default `pickle` serialization. The log records are converted to JSON format and sent
    over a socket connection. This handler is useful for logging systems that require JSON-formatted log
    messages.

    Methods
    -------
    makePickle(record: logging.LogRecord) -> bytes
        Serialize the log record to a JSON-formatted byte string.
    """

    def makePickle(self, record: logging.LogRecord) -> bytes:
        try:
            s = ujson.dumps({k: v for k, v in record.__dict__.items()}).encode()

        # In case the record contains an error message, try to convert it to str
        except TypeError:
            s = ujson.dumps(
                {
                    k: v if isinstance(v, int) else str(v)
                    for k, v in record.__dict__.items()
                }
            ).encode()

        slen = struct.pack(">L", len(s))  # is needed by the servers handler
        return slen + s
