import ujson
import struct
import logging


# By default logging will send the message as pickle - overwrite the method to send json
class UJsonSocketHandler(logging.handlers.SocketHandler):
    def makePickle(self, record: logging.LogRecord) -> bytes:
        s = ujson.dumps(record.__dict__).encode()
        slen = struct.pack(">L", len(s))  # is needed by the servers handler
        return slen + s
