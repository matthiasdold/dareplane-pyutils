import psutil
import time
import subprocess

from pathlib import Path


class TerminationError(Exception):
    pass


def run_logging_server() -> subprocess.Popen:
    cmd = (
        "python -m dareplane_utils.logging.server --logfile=dareplane_test.log"
    )
    return subprocess.Popen(cmd, shell=True)


def process_stop_children(p: psutil.Process):
    i = 0
    print(f"{p.children()=}")
    for cp in p.children():
        process_stop_children(cp)

    try:
        print(f"{p.pid}-{p.status()=} after closing children")
        while p.is_running():
            print(f"terminating {p=}")
            p.terminate()
            time.sleep(0.1)
            i += 1
            if i > 10:
                raise TerminationError(f"Cannot stop process {p=} from running")
    except psutil.NoSuchProcess as err:
        print(f"{err=}")
        pass


def test_logging_server():
    # Run the client script in a subprocess - to ensure processes are separated
    testlog_cmd = f"python -m tests.resources.tlogging"

    testf = Path("dareplane_test.log")
    p_server = run_logging_server()
    with run_logging_server() as p_server:
        with subprocess.Popen(testlog_cmd, shell=True) as p_client:
            time.sleep(1)

            # Check last lines in log file
            with open(testf, "r") as fl:
                ll = fl.readlines()[-8:]

            process_stop_children(psutil.Process(p_server.pid))

            # Stop all child processes of the server

    try:
        assert all(
            [
                e in "".join(ll[:4])
                for e in [
                    "DEBUG",
                    "INFO",
                    "WARNING",
                    "ERROR",
                    "debug1",
                    "info1",
                    "area1",
                ]
            ]
        ), f"Log lines do not match expectation, got {ll[:4]}"

        assert all(
            [
                e in "".join(ll[4:])
                for e in [
                    "DEBUG",
                    "INFO",
                    "WARNING",
                    "ERROR",
                    "debug2",
                    "info2",
                    "area2",
                ]
            ]
        ), f"Log lines do not match expectation, got {ll[:4]}"

    finally:
        try:
            testf.unlink()
        except PermissionError as err:
            print(f"Could not delete test file {testf}, got {err}")


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
