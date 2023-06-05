import ujson
import struct
import logging


# By default logging will send the message as pickle - overwrite the method to send json
class UJsonSocketHandler(logging.handlers.SocketHandler):
    def makePickle(self, record: logging.LogRecord) -> bytes:
        try:
            s = ujson.dumps({k: v for k, v in record.__dict__.items()}).encode()

        # In case the record contains an error message, try to convert it to str
        except TypeError as err:
            s = ujson.dumps(
                {
                    k: v if isinstance(v, int) else str(v)
                    for k, v in record.__dict__.items()
                }
            ).encode()

        slen = struct.pack(">L", len(s))  # is needed by the servers handler
        return slen + s
