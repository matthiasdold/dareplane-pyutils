import logging
import subprocess
import time
from pathlib import Path
from logging.handlers import SocketHandler
import psutil
import pytest

from dareplane_utils.logging.logger import get_logger


class TerminationError(Exception):
    pass


@pytest.fixture
def reset_logging():
    """Reset logging state to ensure clean socket handler for server tests.

    This fixture is necessary because:
    1. Socket handlers persist across tests in the same process
    2. A failed connection attempt (no server) leaves the handler in a bad state
    3. We need to recreate handlers to test actual server communication
    """
    # Close and remove all socket handlers from root logger
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        if isinstance(handler, SocketHandler):
            if hasattr(handler, "sock") and handler.sock:
                try:
                    handler.sock.close()
                except:
                    pass
                handler.sock = None
            handler.close()
            root_logger.removeHandler(handler)

    # Reset the config applied flag so logging can be reconfigured
    import dareplane_utils.logging.logger as logger_module

    logger_module._config_applied = False

    # Clear any connection warnings to test fresh connections
    for handler in root_logger.handlers[:]:
        if isinstance(handler, SocketHandler) and hasattr(
            handler, "_connection_warned"
        ):
            delattr(handler, "_connection_warned")

    yield

    # Cleanup after test
    for handler in root_logger.handlers[:]:
        if isinstance(handler, SocketHandler):
            if hasattr(handler, "sock") and handler.sock:
                try:
                    handler.sock.close()
                except:
                    pass
            handler.close()


def test_opt_out_of_network_logging():
    logger = get_logger("myapp", no_socket_handler=True)
    assert not any([isinstance(h, SocketHandler) for h in logger.handlers])


def run_logging_server() -> subprocess.Popen:
    cmd = ["python", "-m", "dareplane_utils.logging.server", "--logfile=dareplane_test.log"]
    return subprocess.Popen(cmd)


def stop_process_and_children(p: psutil.Process):
    i = 0
    print(f"{p.children()=}")
    for cp in p.children():
        cp.terminate()

    try:
        print(f"{p.pid}-{p.status()=} - after closing children")
        while p.is_running() and not p.status() == "zombie":
            print(f"terminating {p=}")
            p.terminate()
            time.sleep(0.1)
            i += 1
            if i > 10:
                raise TerminationError(f"Cannot stop process {p=} from running")
    except psutil.NoSuchProcess as err:
        print(f"{err=}")
        pass


def test_logging_server(reset_logging):
    testf = Path("dareplane_test.log")

    try:
        with run_logging_server() as p_server:
            print(f"Started logging server with PID {p_server.pid}")
            time.sleep(1.0)

            print("Initializing loggers and sending messages")
            logger1 = get_logger("myapp.area1")
            print("Initialized first logger")
            logger2 = get_logger("myapp.area2")
            print("Initialized second logger")
            print("Setting log level")
            logger1.setLevel(10)
            logger2.setLevel(10)
            print("Log level set")

            print("Sending messages")
            logger1.debug("debug1")
            logger1.info("info1")
            logger1.warning("warning1")
            logger1.error("error1")
            time.sleep(0.1)
            logger2.debug("debug2")
            logger2.info("info2")
            logger2.warning("warning2")
            logger2.error("error2")
            print("Messages sent")

            time.sleep(1)
            # Check last lines in log file
            print("Reading the logfile")
            with open(testf, "r") as fl:
                ll = fl.readlines()

            # delete the loggers to get rid of file handlers, which might block
            # a proper cleanup
            print("Deleting loggers and sending messages")
            del logger1, logger2

            print("Stopping logging server")
            stop_process_and_children(psutil.Process(p_server.pid))

        assert all(
            [
                e in "".join(ll[:4])
                for e in [
                    "debug1",
                    "info1",
                    "warning1",
                    "error1",
                ]
            ]
        ), f"Log lines do not match expectation for logger1, got {ll[:4]}"

        assert all(
            [
                e in "".join(ll[4:])
                for e in [
                    "debug2",
                    "info2",
                    "warning2",
                    "error2",
                ]
            ]
        ), f"Log lines do not match expectation for logger2, got {ll[4:]}"

    finally:
        try:
            testf.unlink()
        except PermissionError as err:
            print(f"Could not delete test file {testf}, got {err}")
        except FileNotFoundError as err:
            print(f"Log file did not exits - got {err}")


# --------------------- plain performance tests ----------------------
# def mytest():
#     # Assuming there is a logging server running, test performance for writing
#     # to disk vs writing to a socket
#     socketHandler = logging.handlers.SocketHandler(
#         "localhost", logging.handlers.DEFAULT_TCP_LOGGING_PORT
#     )
#     logger1 = logging.getLogger("myapp.socket")
#     logger2 = logging.getLogger("myapp.file")
#
#     logger1.addHandler(socketHandler)
#     logger2.addHandler(fh)
#     logger1.setLevel(10)
#     logger2.setLevel(10)
#
#     logger1.debug("test")
#     logger2.debug("test")
#
#     # %timeit logger1.debug("test")
#     # %timeit logger2.debug("test")
#
#     # In [34]:     %timeit logger1.debug("test")
#     # 39.3 µs ± 2.83 µs per loop (mean ± std. dev. of 7 runs, 10,000
#     # loops each)
#
#     # In [35]:     %timeit logger2.debug("test")
#     # 40.5 µs ± 8.8 µs per loop (mean ± std. dev. of 7 runs, 10,000 l
#     # oops each)
